import pytest
from pydantic import ValidationError

from redpath_ai.learning import LearningResponse, explain_findings, retrieve_notes
from redpath_ai.schemas import EvidenceState, Finding


def finding(**changes):
    values = dict(
        id="finding-1", session_id="session-1", target_id="target-1",
        state=EvidenceState.OBSERVED, category="open_port", protocol="tcp",
        port=22, service_hint="ssh", evidence_source="scan:sha256:abc",
    )
    values.update(changes)
    return Finding(**values)


def test_retrieval_is_stable_bounded_and_source_attributed():
    results = retrieve_notes("SSH on TCP port 22", limit=2)
    assert 1 <= len(results) <= 2
    assert "redpath:ssh-basics:v1" in {item.source_id for item in results}
    assert all(item.source_id and len(item.excerpt) <= 700 for item in results)


def test_retrieval_rejects_unbounded_limit_and_empty_query():
    with pytest.raises(ValueError):
        retrieve_notes("ssh", limit=6)
    assert retrieve_notes("!!!") == ()


@pytest.mark.parametrize("state", list(EvidenceState))
def test_explanation_preserves_state_source_and_denies_execution(state):
    response = explain_findings([finding(state=state)])
    item = response.explanations[0]
    assert item.evidence_state is state
    assert item.evidence_source == "scan:sha256:abc"
    assert item.finding_id == "finding-1"
    assert response.execution_authorized is False
    assert "does not by itself prove" in item.what_it_does_not_prove


def test_missing_findings_and_unknown_subject_are_explicit():
    empty = explain_findings([])
    assert empty.explanations == ()
    assert empty.missing_evidence
    unknown = explain_findings([finding(category="xyzzy", service_hint="xyzzy", port=65000)])
    assert unknown.missing_evidence == ("No reviewed learning note matched finding finding-1.",)
    assert unknown.explanations[0].source_ids == ()


def test_large_import_is_bounded_and_reported():
    findings = [finding(id=f"finding-{index}") for index in range(101)]
    response = explain_findings(findings)
    assert len(response.explanations) == 100
    assert any("first 100" in message for message in response.missing_evidence)


def test_learning_contract_cannot_claim_execution_authority():
    with pytest.raises(ValidationError):
        LearningResponse(explanations=(), notes=(), execution_authorized=True)
