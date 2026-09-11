from pathlib import Path
from threading import Event

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
    assert calls[0][1]["stderr"] is ollama.subprocess.DEVNULL


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
