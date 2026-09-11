"""Strict schemas shared by RedPath AI providers."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceState(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    VERIFIED = "verified"


class ProposalKind(str, Enum):
    ACTION = "action"
    MORE_EVIDENCE = "more_evidence"


class Finding(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    state: EvidenceState
    category: str = Field(min_length=1, max_length=80)
    protocol: str | None = Field(default=None, max_length=16)
    port: int | None = Field(default=None, ge=1, le=65535)
    service_hint: str | None = Field(default=None, max_length=100)
    evidence_source: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=500)


class ActionDefinition(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    description: str = Field(min_length=1, max_length=500)
    argument_names: tuple[str, ...] = ()


class RecommendationContext(StrictModel):
    lesson_objective: str = Field(min_length=1, max_length=1000)
    findings: tuple[Finding, ...] = ()
    allowed_actions: tuple[ActionDefinition, ...] = ()
    prior_results: tuple[str, ...] = Field(default=(), max_length=20)


class ProposedStep(StrictModel):
    kind: ProposalKind
    finding_ids: list[str] = Field(default_factory=list, max_length=50)
    action_name: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=1000)
    learning_goal: str = Field(min_length=1, max_length=500)
    requires_approval: Literal[True]
    evidence_needed: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "ProposedStep":
        if self.kind == ProposalKind.ACTION:
            if not self.action_name:
                raise ValueError("action proposals require action_name")
            if not self.finding_ids:
                raise ValueError("action proposals require supporting finding_ids")
            if self.evidence_needed is not None:
                raise ValueError("action proposals cannot set evidence_needed")
        else:
            if self.action_name is not None or self.arguments:
                raise ValueError("more_evidence proposals cannot specify an action")
            if not self.evidence_needed:
                raise ValueError("more_evidence proposals require evidence_needed")
        return self

    def validate_against(self, context: RecommendationContext) -> "ProposedStep":
        """Reject model-created references and actions outside supplied context."""
        known_findings = {finding.id for finding in context.findings}
        unsupported = set(self.finding_ids) - known_findings
        if unsupported:
            raise ValueError(f"unsupported finding IDs: {sorted(unsupported)}")
        if self.kind == ProposalKind.ACTION:
            actions = {action.name: action for action in context.allowed_actions}
            if self.action_name not in actions:
                raise ValueError(f"unknown action: {self.action_name}")
            expected = set(actions[self.action_name].argument_names)
            supplied = set(self.arguments)
            if supplied != expected:
                raise ValueError(
                    f"action arguments must be exactly {sorted(expected)}; got {sorted(supplied)}"
                )
        return self


class Explanation(StrictModel):
    summary: str = Field(min_length=1, max_length=1000)
    what_it_proves: str = Field(min_length=1, max_length=1000)
    limitations: str = Field(min_length=1, max_length=1000)
    terms: dict[str, str] = Field(default_factory=dict)
    study_next: list[str] = Field(default_factory=list, max_length=10)


class ProviderHealth(StrictModel):
    available: bool
    provider: str
    model: str | None = None
    detail: str | None = Field(default=None, max_length=500)
