"""Bounded, consent-gated setup routes for RedPath's fixed local components."""

from __future__ import annotations

from threading import Event, Lock
from typing import Literal

from fastapi import APIRouter, Body, HTTPException, Request

from redpath import __version__
from redpath.contracts import (
    DiagnosticsResponse,
    SetupComponentStatus,
    SetupRepairRequest,
    SetupResponse,
)
from redpath_setup.state import SetupStage
from redpath.operations import protected_operations

router = APIRouter(prefix="/api/v1", tags=["setup"])
COMPONENTS = ("ollama", "model", "wsl", "kali")
ComponentName = Literal["ollama", "model", "wsl", "kali"]
_DIAGNOSTIC_CODES = frozenset({
    "OLLAMA_READY", "MODEL_READY", "MODEL_MISSING", "OLLAMA_UNAVAILABLE",
    "WSL_READY", "WSL2_REQUIRED", "WSL_UNAVAILABLE", "KALI_WSL_REQUIRED",
    "KALI_NOT_INSTALLED", "KALI_IDENTITY_MISMATCH", "KALI_MARKER_CHECK_FAILED",
    "KALI_READY", "OLLAMA_STATUS_UNAVAILABLE", "WSL_STATUS_UNAVAILABLE",
    "SETUP_STATUS_UNAVAILABLE",
})


class SetupOperationController:
    """Own one active setup event so cancellation cannot leak into a later repair."""

    def __init__(self) -> None:
        self._operation_lock = Lock()
        self._state_lock = Lock()
        self._active: tuple[ComponentName, Event] | None = None

    def begin(self, component: ComponentName, cancelled: Event | None = None) -> Event | None:
        if not self._operation_lock.acquire(blocking=False):
            return None
        event = cancelled if cancelled is not None else Event()
        with self._state_lock:
            self._active = (component, event)
        return event

    def complete(self, component: ComponentName, event: Event) -> bool:
        """Atomically finish an operation and report whether its cancel won.

        Cancellation and completion share ``_state_lock`` so a successful
        cancel request is always reflected in the repair response for that
        exact event.  Clearing the active event before releasing the operation
        lock also prevents a later cancel request from being attributed to the
        completed repair.
        """
        with self._state_lock:
            if self._active != (component, event):
                return event.is_set()
            cancelled = event.is_set()
            self._active = None
            self._operation_lock.release()
            return cancelled

    def finish(self, component: ComponentName, event: Event) -> None:
        """Compatibility helper for callers that do not need cancel outcome."""
        self.complete(component, event)

    def cancel(self, component: ComponentName) -> bool:
        with self._state_lock:
            if self._active is None or self._active[0] != component:
                return False
            self._active[1].set()
            return True


def _failed(component: str, code: str = "SETUP_OPERATION_FAILED") -> SetupStage:
    return SetupStage(component, "failed", code, "The setup operation could not be completed.")


def _cancelled(component: ComponentName) -> SetupStage:
    return SetupStage(component, "needs_attention", "CANCELLED", "The setup operation was cancelled.")


def _as_status(component: str, stage: object) -> SetupComponentStatus:
    if not isinstance(stage, SetupStage):
        stage = _failed(component, "SETUP_STATUS_UNAVAILABLE")
    return SetupComponentStatus(status=stage.status, code=stage.code, detail=stage.detail)


def _component_stages(request: Request) -> dict[ComponentName, SetupComponentStatus]:
    ollama = getattr(request.app.state, "ollama_setup", None)
    wsl = getattr(request.app.state, "wsl_setup", None)
    try:
        ollama_stage = ollama.inspect_service()
    except Exception:
        ollama_stage = _failed("ollama", "OLLAMA_STATUS_UNAVAILABLE")
    try:
        model_stage = ollama.inspect_model()
    except Exception:
        model_stage = _failed("model", "OLLAMA_STATUS_UNAVAILABLE")
    try:
        wsl_stage = wsl.inspect_wsl()
    except Exception:
        wsl_stage = _failed("wsl", "WSL_STATUS_UNAVAILABLE")
    try:
        kali_stage = wsl.inspect_kali()
    except Exception:
        kali_stage = _failed("kali", "WSL_STATUS_UNAVAILABLE")
    return {
        "ollama": _as_status("ollama", ollama_stage),
        "model": _as_status("model", model_stage),
        "wsl": _as_status("wsl", wsl_stage),
        "kali": _as_status("kali", kali_stage),
    }


def _component_or_404(component: str) -> ComponentName:
    if component not in COMPONENTS:
        raise HTTPException(status_code=404, detail="Unknown setup component")
    return component  # type: ignore[return-value]


def _operations(request: Request) -> SetupOperationController:
    operations = getattr(request.app.state, "setup_operations", None)
    if not isinstance(operations, SetupOperationController):
        raise HTTPException(status_code=503, detail="Setup controls are unavailable")
    return operations


def _progress(_completed: int, _total: int | None) -> None:
    """The synchronous MVP has no persisted progress stream yet."""


def _repair(request: Request, component: ComponentName, consent: bool, cancellation: Event) -> SetupStage:
    operations = _operations(request)
    cancelled = operations.begin(component, cancellation)
    if cancelled is None:
        raise HTTPException(status_code=409, detail="Another setup operation is in progress")
    try:
        if component == "ollama":
            stage = request.app.state.ollama_setup.install(consent, _progress, cancelled)
        elif component == "model":
            stage = request.app.state.ollama_setup.pull_model(consent, _progress, cancelled)
        elif component == "wsl":
            stage = request.app.state.wsl_setup.enable(consent, cancelled)
        else:
            stage = request.app.state.wsl_setup.install_kali(consent, _progress, cancelled)
    except Exception:
        stage = _failed(component)
    finally:
        cancellation_won = operations.complete(component, cancelled)
    if cancellation_won and stage.status == "ready":
        return _cancelled(component)
    return stage


@router.get("/setup", response_model=SetupResponse)
def get_setup(request: Request) -> SetupResponse:
    with protected_operations(request).operation():
        return SetupResponse(components=_component_stages(request))


@router.get("/diagnostics", response_model=DiagnosticsResponse)
def diagnostics(request: Request) -> DiagnosticsResponse:
    with protected_operations(request).operation():
        components = _component_stages(request)
    return DiagnosticsResponse(
        version=__version__,
        components={
            name: {"status": value.status, "code": value.code if value.code in _DIAGNOSTIC_CODES else "COMPONENT_STATUS_UNAVAILABLE"}
            for name, value in components.items()
        },
        data_path=str(request.app.state.paths.data_dir),
        codes=tuple(value.code if value.code in _DIAGNOSTIC_CODES else "COMPONENT_STATUS_UNAVAILABLE" for value in components.values()),
    )


@router.post("/setup/{component}/repair", response_model=SetupComponentStatus)
def repair_setup(
    component: str, payload: SetupRepairRequest, request: Request
) -> SetupComponentStatus:
    fixed_component = _component_or_404(component)
    with protected_operations(request).operation(cancellable=True) as cancelled:
        return _as_status(fixed_component, _repair(request, fixed_component, payload.consent, cancelled))


@router.post("/setup/{component}/cancel", response_model=SetupComponentStatus)
def cancel_setup(
    component: str, request: Request, payload: None = Body(default=None)
) -> SetupComponentStatus:
    del payload
    fixed_component = _component_or_404(component)
    if not _operations(request).cancel(fixed_component):
        return SetupComponentStatus(
            status="needs_attention", code="NO_ACTIVE_OPERATION", detail="No matching setup operation is active."
        )
    return SetupComponentStatus(
        status="in_progress", code="CANCEL_REQUESTED", detail="Cancellation was requested."
    )
