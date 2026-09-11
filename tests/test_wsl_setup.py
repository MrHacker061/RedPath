from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from redpath_kali import ProcessResult
from redpath_setup.manifest import KALI_ARTIFACT


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


def test_run_in_kali_revalidates_managed_identity_before_fixed_exec_argv(tmp_path):
    from redpath_setup.wsl import WslSetup

    runner = RecordingRunner(ready_results() + [ProcessResult(0, "ok\n")])
    result = WslSetup(tmp_path, runner=runner).run_in_kali(["printf", "ok"], timeout=5)

    assert result == ProcessResult(0, "ok\n")
    assert runner.calls[-1][0] == [
        "wsl.exe", "--distribution", "RedPath-Kali", "--exec", "printf", "ok"
    ]


@pytest.mark.parametrize("arguments", ["printf ok", [], ["printf", 1], ["printf", "bad\x00value"]])
def test_run_in_kali_rejects_untyped_or_malformed_argv_before_wsl(tmp_path, arguments):
    from redpath_setup.wsl import WslSetup, WslSetupError

    runner = RecordingRunner()
    with pytest.raises(WslSetupError, match="arguments"):
        WslSetup(tmp_path, runner=runner).run_in_kali(arguments, timeout=5)
    assert runner.calls == []


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
