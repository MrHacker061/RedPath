"""Emergency-stop persistence synchronized with the local execution fence."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from redpath.contracts import EmergencyStopContract
from redpath.execution_fence import ExecutionFence
from redpath.models import EmergencyStop
from redpath.session_api import audit, get_db, utc

router = APIRouter(prefix="/api/v1", tags=["approvals"])
EMERGENCY_STOP_ID = "local-redpath-service"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def emergency_stop_active(db: Session) -> bool:
    state = db.get(EmergencyStop, EMERGENCY_STOP_ID)
    return bool(state and state.active)


def _stop_contract(state: EmergencyStop | None) -> EmergencyStopContract:
    return EmergencyStopContract(
        active=bool(state and state.active),
        activated_at=utc(state.activated_at) if state and state.activated_at else None,
        cleared_at=utc(state.cleared_at) if state and state.cleared_at else None,
    )


def _execution_fence(request: Request) -> ExecutionFence:
    fence = getattr(request.app.state, "execution_fence", None)
    if not isinstance(fence, ExecutionFence):
        raise HTTPException(status_code=503, detail="Execution fence is unavailable")
    return fence


def _begin_state_change(db: Session) -> None:
    """Serialize short SQLite state transitions; never surround a dispatch."""

    db.execute(text("BEGIN IMMEDIATE"))


@router.get("/emergency-stop", response_model=EmergencyStopContract)
def get_emergency_stop(db: Session = Depends(get_db)) -> EmergencyStopContract:
    return _stop_contract(db.get(EmergencyStop, EMERGENCY_STOP_ID))


@router.post("/emergency-stop", response_model=EmergencyStopContract)
def activate_emergency_stop(
    request: Request, db: Session = Depends(get_db)
) -> EmergencyStopContract:
    def persist() -> EmergencyStopContract:
        _begin_state_change(db)
        state = db.get(EmergencyStop, EMERGENCY_STOP_ID)
        if state is None:
            state = EmergencyStop(id=EMERGENCY_STOP_ID)
            db.add(state)
        if not state.active:
            state.active = True
            state.activated_at = _now()
            state.cleared_at = None
            audit(db, None, "emergency_stop.activated")
            db.commit()
            db.refresh(state)
        else:
            db.rollback()
        return _stop_contract(state)

    return _execution_fence(request).activate(persist)


@router.post("/emergency-stop/clear", response_model=EmergencyStopContract)
def clear_emergency_stop(
    request: Request, db: Session = Depends(get_db)
) -> EmergencyStopContract:
    def persist() -> EmergencyStopContract:
        _begin_state_change(db)
        state = db.get(EmergencyStop, EMERGENCY_STOP_ID)
        if state is None:
            state = EmergencyStop(id=EMERGENCY_STOP_ID, active=False)
            db.add(state)
        if state.active or state.cleared_at is None:
            state.active = False
            state.cleared_at = _now()
            audit(db, None, "emergency_stop.cleared")
            db.commit()
            db.refresh(state)
        else:
            db.rollback()
        return _stop_contract(state)

    return _execution_fence(request).clear(persist)
