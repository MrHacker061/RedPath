"""Small, reviewed learning library and deterministic evidence explanations.

This module has no provider, network, subprocess, or action-registry access. It
turns normalized findings into bounded educational text; it cannot authorize or
execute a security action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

from pydantic import Field

from .schemas import EvidenceState, Finding, StrictModel


MAX_QUERY_CHARS = 300
MAX_RESULTS = 5
MAX_CONTEXT_CHARS = 4_000
_TOKEN = re.compile(r"[a-z0-9]{2,32}")


@dataclass(frozen=True)
class LearningNote:
    source_id: str
    title: str
    keywords: tuple[str, ...]
    body: str


class RetrievedNote(StrictModel):
    source_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    excerpt: str = Field(min_length=1, max_length=700)


class FindingExplanation(StrictModel):
    finding_id: str = Field(min_length=1, max_length=128)
    evidence_state: EvidenceState
    evidence_source: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=700)
    what_it_means: str = Field(min_length=1, max_length=700)
    what_it_does_not_prove: str = Field(min_length=1, max_length=700)
    source_ids: tuple[str, ...] = ()


class LearningResponse(StrictModel):
    explanations: tuple[FindingExplanation, ...]
    notes: tuple[RetrievedNote, ...]
    missing_evidence: tuple[str, ...] = ()
    execution_authorized: Literal[False] = False


STARTER_NOTES: tuple[LearningNote, ...] = (
    LearningNote(
        "redpath:network-port-basics:v1",
        "Ports and services",
        ("port", "tcp", "udp", "service", "open"),
        "A port is a numbered network endpoint. An open-port observation shows that a host answered a specific probe; a service name is often only a scanner hint until independently verified.",
    ),
    LearningNote(
        "redpath:http-basics:v1",
        "HTTP evidence",
        ("http", "https", "web", "80", "443", "header", "tls"),
        "HTTP or HTTPS evidence can identify a web-facing endpoint. A port or banner alone does not establish the application version, a vulnerability, or successful access.",
    ),
    LearningNote(
        "redpath:ssh-basics:v1",
        "SSH evidence",
        ("ssh", "22", "remote", "shell", "login"),
        "SSH commonly provides authenticated remote administration. Seeing SSH does not prove that credentials work or that the service is vulnerable, and it is not permission to attempt access.",
    ),
    LearningNote(
        "redpath:evidence-states:v1",
        "Evidence states",
        ("observed", "inferred", "verified", "evidence", "source"),
        "Observed means directly present in imported evidence. Inferred is a cautious interpretation. Verified requires a separate, recorded check. Keep the original source ID so another person can trace the claim.",
    ),
    LearningNote(
        "redpath:authorization:v1",
        "Authorization boundaries",
        ("authorization", "scope", "target", "permission", "lab"),
        "Learning material explains evidence but grants no testing authority. Only work on targets explicitly included in an active lab or written authorization, using actions allowed by that scope.",
    ),
)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()[:MAX_QUERY_CHARS]))


def retrieve_notes(
    query: str, *, limit: int = 3, notes: Sequence[LearningNote] = STARTER_NOTES
) -> tuple[RetrievedNote, ...]:
    """Return deterministic keyword matches from the reviewed local corpus."""
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULTS}")
    query_tokens = _tokens(query)
    if not query_tokens:
        return ()
    ranked: list[tuple[int, str, LearningNote]] = []
    for note in notes:
        haystack = _tokens(" ".join((note.title, *note.keywords, note.body)))
        score = len(query_tokens & haystack)
        if score:
            ranked.append((-score, note.source_id, note))
    ranked.sort()
    return tuple(
        RetrievedNote(source_id=note.source_id, title=note.title, excerpt=note.body[:700])
        for _, _, note in ranked[:limit]
    )


def explain_findings(findings: Iterable[Finding]) -> LearningResponse:
    """Explain normalized evidence without proposing or performing an action."""
    items = tuple(findings)
    if not items:
        return LearningResponse(
            explanations=(),
            notes=(),
            missing_evidence=("No normalized findings were supplied. Import scan evidence first.",),
        )
    explanations: list[FindingExplanation] = []
    selected: dict[str, RetrievedNote] = {}
    missing: list[str] = []
    for finding in items[:100]:
        # Match subject matter only. Evidence-state and protocol vocabulary are
        # explained by the response itself and must not create a false corpus
        # match for an otherwise unknown service.
        query = " ".join(
            part for part in (
                finding.category,
                str(finding.port),
                finding.service_hint or "",
            ) if part
        )
        notes = retrieve_notes(query, limit=3)
        for note in notes:
            selected[note.source_id] = note
        service = finding.service_hint or "an unidentified service"
        state_text = {
            EvidenceState.OBSERVED: "directly recorded by the imported evidence",
            EvidenceState.INFERRED: "a cautious interpretation that still needs verification",
            EvidenceState.VERIFIED: "marked verified by a separate recorded check",
        }[finding.state]
        explanations.append(FindingExplanation(
            finding_id=finding.id,
            evidence_state=finding.state,
            evidence_source=finding.evidence_source,
            summary=f"{finding.protocol.upper()} port {finding.port} is associated with {service}.",
            what_it_means=f"This claim is {state_text}. Trace it to source {finding.evidence_source}.",
            what_it_does_not_prove=(
                "It does not by itself prove a vulnerability, working credentials, successful access, "
                "or authorization to test the target."
            ),
            source_ids=tuple(note.source_id for note in notes),
        ))
        if not notes:
            missing.append(f"No reviewed learning note matched finding {finding.id}.")
    if len(items) > 100:
        missing.append("Only the first 100 findings were explained; split larger imports into pages.")
    bounded_notes: list[RetrievedNote] = []
    used = 0
    for note in selected.values():
        size = len(note.title) + len(note.excerpt) + len(note.source_id)
        if used + size > MAX_CONTEXT_CHARS:
            break
        bounded_notes.append(note)
        used += size
    return LearningResponse(
        explanations=tuple(explanations),
        notes=tuple(bounded_notes),
        missing_evidence=tuple(missing),
        execution_authorized=False,
    )
