"""Safe AI planning primitives for RedPath.

This package creates recommendations only. It intentionally has no action runner,
shell, SSH, or network-scanning capability.
"""

from .providers import LLMProvider, OllamaProvider, RuleBasedProvider
from .schemas import (
    ActionDefinition,
    ActionArgumentConstraint,
    ArgumentKind,
    CanonicalAIProposal,
    EvidenceState,
    Explanation,
    Finding,
    ProposalKind,
    ProviderCode,
    ProposedStep,
    RecommendationContext,
)

__all__ = [
    "ActionDefinition",
    "ActionArgumentConstraint",
    "ArgumentKind",
    "CanonicalAIProposal",
    "EvidenceState",
    "Explanation",
    "Finding",
    "LLMProvider",
    "OllamaProvider",
    "ProposalKind",
    "ProviderCode",
    "ProposedStep",
    "RecommendationContext",
    "RuleBasedProvider",
]
