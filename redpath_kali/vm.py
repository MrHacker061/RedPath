"""Fail-closed Python wrapper for the existing Kali lifecycle manager.

Only status, start, SSH discovery, and graceful stop are exposed. The manager's
arbitrary guest-command and force-stop features are deliberately absent.
"""
from __future__ import annotations

import json
import os
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
    client_options: tuple[str, ...]


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


SAFE_SSH_OPTIONS = (
    "BatchMode=yes",
    "PasswordAuthentication=no",
    "KbdInteractiveAuthentication=no",
    "PreferredAuthentications=publickey",
    "IdentitiesOnly=yes",
    "ForwardAgent=no",
)


def _is_reparse_or_symlink(path: Path) -> bool:
    """Recognize symlinks and Windows reparse points such as junctions."""
    try:
        stat = path.lstat()
    except OSError:
        return False
    attributes = getattr(stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _regular_unlinked_file(path: Path, description: str) -> Path:
    if _is_reparse_or_symlink(path):
        raise KaliVMError(f"{description} cannot be a symlink or reparse point")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise KaliVMError(f"{description} does not exist") from exc
    if not resolved.is_file():
        raise KaliVMError(f"{description} must be a regular file")
    return resolved


def parse_ssh_config(output: str, *, managed_state_root: Path | str) -> SSHConfig:
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
    if hostname != "127.0.0.1":
        raise KaliVMError("SSH endpoint must be exactly 127.0.0.1")
    try:
        port = int(field("Port"))
    except ValueError as exc:
        raise KaliVMError("SSH port is not an integer") from exc
    if not 1 <= port <= 65535:
        raise KaliVMError("SSH port is outside the valid range")
    user = field("User")
    if user != "vagrant":
        raise KaliVMError("Unexpected SSH user")
    identity_text = field("IdentityFile")
    if identity_text.startswith("\\\\"):
        raise KaliVMError("SSH identity file cannot use a UNC path")
    identity_file = Path(identity_text)
    if not identity_file.is_absolute():
        raise KaliVMError("SSH identity file must be absolute")
    state_root = Path(managed_state_root)
    if not state_root.is_absolute() or _is_reparse_or_symlink(state_root):
        raise KaliVMError("Managed Vagrant state root must be an absolute, unlinked directory")
    try:
        resolved_state_root = state_root.resolve(strict=True)
    except OSError as exc:
        raise KaliVMError("Managed Vagrant state root does not exist") from exc
    if not resolved_state_root.is_dir():
        raise KaliVMError("Managed Vagrant state root must be a directory")
    resolved_identity = _regular_unlinked_file(identity_file, "SSH identity file")
    try:
        relative_identity = resolved_identity.relative_to(resolved_state_root)
    except ValueError as exc:
        raise KaliVMError("SSH identity file is outside managed Vagrant state") from exc
    parts = relative_identity.parts
    if len(parts) < 4 or parts[0] != "machines" or parts[1] != "default" or parts[-1] != "private_key":
        raise KaliVMError("SSH identity file is not the managed default VM private key")
    identities_only = field("IdentitiesOnly").lower() == "yes"
    if not identities_only:
        raise KaliVMError("SSH must enforce IdentitiesOnly yes")
    return SSHConfig("kali-headless", hostname, port, user, resolved_identity,
                     identities_only, SAFE_SSH_OPTIONS)


class KaliVMManager:
    """Runs only the explicitly allowed lifecycle commands through KaliVM.ps1."""

    def __init__(self, repository_root: Path | str, *, runner: Runner = _default_runner,
                 managed_state_root: Path | str | None = None) -> None:
        configured_root = Path(repository_root)
        if not configured_root.is_absolute():
            raise KaliVMError("Repository root must be trusted absolute configuration")
        if _is_reparse_or_symlink(configured_root):
            raise KaliVMError("Repository root cannot be a symlink or reparse point")
        try:
            self.repository_root = configured_root.resolve(strict=True)
        except OSError as exc:
            raise KaliVMError("Repository root does not exist") from exc
        if not self.repository_root.is_dir():
            raise KaliVMError("Repository root must be a directory")
        self.vm_directory = self.repository_root / "vm"
        self.script = self.vm_directory / "KaliVM.ps1"
        self.settings = self.vm_directory / "kali-vm.json"
        default_state = Path(os.environ.get("LOCALAPPDATA", "")) / "HeadlessKaliTerminal" / "state"
        self.managed_state_root = Path(managed_state_root) if managed_state_root is not None else default_state
        self._runner = runner
        self._validate_installation()

    def _validate_installation(self) -> None:
        for path, description in (
            (self.script, "Managed Kali script"),
            (self.settings, "Managed Kali settings"),
            (self.vm_directory / "Vagrantfile", "Managed Vagrantfile"),
        ):
            resolved = _regular_unlinked_file(path, description)
            try:
                resolved.relative_to(self.repository_root)
            except ValueError as exc:
                raise KaliVMError(f"{description} escapes the trusted repository") from exc
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
        command = ("powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
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
        return parse_ssh_config(self._invoke("ssh-config", 30), managed_state_root=self.managed_state_root)

    def stop(self) -> OperationResult:
        # Intentionally never passes -Force.
        output = self._invoke("stop", 150)
        state = self.status().state
        if state not in {VMState.POWEROFF, VMState.NOT_CREATED}:
            raise KaliVMError(f"Graceful stop did not reach poweroff; final state is {state.value}")
        return OperationResult("stop", state, output)
