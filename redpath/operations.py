"""Track protected worker/child lifetime independently of HTTP cancellation."""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Condition, Event
from time import monotonic
from typing import Protocol

from fastapi import HTTPException, Request


class OwnedChild(Protocol):
    def poll(self) -> int | None: ...


_current: ContextVar[ProtectedOperations | None] = ContextVar("redpath_protected_worker", default=None)


class ProtectedOperations:
    def __init__(self) -> None:
        self._condition = Condition()
        self._accepting = True
        self._workers: dict[object, Event | None] = {}
        self._children: dict[int, OwnedChild] = {}

    @contextmanager
    def operation(self, *, cancellable: bool = False) -> Iterator[Event | None]:
        """Enter/exit inside the sync worker, never in an HTTP dependency."""
        ticket = object()
        cancelled = Event() if cancellable else None
        with self._condition:
            if not self._accepting:
                raise HTTPException(status_code=503, detail="APPLICATION_SHUTTING_DOWN")
            self._workers[ticket] = cancelled
        token = _current.set(self)
        try:
            yield cancelled
        finally:
            _current.reset(token)
            with self._condition:
                del self._workers[ticket]
                self._condition.notify_all()
            self._reap_children()

    def close_admission(self) -> None:
        with self._condition:
            self._accepting = False
            for cancelled in self._workers.values():
                if cancelled is not None:
                    cancelled.set()
            self._condition.notify_all()

    def own_child(self, process: OwnedChild) -> None:
        with self._condition:
            self._children[id(process)] = process
        self._reap_children()

    def _reap_children(self) -> None:
        with self._condition:
            children = tuple(self._children.items())
        for key, child in children:
            try:
                exited = type(child.poll()) is int
            except Exception:
                exited = False  # Uncertain ownership must retain the guard.
            if exited:
                with self._condition:
                    self._children.pop(key, None)
                    self._condition.notify_all()

    def wait_idle(self, timeout: float | None) -> bool:
        """None explicitly waits until all protected workers/children finish."""
        if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
            raise ValueError("shutdown wait must be finite and nonnegative")
        deadline = None if timeout is None else monotonic() + timeout
        while True:
            self._reap_children()
            with self._condition:
                if not self._workers and not self._children:
                    return True
                remaining = None if deadline is None else deadline - monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                # Condition.wait releases the lock required by finishing workers.
                self._condition.wait(0.05 if remaining is None else min(0.05, remaining))


def protected_operations(request: Request) -> ProtectedOperations:
    operations = getattr(request.app.state, "protected_operations", None)
    if not isinstance(operations, ProtectedOperations):
        raise HTTPException(status_code=503, detail="PROTECTED_OPERATIONS_UNAVAILABLE")
    return operations


def own_child(process: OwnedChild) -> None:
    operations = _current.get()
    if operations is not None:
        operations.own_child(process)
