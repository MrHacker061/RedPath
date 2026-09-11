"""Typed validation boundary between untrusted AI output and policy/persistence."""

import hashlib
import hmac
import ipaddress
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import ConfigDict, Field

from redpath.contracts import AIProposal, StrictModel
from redpath_ai.schemas import (
    ActionArgumentConstraint,
    ActionDefinition,
    ArgumentKind,
)


class ActionArguments(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HttpHeadersArguments(ActionArguments):
    target_id: str = Field(min_length=1, max_length=128)
    port: int = Field(ge=1, le=65535)


class TlsCertificateArguments(ActionArguments):
    target_id: str = Field(min_length=1, max_length=128)
    port: int = Field(ge=1, le=65535)


class TcpConnectionArguments(ActionArguments):
    target_id: str = Field(min_length=1, max_length=128)
    port: int = Field(ge=1, le=65535)
    timeout_seconds: int = Field(default=5, ge=1, le=10)


ACTION_ARGUMENT_MODELS = {
    "inspect_http_headers": HttpHeadersArguments,
    "inspect_tls_certificate": TlsCertificateArguments,
    "check_tcp_connection": TcpConnectionArguments,
}


RECOMMENDATION_ACTIONS = (
    ActionDefinition(
        name="inspect_http_headers",
        description="Read HTTP response headers through the fixed inspection adapter.",
        argument_constraints=(
            ActionArgumentConstraint(name="target_id", kind=ArgumentKind.TARGET_ID),
            ActionArgumentConstraint(name="port", kind=ArgumentKind.PORT),
        ),
    ),
    ActionDefinition(
        name="inspect_tls_certificate",
        description="Read TLS certificate metadata through the fixed inspection adapter.",
        argument_constraints=(
            ActionArgumentConstraint(name="target_id", kind=ArgumentKind.TARGET_ID),
            ActionArgumentConstraint(name="port", kind=ArgumentKind.PORT),
        ),
    ),
    ActionDefinition(
        name="check_tcp_connection",
        description="Attempt a bounded TCP connection through the fixed connectivity adapter.",
        argument_constraints=(
            ActionArgumentConstraint(name="target_id", kind=ArgumentKind.TARGET_ID),
            ActionArgumentConstraint(name="port", kind=ArgumentKind.PORT),
            ActionArgumentConstraint(
                name="timeout_seconds",
                kind=ArgumentKind.INTEGER,
                required=False,
                minimum=1,
                maximum=10,
            ),
        ),
    ),
)


class ValidatedProposal(StrictModel):
    """Proposal safe to persist for policy review, not authority to execute."""

    finding_ids: tuple[str, ...]
    action_name: Literal[
        "inspect_http_headers", "inspect_tls_certificate", "check_tcp_connection"
    ]
    arguments: dict[str, Any]
    reason: str
    learning_goal: str
    requires_approval: Literal[True]


def validate_untrusted_proposal(
    proposal: AIProposal,
    *,
    authorized_target_id: str,
    available_finding_ids: set[str],
) -> ValidatedProposal:
    """Validate action-specific values and bind references to backend-owned state."""

    argument_model = ACTION_ARGUMENT_MODELS.get(proposal.action_name)
    if argument_model is None:
        raise ValueError(f"unknown registered action: {proposal.action_name}")
    arguments = argument_model.model_validate(proposal.arguments)
    if arguments.target_id != authorized_target_id:
        raise ValueError("proposal target does not match the authorized session target")
    unsupported = set(proposal.finding_ids) - available_finding_ids
    if unsupported:
        raise ValueError("proposal references findings outside the session")
    return ValidatedProposal(
        finding_ids=tuple(proposal.finding_ids),
        action_name=proposal.action_name,
        arguments=arguments.model_dump(),
        reason=proposal.reason,
        learning_goal=proposal.learning_goal,
        requires_approval=True,
    )


def action_protected_hash(
    proposal: ValidatedProposal,
    *,
    session_id: str,
    target_id: str,
    target_address: str,
    proposal_id: str,
) -> str:
    """Bind approval to one exact scoped proposal and its protected action."""

    protected = {
        "session_id": session_id,
        "target_id": target_id,
        "target_address": str(ipaddress.ip_address(target_address)),
        "proposal_id": proposal_id,
        "action_name": proposal.action_name,
        "arguments": proposal.arguments,
    }
    canonical = json.dumps(
        protected, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def revalidate_approval_before_execution(
    proposal: ValidatedProposal,
    *,
    session_id: str,
    target_id: str,
    target_address: str,
    proposal_id: str,
    approved_protected_hash: str,
    approval_status: str,
    approval_expires_at: datetime,
    approval_used_at: datetime | None,
    emergency_stop_active: bool,
) -> None:
    """Fail closed if approval scope or protected action changed."""

    if emergency_stop_active:
        raise ValueError("Emergency stop is active")
    if approval_status != "approved":
        raise ValueError("approval is not approved")
    expires_at = (
        approval_expires_at.replace(tzinfo=timezone.utc)
        if approval_expires_at.tzinfo is None
        else approval_expires_at.astimezone(timezone.utc)
    )
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("approval has expired")
    if approval_used_at is not None:
        raise ValueError("approval has already been used")
    current_hash = action_protected_hash(
        proposal,
        session_id=session_id,
        target_id=target_id,
        target_address=target_address,
        proposal_id=proposal_id,
    )
    if not hmac.compare_digest(current_hash, approved_protected_hash):
        raise ValueError("action no longer matches the exact approved name and arguments")
