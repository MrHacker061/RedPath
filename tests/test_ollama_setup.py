from pathlib import Path
from threading import Event

from redpath_ai.providers import OllamaProvider
from redpath_setup.manifest import OLLAMA_ARTIFACT


class RecordingRunner:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.calls: list[list[str]] = []
        self.timeouts: list[float] = []

    def __call__(self, argv, _cwd: Path, timeout: float):
        self.calls.append(list(argv))
        self.timeouts.append(timeout)
        return type("Result", (), {"returncode": self.exit_code, "stdout": "untrusted", "stderr": "untrusted"})()


def installed_provider() -> OllamaProvider:
    return OllamaProvider(transport=lambda *_: {"models": [{"name": "qwen2.5:7b-instruct-q4_K_M"}]})


def unavailable_provider() -> OllamaProvider:
    return OllamaProvider(transport=lambda *_: {"models": []})


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
    stage = OllamaSetup(tmp_path, runner=runner, provider=installed_provider()).pull_model(True, lambda *_: None, Event())
    assert runner.calls == [["ollama", "pull", "qwen2.5:7b-instruct-q4_K_M"]]
    assert runner.timeouts == [600]
    assert stage.status == "ready"


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
