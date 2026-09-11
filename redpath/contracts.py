from enum import StrEnum
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceState(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    VERIFIED = "verified"


class SessionState(StrEnum):
    DRAFT = "draft"
    AUTHORIZED = "authorized"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class NormalizedFinding(StrictModel):
    id: str
    session_id: str
    target_id: str
    state: EvidenceState
    category: str
    protocol: Literal["tcp", "udp"]
    port: int = Field(ge=1, le=65535)
    service_hint: str | None = None
    evidence_source: str


class AIProposal(StrictModel):
    """Untrusted wire data from an AI provider; never execute this directly."""

    finding_ids: list[str] = Field(min_length=1)
    action_name: str
    arguments: dict[str, Any]
    reason: str
    learning_goal: str
    requires_approval: Literal[True] = True


class ComponentHealth(StrictModel):
    status: Literal["healthy", "degraded", "offline", "standby", "unknown"]


class PolicyDecisionContract(StrictModel):
    proposal_id: str
    allowed: bool
    code: str
    reason: str


class RecommendationProposalContract(AIProposal):
    id: str
    session_id: str


class RecommendationPolicyDecisionContract(StrictModel):
    id: str
    proposal_id: str
    allowed: bool
    code: str
    explanation: str


class RecommendationResponse(StrictModel):
    proposal: RecommendationProposalContract
    policy_decision: RecommendationPolicyDecisionContract


class ActionResultContract(StrictModel):
    action_id: str
    status: Literal["completed", "failed", "timed_out", "cancelled"]
    exit_code: int | None = None
    parser: str
    evidence: list[dict[str, Any]]
    cleanup_status: Literal["not_required", "pending", "completed", "failed"]


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    database: Literal["ok", "unavailable"]
    services: dict[Literal["fastapi", "ollama", "kali"], ComponentHealth]


class SessionCreate(StrictModel):
    authorization_confirmed: bool
    expires_at: datetime


class SessionSummary(StrictModel):
    id: str
    state: SessionState
    authorization_confirmed: bool
    expires_at: datetime
    created_at: datetime


class LessonSourceCreate(StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=250)


class LessonSourceContract(LessonSourceCreate):
    id: str


class AuthorizedTargetCreate(StrictModel):
    address: str = Field(min_length=1, max_length=255)
    authorization_source: str = Field(min_length=1, max_length=100)
    expires_at: datetime


class AuthorizedTargetContract(AuthorizedTargetCreate):
    id: str
    locked: bool


class SessionDetail(SessionSummary):
    lesson_source: LessonSourceContract | None = None
    target: AuthorizedTargetContract | None = None


class ScanImportRequest(StrictModel):
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\]+\.xml$")
    xml_text: str = Field(min_length=1, max_length=1_000_000)


class ScanImportContract(StrictModel):
    id: str
    source_type: Literal["nmap_xml"]
    content_hash: str
    created_at: datetime


class ScanImportResponse(StrictModel):
    scan_import: ScanImportContract
    findings: list[NormalizedFinding]


class ApprovalDecisionContract(StrictModel):
    proposal_id: str
    status: Literal["approved", "rejected"]
    approval_id: str | None
    expires_at: datetime | None


class EmergencyStopContract(StrictModel):
    active: bool
    activated_at: datetime | None = None
    cleared_at: datetime | None = None


class AuditEventContract(StrictModel):
    id: str
    session_id: str | None
    event_type: str = Field(max_length=100)
    details: dict[str, str | int | bool | list[str] | None]
    created_at: datetime


class AuditHistoryContract(StrictModel):
    events: tuple[AuditEventContract, ...] = Field(max_length=100)
    truncated: bool


class ReportTargetContract(StrictModel):
    target_id: str
    expires_at: datetime
    locked: bool


class ReportEvidenceContract(StrictModel):
    total: int = Field(ge=0)
    observed: int = Field(ge=0)
    inferred: int = Field(ge=0)
    verified: int = Field(ge=0)


class ReportProposalContract(StrictModel):
    proposal_id: str
    action_name: str = Field(max_length=100)
    policy_allowed: bool
    policy_code: str = Field(max_length=80)


class ReportApprovalContract(StrictModel):
    proposal_id: str
    status: Literal["approved", "rejected"]
    expires_at: datetime | None
    used: bool


class LearningReportContract(StrictModel):
    report_id: str
    session_id: str
    session_state: SessionState
    generated_at: datetime
    target: ReportTargetContract | None
    evidence: ReportEvidenceContract
    proposals: tuple[ReportProposalContract, ...] = Field(max_length=100)
    approvals: tuple[ReportApprovalContract, ...] = Field(max_length=100)
    proposals_truncated: bool
    approvals_truncated: bool
    audit_event_count: int = Field(ge=0)
    execution_authorized: Literal[False] = False
