from enum import StrEnum
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
