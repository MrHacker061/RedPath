from io import BufferedReader, FileIO, StringIO, TextIOWrapper
import os
from pathlib import Path
from threading import Event, Thread

import pytest

from redpath_ai.providers import OllamaProvider
from redpath_setup.manifest import OLLAMA_ARTIFACT


class RecordingRunner:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.calls: list[list[str]] = []
        self.timeouts: list[float] = []

    def __call__(self, argv, _cwd: Path, timeout: float, _cancelled: Event, progress):
        self.calls.append(list(argv))
        self.timeouts.append(timeout)
        progress(0, None)
        return type("Result", (), {"returncode": self.exit_code, "stdout": "untrusted", "stderr": "untrusted"})()


def tags_provider(models):
    calls = []

    def transport(url, body, timeout):
        calls.append((url, body, timeout))
        return {"models": models}

    return OllamaProvider(transport=transport), calls


def installed_provider() -> OllamaProvider:
    return tags_provider([{"name": "qwen2.5:7b-instruct-q4_K_M"}])[0]


def unavailable_provider() -> OllamaProvider:
    return OllamaProvider(transport=lambda *_: {"models": []})


class CancelledProcess:
    returncode = None

    def __init__(self, cancelled: Event) -> None:
        self.cancelled = cancelled
        self.terminated = False
        self.stdout = StringIO()
        self.stderr = StringIO()

    def poll(self):
        self.cancelled.set()
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class StreamedProcess:
    def __init__(self) -> None:
        self.returncode = 0
        self.polls = 0
        self.stdout = StringIO()
        self.stderr = StringIO(
            "\rpulling 8a7fbc4e30f2:  12% |██▏               | 512 MB/4.1 GB\r"
            "unexpected status\r"
            "\rpulling invalid:  57% |██████████        |\r"
            "\rpulling 8a7fbc4e30f2:  57% |██████████        | 2.3 GB/4.1 GB\r"
            "\rpulling 8a7fbc4e30f2:  101% |██████████████████|\r"
        )

    def poll(self):
        self.polls += 1
        return None if self.polls < 3 else self.returncode


class ExitedProcess:
    returncode = 0

    def __init__(self, stderr) -> None:
        self.stdout = StringIO()
        self.stderr = stderr

    def poll(self):
        return self.returncode


def test_ollama_install_requires_consent(tmp_path):
    from redpath_setup.ollama import OllamaSetup

    setup = OllamaSetup(tmp_path, runner=RecordingRunner(), downloader=lambda *_: None)
    stage = setup.install(False, lambda *_: None, Event())
    assert stage.code == "CONSENT_REQUIRED"
    assert setup.runner.calls == []


def test_ollama_install_passes_only_pinned_artifact_to_verified_downloader(tmp_path):
    from redpath_setup.ollama import OllamaSetup

    downloaded = []

    def downloader(artifact, destination, _progress, _cancelled):
        downloaded.append((artifact, destination))
        installer = destination / artifact.filename
        installer.write_bytes(b"verified by downloader")
        return installer

    runner = RecordingRunner()
    stage = OllamaSetup(tmp_path, runner=runner, downloader=downloader, provider=installed_provider()).install(
        True, lambda *_: None, Event()
    )
    assert downloaded == [(OLLAMA_ARTIFACT, tmp_path)]
    assert runner.calls == [[str(tmp_path / "OllamaSetup.exe"), "/VERYSILENT", "/NORESTART"]]
    assert runner.timeouts == [600]
    assert stage.status == "ready"


def test_ollama_install_redacts_installer_failure_output(tmp_path):
    from redpath_setup.ollama import OllamaSetup

    def downloader(artifact, destination, _progress, _cancelled):
        installer = destination / artifact.filename
        installer.write_bytes(b"verified by downloader")
        return installer

    stage = OllamaSetup(tmp_path, runner=RecordingRunner(exit_code=1), downloader=downloader).install(
        True, lambda *_: None, Event()
    )
    assert (stage.status, stage.code) == ("failed", "OLLAMA_INSTALL_FAILED")
    assert "untrusted" not in stage.detail


def test_model_pull_uses_exact_model_name_and_confirms_loopback_tags(tmp_path):
    from redpath_setup.ollama import OllamaSetup

    runner = RecordingRunner()
    provider, health_calls = tags_provider([{"name": "qwen2.5:7b-instruct-q4_K_M"}])
    stage = OllamaSetup(tmp_path, runner=runner, provider=provider).pull_model(True, lambda *_: None, Event())
    assert runner.calls == [["ollama", "pull", "qwen2.5:7b-instruct-q4_K_M"]]
    assert runner.timeouts == [600]
    assert stage.status == "ready"
    assert health_calls == [("http://127.0.0.1:11434/api/tags", None, 20.0)]


def test_successful_model_pull_reports_missing_model_when_tags_omits_it(tmp_path):
    from redpath_setup.ollama import OllamaSetup

    provider, health_calls = tags_provider([])
    stage = OllamaSetup(tmp_path, runner=RecordingRunner(), provider=provider).pull_model(True, lambda *_: None, Event())
    assert (stage.status, stage.code) == ("needs_attention", "MODEL_MISSING")
    assert health_calls == [("http://127.0.0.1:11434/api/tags", None, 20.0)]


def test_cancellable_runner_terminates_active_child_and_reports_only_numeric_progress(tmp_path, monkeypatch):
    from redpath_setup import ollama

    cancelled = Event()
    child = CancelledProcess(cancelled)
    calls = []
    monkeypatch.setattr(ollama.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)) or child)
    progress = []
    with pytest.raises(ollama.ProcessCancelled):
        ollama._run(
            ["ollama", "pull", "qwen2.5:7b-instruct-q4_K_M"], tmp_path, 600, cancelled,
            lambda done, total: progress.append((done, total)),
        )
    assert child.terminated
    assert progress == [(0, None)]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["stdout"] is ollama.subprocess.DEVNULL
    assert calls[0][1]["stderr"] is ollama.subprocess.PIPE


def test_runner_emits_valid_intermediate_stderr_progress_without_raw_output(tmp_path, monkeypatch):
    from redpath_setup import ollama

    monkeypatch.setattr(ollama.subprocess, "Popen", lambda *_args, **_kwargs: StreamedProcess())
    progress = []
    result = ollama._run(
        ["ollama", "pull", "qwen2.5:7b-instruct-q4_K_M"], tmp_path, 600, Event(),
        lambda done, total: progress.append((done, total)),
    )
    assert result.returncode == 0
    assert progress == [(0, None), (12, 100), (57, 100), (100, 100)]


@pytest.mark.parametrize("timeout", [0, 600])
def test_runner_kills_unresponsive_child_with_cleanup_waits_inside_deadline(tmp_path, monkeypatch, timeout):
    from redpath_setup import ollama

    cancelled = Event()
    waits = []

    class UnresponsiveProcess(CancelledProcess):
        def wait(self, timeout=None):
            waits.append(timeout)
            raise ollama.subprocess.TimeoutExpired("fixed-command", timeout)

    child = UnresponsiveProcess(cancelled)
    monkeypatch.setattr(ollama.subprocess, "Popen", lambda *_args, **_kwargs: child)
    expected = ollama.subprocess.TimeoutExpired if timeout == 0 else ollama.ProcessCancelled
    with pytest.raises(expected):
        ollama._run(["ollama", "pull", "qwen2.5:7b-instruct-q4_K_M"], tmp_path, timeout, cancelled, lambda *_: None)
    assert child.returncode == -9
    assert len(waits) == 2
    assert all(0 <= wait <= 0.1 for wait in waits)
    if timeout == 0:
        assert waits == [0, 0]


@pytest.mark.parametrize("state", ["exited", "cancelled", "timeout"])
def test_runner_returns_with_real_progress_pipe_held_open(tmp_path, monkeypatch, state):
    from redpath_setup import ollama

    reading = Event()
    read_fd, write_fd = os.pipe()

    class ObservedPipe(FileIO):
        def readinto(self, buffer):
            # BufferedReader holds its lock before calling the raw read.
            reading.set()
            return super().readinto(buffer)

    pipe = TextIOWrapper(BufferedReader(ObservedPipe(read_fd, "rb")))
    cancelled = Event()

    class PipeProcess(ExitedProcess):
        def __init__(self):
            super().__init__(pipe)
            self.returncode = 0 if state == "exited" else None

        def poll(self):
            assert reading.wait(1)
            if state == "cancelled":
                cancelled.set()
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def wait(self, timeout=None):
            return self.returncode

    child = PipeProcess()
    monkeypatch.setattr(ollama.subprocess, "Popen", lambda *_args, **_kwargs: child)
    outcomes = []

    def run():
        try:
            outcomes.append(ollama._run(
                ["ollama", "pull", "qwen2.5:7b-instruct-q4_K_M"], tmp_path,
                0.05 if state == "timeout" else 600, cancelled, lambda *_: None,
            ))
        except Exception as error:
            outcomes.append(error)

    worker = Thread(target=run, daemon=True)
    worker.start()
    try:
        worker.join(timeout=1)
        assert not worker.is_alive(), "runner blocked closing a pipe still being read"
        if state == "exited":
            assert outcomes[0].returncode == 0
        else:
            expected = ollama.ProcessCancelled if state == "cancelled" else ollama.subprocess.TimeoutExpired
            assert isinstance(outcomes[0], expected)
            assert child.returncode == -15
    finally:
        # Release the inherited writer even on RED so pytest itself cannot hang.
        os.close(write_fd)
        worker.join(timeout=2)


def test_model_pull_requires_consent_before_running_command(tmp_path):
    from redpath_setup.ollama import OllamaSetup

    runner = RecordingRunner()
    stage = OllamaSetup(tmp_path, runner=runner).pull_model(False, lambda *_: None, Event())
    assert stage.code == "CONSENT_REQUIRED"
    assert runner.calls == []


def test_inspect_reports_missing_configured_model(tmp_path):
    from redpath_setup.ollama import OllamaSetup

    stage = OllamaSetup(tmp_path, provider=unavailable_provider()).inspect()
    assert (stage.status, stage.code) == ("needs_attention", "MODEL_MISSING")
