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


class ArgumentKind(str, Enum):
    TARGET_ID = "target_id"
    PORT = "port"
    PROTOCOL = "protocol"
    FINDING_ID = "finding_id"
    STRING = "string"
    INTEGER = "integer"


class ProviderCode(str, Enum):
    OLLAMA_SUCCESS = "AI_OLLAMA_SUCCESS"
    OLLAMA_INVALID_OUTPUT_FALLBACK = "AI_OLLAMA_INVALID_OUTPUT_FALLBACK"
    OLLAMA_UNAVAILABLE_FALLBACK = "AI_OLLAMA_UNAVAILABLE_FALLBACK"
    RULE_BASED_SUCCESS = "AI_RULE_BASED_SUCCESS"
    EXPLANATION_FALLBACK = "AI_EXPLANATION_FALLBACK"


class Finding(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    state: EvidenceState
    category: str = Field(min_length=1, max_length=80)
    protocol: Literal["tcp", "udp"]
    port: int = Field(ge=1, le=65535)
    service_hint: str | None = Field(default=None, max_length=100)
    evidence_source: str = Field(min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=500)


class ActionArgumentConstraint(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    kind: ArgumentKind
    required: bool = True
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_bounds(self) -> "ActionArgumentConstraint":
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        return self


class ActionDefinition(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    description: str = Field(min_length=1, max_length=500)
    argument_constraints: tuple[ActionArgumentConstraint, ...] = ()

    @model_validator(mode="after")
    def unique_argument_names(self) -> "ActionDefinition":
        names = [item.name for item in self.argument_constraints]
        if len(names) != len(set(names)):
            raise ValueError("action argument names must be unique")
        return self


class RecommendationContext(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    lesson_objective: str = Field(min_length=1, max_length=1000)
    findings: tuple[Finding, ...] = ()
    allowed_actions: tuple[ActionDefinition, ...] = ()
    prior_results: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def findings_are_bound_to_context(self) -> "RecommendationContext":
        for finding in self.findings:
            if finding.session_id != self.session_id or finding.target_id != self.target_id:
                raise ValueError("every finding must match the context session_id and target_id")
        return self


class CanonicalAIProposal(StrictModel):
    """Exact adapter shape consumed by Worker 1's backend contract."""

    finding_ids: list[str] = Field(min_length=1)
    action_name: str
    arguments: dict[str, Any]
    reason: str
    learning_goal: str
    requires_approval: Literal[True] = True


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
        """Cross the untrusted-model boundary using trusted backend context.

        This method must run before persistence or policy evaluation. It rejects
        model-created references and type-checks every action value against the
        trusted action definition, including exact target binding.
        """
        known_findings = {finding.id for finding in context.findings}
        unsupported = set(self.finding_ids) - known_findings
        if unsupported:
            raise ValueError(f"unsupported finding IDs: {sorted(unsupported)}")
        if self.kind == ProposalKind.ACTION:
            actions = {action.name: action for action in context.allowed_actions}
            if self.action_name not in actions:
                raise ValueError(f"unknown action: {self.action_name}")
            constraints = {
                constraint.name: constraint
                for constraint in actions[self.action_name].argument_constraints
            }
            expected = {name for name, item in constraints.items() if item.required}
            supplied = set(self.arguments)
            if not expected <= supplied or not supplied <= set(constraints):
                raise ValueError(
                    f"action arguments do not match the registered schema"
                )
            supporting = {item.id: item for item in context.findings if item.id in self.finding_ids}
            for name, value in self.arguments.items():
                self._validate_argument(name, value, constraints[name], context, supporting)
        return self

    def to_canonical_proposal(self, context: RecommendationContext) -> CanonicalAIProposal:
        """Validate untrusted output and adapt only executable proposal fields."""
        self.validate_against(context)
        if self.kind is not ProposalKind.ACTION or self.action_name is None:
            raise ValueError("more_evidence responses are not backend action proposals")
        return CanonicalAIProposal(
            finding_ids=self.finding_ids,
            action_name=self.action_name,
            arguments=self.arguments,
            reason=self.reason,
            learning_goal=self.learning_goal,
            requires_approval=True,
        )

    @staticmethod
    def _validate_argument(
        name: str,
        value: Any,
        constraint: ActionArgumentConstraint,
        context: RecommendationContext,
        supporting: dict[str, Finding],
    ) -> None:
        kind = constraint.kind
        if kind == ArgumentKind.TARGET_ID:
            if not isinstance(value, str) or value != context.target_id:
                raise ValueError(f"{name} must equal the authorized context target_id")
        elif kind == ArgumentKind.FINDING_ID:
            if not isinstance(value, str) or value not in supporting:
                raise ValueError(f"{name} must reference a supporting finding")
        elif kind == ArgumentKind.PORT:
            if type(value) is not int or not 1 <= value <= 65535:
                raise ValueError(f"{name} must be a valid integer port")
            if value not in {item.port for item in supporting.values()}:
                raise ValueError(f"{name} must match a supporting finding port")
        elif kind == ArgumentKind.PROTOCOL:
            if value not in {"tcp", "udp"} or value not in {item.protocol for item in supporting.values()}:
                raise ValueError(f"{name} must match a supporting finding protocol")
        elif kind == ArgumentKind.STRING:
            if not isinstance(value, str) or not 1 <= len(value) <= 256:
                raise ValueError(f"{name} must be a bounded string")
        elif kind == ArgumentKind.INTEGER:
            if type(value) is not int:
                raise ValueError(f"{name} must be an integer")
        if type(value) is int:
            if constraint.minimum is not None and value < constraint.minimum:
                raise ValueError(f"{name} is below the registered minimum")
            if constraint.maximum is not None and value > constraint.maximum:
                raise ValueError(f"{name} is above the registered maximum")
        if constraint.choices and value not in constraint.choices:
            raise ValueError(f"{name} is not an allowed registered value")


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
