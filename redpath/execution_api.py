"""Guarded execution of already-approved fixed Kali actions."""
import json
import logging
from typing import Any, NoReturn

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from redpath.action_registry import (
    ValidatedProposal,
    revalidate_approval_before_execution,
)
from redpath.approval_api import (
    _begin_state_change,
    _decision_context,
    _now,
    emergency_stop_active,
)
from redpath.contracts import ActionResultContract
from redpath.models import (
    Action,
    ActionResult as StoredActionResult,
    Approval,
    AuthorizedTarget,
    PolicyDecision,
)
from redpath.session_api import audit, get_db
from redpath_kali import ActionResult as KaliActionResult
from redpath_kali import ActionStatus

router = APIRouter(prefix="/api/v1", tags=["actions"])
MAX_EVIDENCE_TEXT_CHARS = 4_096
MAX_PERSISTED_EVIDENCE_CHARS = 16_384
PARSERS = {
    "check_tcp_connection": "tcp_connection_v1",
    "inspect_http_headers": "http_headers_v1",
    "inspect_tls_certificate": "tls_certificate_v1",
}
STATUS_MAP = {
    ActionStatus.SUCCEEDED: "completed",
    ActionStatus.FAILED: "failed",
    ActionStatus.TIMED_OUT: "timed_out",
}
_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
})


def _redacted_bounded_text(value: str) -> tuple[str, bool]:
    lines: list[str] = []
    for line in value.splitlines(keepends=True):
        name, separator, _ = line.partition(":")
        if separator and name.strip().lower() in _SENSITIVE_HEADERS:
            ending = "\n" if line.endswith("\n") else ""
            lines.append(f"{name}: [redacted]{ending}")
        else:
            lines.append(line)
    text = "".join(lines)
    if len(text) <= MAX_EVIDENCE_TEXT_CHARS:
        return text, False
    return text[:MAX_EVIDENCE_TEXT_CHARS] + "\n[output truncated by backend]", True


def _evidence(result: KaliActionResult) -> list[dict[str, Any]]:
    stdout, stdout_truncated = _redacted_bounded_text(result.stdout)
    stderr, stderr_truncated = _redacted_bounded_text(result.stderr)
    error, error_truncated = _redacted_bounded_text(result.error or "")
    evidence: list[dict[str, Any]] = [{
        "kind": "execution",
        "action_name": result.action_name,
        "target_id": result.target_id,
        "target_address": result.target_address,
        "port": result.port,
        "output_truncated": (
            result.output_truncated
            or stdout_truncated
            or stderr_truncated
            or error_truncated
        ),
    }]
    if stdout:
        evidence.append({"kind": "stdout", "text": stdout})
    if stderr:
        evidence.append({"kind": "stderr", "text": stderr})
    if error:
        evidence.append({"kind": "error", "text": error})
    serialized = json.dumps(
        evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    if len(serialized) > MAX_PERSISTED_EVIDENCE_CHARS:
        raise ValueError("bounded action evidence exceeded its persistence limit")
    return evidence


def _latest_policy(db: Session, proposal_id: str) -> PolicyDecision | None:
    return db.scalar(
        select(PolicyDecision)
        .where(PolicyDecision.proposal_id == proposal_id)
        .order_by(PolicyDecision.created_at.desc(), PolicyDecision.id.desc())
    )


def _revalidate_claimed_action(
    db: Session,
    *,
    action_id: str,
    approval_id: str,
    session_id: str,
    proposal_id: str,
) -> tuple[Action, AuthorizedTarget, ValidatedProposal]:
    item, target, proposal, validated = _decision_context(
        db, session_id, proposal_id
    )
    action = db.get(Action, action_id)
    approval = db.scalar(
        select(Approval).where(
            Approval.id == approval_id,
            Approval.session_id == item.id,
            Approval.proposal_id == proposal.id,
            Approval.target_id == target.id,
        )
    )
    policy = _latest_policy(db, proposal.id)
    if (
        action is None
        or approval is None
        or action.session_id != item.id
        or action.proposal_id != proposal.id
        or action.approval_id != approval.id
        or action.status != "running"
        or action.name != validated.action_name
        or json.loads(action.arguments_json) != validated.arguments
        or approval.used_at is None
        or policy is None
        or not policy.allowed
    ):
        raise ValueError("claimed action authorization changed")
    revalidate_approval_before_execution(
        validated,
        session_id=item.id,
        target_id=target.id,
        proposal_id=proposal.id,
        approved_protected_hash=approval.protected_hash,
        approval_status=approval.status,
        approval_expires_at=approval.expires_at,
        # The exact action/approval claim above owns this use marker.
        approval_used_at=None,
        emergency_stop_active=emergency_stop_active(db),
    )
    return action, target, validated


def _deny(
    db: Session,
    *,
    session_id: str,
    proposal_id: str,
    code: str,
    detail: str,
) -> NoReturn:
    audit(
        db,
        session_id,
        "action.denied",
        proposal_id=proposal_id,
        code=code,
    )
    db.commit()
    raise HTTPException(status_code=409, detail=detail)


def _persist_result(
    db: Session,
    action: Action,
    *,
    status: str,
    exit_code: int | None,
    parser: str,
    evidence: list[dict[str, Any]],
    cleanup_status: str,
) -> ActionResultContract:
    action.status = status
    stored = StoredActionResult(
        action_id=action.id,
        status=status,
        exit_code=exit_code,
        parser=parser,
        evidence_json=json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ),
        cleanup_status=cleanup_status,
    )
    db.add(stored)
    audit(
        db,
        action.session_id,
        f"action.{status}",
        action_id=action.id,
        proposal_id=action.proposal_id,
        status=status,
        exit_code=exit_code,
        cleanup_status=cleanup_status,
    )
    db.commit()
    return ActionResultContract(
        action_id=action.id,
        status=status,
        exit_code=exit_code,
        parser=parser,
        evidence=evidence,
        cleanup_status=cleanup_status,
    )


def _persist_dispatch_failure(db: Session, action: Action) -> NoReturn:
    _persist_result(
        db,
        action,
        status="failed",
        exit_code=None,
        parser=PARSERS[action.name],
        evidence=[],
        cleanup_status="not_required",
    )
    raise HTTPException(status_code=503, detail="Kali action dispatch failed")


def _valid_dispatch_result(result: object) -> bool:
    return (
        isinstance(result, KaliActionResult)
        and isinstance(result.status, ActionStatus)
        and result.status in STATUS_MAP
        and (result.exit_code is None or type(result.exit_code) is int)
        and type(result.stdout) is str
        and type(result.stderr) is str
        and type(result.output_truncated) is bool
        and (result.error is None or type(result.error) is str)
    )


@router.post(
    "/sessions/{session_id}/proposals/{proposal_id}/run",
    response_model=ActionResultContract,
)
def run_approved_action(
    session_id: str,
    proposal_id: str,
    request: Request,
    payload: None = Body(default=None),
    db: Session = Depends(get_db),
) -> ActionResultContract:
    del payload
    _begin_state_change(db)
    item, target, proposal, validated = _decision_context(db, session_id, proposal_id)
    approval = db.scalar(
        select(Approval).where(
            Approval.session_id == item.id,
            Approval.proposal_id == proposal.id,
            Approval.target_id == target.id,
        )
    )
    if approval is None:
        _deny(
            db,
            session_id=item.id,
            proposal_id=proposal.id,
            code="APPROVAL_REQUIRED",
            detail="An unused approval is required",
        )
    if db.scalar(
        select(Action).where(
            or_(
                Action.proposal_id == proposal.id,
                Action.approval_id == approval.id,
            )
        )
    ) is not None:
        _deny(
            db,
            session_id=item.id,
            proposal_id=proposal.id,
            code="APPROVAL_ALREADY_CLAIMED",
            detail="Approval was already claimed",
        )
    policy = _latest_policy(db, proposal.id)
    if policy is None or not policy.allowed:
        _deny(
            db,
            session_id=item.id,
            proposal_id=proposal.id,
            code="POLICY_NOT_ALLOWED",
            detail="Policy no longer allows this proposal",
        )
    try:
        revalidate_approval_before_execution(
            validated,
            session_id=item.id,
            target_id=target.id,
            proposal_id=proposal.id,
            approved_protected_hash=approval.protected_hash,
            approval_status=approval.status,
            approval_expires_at=approval.expires_at,
            approval_used_at=approval.used_at,
            emergency_stop_active=emergency_stop_active(db),
        )
    except (TypeError, ValueError, ValidationError):
        _deny(
            db,
            session_id=item.id,
            proposal_id=proposal.id,
            code="APPROVAL_REVALIDATION_FAILED",
            detail="Approval is not valid for execution",
        )

    action = Action(
        session_id=item.id,
        proposal_id=proposal.id,
        approval_id=approval.id,
        name=validated.action_name,
        arguments_json=json.dumps(
            validated.arguments, sort_keys=True, separators=(",", ":")
        ),
        status="running",
    )
    approval.used_at = _now()
    db.add(action)
    audit(
        db,
        item.id,
        "action.started",
        action_id=action.id,
        proposal_id=proposal.id,
        approval_id=approval.id,
        target_id=target.id,
        status="running",
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Approval was already claimed") from exc

    action_id = action.id
    approval_id = approval.id
    db.expire_all()
    _begin_state_change(db)
    try:
        action, target, validated = _revalidate_claimed_action(
            db,
            action_id=action_id,
            approval_id=approval_id,
            session_id=session_id,
            proposal_id=proposal_id,
        )
    except (
        HTTPException,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        ValidationError,
    ):
        action = db.get(Action, action_id)
        if action is None:
            raise HTTPException(
                status_code=409, detail="Authorization changed before dispatch"
            ) from None
        _persist_result(
            db,
            action,
            status="cancelled",
            exit_code=None,
            parser=PARSERS[action.name],
            evidence=[],
            cleanup_status="not_required",
        )
        raise HTTPException(
            status_code=409, detail="Authorization changed before dispatch"
        ) from None

    dispatcher = getattr(request.app.state, "action_dispatcher", None)
    if dispatcher is None:
        _persist_result(
            db,
            action,
            status="failed",
            exit_code=None,
            parser=PARSERS[action.name],
            evidence=[],
            cleanup_status="not_required",
        )
        raise HTTPException(status_code=503, detail="Kali action dispatcher is unavailable")
    try:
        result = dispatcher.dispatch(
            action.name,
            json.loads(action.arguments_json),
            authorized_target_id=target.id,
            authorized_target_address=target.address,
        )
    except Exception:
        logging.getLogger(__name__).error("Fixed Kali action dispatch failed")
        _persist_dispatch_failure(db, action)

    if not _valid_dispatch_result(result):
        _persist_dispatch_failure(db, action)
    assert isinstance(result, KaliActionResult)
    expected_scope = (
        action.name,
        target.id,
        target.address,
        validated.arguments["port"],
    )
    actual_scope = (
        result.action_name,
        result.target_id,
        result.target_address,
        result.port,
    )
    if actual_scope != expected_scope:
        _persist_dispatch_failure(db, action)

    terminal_status = STATUS_MAP[result.status]
    return _persist_result(
        db,
        action,
        status=terminal_status,
        exit_code=result.exit_code,
        parser=PARSERS[action.name],
        evidence=_evidence(result),
        cleanup_status="completed",
    )
