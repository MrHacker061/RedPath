"""Fail-closed Python wrapper for the existing Kali lifecycle manager.

Only status, start, SSH discovery, and graceful stop are exposed. The manager's
arbitrary guest-command and force-stop features are deliberately absent.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

MAX_CAPTURE_CHARS = 32_768
EXPECTED_VM_NAME = "Headless-Kali-Terminal"
EXPECTED_ADDRESS = "192.168.56.10"


class KaliVMError(RuntimeError):
    """Lifecycle execution or validation failed closed."""


class VMState(str, Enum):
    NOT_CREATED = "not_created"
    POWEROFF = "poweroff"
    RUNNING = "running"
    OTHER = "other"


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class OperationResult:
    operation: str
    state: VMState
    output: str


@dataclass(frozen=True)
class SSHConfig:
    alias: str
    hostname: str
    port: int
    user: str
    identity_file: Path
    identities_only: bool


Runner = Callable[[Sequence[str], Path, float], ProcessResult]


def _bounded(text: str) -> str:
    return text if len(text) <= MAX_CAPTURE_CHARS else text[:MAX_CAPTURE_CHARS] + "\n[output truncated]"


def _default_runner(arguments: Sequence[str], cwd: Path, timeout: float) -> ProcessResult:
    try:
        completed = subprocess.run(list(arguments), cwd=cwd, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   timeout=timeout, check=False, shell=False)
    except subprocess.TimeoutExpired as exc:
        raise KaliVMError(f"Kali VM operation timed out after {timeout:g} seconds") from exc
    except OSError as exc:
        raise KaliVMError(f"Could not launch the Kali VM manager: {exc}") from exc
    return ProcessResult(completed.returncode, _bounded(completed.stdout), _bounded(completed.stderr))


def parse_status(output: str) -> VMState:
    matches = re.findall(r"(?im)^\s*VM state:\s*([a-z0-9_-]+)\s*$", output)
    if len(matches) != 1:
        raise KaliVMError("Expected exactly one VM state in lifecycle output")
    try:
        return VMState(matches[0].lower())
    except ValueError:
        return VMState.OTHER


def parse_ssh_config(output: str) -> SSHConfig:
    blocks = re.split(r"(?im)(?=^\s*Host\s+)", output)
    blocks = [b for b in blocks if re.search(r"(?im)^\s*Host\s+kali-headless\s*$", b)]
    if len(blocks) != 1:
        raise KaliVMError("Expected exactly one kali-headless SSH configuration")
    block = blocks[0]

    def field(name: str) -> str:
        values = re.findall(rf"(?im)^\s*{re.escape(name)}\s+(.+?)\s*$", block)
        if len(values) != 1:
            raise KaliVMError(f"Expected exactly one SSH {name} value")
        return values[0].strip().strip('"')

    hostname = field("HostName")
    if hostname not in {"127.0.0.1", "localhost"}:
        raise KaliVMError("SSH endpoint must use Windows loopback")
    try:
        port = int(field("Port"))
    except ValueError as exc:
        raise KaliVMError("SSH port is not an integer") from exc
    if not 1 <= port <= 65535:
        raise KaliVMError("SSH port is outside the valid range")
    user = field("User")
    if user != "vagrant":
        raise KaliVMError("Unexpected SSH user")
    identity_file = Path(field("IdentityFile"))
    if not identity_file.is_absolute():
        raise KaliVMError("SSH identity file must be absolute")
    identities_only = field("IdentitiesOnly").lower() == "yes"
    if not identities_only:
        raise KaliVMError("SSH must enforce IdentitiesOnly yes")
    return SSHConfig("kali-headless", hostname, port, user, identity_file, identities_only)


class KaliVMManager:
    """Runs only the explicitly allowed lifecycle commands through KaliVM.ps1."""

    def __init__(self, repository_root: Path | str, *, runner: Runner = _default_runner,
                 powershell: str = "powershell.exe") -> None:
        self.repository_root = Path(repository_root).resolve()
        self.vm_directory = self.repository_root / "vm"
        self.script = self.vm_directory / "KaliVM.ps1"
        self.settings = self.vm_directory / "kali-vm.json"
        self._runner, self._powershell = runner, powershell
        self._validate_installation()

    def _validate_installation(self) -> None:
        if not self.script.is_file() or not self.settings.is_file():
            raise KaliVMError("Managed Kali script and settings are required")
        try:
            settings = json.loads(self.settings.read_text(encoding="utf-8"))
            vagrantfile = (self.vm_directory / "Vagrantfile").read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            raise KaliVMError(f"Could not validate the Kali VM files: {exc}") from exc
        expected = {"vmName": EXPECTED_VM_NAME, "memoryMB": 4096, "cpus": 4}
        if any(settings.get(key) != value for key, value in expected.items()):
            raise KaliVMError("Unexpected managed Kali identity or resources")
        if EXPECTED_ADDRESS not in vagrantfile:
            raise KaliVMError("Expected host-only Kali address is missing")

    def _invoke(self, operation: str, timeout: float) -> str:
        if operation not in {"status", "start", "ssh-config", "stop"}:
            raise KaliVMError(f"Unsupported Kali VM operation: {operation}")
        command = (self._powershell, "-NoLogo", "-NoProfile", "-NonInteractive",
                   "-ExecutionPolicy", "Bypass", "-File", str(self.script), operation)
        result = self._runner(command, self.vm_directory, timeout)
        output = _bounded("\n".join(x for x in (result.stdout, result.stderr) if x))
        if result.returncode:
            raise KaliVMError(f"Kali VM {operation} failed with exit code {result.returncode}: {output}")
        return output

    def status(self) -> OperationResult:
        output = self._invoke("status", 30)
        return OperationResult("status", parse_status(output), output)

    def start(self) -> OperationResult:
        output = self._invoke("start", 660)
        state = self.status().state
        if state is not VMState.RUNNING:
            raise KaliVMError(f"Start completed but final state is {state.value}")
        return OperationResult("start", state, output)

    def discover_ssh_config(self) -> SSHConfig:
        if self.status().state is not VMState.RUNNING:
            raise KaliVMError("SSH configuration is available only while Kali is running")
        return parse_ssh_config(self._invoke("ssh-config", 30))

    def stop(self) -> OperationResult:
        # Intentionally never passes -Force.
        output = self._invoke("stop", 150)
        state = self.status().state
        if state not in {VMState.POWEROFF, VMState.NOT_CREATED}:
            raise KaliVMError(f"Graceful stop did not reach poweroff; final state is {state.value}")
        return OperationResult("stop", state, output)
