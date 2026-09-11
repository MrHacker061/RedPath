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

router = APIRouter(prefix="/api/v1", tags=["setup"])
COMPONENTS = ("ollama", "model", "wsl", "kali")
ComponentName = Literal["ollama", "model", "wsl", "kali"]


def _failed(component: str, code: str = "SETUP_OPERATION_FAILED") -> SetupStage:
    return SetupStage(component, "failed", code, "The setup operation could not be completed.")


def _as_status(component: str, stage: object) -> SetupComponentStatus:
    if not isinstance(stage, SetupStage):
        stage = _failed(component, "SETUP_STATUS_UNAVAILABLE")
    return SetupComponentStatus(status=stage.status, code=stage.code, detail=stage.detail)


def _component_stages(request: Request) -> dict[ComponentName, SetupComponentStatus]:
    ollama = getattr(request.app.state, "ollama_setup", None)
    wsl = getattr(request.app.state, "wsl_setup", None)
    try:
        ollama_stage = ollama.inspect()
    except Exception:
        ollama_stage = _failed("ollama", "OLLAMA_STATUS_UNAVAILABLE")
    try:
        wsl_stage = wsl.inspect()
    except Exception:
        wsl_stage = _failed("wsl", "WSL_STATUS_UNAVAILABLE")
    return {
        "ollama": _as_status("ollama", ollama_stage),
        "model": _as_status("model", ollama_stage),
        "wsl": _as_status("wsl", wsl_stage),
        "kali": _as_status("kali", wsl_stage),
    }


def _component_or_404(component: str) -> ComponentName:
    if component not in COMPONENTS:
        raise HTTPException(status_code=404, detail="Unknown setup component")
    return component  # type: ignore[return-value]


def _cancellations(request: Request) -> dict[ComponentName, Event]:
    events = getattr(request.app.state, "setup_cancellations", None)
    if not isinstance(events, dict) or set(events) != set(COMPONENTS):
        raise HTTPException(status_code=503, detail="Setup controls are unavailable")
    if not all(isinstance(event, Event) for event in events.values()):
        raise HTTPException(status_code=503, detail="Setup controls are unavailable")
    return events


def _progress(_completed: int, _total: int | None) -> None:
    """The synchronous MVP has no persisted progress stream yet."""


def _repair(request: Request, component: ComponentName, consent: bool) -> SetupStage:
    lock = getattr(request.app.state, "setup_lock", None)
    if lock is None or not hasattr(lock, "acquire") or not hasattr(lock, "release"):
        raise HTTPException(status_code=503, detail="Setup controls are unavailable")
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Another setup operation is in progress")
    try:
        cancelled = _cancellations(request)[component]
        cancelled.clear()
        if component == "ollama":
            return request.app.state.ollama_setup.install(consent, _progress, cancelled)
        if component == "model":
            return request.app.state.ollama_setup.pull_model(consent, _progress, cancelled)
        if component == "wsl":
            return request.app.state.wsl_setup.enable(consent)
        return request.app.state.wsl_setup.install_kali(consent, _progress, cancelled)
    except Exception:
        return _failed(component)
    finally:
        lock.release()


@router.get("/setup", response_model=SetupResponse)
def get_setup(request: Request) -> SetupResponse:
    return SetupResponse(components=_component_stages(request))


@router.get("/diagnostics", response_model=DiagnosticsResponse)
def diagnostics(request: Request) -> DiagnosticsResponse:
    components = _component_stages(request)
    return DiagnosticsResponse(
        version=__version__,
        components={name: {"status": value.status, "code": value.code} for name, value in components.items()},
        data_path=str(request.app.state.paths.data_dir),
        codes=tuple(value.code for value in components.values()),
    )


@router.post("/setup/{component}/repair", response_model=SetupComponentStatus)
def repair_setup(
    component: str, payload: SetupRepairRequest, request: Request
) -> SetupComponentStatus:
    fixed_component = _component_or_404(component)
    return _as_status(fixed_component, _repair(request, fixed_component, payload.consent))


@router.post("/setup/{component}/cancel", response_model=SetupComponentStatus)
def cancel_setup(
    component: str, request: Request, payload: None = Body(default=None)
) -> SetupComponentStatus:
    del payload
    fixed_component = _component_or_404(component)
    _cancellations(request)[fixed_component].set()
    return SetupComponentStatus(
        status="in_progress", code="CANCEL_REQUESTED", detail="Cancellation was requested."
    )
