"""Consent-gated setup for the pinned local Ollama runtime."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event
from typing import Protocol

from redpath_ai.providers import OLLAMA_MODEL, OllamaProvider

from .downloads import DownloadCancelledError, DownloadError, download_verified
from .manifest import OLLAMA_ARTIFACT
from .state import SetupStage

INSTALL_TIMEOUT_SECONDS = 600
Progress = Callable[[int, int | None], None]


class CommandResult(Protocol):
    returncode: int


Runner = Callable[[Sequence[str], Path, float], CommandResult]
Downloader = Callable[[object, Path, Progress, Event], Path]


def _run(argv: Sequence[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    """Run a fixed setup command without exposing or retaining its output."""
    return subprocess.run(
        list(argv),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )


class OllamaSetup:
    """Inspect and repair only the pinned, loopback-only Ollama configuration."""

    def __init__(
        self,
        destination: Path,
        *,
        runner: Runner = _run,
        downloader: Downloader = download_verified,
        provider: OllamaProvider | None = None,
    ) -> None:
        self.destination = Path(destination)
        self.runner = runner
        self.downloader = downloader
        self.provider = provider or OllamaProvider(model=OLLAMA_MODEL)

    def inspect(self) -> SetupStage:
        health = self.provider.health()
        if health.available:
            return SetupStage("ollama", "ready", "OK", "Pinned local model is ready.")
        if health.detail == "configured model is not installed":
            return SetupStage("ollama", "needs_attention", "MODEL_MISSING", "The configured local model is not installed.")
        return SetupStage("ollama", "needs_attention", "OLLAMA_UNAVAILABLE", "The local Ollama service is unavailable.")

    def install(self, consent: bool, progress: Progress, cancelled: Event) -> SetupStage:
        if not consent:
            return self._consent_required()
        if cancelled.is_set():
            return self._cancelled()
        try:
            self.destination.mkdir(parents=True, exist_ok=True)
            self.downloader(OLLAMA_ARTIFACT, self.destination, progress, cancelled)
        except DownloadCancelledError:
            return self._cancelled()
        except DownloadError:
            return SetupStage("ollama", "failed", "OLLAMA_DOWNLOAD_FAILED", "The pinned installer could not be verified.")
        except OSError:
            return SetupStage("ollama", "failed", "OLLAMA_DOWNLOAD_FAILED", "The pinned installer could not be prepared.")
        if cancelled.is_set():
            return self._cancelled()

        installer = self.destination / OLLAMA_ARTIFACT.filename
        if not installer.is_file() or installer.is_symlink():
            return SetupStage("ollama", "failed", "OLLAMA_INSTALLER_INVALID", "The verified installer is unavailable.")
        try:
            result = self.runner(
                [str(installer), "/VERYSILENT", "/NORESTART"], self.destination, INSTALL_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            return SetupStage("ollama", "failed", "OLLAMA_INSTALL_TIMEOUT", "The installer did not finish in time.")
        except OSError:
            return SetupStage("ollama", "failed", "OLLAMA_INSTALL_FAILED", "The installer could not be started.")
        if result.returncode != 0:
            return SetupStage("ollama", "failed", "OLLAMA_INSTALL_FAILED", "The installer did not complete successfully.")
        return self.inspect()

    def pull_model(self, consent: bool, progress: Progress, cancelled: Event) -> SetupStage:
        if not consent:
            return self._consent_required()
        if cancelled.is_set():
            return self._cancelled()
        progress(0, None)
        try:
            result = self.runner(["ollama", "pull", OLLAMA_MODEL], self.destination, INSTALL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return SetupStage("ollama", "failed", "OLLAMA_MODEL_PULL_TIMEOUT", "The model download did not finish in time.")
        except OSError:
            return SetupStage("ollama", "failed", "OLLAMA_MODEL_PULL_FAILED", "The model download could not be started.")
        if result.returncode != 0:
            return SetupStage("ollama", "failed", "OLLAMA_MODEL_PULL_FAILED", "The model download did not complete successfully.")
        if cancelled.is_set():
            return self._cancelled()
        progress(1, 1)
        return self.inspect()

    @staticmethod
    def _consent_required() -> SetupStage:
        return SetupStage("ollama", "needs_attention", "CONSENT_REQUIRED", "Explicit consent is required before changing Ollama.")

    @staticmethod
    def _cancelled() -> SetupStage:
        return SetupStage("ollama", "needs_attention", "CANCELLED", "The Ollama setup operation was cancelled.")
