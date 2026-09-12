"""WSL transport for the existing closed-world Kali action registry."""

from __future__ import annotations

import subprocess
from typing import Protocol, Sequence

from redpath_setup.wsl import WslSetupError

from .action_specs import render_fixed_action
from .actions import (
    ActionResult,
    ActionStatus,
    _action_result,
)
from .vm import ProcessResult


class WslRunner(Protocol):
    def run_in_kali(self, arguments: Sequence[str], timeout: float) -> ProcessResult: ...


class WSLActionDispatcher:
    """Dispatch exactly one registry-validated learning action through RedPath-Kali."""

    def __init__(self, setup: WslRunner) -> None:
        self._setup = setup

    def dispatch(
        self,
        action_name: str,
        arguments: dict[str, object],
        *,
        authorized_target_id: str,
        authorized_target_address: str,
    ) -> ActionResult:
        invocation = render_fixed_action(
            action_name, arguments, authorized_target_id, authorized_target_address
        )
        try:
            completed = self._setup.run_in_kali(
                invocation.guest_argv, float(invocation.process_timeout)
            )
        except subprocess.TimeoutExpired as exc:
            return _action_result(
                invocation, status=ActionStatus.TIMED_OUT, stdout=exc.output, stderr=exc.stderr,
                error=f"fixed action timed out after {exc.timeout:g} seconds",
            )
        except (OSError, WslSetupError):
            return _action_result(
                invocation, status=ActionStatus.FAILED, error="managed Kali WSL is unavailable"
            )
        if not isinstance(completed, ProcessResult) or type(completed.returncode) is not int:
            return _action_result(
                invocation, status=ActionStatus.FAILED, error="managed Kali WSL returned an invalid result"
            )
        if completed.returncode != 0:
            return _action_result(
                invocation, status=ActionStatus.FAILED, exit_code=completed.returncode,
                stdout=completed.stdout, stderr=completed.stderr,
                error=f"fixed action exited with status {completed.returncode}",
            )
        return _action_result(
            invocation, status=ActionStatus.SUCCEEDED, exit_code=0,
            stdout=completed.stdout, stderr=completed.stderr,
        )
