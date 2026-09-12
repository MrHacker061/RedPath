"""Closed-world action execution through the managed Kali VM.

Caller data can select one of three action templates, an authorized target ID,
and bounded numeric values. It can never provide command text or SSH options.
"""
from __future__ import annotations

import ipaddress
import re
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol, Sequence

from .vm import KaliVMError, ProcessResult, SAFE_SSH_OPTIONS, SSHConfig

MAX_ACTION_OUTPUT_CHARS = 16_384
_TRUNCATION_MARKER = "\n[output truncated]"
_TARGET_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_IPV6_ULA = ipaddress.ip_network("fc00::/7")


class KaliActionError(KaliVMError):
    """An action request or trusted transport configuration failed closed."""


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


@dataclass(frozen=True)
class _ActionInvocation:
    name: str
    target_id: str
    target_address: str
    port: int
    remote_command: str
    process_timeout: int


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


def _validate_target_id(value: object) -> str:
    if type(value) is not str or _TARGET_ID_PATTERN.fullmatch(value) is None:
        raise KaliActionError("authorized target identifier is invalid")
    return value


def _validate_private_address(
    value: object,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if type(value) is not str or "%" in value:
        raise KaliActionError("target must be a literal private lab address")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise KaliActionError("target must be a literal private lab address") from exc
    allowed = (
        isinstance(address, ipaddress.IPv4Address)
        and any(address in network for network in _RFC1918_NETWORKS)
    ) or (isinstance(address, ipaddress.IPv6Address) and address in _IPV6_ULA)
    if not allowed:
        raise KaliActionError("target must be a literal private lab address")
    return address


def _strict_integer(
    value: object, *, name: str, minimum: int, maximum: int
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise KaliActionError(f"{name} must be an integer from {minimum} through {maximum}")
    return value


def _validate_invocation(
    action_name: object,
    arguments: object,
    authorized_target_id: object,
    authorized_target_address: object,
) -> _ActionInvocation:
    schemas = {
        "check_tcp_connection": ({"target_id", "port"}, {"timeout_seconds"}),
        "inspect_http_headers": ({"target_id", "port"}, set()),
        "inspect_tls_certificate": ({"target_id", "port"}, set()),
    }
    if type(action_name) is not str or action_name not in schemas:
        raise KaliActionError("unknown fixed Kali action")
    if type(arguments) is not dict:
        raise KaliActionError("action arguments must be a plain object")

    required, optional = schemas[action_name]
    keys = set(arguments)
    if keys != required and not (required <= keys <= required | optional):
        raise KaliActionError("action arguments do not match the fixed schema")

    trusted_target_id = _validate_target_id(authorized_target_id)
    supplied_target_id = _validate_target_id(arguments.get("target_id"))
    if supplied_target_id != trusted_target_id:
        raise KaliActionError("action target does not match the authorized target")
    address = _validate_private_address(authorized_target_address)
    address_text = str(address)
    port = _strict_integer(
        arguments.get("port"), name="port", minimum=1, maximum=65_535
    )

    if action_name == "check_tcp_connection":
        action_timeout = _strict_integer(
            arguments.get("timeout_seconds", 5),
            name="timeout_seconds",
            minimum=1,
            maximum=10,
        )
        remote_command = (
            f"timeout --signal=KILL {action_timeout}s nc -vz -w {action_timeout} "
            f"{address_text} {port}"
        )
        process_timeout = action_timeout + 5
    elif action_name == "inspect_http_headers":
        url_host = f"[{address_text}]" if address.version == 6 else address_text
        remote_command = (
            "timeout --signal=KILL 10s curl --head --silent --show-error "
            "--max-time 8 --connect-timeout 5 --proto =http -- "
            f"http://{url_host}:{port}/"
        )
        process_timeout = 15
    else:
        endpoint_host = f"[{address_text}]" if address.version == 6 else address_text
        remote_command = (
            "timeout --signal=KILL 10s openssl s_client -brief "
            f"-connect {endpoint_host}:{port}"
        )
        process_timeout = 15

    return _ActionInvocation(
        name=action_name,
        target_id=trusted_target_id,
        target_address=address_text,
        port=port,
        remote_command=remote_command,
        process_timeout=process_timeout,
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
        invocation = _validate_invocation(
            action_name,
            arguments,
            authorized_target_id,
            authorized_target_address,
        )
        try:
            ssh = self._vm_manager.discover_ssh_config()
        except KaliVMError:
            return self._result(
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
            return self._result(
                invocation,
                status=ActionStatus.TIMED_OUT,
                stdout=exc.output,
                stderr=exc.stderr,
                error=f"fixed action timed out after {exc.timeout:g} seconds",
            )
        except OSError:
            return self._result(
                invocation,
                status=ActionStatus.FAILED,
                error="fixed action runner unavailable",
            )

        if type(completed.returncode) is not int:
            return self._result(
                invocation,
                status=ActionStatus.FAILED,
                error="fixed action runner returned an invalid result",
            )
        if completed.returncode != 0:
            return self._result(
                invocation,
                status=ActionStatus.FAILED,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                error=f"fixed action exited with status {completed.returncode}",
            )
        return self._result(
            invocation,
            status=ActionStatus.SUCCEEDED,
            exit_code=0,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    @staticmethod
    def _result(
        invocation: _ActionInvocation,
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
