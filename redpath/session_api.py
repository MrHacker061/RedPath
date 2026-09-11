import hashlib
import ipaddress
import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from redpath.action_registry import (
    RECOMMENDATION_ACTIONS,
    ValidatedProposal,
    validate_untrusted_proposal,
)
from redpath.contracts import (
    AIProposal,
    AuthorizedTargetContract,
    AuthorizedTargetCreate,
    LessonSourceContract,
    LessonSourceCreate,
    NormalizedFinding,
    RecommendationPolicyDecisionContract,
    RecommendationProposalContract,
    RecommendationResponse,
    ScanImportContract,
    ScanImportRequest,
    ScanImportResponse,
    SessionCreate,
    SessionDetail,
    SessionState,
    SessionSummary,
)
from redpath.models import (
    AuditEvent,
    AuthorizedTarget,
    Finding,
    LabSession,
    LessonSource,
    PolicyDecision,
    Proposal,
    ScanImport,
)
from redpath_ai import LearningResponse, RuleBasedProvider, explain_findings
from redpath_ai.schemas import EvidenceState as AIEvidenceState, Finding as AIFinding
from redpath_ai.schemas import ProposedStep, RecommendationContext

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])
Parser = Callable[[str, str, str, str, str], list[dict[str, Any]]]
POLICY_VALIDATED_REQUIRES_APPROVAL = "POLICY_VALIDATED_REQUIRES_APPROVAL"
PROVIDER_OUTPUT_REJECTED = "PROVIDER_OUTPUT_REJECTED"
NO_SAFE_ACTION_RECOMMENDATION = "NO_SAFE_ACTION_RECOMMENDATION"
ACTIVE_AUTHORIZED_TARGET_REQUIRED = "ACTIVE_AUTHORIZED_TARGET_REQUIRED"


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        yield db


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def active_session(db: Session, session_id: str) -> LabSession:
    item = db.get(LabSession, session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if item.state in {SessionState.COMPLETED.value, SessionState.EXPIRED.value, SessionState.BLOCKED.value}:
        raise HTTPException(status_code=409, detail="Session is not active")
    if item.expires_at is None or utc(item.expires_at) <= datetime.now(timezone.utc):
        item.state = SessionState.EXPIRED.value
        audit(db, item.id, "session.expired")
        db.commit()
        raise HTTPException(status_code=409, detail="Session has expired")
    return item


def refresh_expiration(db: Session, item: LabSession) -> None:
    if item.state not in {SessionState.COMPLETED.value, SessionState.EXPIRED.value} and item.expires_at is not None and utc(item.expires_at) <= datetime.now(timezone.utc):
        item.state = SessionState.EXPIRED.value
        audit(db, item.id, "session.expired")
        db.commit()


def audit(db: Session, session_id: str | None, event_type: str, **details: Any) -> None:
    db.add(AuditEvent(session_id=session_id, event_type=event_type, safe_details_json=json.dumps(details, sort_keys=True)))


def session_summary(item: LabSession) -> SessionSummary:
    return SessionSummary.model_validate({
        "id": item.id, "state": item.state, "authorization_confirmed": item.authorization_confirmed,
        "expires_at": item.expires_at, "created_at": item.created_at,
    })


def session_detail(db: Session, item: LabSession) -> SessionDetail:
    lesson = db.scalar(select(LessonSource).where(LessonSource.session_id == item.id))
    target = db.scalar(select(AuthorizedTarget).where(AuthorizedTarget.session_id == item.id))
    return SessionDetail(**session_summary(item).model_dump(), lesson_source=(LessonSourceContract(id=lesson.id, url=lesson.url, title=lesson.title) if lesson else None), target=(AuthorizedTargetContract(id=target.id, address=target.address, authorization_source=target.authorization_source, expires_at=target.expires_at, locked=target.locked) if target else None))


def validate_private_target(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Target must be a private IP address literal") from exc
    private_ranges = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("fc00::/7"),
    )
    if not any(address in network for network in private_ranges) or address.is_link_local or address.is_multicast or address.is_unspecified:
        raise HTTPException(status_code=422, detail="Target must be a private, non-special-use IP address")
    return address.compressed


@router.post("", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> SessionSummary:
    if utc(payload.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Session expiration must be in the future")
    state = SessionState.AUTHORIZED.value if payload.authorization_confirmed else SessionState.DRAFT.value
    item = LabSession(state=state, authorization_confirmed=payload.authorization_confirmed, starts_at=datetime.now(timezone.utc), expires_at=utc(payload.expires_at))
    db.add(item)
    db.flush()
    audit(db, item.id, "session.created", authorization_confirmed=item.authorization_confirmed)
    db.commit()
    db.refresh(item)
    return session_summary(item)


@router.get("", response_model=list[SessionSummary])
def list_sessions(db: Session = Depends(get_db)) -> list[SessionSummary]:
    items = db.scalars(select(LabSession).order_by(LabSession.created_at.desc())).all()
    for item in items:
        refresh_expiration(db, item)
    return [session_summary(item) for item in items]


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, db: Session = Depends(get_db)) -> SessionDetail:
    item = db.get(LabSession, session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    refresh_expiration(db, item)
    return session_detail(db, item)


@router.post("/{session_id}/close", response_model=SessionDetail)
def close_session(session_id: str, db: Session = Depends(get_db)) -> SessionDetail:
    item = active_session(db, session_id)
    item.state = SessionState.COMPLETED.value
    target = db.scalar(select(AuthorizedTarget).where(AuthorizedTarget.session_id == item.id))
    if target:
        target.locked = True
    audit(db, item.id, "session.closed")
    db.commit()
    return session_detail(db, item)


@router.post("/{session_id}/lesson-source", response_model=LessonSourceContract, status_code=201)
def add_lesson_source(session_id: str, payload: LessonSourceCreate, db: Session = Depends(get_db)) -> LessonSourceContract:
    item = active_session(db, session_id)
    parsed = urlparse(payload.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Lesson source must be an HTTP or HTTPS URL")
    lesson = LessonSource(session_id=item.id, url=payload.url, title=payload.title)
    db.add(lesson)
    audit(db, item.id, "lesson_source.registered")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Session already has a lesson source") from exc
    return LessonSourceContract(id=lesson.id, url=lesson.url, title=lesson.title)


@router.post("/{session_id}/target", response_model=AuthorizedTargetContract, status_code=201)
def add_target(session_id: str, payload: AuthorizedTargetCreate, db: Session = Depends(get_db)) -> AuthorizedTargetContract:
    item = active_session(db, session_id)
    if not item.authorization_confirmed:
        raise HTTPException(status_code=409, detail="Authorization must be confirmed before adding a target")
    target_expires = utc(payload.expires_at)
    if target_expires <= datetime.now(timezone.utc) or target_expires > utc(item.expires_at):
        raise HTTPException(status_code=422, detail="Target expiration must be active and within the session")
    target = AuthorizedTarget(session_id=item.id, address=validate_private_target(payload.address), authorization_source=payload.authorization_source, expires_at=target_expires)
    db.add(target)
    item.state = SessionState.READY.value
    db.flush()
    audit(db, item.id, "target.registered", target_id=target.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Session already has a target") from exc
    return AuthorizedTargetContract(id=target.id, address=target.address, authorization_source=target.authorization_source, expires_at=target.expires_at, locked=target.locked)


@router.post("/{session_id}/scan-import", response_model=ScanImportResponse, status_code=201)
def import_scan(session_id: str, payload: ScanImportRequest, request: Request, db: Session = Depends(get_db)) -> ScanImportResponse:
    item = active_session(db, session_id)
    target = db.scalar(select(AuthorizedTarget).where(AuthorizedTarget.session_id == item.id))
    if not item.authorization_confirmed or target is None or target.locked or utc(target.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="An active authorized target is required")
    parser: Parser | None = getattr(request.app.state, "nmap_parser", None)
    if parser is None:
        raise HTTPException(status_code=503, detail="Nmap XML parser is not configured")
    digest = hashlib.sha256(payload.xml_text.encode("utf-8")).hexdigest()
    imported = ScanImport(session_id=item.id, source_type="nmap_xml", content_hash=digest)
    db.add(imported)
    db.flush()
    try:
        parsed = parser(payload.xml_text, item.id, target.id, imported.id, target.address)
        normalized = []
        for value in parsed:
            finding = NormalizedFinding.model_validate(value)
            normalized.append(finding.model_copy(update={"id": str(uuid.uuid5(uuid.UUID(imported.id), finding.id))}))
        if any(finding.session_id != item.id or finding.target_id != target.id for finding in normalized):
            raise ValueError("Parser returned findings outside the import scope")
    except (ValueError, TypeError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="Nmap XML could not be parsed safely") from exc
    for finding in normalized:
        data = finding.model_dump()
        db.add(Finding(id=data["id"], session_id=item.id, target_id=target.id, scan_import_id=imported.id, evidence_ref=data["evidence_source"], state=data["state"].value, category=data["category"], protocol=data["protocol"], port=data["port"], service_hint=data["service_hint"]))
    audit(db, item.id, "scan_import.created", scan_import_id=imported.id, finding_count=len(normalized), content_hash=digest)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="Nmap XML produced conflicting findings") from exc
    return ScanImportResponse(scan_import=ScanImportContract(id=imported.id, source_type=imported.source_type, content_hash=imported.content_hash, created_at=imported.created_at), findings=normalized)


@router.get("/{session_id}/explanation", response_model=LearningResponse)
def explain_session_findings(session_id: str, db: Session = Depends(get_db)) -> LearningResponse:
    item = active_session(db, session_id)
    stored = db.scalars(select(Finding).where(Finding.session_id == item.id).order_by(Finding.created_at, Finding.id)).all()
    findings = [AIFinding(
        id=value.id, session_id=value.session_id, target_id=value.target_id,
        state=AIEvidenceState(value.state), category=value.category, protocol=value.protocol,
        port=value.port, service_hint=value.service_hint,
        evidence_source=value.evidence_ref,
    ) for value in stored]
    response = explain_findings(findings)
    audit(db, item.id, "learning.explanation.generated", finding_count=len(findings), source_ids=sorted({source for explanation in response.explanations for source in explanation.source_ids}))
    db.commit()
    return response


def recommendation_context(
    item: LabSession,
    target: AuthorizedTarget,
    findings: list[Finding],
) -> RecommendationContext:
    return RecommendationContext(
        session_id=item.id,
        target_id=target.id,
        lesson_objective="Choose a safe, evidence-supported next learning action.",
        findings=tuple(
            AIFinding(
                id=value.id,
                session_id=value.session_id,
                target_id=value.target_id,
                state=AIEvidenceState(value.state),
                category=value.category,
                protocol=value.protocol,
                port=value.port,
                service_hint=value.service_hint,
                evidence_source=value.evidence_ref,
            )
            for value in findings
        ),
        allowed_actions=RECOMMENDATION_ACTIONS,
    )


def validate_provider_recommendation(
    step: Any, context: RecommendationContext
) -> ValidatedProposal:
    untrusted_step = ProposedStep.model_validate(step)
    canonical = untrusted_step.to_canonical_proposal(context)
    wire_proposal = AIProposal.model_validate(canonical.model_dump())
    return validate_untrusted_proposal(
        wire_proposal,
        authorized_target_id=context.target_id,
        available_finding_ids={finding.id for finding in context.findings},
    )


@router.post(
    "/{session_id}/recommendation",
    response_model=RecommendationResponse,
    status_code=status.HTTP_201_CREATED,
)
def recommend_session_action(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    item = active_session(db, session_id)
    target = db.scalar(
        select(AuthorizedTarget).where(AuthorizedTarget.session_id == item.id)
    )
    target_is_private = False
    if target is not None:
        try:
            validate_private_target(target.address)
            target_is_private = True
        except HTTPException:
            pass
    if (
        not item.authorization_confirmed
        or target is None
        or target.locked
        or utc(target.expires_at) <= datetime.now(timezone.utc)
        or not target_is_private
    ):
        audit(
            db,
            item.id,
            "recommendation.rejected",
            code=ACTIVE_AUTHORIZED_TARGET_REQUIRED,
        )
        db.commit()
        raise HTTPException(status_code=409, detail="An active authorized target is required")

    stored = db.scalars(
        select(Finding)
        .where(Finding.session_id == item.id, Finding.target_id == target.id)
        .order_by(Finding.created_at, Finding.id)
    ).all()
    context = recommendation_context(item, target, list(stored))
    provider = request.app.state.llm_provider
    used_fallback = False
    try:
        step = provider.recommend_next_step(context)
        validated = validate_provider_recommendation(step, context)
    except Exception:
        # Provider output is an untrusted boundary. Record only a stable code,
        # then retry through the deterministic local provider.
        used_fallback = True
        audit(
            db,
            item.id,
            "recommendation.provider.fallback",
            code=PROVIDER_OUTPUT_REJECTED,
        )
        try:
            fallback_step = RuleBasedProvider().recommend_next_step(context)
            validated = validate_provider_recommendation(fallback_step, context)
        except Exception:
            # A broken fallback must stop at proposal generation, never advance
            # into persistence or any execution path.
            audit(
                db,
                item.id,
                "recommendation.rejected",
                code=NO_SAFE_ACTION_RECOMMENDATION,
            )
            db.commit()
            raise HTTPException(
                status_code=409,
                detail="No safe action recommendation is available",
            ) from None

    proposal = Proposal(
        session_id=item.id,
        action_name=validated.action_name,
        arguments_json=json.dumps(validated.arguments, sort_keys=True),
        finding_ids_json=json.dumps(list(validated.finding_ids)),
        reason=validated.reason,
        learning_goal=validated.learning_goal,
        requires_approval=True,
    )
    db.add(proposal)
    db.flush()
    explanation = (
        "The proposal is session-bound and allowlisted; explicit approval is still required."
    )
    decision = PolicyDecision(
        proposal_id=proposal.id,
        allowed=True,
        code=POLICY_VALIDATED_REQUIRES_APPROVAL,
        reason=explanation,
    )
    db.add(decision)
    db.flush()
    audit(
        db,
        item.id,
        "recommendation.proposal.created",
        proposal_id=proposal.id,
        policy_decision_id=decision.id,
        policy_code=decision.code,
        used_fallback=used_fallback,
    )
    db.commit()
    return RecommendationResponse(
        proposal=RecommendationProposalContract(
            id=proposal.id,
            session_id=item.id,
            finding_ids=list(validated.finding_ids),
            action_name=validated.action_name,
            arguments=validated.arguments,
            reason=validated.reason,
            learning_goal=validated.learning_goal,
            requires_approval=True,
        ),
        policy_decision=RecommendationPolicyDecisionContract(
            id=decision.id,
            proposal_id=proposal.id,
            allowed=decision.allowed,
            code=decision.code,
            explanation=decision.reason,
        ),
    )
