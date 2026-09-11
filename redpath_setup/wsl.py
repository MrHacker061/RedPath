"""Fail-closed WSL2 setup for RedPath's one managed Kali distribution.

This module owns only WSL setup and transport.  The action registry validates
which fixed Kali argv is allowed before it calls :meth:`WslSetup.run_in_kali`.
"""

from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event
from typing import Protocol

from redpath_kali import ProcessResult

from .downloads import DownloadCancelledError, DownloadError, download_verified
from .manifest import Artifact, KALI_ARTIFACT
from .state import SetupStage

DISTRIBUTION_NAME = "RedPath-Kali"
MANAGED_MARKER = "/etc/redpath-managed"
STATUS_TIMEOUT_SECONDS = 30
ENABLE_TIMEOUT_SECONDS = 120
IMPORT_TIMEOUT_SECONDS = 1_800
MAX_ACTION_TIMEOUT_SECONDS = 60


class WslSetupError(RuntimeError):
    """WSL setup or trusted managed-distribution validation failed closed."""


class WslMarkerCheckError(WslSetupError):
    """The marker probe could not establish whether RedPath owns the distro."""


class Runner(Protocol):
    def __call__(self, argv: Sequence[str], cwd: Path, timeout: float) -> ProcessResult: ...


Progress = Callable[[int, int | None], None]
Downloader = Callable[[Artifact, Path, Progress, Event], Path]


def _run(argv: Sequence[str], cwd: Path, timeout: float) -> ProcessResult:
    """Run one fixed WSL argv without a shell or inherited interactive input."""
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _normalized_wsl_text(*values: str) -> str:
    """Normalize UTF-16LE/NUL console redirection decoded as UTF-8 text."""
    text = "\n".join(values).replace("\x00", "")
    return text.lstrip("\ufeff\ufffd")


def _restart_pending(result: ProcessResult) -> bool:
    text = _normalized_wsl_text(result.stdout, result.stderr).casefold()
    no_restart = r"(?:no|not)\s+(?:restart|reboot)\s+(?:is\s+)?required|(?:restart|reboot)\s+(?:is\s+)?not\s+required"
    return re.search(no_restart, text) is None and re.search(r"\b(?:restart|reboot)\b", text) is not None


def _wsl2_available(result: ProcessResult) -> bool:
    if result.returncode != 0:
        return False
    text = _normalized_wsl_text(result.stdout, result.stderr).casefold()
    return "default version: 1" not in text and "default version 1" not in text


def _valid_arguments(arguments: Sequence[str]) -> tuple[str, ...]:
    if isinstance(arguments, (str, bytes)):
        raise WslSetupError("Kali arguments must be a typed argv sequence")
    try:
        values = tuple(arguments)
    except TypeError as exc:
        raise WslSetupError("Kali arguments must be a typed argv sequence") from exc
    if not values or any(type(value) is not str or not value or "\x00" in value for value in values):
        raise WslSetupError("Kali arguments must be a non-empty typed argv sequence")
    return values


class WslSetup:
    """Set up and use exactly ``RedPath-Kali``; never unregisters a distro."""

    def __init__(
        self,
        destination: Path,
        *,
        runner: Runner = _run,
        downloader: Downloader = download_verified,
    ) -> None:
        self.destination = Path(destination)
        self.runner = runner
        self.downloader = downloader

    def _cwd(self) -> Path:
        return self.destination if self.destination.is_dir() else Path.cwd()

    def _invoke(self, argv: Sequence[str], timeout: float) -> ProcessResult:
        result = self.runner(tuple(argv), self._cwd(), timeout)
        if not isinstance(result, ProcessResult):
            raise WslSetupError("WSL runner returned an invalid result")
        return result

    def _distribution_names(self) -> tuple[str, ...]:
        result = self._invoke(("wsl.exe", "--list", "--quiet"), STATUS_TIMEOUT_SECONDS)
        if result.returncode != 0:
            raise WslSetupError("WSL distribution listing failed")
        text = _normalized_wsl_text(result.stdout)
        return tuple(line.strip() for line in text.splitlines() if line.strip())

    def _managed_distribution_exists(self) -> bool:
        matches = [name for name in self._distribution_names() if name.casefold() == DISTRIBUTION_NAME.casefold()]
        if len(matches) > 1:
            raise WslSetupError("managed Kali distribution identity is ambiguous")
        return len(matches) == 1

    def _has_managed_marker(self) -> bool:
        result = self._invoke(
            ("wsl.exe", "--distribution", DISTRIBUTION_NAME, "--exec", "/usr/bin/test", "-f", MANAGED_MARKER),
            STATUS_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        raise WslMarkerCheckError("managed Kali marker check failed")

    @staticmethod
    def _consent_required() -> SetupStage:
        return SetupStage("wsl", "needs_attention", "CONSENT_REQUIRED", "Explicit consent is required before changing WSL.")

    @staticmethod
    def _cancelled() -> SetupStage:
        return SetupStage("wsl", "needs_attention", "CANCELLED", "The Kali setup operation was cancelled.")

    def inspect(self) -> SetupStage:
        """Confirm WSL2 and the exact, marker-owned Kali distribution."""
        try:
            status = self._invoke(("wsl.exe", "--status"), STATUS_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired, WslSetupError):
            return SetupStage("wsl", "needs_attention", "WSL_UNAVAILABLE", "WSL2 is unavailable.")
        if not _wsl2_available(status):
            return SetupStage("wsl", "needs_attention", "WSL2_REQUIRED", "WSL2 must be enabled before Kali can be used.")
        try:
            if not self._managed_distribution_exists():
                return SetupStage("wsl", "needs_attention", "KALI_NOT_INSTALLED", "The managed Kali distribution is not installed.")
            if not self._has_managed_marker():
                return SetupStage("wsl", "failed", "KALI_IDENTITY_MISMATCH", "The existing Kali distribution is not managed by RedPath.")
        except WslMarkerCheckError:
            return SetupStage("wsl", "failed", "KALI_MARKER_CHECK_FAILED", "The managed Kali ownership marker could not be checked.")
        except (OSError, subprocess.TimeoutExpired, WslSetupError):
            return SetupStage("wsl", "needs_attention", "WSL_UNAVAILABLE", "WSL2 is unavailable.")
        return SetupStage("wsl", "ready", "KALI_READY", "The managed Kali distribution is ready.")

    def enable(self, consent: bool) -> SetupStage:
        """Request WSL2 setup only after an explicit user consent receipt."""
        if consent is not True:
            return self._consent_required()
        try:
            result = self._invoke(("wsl.exe", "--install", "--no-distribution"), ENABLE_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired, WslSetupError):
            return SetupStage("wsl", "failed", "WSL_ENABLE_FAILED", "Windows could not start WSL2 setup.")
        if result.returncode == 3010:
            return SetupStage("wsl", "needs_attention", "RESTART_REQUIRED", "Restart Windows, then return to RedPath setup.")
        if result.returncode != 0:
            return SetupStage("wsl", "failed", "WSL_ENABLE_FAILED", "Windows could not enable WSL2.")
        if _restart_pending(result):
            return SetupStage("wsl", "needs_attention", "RESTART_REQUIRED", "Restart Windows, then return to RedPath setup.")
        return self.inspect()

    def install_kali(self, consent: bool, progress: Progress, cancelled: Event) -> SetupStage:
        """Import the verified Kali artifact and write RedPath's fixed marker."""
        if consent is not True:
            return self._consent_required()
        if cancelled.is_set():
            return self._cancelled()

        initial = self.inspect()
        if initial.code != "KALI_NOT_INSTALLED":
            return initial

        try:
            self.destination.mkdir(parents=True, exist_ok=True)
            verified_file = Path(self.downloader(KALI_ARTIFACT, self.destination, progress, cancelled))
        except DownloadCancelledError:
            return self._cancelled()
        except (DownloadError, OSError):
            return SetupStage("wsl", "failed", "KALI_DOWNLOAD_FAILED", "The pinned Kali artifact could not be verified.")
        if cancelled.is_set():
            return self._cancelled()

        expected_file = self.destination / KALI_ARTIFACT.filename
        if verified_file != expected_file or not expected_file.is_file() or expected_file.is_symlink():
            return SetupStage("wsl", "failed", "KALI_ARTIFACT_INVALID", "The verified Kali artifact is unavailable.")

        try:
            imported = self._invoke(
                (
                    "wsl.exe", "--import", DISTRIBUTION_NAME, str(self.destination / DISTRIBUTION_NAME),
                    str(expected_file), "--version", "2",
                ),
                IMPORT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired, WslSetupError):
            return SetupStage("wsl", "failed", "KALI_IMPORT_FAILED", "The managed Kali distribution could not be imported.")
        if imported.returncode != 0:
            return SetupStage("wsl", "failed", "KALI_IMPORT_FAILED", "The managed Kali distribution could not be imported.")

        try:
            marked = self._invoke(
                ("wsl.exe", "--distribution", DISTRIBUTION_NAME, "--exec", "/usr/bin/touch", MANAGED_MARKER),
                STATUS_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired, WslSetupError):
            return SetupStage("wsl", "failed", "KALI_MARKER_FAILED", "The imported Kali distribution could not be marked safely.")
        if marked.returncode != 0:
            return SetupStage("wsl", "failed", "KALI_MARKER_FAILED", "The imported Kali distribution could not be marked safely.")
        return SetupStage("wsl", "ready", "KALI_READY", "The managed Kali distribution is ready.")

    def run_in_kali(self, arguments: Sequence[str], timeout: float) -> ProcessResult:
        """Execute a prevalidated fixed action in the owned Kali distribution."""
        argv = _valid_arguments(arguments)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= MAX_ACTION_TIMEOUT_SECONDS:
            raise WslSetupError("Kali timeout must be a finite number from 0 through 60 seconds")
        stage = self.inspect()
        if stage.code != "KALI_READY":
            raise WslSetupError("managed Kali distribution is not ready")
        return self._invoke(("wsl.exe", "--distribution", DISTRIBUTION_NAME, "--exec", *argv), float(timeout))
