"""Safe, fixed-operation integration with RedPath's managed Kali VM."""
from .actions import (
    ActionResult,
    ActionStatus,
    KaliActionDispatcher,
    KaliActionError,
)
from .vm import (
    KaliVMError,
    KaliVMManager,
    OperationResult,
    ProcessResult,
    SSHConfig,
    VMState,
    parse_ssh_config,
    parse_status,
)

__all__ = [
    "ActionResult",
    "ActionStatus",
    "KaliActionDispatcher",
    "KaliActionError",
    "KaliVMError",
    "KaliVMManager",
    "OperationResult",
    "ProcessResult",
    "SSHConfig",
    "VMState",
    "parse_ssh_config",
    "parse_status",
]
