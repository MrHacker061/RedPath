"""Process-local ordering for emergency stops and action starts."""
from collections.abc import Callable
from threading import Lock
from typing import TypeVar

T = TypeVar("T")


class ExecutionFence:
    """Linearize stop changes with the instant a dispatch is allowed to start."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._stopped = False

    def activate(self, persist: Callable[[], T]) -> T:
        with self._lock:
            # Stay fail-closed even if durable stop persistence fails.
            self._stopped = True
            return persist()

    def clear(self, persist: Callable[[], T]) -> T:
        with self._lock:
            result = persist()
            self._stopped = False
            return result

    def try_start(self, durable_check: Callable[[], bool]) -> bool:
        with self._lock:
            if self._stopped:
                return False
            allowed = durable_check()
            if not allowed:
                self._stopped = True
            return allowed
