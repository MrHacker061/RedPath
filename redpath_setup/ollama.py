"""Consent-gated setup for the pinned local Ollama runtime."""

from __future__ import annotations

import re
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
MAX_PROGRESS_LINE_CHARS = 4096
READER_DRAIN_SECONDS = 0.25
Progress = Callable[[int, int | None], None]
_PULL_PROGRESS = re.compile(r"pulling [0-9a-f]{12,64}:\s*(\d{1,3})%")


class CommandResult(Protocol):
    returncode: int


Runner = Callable[[Sequence[str], Path, float, Event, Progress], CommandResult]
Downloader = Callable[[object, Path, Progress, Event], Path]


class ProcessCancelled(RuntimeError):
    """A setup operation was cancelled while its child process was active."""


def _stop(process: subprocess.Popen[str], deadline: float) -> None:
    process.terminate()
    try:
        process.wait(timeout=max(0, min(0.1, deadline - time.monotonic())))
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=max(0, min(0.1, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            # Termination is requested; reaping must not extend the deadline.
            pass


def _read_progress_lines(stderr, updates: Queue[int], stopped: Event) -> None:
    try:
        while not stopped.is_set():
            try:
                line = stderr.readline(MAX_PROGRESS_LINE_CHARS)
            except (OSError, ValueError):
                return
            if not line:
                return
            for update in _progress_fields(line):
                while not stopped.is_set():
                    try:
                        updates.put(update, timeout=0.1)
                        break
                    except Full:
                        pass
    finally:
        # Only the reader closes its stream: concurrent close can block on
        # BufferedReader's lock while a descendant still holds the write end.
        stderr.close()


def _progress_fields(line: str) -> tuple[int, ...]:
    return tuple(percent for match in _PULL_PROGRESS.finditer(line) if 0 <= (percent := int(match.group(1))) <= 100)


def _run(
    argv: Sequence[str], cwd: Path, timeout: float, cancelled: Event, progress: Progress
) -> subprocess.CompletedProcess[str]:
    """Run a fixed command with bounded numeric progress and responsive cancellation."""
    deadline = time.monotonic() + timeout
    progress(0, None)
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    assert process.stderr is not None
    updates: Queue[int] = Queue(maxsize=1)
    stopped = Event()
    reader = Thread(target=_read_progress_lines, args=(process.stderr, updates, stopped), daemon=True)
    reader.start()
    latest: int | None = None

    def report(update: int) -> None:
        nonlocal latest
        latest = update
        progress(update, 100)

    def close_reader(join_timeout: float) -> None:
        stopped.set()
        # An inherited writer may outlive the child. Leave the daemon reader
        # to close its own pipe at EOF instead of blocking this operation.
        reader.join(timeout=max(0, join_timeout))

    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _stop(process, deadline)
            close_reader(0)
            raise subprocess.TimeoutExpired(list(argv), timeout)
        if cancelled.is_set():
            _stop(process, deadline)
            close_reader(min(0.1, deadline - time.monotonic()))
            raise ProcessCancelled()
        try:
            report(updates.get(timeout=min(0.1, remaining)))
        except Empty:
            pass
    drain_deadline = min(deadline, time.monotonic() + READER_DRAIN_SECONDS)
    while reader.is_alive() and time.monotonic() < drain_deadline:
        try:
            report(updates.get(timeout=min(0.05, drain_deadline - time.monotonic())))
        except Empty:
            pass
    close_reader(min(0.1, deadline - time.monotonic()))
    while not updates.empty():
        report(updates.get_nowait())
    if latest is None:
        progress(1, 1)
    elif latest != 100:
        progress(100, 100)
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

    def inspect_service(self) -> SetupStage:
        health = self.provider.health()
        if health.detail == "local Ollama endpoint is unavailable":
            return SetupStage("ollama", "needs_attention", "OLLAMA_UNAVAILABLE", "The local Ollama service is unavailable.")
        return SetupStage("ollama", "ready", "OLLAMA_READY", "The local Ollama service is ready.")

    def inspect_model(self) -> SetupStage:
        health = self.provider.health()
        if health.available:
            return SetupStage("model", "ready", "MODEL_READY", "The pinned local model is ready.")
        if health.detail == "configured model is not installed":
            return SetupStage("model", "needs_attention", "MODEL_MISSING", "The configured local model is not installed.")
        return SetupStage("model", "needs_attention", "OLLAMA_UNAVAILABLE", "The local Ollama service is unavailable.")

    def inspect(self) -> SetupStage:
        """Compatibility alias for callers that need model readiness."""
        return self.inspect_model()

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
