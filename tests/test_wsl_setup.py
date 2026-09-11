from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import get_args
from unittest.mock import patch
import subprocess

import pytest

from redpath_kali import ProcessResult
from redpath_setup.manifest import Artifact, KALI_ARTIFACT


class RecordingRunner:
    """A fake runner: WSL is never invoked by these tests."""

    def __init__(self, results: list[ProcessResult] | None = None) -> None:
        self.results = list(results or [])
        self.calls: list[tuple[list[str], Path, float]] = []

    def __call__(self, argv, cwd: Path, timeout: float) -> ProcessResult:
        self.calls.append((list(argv), cwd, timeout))
        return self.results.pop(0) if self.results else ProcessResult(0)


def ready_results() -> list[ProcessResult]:
    return [
        ProcessResult(0, "Default Version: 2\n"),
        ProcessResult(0, "RedPath-Kali\n"),
        ProcessResult(0),
    ]


def verified_kali_download(artifact, destination: Path, _progress, _cancelled: Event) -> Path:
    assert artifact == KALI_ARTIFACT
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / artifact.filename
    path.write_bytes(b"test-only verified fixture")
    return path


def redirected_utf16(text: str) -> str:
    """Match Windows' UTF-16LE console redirection after UTF-8 replacement decoding."""
    return (b"\xff\xfe" + text.encode("utf-16-le")).decode("utf-8", errors="replace")


def test_inspect_requires_wsl2_and_an_exact_case_insensitive_managed_distribution(tmp_path):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(
        [
            ProcessResult(0, "Default Version: 2\n"),
            ProcessResult(0, "  redpath-kali \nOther-Distro\n"),
            ProcessResult(0),
        ]
    )
    stage = WslSetup(tmp_path, runner=runner).inspect()

    assert (stage.status, stage.code) == ("ready", "KALI_READY")
    assert [call[0] for call in runner.calls] == [
        ["wsl.exe", "--status"],
        ["wsl.exe", "--list", "--quiet"],
        ["wsl.exe", "--distribution", "RedPath-Kali", "--exec", "/usr/bin/test", "-f", "/etc/redpath-managed"],
    ]


def test_inspect_refuses_an_unmarked_distribution_without_running_an_action(tmp_path):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(
        [
            ProcessResult(0, "Default Version: 2\n"),
            ProcessResult(0, "RedPath-Kali\n"),
            ProcessResult(1),
        ]
    )
    stage = WslSetup(tmp_path, runner=runner).inspect()

    assert (stage.status, stage.code) == ("failed", "KALI_IDENTITY_MISMATCH")
    assert len(runner.calls) == 3


def test_inspect_normalizes_utf16_nul_redirected_wsl_output_before_matching_and_detecting_wsl1(tmp_path):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(
        [
            ProcessResult(0, redirected_utf16("Default Version: 2\r\n")),
            ProcessResult(0, redirected_utf16("RedPath-Kali\r\n")),
            ProcessResult(0),
        ]
    )
    assert WslSetup(tmp_path, runner=runner).inspect().code == "KALI_READY"

    runner = RecordingRunner([ProcessResult(0, redirected_utf16("Default Version: 1\r\n"))])
    assert WslSetup(tmp_path, runner=runner).inspect_wsl().code == "WSL2_REQUIRED"


def test_enable_requires_consent_and_reports_pending_restart(tmp_path):
    from redpath_setup.wsl import WslSetup

    denied = RecordingRunner()
    stage = WslSetup(tmp_path, runner=denied).enable(False)
    assert stage.code == "CONSENT_REQUIRED"
    assert denied.calls == []

    runner = RecordingRunner([ProcessResult(0, "Changes will be effective after a restart.\n")])
    stage = WslSetup(tmp_path, runner=runner).enable(True)
    assert (stage.status, stage.code) == ("needs_attention", "RESTART_REQUIRED")
    assert runner.calls[0][0] == ["wsl.exe", "--install", "--no-distribution"]


def test_enable_uses_the_active_cancellation_event_without_running_real_wsl(tmp_path):
    from redpath_setup.wsl import WslOperationCancelled, WslSetup

    events = []

    def cancellable_runner(argv, _cwd, _timeout, cancelled):
        events.append((list(argv), cancelled))
        cancelled.set()
        raise WslOperationCancelled()

    event = Event()
    stage = WslSetup(
        tmp_path, runner=RecordingRunner(), cancellable_runner=cancellable_runner
    ).enable(True, event)

    assert (stage.status, stage.code) == ("needs_attention", "CANCELLED")
    assert events == [(["wsl.exe", "--install", "--no-distribution"], event)]


def test_default_cancellable_runner_terminates_then_kills_a_fake_wsl_process(tmp_path, monkeypatch):
    from redpath_setup import wsl

    class HungProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            if not self.killed:
                raise subprocess.TimeoutExpired("wsl.exe", timeout)
            return -9

        def communicate(self, timeout):
            raise subprocess.TimeoutExpired("wsl.exe", timeout)

    process = HungProcess()
    cancelled = Event()
    cancelled.set()
    with patch("redpath_setup.wsl.subprocess.Popen", return_value=process) as popen:
        with pytest.raises(wsl.WslOperationCancelled):
            wsl._run_cancellable(["wsl.exe", "--install", "--no-distribution"], tmp_path, 120, cancelled)

    assert process.terminated and process.killed
    assert popen.call_args.kwargs["shell"] is False


def test_default_cancellable_runner_rejects_cancel_arriving_during_communicate(tmp_path):
    from redpath_setup import wsl

    cancelled = Event()

    class CompletingProcess:
        returncode = 0

        def poll(self):
            return 0

        def communicate(self, timeout):
            cancelled.set()
            return "ready", ""

    with patch("redpath_setup.wsl.subprocess.Popen", return_value=CompletingProcess()):
        with pytest.raises(wsl.WslOperationCancelled):
            wsl._run_cancellable(["wsl.exe", "--install", "--no-distribution"], tmp_path, 120, cancelled)


def test_enable_does_not_report_ready_after_command_acknowledges_cancellation(tmp_path):
    from redpath_setup.wsl import WslSetup

    cancelled = Event()

    def cancellable_runner(_argv, _cwd, _timeout, event):
        event.set()
        return ProcessResult(0, "", "")

    stage = WslSetup(
        tmp_path, runner=RecordingRunner(), cancellable_runner=cancellable_runner
    ).enable(True, cancelled)

    assert (stage.status, stage.code) == ("needs_attention", "CANCELLED")


def test_kali_marker_creation_cannot_return_ready_after_acknowledged_cancel(tmp_path):
    from redpath_setup.wsl import WslOperationCancelled, WslSetup

    cancelled = Event()
    calls = []

    def cancellable_runner(argv, _cwd, _timeout, event):
        calls.append(list(argv))
        if len(calls) == 1:
            return ProcessResult(0)
        event.set()
        raise WslOperationCancelled()

    stage = WslSetup(
        tmp_path,
        runner=RecordingRunner([ProcessResult(0, "Default Version: 2\n"), ProcessResult(0, "")]),
        downloader=verified_kali_download,
        cancellable_runner=cancellable_runner,
    ).install_kali(True, lambda *_: None, cancelled)

    assert (stage.status, stage.code) == ("needs_attention", "CANCELLED")
    assert calls[1] == ["wsl.exe", "--distribution", "RedPath-Kali", "--exec", "/usr/bin/touch", "/etc/redpath-managed"]


def test_import_uses_the_active_cancellation_event_without_running_real_wsl(tmp_path):
    from redpath_setup.wsl import WslOperationCancelled, WslSetup

    calls = []

    def cancellable_runner(argv, _cwd, _timeout, cancelled):
        calls.append((list(argv), cancelled))
        cancelled.set()
        raise WslOperationCancelled()

    event = Event()
    runner = RecordingRunner([ProcessResult(0, "Default Version: 2\n"), ProcessResult(0, "")])
    stage = WslSetup(
        tmp_path, runner=runner, downloader=verified_kali_download,
        cancellable_runner=cancellable_runner,
    ).install_kali(True, lambda *_: None, event)

    assert (stage.status, stage.code) == ("needs_attention", "CANCELLED")
    assert calls[0][0][:3] == ["wsl.exe", "--import", "RedPath-Kali"]
    assert calls[0][1] is event


@pytest.mark.parametrize("consent", [1, "true", object()])
def test_enable_and_kali_install_require_the_boolean_true_consent_value(tmp_path, consent):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner()
    setup = WslSetup(tmp_path, runner=runner, downloader=verified_kali_download)
    assert setup.enable(consent).code == "CONSENT_REQUIRED"
    assert setup.install_kali(consent, lambda *_: None, Event()).code == "CONSENT_REQUIRED"
    assert runner.calls == []


def test_enable_treats_exit_3010_as_restart_required_before_generic_failure(tmp_path):
    from redpath_setup.wsl import WslSetup

    stage = WslSetup(tmp_path, runner=RecordingRunner([ProcessResult(3010)])).enable(True)
    assert (stage.status, stage.code) == ("needs_attention", "RESTART_REQUIRED")


def test_enable_does_not_mistake_no_restart_required_for_a_pending_restart(tmp_path):
    from redpath_setup import wsl
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(
        [
            ProcessResult(0, "No restart required.\n"),
            ProcessResult(0, "Default Version: 2\n"),
            ProcessResult(0, ""),
        ]
    )
    stage = WslSetup(tmp_path, runner=runner).enable(True)
    assert stage.code == "WSL_READY"
    assert len(runner.calls) == 2
    assert wsl._restart_pending(ProcessResult(0, redirected_utf16("No restart required.\r\n"))) is False


def test_kali_import_uses_the_pinned_artifact_managed_name_and_fixed_marker_command(tmp_path):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(
        [
            ProcessResult(0, "Default Version: 2\n"),
            ProcessResult(0, ""),
            ProcessResult(0),
            ProcessResult(0),
        ]
    )
    stage = WslSetup(tmp_path, runner=runner, downloader=verified_kali_download).install_kali(
        True, lambda *_: None, Event()
    )

    artifact_path = tmp_path / KALI_ARTIFACT.filename
    assert (stage.status, stage.code) == ("ready", "KALI_READY")
    assert runner.calls[2][0] == [
        "wsl.exe", "--import", "RedPath-Kali", str(tmp_path / "RedPath-Kali"), str(artifact_path), "--version", "2"
    ]
    assert runner.calls[3][0] == [
        "wsl.exe", "--distribution", "RedPath-Kali", "--exec", "/usr/bin/touch", "/etc/redpath-managed"
    ]


def test_install_refuses_existing_distribution_without_the_managed_marker_and_does_not_import(tmp_path):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(
        [
            ProcessResult(0, "Default Version: 2\n"),
            ProcessResult(0, "RedPath-Kali\n"),
            ProcessResult(1),
        ]
    )
    stage = WslSetup(tmp_path, runner=runner, downloader=verified_kali_download).install_kali(
        True, lambda *_: None, Event()
    )

    assert (stage.status, stage.code) == ("failed", "KALI_IDENTITY_MISMATCH")
    assert not any("--import" in call[0] for call in runner.calls)


def test_inspect_distinguishes_a_missing_marker_from_a_marker_check_failure(tmp_path):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(
        [
            ProcessResult(0, "Default Version: 2\n"),
            ProcessResult(0, "RedPath-Kali\n"),
            ProcessResult(2, "", "WSL transport failure"),
        ]
    )
    stage = WslSetup(tmp_path, runner=runner).inspect()
    assert (stage.status, stage.code) == ("failed", "KALI_MARKER_CHECK_FAILED")


def test_run_in_kali_revalidates_managed_identity_before_fixed_exec_argv(tmp_path):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(ready_results() + [ProcessResult(0, "ok\n")])
    result = WslSetup(tmp_path, runner=runner).run_in_kali(["printf", "ok"], timeout=5)

    assert result == ProcessResult(0, "ok\n")
    assert runner.calls[-1][0] == [
        "wsl.exe", "--distribution", "RedPath-Kali", "--exec", "printf", "ok"
    ]


@pytest.mark.parametrize(
    "arguments, timeout",
    [
        ("printf ok", 5),
        ([], 5),
        (["printf", 1], 5),
        (["printf", "bad\x00value"], 5),
        (["printf", "ok"], float("nan")),
        (["printf", "ok"], float("inf")),
        (["printf", "ok"], float("-inf")),
        (["printf", "ok"], 0),
        (["printf", "ok"], 61),
    ],
)
def test_run_in_kali_rejects_untyped_malformed_or_unbounded_inputs_before_wsl(tmp_path, arguments, timeout):
    from redpath_setup.wsl import WslSetup, WslSetupError

    runner = RecordingRunner()
    with pytest.raises(WslSetupError):
        WslSetup(tmp_path, runner=runner).run_in_kali(arguments, timeout=timeout)
    assert runner.calls == []


@pytest.mark.parametrize(
    "timeout",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        0,
        61,
        pytest.param(10**10000, id="huge_integer"),
    ],
)
def test_timeout_rejection_is_bounded_and_uses_the_exact_range_message(tmp_path, timeout):
    from redpath_setup.wsl import WslSetup, WslSetupError

    runner = RecordingRunner()
    with pytest.raises(WslSetupError, match="greater than 0 and at most 60"):
        WslSetup(tmp_path, runner=runner).run_in_kali(["printf", "ok"], timeout=timeout)
    assert runner.calls == []


def test_downloader_type_contract_accepts_the_concrete_artifact_model():
    from redpath_setup import wsl

    parameters, return_type = get_args(wsl.Downloader)
    assert parameters[0] is Artifact
    assert return_type is Path


def test_default_runner_uses_argument_array_without_a_shell(tmp_path):
    from redpath_setup import wsl

    completed = SimpleNamespace(returncode=0, stdout="safe", stderr="")
    with patch("redpath_setup.wsl.subprocess.run", return_value=completed) as run:
        assert wsl._run(["wsl.exe", "--status"], tmp_path, 10) == ProcessResult(0, "safe", "")

    argv, kwargs = run.call_args
    assert argv[0] == ["wsl.exe", "--status"]
    assert kwargs["shell"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 10
