"""Closed-world action execution through the managed Kali VM.

Caller data can select one of three action templates, an authorized target ID,
and bounded numeric values. It can never provide command text or SSH options.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol, Sequence

from .action_specs import FixedActionSpec, KaliActionError, render_fixed_action
from .vm import KaliVMError, ProcessResult, SAFE_SSH_OPTIONS, SSHConfig

MAX_ACTION_OUTPUT_CHARS = 16_384
_TRUNCATION_MARKER = "\n[output truncated]"


class ActionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class ActionResult:
    """Bounded evidence returned by one fixed action attempt."""

    action_name: str
    target_id: str
    target_address: str
    port: int
    status: ActionStatus
    exit_code: int | None
    stdout: str
    stderr: str
    output_truncated: bool
    error: str | None = None


class SSHConfigProvider(Protocol):
    def discover_ssh_config(self) -> SSHConfig: ...


ActionRunner = Callable[[Sequence[str], Path, float], ProcessResult]


def _default_action_runner(
    arguments: Sequence[str], cwd: Path, timeout: float
) -> ProcessResult:
    completed = subprocess.run(
        list(arguments),
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


def _bounded(value: object) -> tuple[str, bool]:
    if value is None:
        text = ""
    elif isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    if len(text) <= MAX_ACTION_OUTPUT_CHARS:
        return text, False
    return text[:MAX_ACTION_OUTPUT_CHARS] + _TRUNCATION_MARKER, True


def _action_result(
    invocation: FixedActionSpec,
    *,
    status: ActionStatus,
    exit_code: int | None = None,
    stdout: object = "",
    stderr: object = "",
    error: str | None = None,
) -> ActionResult:
    bounded_stdout, stdout_truncated = _bounded(stdout)
    bounded_stderr, stderr_truncated = _bounded(stderr)
    return ActionResult(
        action_name=invocation.name,
        target_id=invocation.target_id,
        target_address=invocation.target_address,
        port=invocation.port,
        status=status,
        exit_code=exit_code,
        stdout=bounded_stdout,
        stderr=bounded_stderr,
        output_truncated=stdout_truncated or stderr_truncated,
        error=error,
    )


def _validate_ssh_config(config: SSHConfig) -> None:
    valid = (
        config.alias == "kali-headless"
        and config.hostname == "127.0.0.1"
        and type(config.port) is int
        and 1 <= config.port <= 65_535
        and config.user == "vagrant"
        and config.identities_only is True
        and config.client_options == SAFE_SSH_OPTIONS
        and isinstance(config.identity_file, Path)
        and config.identity_file.is_absolute()
    )
    if not valid:
        raise KaliActionError("managed Kali SSH configuration is unsafe")


def _ssh_argv(
    config: SSHConfig,
    remote_command: str,
    known_hosts_file: Path,
) -> tuple[str, ...]:
    return (
        "ssh.exe",
        "-T",
        "-x",
        "-a",
        *(part for option in SAFE_SSH_OPTIONS for part in ("-o", option)),
        "-o",
        "ConnectTimeout=5",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={known_hosts_file}",
        "-i",
        str(config.identity_file),
        "-p",
        str(config.port),
        "--",
        f"{config.user}@{config.hostname}",
        remote_command,
    )


class KaliActionDispatcher:
    """Validate and run exactly one of RedPath's three fixed learning actions."""

    def __init__(
        self,
        vm_manager: SSHConfigProvider,
        *,
        runner: ActionRunner = _default_action_runner,
    ) -> None:
        self._vm_manager = vm_manager
        self._runner = runner

    def dispatch(
        self,
        action_name: str,
        arguments: dict[str, object],
        *,
        authorized_target_id: str,
        authorized_target_address: str,
    ) -> ActionResult:
        invocation = render_fixed_action(
            action_name,
            arguments,
            authorized_target_id,
            authorized_target_address,
        )
        try:
            ssh = self._vm_manager.discover_ssh_config()
        except KaliVMError:
            return _action_result(
                invocation,
                status=ActionStatus.FAILED,
                error="managed Kali SSH is unavailable",
            )
        _validate_ssh_config(ssh)

        try:
            with tempfile.TemporaryDirectory(prefix="redpath-action-") as workdir:
                command = _ssh_argv(
                    ssh,
                    invocation.remote_command,
                    Path(workdir) / "known_hosts",
                )
                completed = self._runner(
                    command,
                    Path(workdir),
                    invocation.process_timeout,
                )
        except subprocess.TimeoutExpired as exc:
            return _action_result(
                invocation,
                status=ActionStatus.TIMED_OUT,
                stdout=exc.output,
                stderr=exc.stderr,
                error=f"fixed action timed out after {exc.timeout:g} seconds",
            )
        except OSError:
            return _action_result(
                invocation,
                status=ActionStatus.FAILED,
                error="fixed action runner unavailable",
            )

        if type(completed.returncode) is not int:
            return _action_result(
                invocation,
                status=ActionStatus.FAILED,
                error="fixed action runner returned an invalid result",
            )
        if completed.returncode != 0:
            return _action_result(
                invocation,
                status=ActionStatus.FAILED,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                error=f"fixed action exited with status {completed.returncode}",
            )
        return _action_result(
            invocation,
            status=ActionStatus.SUCCEEDED,
            exit_code=0,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
