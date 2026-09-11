from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from threading import Event
from urllib.error import URLError

import pytest

from redpath_setup.downloads import (
    ArtifactVerificationError,
    DownloadCancelledError,
    InsecureDownloadError,
    download_verified,
)
from redpath_setup.manifest import KALI_ARTIFACT, OLLAMA_ARTIFACT
from redpath_setup.state import SetupStage, SetupState


class FakeResponse:
    def __init__(self, body: bytes, url: str = "https://example.test/a"):
        self._stream = BytesIO(body)
        self.url = url
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()

    def geturl(self) -> str:
        return self.url


def fake_opener(body: bytes, url: str = "https://example.test/a"):
    def open_url(_request):
        return FakeResponse(body, url)

    return open_url


def test_manifest_contains_exact_pinned_artifacts():
    assert (OLLAMA_ARTIFACT.version, OLLAMA_ARTIFACT.url, OLLAMA_ARTIFACT.sha256) == (
        "0.34.0",
        "https://github.com/ollama/ollama/releases/download/v0.34.0/OllamaSetup.exe",
        "e2b98770fb87f3b4c593c22f2e8eda59bcac1cd7b141f1388c4181a8bf271a72",
    )
    assert (KALI_ARTIFACT.version, KALI_ARTIFACT.url, KALI_ARTIFACT.sha256) == (
        "2026.2",
        "https://kali.download/wsl-images/kali-2026.2/kali-linux-2026.2-wsl-rootfs-amd64.wsl",
        "1b172389e9109e9bb0c3d1fa18eda078271484dbcef8dbee4aab8b1f369466c6",
    )


def test_download_rejects_wrong_checksum(tmp_path):
    artifact = replace(OLLAMA_ARTIFACT, sha256="0" * 64, filename="a.bin")
    with pytest.raises(ArtifactVerificationError):
        download_verified(artifact, tmp_path, lambda *_: None, Event(), opener=fake_opener(b"wrong"))
    assert not (tmp_path / "a.bin").exists()


def test_download_reports_progress_and_writes_verified_file(tmp_path):
    import hashlib

    body = b"verified payload"
    artifact = replace(OLLAMA_ARTIFACT, sha256=hashlib.sha256(body).hexdigest(), filename="a.bin")
    progress = []
    result = download_verified(artifact, tmp_path, lambda done, total: progress.append((done, total)), Event(), opener=fake_opener(body))
    assert result == tmp_path / "a.bin"
    assert result.read_bytes() == body
    assert progress[-1] == (len(body), len(body))


def test_download_cancellation_removes_partial_file(tmp_path):
    cancelled = Event()
    cancelled.set()
    artifact = replace(OLLAMA_ARTIFACT, filename="a.bin")
    with pytest.raises(DownloadCancelledError):
        download_verified(artifact, tmp_path, lambda *_: None, cancelled, opener=fake_opener(b"payload"))
    assert not (tmp_path / "a.bin").exists()


def test_download_rejects_non_https_url_and_redirect(tmp_path):
    artifact = replace(OLLAMA_ARTIFACT, url="http://example.test/a", filename="a.bin")
    with pytest.raises(InsecureDownloadError):
        download_verified(artifact, tmp_path, lambda *_: None, Event(), opener=fake_opener(b"payload"))

    artifact = replace(OLLAMA_ARTIFACT, filename="a.bin")
    with pytest.raises(InsecureDownloadError):
        download_verified(
            artifact,
            tmp_path,
            lambda *_: None,
            Event(),
            opener=fake_opener(b"payload", "http://example.test/redirect"),
        )


def test_setup_state_round_trips_atomically(tmp_path):
    path = tmp_path / "setup.json"
    SetupState(stages={"ollama": SetupStage("ollama", "ready", "OK", "Ready")}).save(path)
    assert SetupState.load(path).stages["ollama"].status == "ready"
    assert not path.with_suffix(".tmp").exists()


def test_corrupt_setup_state_is_replaced_with_safe_empty_state(tmp_path):
    path = tmp_path / "setup.json"
    path.write_text("not json", encoding="utf-8")
    state = SetupState.load(path)
    assert state.stages == {}
    assert state.code == "SETUP_STATE_INVALID"


def test_missing_setup_state_starts_empty(tmp_path):
    state = SetupState.load(tmp_path / "missing.json")
    assert state.stages == {}
    assert state.code == "OK"


def test_setup_state_rejects_invalid_stage(tmp_path):
    path = tmp_path / "setup.json"
    path.write_text('{"stages":{"ollama":{"name":"ollama","status":"unknown","code":"X","detail":"bad"}}}', encoding="utf-8")
    state = SetupState.load(path)
    assert state.stages == {}
    assert state.code == "SETUP_STATE_INVALID"
