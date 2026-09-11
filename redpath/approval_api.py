"""Approval, emergency-stop, audit-history, and bounded report APIs."""
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from redpath.action_registry import (
    ValidatedProposal,
    action_protected_hash,
    validate_untrusted_proposal,
)
from redpath.contracts import (
    AIProposal,
    ApprovalDecisionContract,
    AuditEventContract,
    AuditHistoryContract,
    EmergencyStopContract,
    LearningReportContract,
    ReportApprovalContract,
    ReportEvidenceContract,
    ReportProposalContract,
    ReportTargetContract,
)
from redpath.models import (
    Approval,
    AuditEvent,
    AuthorizedTarget,
    EmergencyStop,
    Finding,
    LabSession,
    PolicyDecision,
    Proposal,
    Report,
)
from redpath.session_api import active_session, audit, get_db, utc, validate_private_target

router = APIRouter(prefix="/api/v1", tags=["approvals"])
EMERGENCY_STOP_ID = "local-redpath-service"
APPROVAL_TTL = timedelta(minutes=15)
MAX_REPORT_ITEMS = 100
SAFE_AUDIT_KEYS = frozenset({
    "approval_id",
    "authorization_confirmed",
    "code",
    "content_hash",
    "expires_at",
    "finding_count",
    "policy_code",
    "policy_decision_id",
    "proposal_id",
    "report_id",
    "source_ids",
    "status",
    "target_id",
    "used_fallback",
})
def _now() -> datetime:
    return datetime.now(timezone.utc)


def emergency_stop_active(db: Session) -> bool:
    """Return the local service stop state for approval/action gates."""

    state = db.get(EmergencyStop, EMERGENCY_STOP_ID)
    return bool(state and state.active)
def _stop_contract(state: EmergencyStop | None) -> EmergencyStopContract:
    return EmergencyStopContract(
        active=bool(state and state.active),
        activated_at=utc(state.activated_at) if state and state.activated_at else None,
        cleared_at=utc(state.cleared_at) if state and state.cleared_at else None,
    )


def _begin_state_change(db: Session) -> None:
    """Serialize stop and approval transitions in the local SQLite service."""

    db.execute(text("BEGIN IMMEDIATE"))
@router.get("/emergency-stop", response_model=EmergencyStopContract)
def get_emergency_stop(db: Session = Depends(get_db)) -> EmergencyStopContract:
    return _stop_contract(db.get(EmergencyStop, EMERGENCY_STOP_ID))


@router.post("/emergency-stop", response_model=EmergencyStopContract)
def activate_emergency_stop(db: Session = Depends(get_db)) -> EmergencyStopContract:
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
    return _stop_contract(state)
@router.post("/emergency-stop/clear", response_model=EmergencyStopContract)
def clear_emergency_stop(db: Session = Depends(get_db)) -> EmergencyStopContract:
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
    return _stop_contract(state)


def _proposal_for_session(db: Session, session_id: str, proposal_id: str) -> Proposal:
    proposal = db.scalar(
        select(Proposal).where(
            Proposal.id == proposal_id,
            Proposal.session_id == session_id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal
def _active_target(db: Session, item: LabSession) -> AuthorizedTarget:
    target = db.scalar(
        select(AuthorizedTarget).where(AuthorizedTarget.session_id == item.id)
    )
    if (
        not item.authorization_confirmed
        or target is None
        or target.locked
        or utc(target.expires_at) <= _now()
    ):
        raise HTTPException(status_code=409, detail="An active authorized target is required")
    try:
        validate_private_target(target.address)
    except HTTPException:
        raise HTTPException(
            status_code=409, detail="An active authorized target is required"
        ) from None
    return target


def _validated_stored_proposal(
    db: Session, proposal: Proposal, target: AuthorizedTarget
) -> ValidatedProposal:
    finding_ids = json.loads(proposal.finding_ids_json)
    arguments = json.loads(proposal.arguments_json)
    wire = AIProposal.model_validate({
        "finding_ids": finding_ids,
        "action_name": proposal.action_name,
        "arguments": arguments,
        "reason": proposal.reason,
        "learning_goal": proposal.learning_goal,
        "requires_approval": proposal.requires_approval,
    })
    available = set(db.scalars(
        select(Finding.id).where(
            Finding.session_id == proposal.session_id,
            Finding.target_id == target.id,
        )
    ).all())
    return validate_untrusted_proposal(
        wire,
        authorized_target_id=target.id,
        available_finding_ids=available,
    )


def _decision_context(
    db: Session, session_id: str, proposal_id: str
) -> tuple[LabSession, AuthorizedTarget, Proposal, ValidatedProposal]:
    item = active_session(db, session_id)
    target = _active_target(db, item)
    proposal = _proposal_for_session(db, item.id, proposal_id)
    try:
        validated = _validated_stored_proposal(db, proposal, target)
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
        audit(
            db,
            item.id,
            "approval.denied",
            proposal_id=proposal.id,
            code="PROPOSAL_REVALIDATION_FAILED",
        )
        db.commit()
        raise HTTPException(
            status_code=409, detail="Proposal is not valid for approval"
        ) from None
    return item, target, proposal, validated


def _existing_decision(db: Session, proposal_id: str) -> Approval | None:
    return db.scalar(select(Approval).where(Approval.proposal_id == proposal_id))
def _record_decision(
    db: Session,
    *,
    item: LabSession,
    target: AuthorizedTarget,
    proposal: Proposal,
    validated: ValidatedProposal,
    decision_status: str,
) -> Approval:
    expires_at = min(utc(item.expires_at), utc(target.expires_at), _now() + APPROVAL_TTL)
    protected_hash = action_protected_hash(
        validated,
        session_id=item.id,
        target_id=target.id,
        proposal_id=proposal.id,
    )
    decision = Approval(
        session_id=item.id,
        proposal_id=proposal.id,
        target_id=target.id,
        status=decision_status,
        protected_hash=protected_hash,
        expires_at=expires_at,
    )
    db.add(decision)
    db.flush()
    details: dict[str, Any] = {
        "proposal_id": proposal.id,
        "status": decision_status,
        "expires_at": expires_at.isoformat(),
    }
    if decision_status == "approved":
        details["approval_id"] = decision.id
    audit(db, item.id, f"approval.{decision_status}", **details)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        audit(
            db,
            item.id,
            "approval.duplicate_rejected",
            proposal_id=proposal.id,
            code="PROPOSAL_ALREADY_DECIDED",
        )
        db.commit()
        raise HTTPException(
            status_code=409, detail="Proposal has already been decided"
        ) from exc
    db.refresh(decision)
    return decision


@router.post(
    "/sessions/{session_id}/proposals/{proposal_id}/approve",
    response_model=ApprovalDecisionContract,
)
def approve_proposal(
    session_id: str, proposal_id: str, db: Session = Depends(get_db)
) -> ApprovalDecisionContract:
    _begin_state_change(db)
    item, target, proposal, validated = _decision_context(db, session_id, proposal_id)
    if emergency_stop_active(db):
        audit(
            db,
            item.id,
            "approval.denied",
            proposal_id=proposal.id,
            code="EMERGENCY_STOP_ACTIVE",
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Emergency stop is active")
    if _existing_decision(db, proposal.id) is not None:
        raise HTTPException(status_code=409, detail="Proposal has already been decided")
    policy = db.scalar(
        select(PolicyDecision)
        .where(PolicyDecision.proposal_id == proposal.id)
        .order_by(PolicyDecision.created_at.desc(), PolicyDecision.id.desc())
    )
    if policy is None or not policy.allowed:
        audit(
            db,
            item.id,
            "approval.denied",
            proposal_id=proposal.id,
            code="POLICY_DENIED",
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Policy did not allow this proposal")
    decision = _record_decision(
        db,
        item=item,
        target=target,
        proposal=proposal,
        validated=validated,
        decision_status="approved",
    )
    return ApprovalDecisionContract(
        proposal_id=proposal.id,
        status="approved",
        approval_id=decision.id,
        expires_at=utc(decision.expires_at),
    )


@router.post(
    "/sessions/{session_id}/proposals/{proposal_id}/reject",
    response_model=ApprovalDecisionContract,
)
def reject_proposal(
    session_id: str, proposal_id: str, db: Session = Depends(get_db)
) -> ApprovalDecisionContract:
    _begin_state_change(db)
    item, target, proposal, validated = _decision_context(db, session_id, proposal_id)
    if _existing_decision(db, proposal.id) is not None:
        raise HTTPException(status_code=409, detail="Proposal has already been decided")
    _record_decision(
        db,
        item=item,
        target=target,
        proposal=proposal,
        validated=validated,
        decision_status="rejected",
    )
    return ApprovalDecisionContract(
        proposal_id=proposal.id,
        status="rejected",
        approval_id=None,
        expires_at=None,
    )
def _bounded_audit_value(value: Any) -> str | int | bool | list[str] | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return max(-1_000_000_000, min(value, 1_000_000_000))
    if isinstance(value, str):
        return value[:160]
    if isinstance(value, list):
        return [str(item)[:160] for item in value[:20]]
    return None


def _safe_audit_details(raw: str) -> dict[str, str | int | bool | list[str] | None]:
    try:
        details = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(details, dict):
        return {}
    return {
        key: _bounded_audit_value(value)
        for key, value in details.items()
        if key in SAFE_AUDIT_KEYS
    }


@router.get(
    "/sessions/{session_id}/audit-history", response_model=AuditHistoryContract
)
def get_audit_history(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AuditHistoryContract:
    if db.get(LabSession, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    events = list(db.scalars(
        select(AuditEvent)
        .where(or_(AuditEvent.session_id == session_id, AuditEvent.session_id.is_(None)))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit + 1)
    ).all())
    return AuditHistoryContract(
        events=tuple(
            AuditEventContract(
                id=event.id,
                session_id=event.session_id,
                event_type=event.event_type[:100],
                details=_safe_audit_details(event.safe_details_json),
                created_at=utc(event.created_at),
            )
            for event in events[:limit]
        ),
        truncated=len(events) > limit,
    )


@router.get("/sessions/{session_id}/report", response_model=LearningReportContract)
def get_learning_report(
    session_id: str, db: Session = Depends(get_db)
) -> LearningReportContract:
    item = db.get(LabSession, session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    target = db.scalar(
        select(AuthorizedTarget).where(AuthorizedTarget.session_id == session_id)
    )
    evidence_counts = {
        state: count
        for state, count in db.execute(
            select(Finding.state, func.count(Finding.id))
            .where(Finding.session_id == session_id)
            .group_by(Finding.state)
        ).all()
    }
    proposals = list(db.scalars(
        select(Proposal)
        .where(Proposal.session_id == session_id)
        .order_by(Proposal.created_at, Proposal.id)
        .limit(MAX_REPORT_ITEMS + 1)
    ).all())
    approvals = list(db.scalars(
        select(Approval)
        .where(Approval.session_id == session_id)
        .order_by(Approval.created_at, Approval.id)
        .limit(MAX_REPORT_ITEMS + 1)
    ).all())
    proposal_ids = [proposal.id for proposal in proposals[:MAX_REPORT_ITEMS]]
    policies_by_proposal: dict[str, tuple[bool, str]] = {}
    if proposal_ids:
        ranked_policies = select(
            PolicyDecision.proposal_id.label("proposal_id"),
            PolicyDecision.allowed.label("allowed"),
            PolicyDecision.code.label("code"),
            func.row_number().over(
                partition_by=PolicyDecision.proposal_id,
                order_by=(PolicyDecision.created_at.desc(), PolicyDecision.id.desc()),
            ).label("rank"),
        ).where(PolicyDecision.proposal_id.in_(proposal_ids)).subquery()
        policies_by_proposal = {
            row.proposal_id: (row.allowed, row.code)
            for row in db.execute(
                select(
                    ranked_policies.c.proposal_id,
                    ranked_policies.c.allowed,
                    ranked_policies.c.code,
                ).where(ranked_policies.c.rank == 1)
            )
        }
    report = db.scalar(select(Report).where(Report.session_id == session_id))
    if report is None:
        report = Report(session_id=session_id, content="{}")
        db.add(report)
        db.flush()
    generated_at = _now()
    total_findings = sum(evidence_counts.values())
    contract = LearningReportContract(
        report_id=report.id,
        session_id=item.id,
        session_state=item.state,
        generated_at=generated_at,
        target=(
            ReportTargetContract(
                target_id=target.id,
                expires_at=utc(target.expires_at),
                locked=target.locked,
            )
            if target else None
        ),
        evidence=ReportEvidenceContract(
            total=total_findings,
            observed=evidence_counts.get("observed", 0),
            inferred=evidence_counts.get("inferred", 0),
            verified=evidence_counts.get("verified", 0),
        ),
        proposals=tuple(
            ReportProposalContract(
                proposal_id=proposal.id,
                action_name=proposal.action_name[:100],
                policy_allowed=policies_by_proposal.get(proposal.id, (False, ""))[0],
                policy_code=policies_by_proposal.get(
                    proposal.id, (False, "NO_POLICY_DECISION")
                )[1][:80],
            )
            for proposal in proposals[:MAX_REPORT_ITEMS]
        ),
        approvals=tuple(
            ReportApprovalContract(
                proposal_id=approval.proposal_id,
                status=approval.status,
                expires_at=utc(approval.expires_at) if approval.expires_at else None,
                used=approval.used_at is not None,
            )
            for approval in approvals[:MAX_REPORT_ITEMS]
        ),
        proposals_truncated=len(proposals) > MAX_REPORT_ITEMS,
        approvals_truncated=len(approvals) > MAX_REPORT_ITEMS,
        audit_event_count=db.scalar(
            select(func.count(AuditEvent.id)).where(AuditEvent.session_id == session_id)
        ) or 0,
        execution_authorized=False,
    )
    report.content = contract.model_dump_json()
    report.generated_at = generated_at
    audit(db, item.id, "report.generated", report_id=report.id)
    db.commit()
    return contract
