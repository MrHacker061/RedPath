"""Boundary for future fixed, approval-bound app-initiated checks."""

from redpath.action_registry import ValidatedProposal
from redpath.contracts import ActionResultContract


def run_approved_check(
    proposal: ValidatedProposal, *, approved_protected_hash: str
) -> ActionResultContract:
    raise NotImplementedError("Approved check execution is not implemented")
