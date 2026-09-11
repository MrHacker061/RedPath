import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from redpath.action_registry import ACTION_ARGUMENT_MODELS, RECOMMENDATION_ACTIONS
from redpath.app import create_app
from redpath.config import Settings
from redpath.models import (
    Action,
    AuditEvent,
    AuthorizedTarget,
    LabSession,
    PolicyDecision,
    Proposal,
)
from redpath_ai import LLMProvider, RuleBasedProvider
from redpath_ai.schemas import (
    Explanation,
    ProposalKind,
    ProviderHealth,
    ProposedStep,
    RecommendationContext,
)


class StubProvider(LLMProvider):
    def __init__(self, recommendation):
        self.recommendation = recommendation
        self.context = None

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=True, provider="test")

    def recommend_next_step(self, context: RecommendationContext) -> ProposedStep:
        self.context = context
        if isinstance(self.recommendation, Exception):
            raise self.recommendation
        if callable(self.recommendation):
            return self.recommendation(context)
        return self.recommendation

    def explain_result(self, result: str) -> Explanation:
        raise AssertionError("recommendation endpoint must not explain or execute results")


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'recommendations.db'}"))


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


def future(hours=2):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def seed_finding(client, app, *, address="192.168.56.20", service="http", port=80):
    session = client.post(
        "/api/v1/sessions",
        json={"authorization_confirmed": True, "expires_at": future()},
    ).json()
    client.post(
        f"/api/v1/sessions/{session['id']}/lesson-source",
        json={"url": "https://tryhackme.com/room/must-not-enter-model-context"},
    )
    target_response = client.post(
        f"/api/v1/sessions/{session['id']}/target",
        json={
            "address": address,
            "authorization_source": "owned_training_lab",
            "expires_at": future(1),
        },
    )
    target = target_response.json()

    def parser(_xml, session_id, target_id, _scan_id, _target_address):
        return [{
            "id": f"finding-{port}",
            "session_id": session_id,
            "target_id": target_id,
            "state": "observed",
            "category": "open_port",
            "protocol": "tcp",
            "port": port,
            "service_hint": service,
            "evidence_source": f"nmap:stable:port:{port}",
        }]

    app.state.nmap_parser = parser
    scan = client.post(
        f"/api/v1/sessions/{session['id']}/scan-import",
        json={"filename": "owned-lab.xml", "xml_text": "<nmaprun/>"},
    )
    assert scan.status_code == 201
    return session, target, scan.json()["findings"][0]


def valid_step(context: RecommendationContext, **changes) -> ProposedStep:
    finding = context.findings[0]
    data = {
        "kind": ProposalKind.ACTION,
        "finding_ids": [finding.id],
        "action_name": "inspect_http_headers",
        "arguments": {"target_id": context.target_id, "port": finding.port},
        "reason": "Inspect the observed HTTP service with a limited fixed check.",
        "learning_goal": "Learn what HTTP headers can and cannot prove.",
        "requires_approval": True,
        "evidence_needed": None,
    }
    data.update(changes)
    return ProposedStep.model_validate(data)


def test_recommendation_uses_scoped_context_and_persists_strict_contract(client, app):
    session, target, finding = seed_finding(client, app)
    other_session, _, other_finding = seed_finding(
        client, app, address="192.168.56.21", service="https", port=443
    )
    provider = StubProvider(lambda context: valid_step(context))
    app.state.llm_provider = provider

    response = client.post(f"/api/v1/sessions/{session['id']}/recommendation")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"proposal", "policy_decision"}
    assert set(body["proposal"]) == {
        "id", "session_id", "finding_ids", "action_name", "arguments",
        "reason", "learning_goal", "requires_approval",
    }
    assert set(body["policy_decision"]) == {
        "id", "proposal_id", "allowed", "code", "explanation",
    }
    assert body["proposal"] == {
        "id": body["proposal"]["id"],
        "session_id": session["id"],
        "finding_ids": [finding["id"]],
        "action_name": "inspect_http_headers",
        "arguments": {"target_id": target["id"], "port": 80},
        "reason": "Inspect the observed HTTP service with a limited fixed check.",
        "learning_goal": "Learn what HTTP headers can and cannot prove.",
        "requires_approval": True,
    }
    assert body["policy_decision"] == {
        "id": body["policy_decision"]["id"],
        "proposal_id": body["proposal"]["id"],
        "allowed": True,
        "code": "POLICY_VALIDATED_REQUIRES_APPROVAL",
        "explanation": "The proposal is session-bound and allowlisted; explicit approval is still required.",
    }
    assert provider.context.session_id == session["id"]
    assert provider.context.target_id == target["id"]
    assert [item.id for item in provider.context.findings] == [finding["id"]]
    assert other_finding["id"] not in provider.context.model_dump_json()
    assert other_session["id"] not in provider.context.model_dump_json()
    assert "tryhackme" not in provider.context.model_dump_json()
    assert "192.168.56.20" not in provider.context.model_dump_json()

    with app.state.session_factory() as db:
        proposal = db.get(Proposal, body["proposal"]["id"])
        decision = db.get(PolicyDecision, body["policy_decision"]["id"])
        assert json.loads(proposal.finding_ids_json) == [finding["id"]]
        assert json.loads(proposal.arguments_json) == {"port": 80, "target_id": target["id"]}
        assert decision.proposal_id == proposal.id
        assert decision.code == "POLICY_VALIDATED_REQUIRES_APPROVAL"
        assert db.scalar(select(Action)) is None


@pytest.mark.parametrize(
    "unsafe_result",
    [
        lambda context: valid_step(context, action_name="free_form_shell"),
        lambda context: valid_step(context, finding_ids=["invented-finding"]),
        lambda context: valid_step(
            context,
            arguments={"target_id": "target-from-another-session", "port": 80},
        ),
        {"raw": "MODEL_RAW_OUTPUT_MUST_NOT_BE_LOGGED"},
        RuntimeError("MODEL_RAW_OUTPUT_MUST_NOT_BE_LOGGED"),
    ],
    ids=["unknown-action", "unsupported-finding", "target-mismatch", "malformed", "provider-error"],
)
def test_unsafe_provider_output_falls_back_without_logging_raw_output(
    client, app, unsafe_result
):
    session, target, finding = seed_finding(client, app)
    app.state.llm_provider = StubProvider(unsafe_result)

    response = client.post(f"/api/v1/sessions/{session['id']}/recommendation")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["proposal"]["finding_ids"] == [finding["id"]]
    assert body["proposal"]["action_name"] == "inspect_http_headers"
    assert body["proposal"]["arguments"] == {"target_id": target["id"], "port": 80}
    with app.state.session_factory() as db:
        details = " ".join(db.scalars(select(AuditEvent.safe_details_json)).all())
        event_types = set(db.scalars(select(AuditEvent.event_type)).all())
        assert "recommendation.provider.fallback" in event_types
        assert "MODEL_RAW_OUTPUT_MUST_NOT_BE_LOGGED" not in details
        assert db.scalar(select(Action)) is None


def test_more_evidence_fallback_fails_closed_without_persistence(client, app):
    session, _, _ = seed_finding(client, app, service="unknown", port=31337)
    app.state.llm_provider = StubProvider({"malformed": True})

    response = client.post(f"/api/v1/sessions/{session['id']}/recommendation")

    assert response.status_code == 409
    assert response.json() == {"detail": "No safe action recommendation is available"}
    with app.state.session_factory() as db:
        assert db.scalar(select(Proposal)) is None
        assert db.scalar(select(PolicyDecision)) is None
        assert db.scalar(select(Action)) is None
        rejected = db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "recommendation.rejected")
        ).all()
        assert json.loads(rejected[-1].safe_details_json) == {
            "code": "NO_SAFE_ACTION_RECOMMENDATION"
        }


@pytest.mark.parametrize("expired_resource", ["session", "target"])
def test_recommendation_requires_active_session_and_target(
    client, app, expired_resource
):
    session, target, _ = seed_finding(client, app)
    with app.state.session_factory() as db:
        if expired_resource == "session":
            stored = db.get(LabSession, session["id"])
        else:
            stored = db.get(AuthorizedTarget, target["id"])
        stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    response = client.post(f"/api/v1/sessions/{session['id']}/recommendation")

    assert response.status_code == 409
    with app.state.session_factory() as db:
        assert db.scalar(select(Proposal)) is None
        assert db.scalar(select(PolicyDecision)) is None
        assert db.scalar(select(Action)) is None


def test_application_defaults_to_rule_based_recommendation_provider(app):
    assert isinstance(app.state.llm_provider, RuleBasedProvider)


def test_recommendation_rechecks_private_target_boundary(client, app):
    session, target, _ = seed_finding(client, app)
    with app.state.session_factory() as db:
        stored = db.get(AuthorizedTarget, target["id"])
        stored.address = "8.8.8.8"
        db.commit()

    response = client.post(f"/api/v1/sessions/{session['id']}/recommendation")

    assert response.status_code == 409
    with app.state.session_factory() as db:
        assert db.scalar(select(Proposal)) is None
        assert db.scalar(select(PolicyDecision)) is None
        assert db.scalar(select(Action)) is None


def test_recommendation_metadata_covers_exact_backend_action_registry():
    assert {action.name for action in RECOMMENDATION_ACTIONS} == set(
        ACTION_ARGUMENT_MODELS
    )
