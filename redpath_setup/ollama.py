"""Consent-gated setup for the pinned local Ollama runtime."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Protocol

from redpath_ai.providers import OLLAMA_MODEL, OllamaProvider

from .downloads import DownloadCancelledError, DownloadError, download_verified
from .manifest import OLLAMA_ARTIFACT
from .state import SetupStage

INSTALL_TIMEOUT_SECONDS = 600
MAX_PROGRESS_LINE_BYTES = 4096
Progress = Callable[[int, int | None], None]


class CommandResult(Protocol):
    returncode: int


Runner = Callable[[Sequence[str], Path, float, Event, Progress], CommandResult]
Downloader = Callable[[object, Path, Progress, Event], Path]


class ProcessCancelled(RuntimeError):
    """A setup operation was cancelled while its child process was active."""


def _stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _read_progress_lines(stdout, updates: Queue[tuple[int, int]], stopped: Event) -> None:
    while not stopped.is_set():
        line = stdout.readline(MAX_PROGRESS_LINE_BYTES)
        if not line:
            return
        update = _progress_fields(line)
        if update is None:
            continue
        while not stopped.is_set():
            try:
                updates.put(update, timeout=0.1)
                break
            except Full:
                pass


def _progress_fields(line: bytes) -> tuple[int, int] | None:
    try:
        value = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    completed, total = value.get("completed"), value.get("total")
    if type(completed) is not int or type(total) is not int or not 0 <= completed <= total or total <= 0:
        return None
    return completed, total


def _run(
    argv: Sequence[str], cwd: Path, timeout: float, cancelled: Event, progress: Progress
) -> subprocess.CompletedProcess[str]:
    """Run a fixed command with bounded numeric progress and responsive cancellation."""
    progress(0, None)
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    assert process.stdout is not None
    updates: Queue[tuple[int, int]] = Queue(maxsize=1)
    stopped = Event()
    reader = Thread(target=_read_progress_lines, args=(process.stdout, updates, stopped), daemon=True)
    reader.start()
    latest: tuple[int, int] | None = None

    def report(update: tuple[int, int]) -> None:
        nonlocal latest
        latest = update
        progress(*update)

    deadline = time.monotonic() + timeout
    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            stopped.set()
            _stop(process)
            raise subprocess.TimeoutExpired(list(argv), timeout)
        if cancelled.is_set():
            stopped.set()
            _stop(process)
            raise ProcessCancelled()
        try:
            report(updates.get(timeout=min(0.1, remaining)))
        except Empty:
            pass
    while reader.is_alive():
        try:
            report(updates.get(timeout=0.1))
        except Empty:
            pass
    reader.join()
    while not updates.empty():
        report(updates.get_nowait())
    if latest is None:
        progress(1, 1)
    elif latest[0] != latest[1]:
        progress(latest[1], latest[1])
    return subprocess.CompletedProcess(list(argv), process.returncode)


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
                [str(installer), "/VERYSILENT", "/NORESTART"], self.destination, INSTALL_TIMEOUT_SECONDS, cancelled, progress
            )
        except ProcessCancelled:
            return self._cancelled()
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
        try:
            result = self.runner(
                ["ollama", "pull", OLLAMA_MODEL], self.destination, INSTALL_TIMEOUT_SECONDS, cancelled, progress
            )
        except ProcessCancelled:
            return self._cancelled()
        except subprocess.TimeoutExpired:
            return SetupStage("ollama", "failed", "OLLAMA_MODEL_PULL_TIMEOUT", "The model download did not finish in time.")
        except OSError:
            return SetupStage("ollama", "failed", "OLLAMA_MODEL_PULL_FAILED", "The model download could not be started.")
        if result.returncode != 0:
            return SetupStage("ollama", "failed", "OLLAMA_MODEL_PULL_FAILED", "The model download did not complete successfully.")
        if cancelled.is_set():
            return self._cancelled()
        return self.inspect()

    @staticmethod
    def _consent_required() -> SetupStage:
        return SetupStage("ollama", "needs_attention", "CONSENT_REQUIRED", "Explicit consent is required before changing Ollama.")

    @staticmethod
    def _cancelled() -> SetupStage:
        return SetupStage("ollama", "needs_attention", "CANCELLED", "The Ollama setup operation was cancelled.")
