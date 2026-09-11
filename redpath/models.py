import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from redpath.contracts import EvidenceState, SessionState
from redpath.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class User(Timestamped, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(120))


class LabSession(Timestamped, Base):
    __tablename__ = "lab_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    state: Mapped[str] = mapped_column(String(20), default=SessionState.DRAFT.value)
    authorization_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_status: Mapped[str] = mapped_column(String(20), default="not_started")


class LessonSource(Timestamped, Base):
    __tablename__ = "lesson_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"), unique=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(250))


class AuthorizedTarget(Timestamped, Base):
    __tablename__ = "authorized_targets"
    __table_args__ = (UniqueConstraint("id", "session_id", name="uq_target_session"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"), unique=True)
    address: Mapped[str] = mapped_column(String(255))
    authorization_source: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class ScanImport(Timestamped, Base):
    __tablename__ = "scan_imports"
    __table_args__ = (UniqueConstraint("id", "session_id", name="uq_scan_session"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"))
    source_type: Mapped[str] = mapped_column(String(40))
    content_hash: Mapped[str] = mapped_column(String(64))


class Finding(Timestamped, Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("scan_import_id", "protocol", "port", name="uq_scan_port"),
        ForeignKeyConstraint(
            ["target_id", "session_id"],
            ["authorized_targets.id", "authorized_targets.session_id"],
            name="fk_finding_target_session",
        ),
        ForeignKeyConstraint(
            ["scan_import_id", "session_id"],
            ["scan_imports.id", "scan_imports.session_id"],
            name="fk_finding_scan_session",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"))
    target_id: Mapped[str] = mapped_column(String(36))
    scan_import_id: Mapped[str] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(String(20), default=EvidenceState.OBSERVED.value)
    category: Mapped[str] = mapped_column(String(80))
    protocol: Mapped[str] = mapped_column(String(8))
    port: Mapped[int] = mapped_column(Integer)
    service_hint: Mapped[str | None] = mapped_column(String(100))


class ModelRequest(Timestamped, Base):
    __tablename__ = "model_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"))
    provider: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(120))
    sanitized_context: Mapped[str] = mapped_column(Text)


class ModelResponse(Timestamped, Base):
    __tablename__ = "model_responses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("model_requests.id"), unique=True)
    schema_valid: Mapped[bool] = mapped_column(Boolean)
    content: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class Proposal(Timestamped, Base):
    __tablename__ = "proposals"
    __table_args__ = (UniqueConstraint("id", "session_id", name="uq_proposal_session"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"))
    model_response_id: Mapped[str | None] = mapped_column(ForeignKey("model_responses.id"))
    action_name: Mapped[str] = mapped_column(String(100))
    arguments_json: Mapped[str] = mapped_column(Text)
    finding_ids_json: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    learning_goal: Mapped[str] = mapped_column(Text)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)


class PolicyDecision(Timestamped, Base):
    __tablename__ = "policy_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"))
    allowed: Mapped[bool] = mapped_column(Boolean)
    code: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)


class Approval(Timestamped, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="uq_approval_session"),
        UniqueConstraint(
            "id", "proposal_id", "session_id", name="uq_approval_proposal_session"
        ),
        ForeignKeyConstraint(
            ["proposal_id", "session_id"],
            ["proposals.id", "proposals.session_id"],
            name="fk_approval_proposal_session",
        ),
        ForeignKeyConstraint(
            ["target_id", "session_id"],
            ["authorized_targets.id", "authorized_targets.session_id"],
            name="fk_approval_target_session",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"))
    proposal_id: Mapped[str] = mapped_column(String(36), unique=True)
    target_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    protected_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Action(Timestamped, Base):
    __tablename__ = "actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["proposal_id", "session_id"],
            ["proposals.id", "proposals.session_id"],
            name="fk_action_proposal_session",
        ),
        ForeignKeyConstraint(
            ["approval_id", "proposal_id", "session_id"],
            ["approvals.id", "approvals.proposal_id", "approvals.session_id"],
            name="fk_action_exact_approval",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"))
    proposal_id: Mapped[str] = mapped_column(String(36), unique=True)
    approval_id: Mapped[str] = mapped_column(String(36), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    arguments_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class ActionResult(Timestamped, Base):
    __tablename__ = "action_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    parser: Mapped[str] = mapped_column(String(100))
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    cleanup_status: Mapped[str] = mapped_column(String(20))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("lab_sessions.id"))
    event_type: Mapped[str] = mapped_column(String(100))
    safe_details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Report(Timestamped, Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("lab_sessions.id"), unique=True)
    content: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
