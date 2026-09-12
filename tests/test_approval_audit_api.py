import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from redpath.action_registry import ValidatedProposal, action_protected_hash
from redpath.app import create_app
from redpath.config import Settings
from redpath.models import (
    Action,
    Approval,
    AuditEvent,
    PolicyDecision,
    Proposal,
    Report,
)


@pytest.fixture
def app(tmp_path, security_config):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'approvals.db'}"), security=security_config)


@pytest.fixture
def client(app, client_options):
    with TestClient(app, **client_options) as value:
        yield value


def future(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def seed_recommendation(client, app, *, session_minutes=120, target_minutes=60):
    session = client.post(
        "/api/v1/sessions",
        json={"authorization_confirmed": True, "expires_at": future(session_minutes)},
    ).json()
    target = client.post(
        f"/api/v1/sessions/{session['id']}/target",
        json={
            "address": "192.168.56.20",
            "authorization_source": "owned_training_lab",
            "expires_at": future(target_minutes),
        },
    ).json()

    def parser(_xml, session_id, target_id, _scan_id, _target_address):
        return [{
            "id": "finding-80",
            "session_id": session_id,
            "target_id": target_id,
            "state": "observed",
            "category": "open_port",
            "protocol": "tcp",
            "port": 80,
            "service_hint": "http",
            "evidence_source": "nmap:stable:port:80",
        }]

    app.state.nmap_parser = parser
    imported = client.post(
        f"/api/v1/sessions/{session['id']}/scan-import",
        json={"filename": "owned-lab.xml", "xml_text": "<nmaprun/>"},
    )
    assert imported.status_code == 201
    recommendation = client.post(
        f"/api/v1/sessions/{session['id']}/recommendation"
    )
    assert recommendation.status_code == 201
    return session, target, recommendation.json()


def approval_route(session_id: str, proposal_id: str, decision: str) -> str:
    return f"/api/v1/sessions/{session_id}/proposals/{proposal_id}/{decision}"


def test_action_hash_binds_session_target_proposal_action_and_arguments():
    proposal = ValidatedProposal(
        finding_ids=("finding-80",),
        action_name="inspect_http_headers",
        arguments={"target_id": "target-1", "port": 80},
        reason="Inspect the service.",
        learning_goal="Understand HTTP headers.",
        requires_approval=True,
    )
    original = action_protected_hash(
        proposal,
        session_id="session-1",
        target_id="target-1",
        target_address="192.168.56.20",
        proposal_id="proposal-1",
    )

    assert original != action_protected_hash(
        proposal,
        session_id="session-2",
        target_id="target-1",
        target_address="192.168.56.20",
        proposal_id="proposal-1",
    )
    assert original != action_protected_hash(
        proposal,
        session_id="session-1",
        target_id="target-2",
        target_address="192.168.56.20",
        proposal_id="proposal-1",
    )
    assert original != action_protected_hash(
        proposal,
        session_id="session-1",
        target_id="target-1",
        target_address="192.168.56.21",
        proposal_id="proposal-1",
    )
    assert action_protected_hash(
        proposal,
        session_id="session-1",
        target_id="target-1",
        target_address="fd00:0:0:0:0:0:0:20",
        proposal_id="proposal-1",
    ) == action_protected_hash(
        proposal,
        session_id="session-1",
        target_id="target-1",
        target_address="fd00::20",
        proposal_id="proposal-1",
    )
    assert original != action_protected_hash(
        proposal,
        session_id="session-1",
        target_id="target-1",
        target_address="192.168.56.20",
        proposal_id="proposal-2",
    )


def test_approve_returns_exact_contract_and_persists_short_lived_binding(client, app):
    session, target, recommendation = seed_recommendation(
        client, app, session_minutes=90, target_minutes=3
    )
    proposal = recommendation["proposal"]

    response = client.post(approval_route(session["id"], proposal["id"], "approve"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"proposal_id", "status", "approval_id", "expires_at"}
    assert body["proposal_id"] == proposal["id"]
    assert body["status"] == "approved"
    assert isinstance(body["approval_id"], str)
    assert datetime.fromisoformat(body["expires_at"]) <= datetime.fromisoformat(
        target["expires_at"]
    )
    with app.state.session_factory() as db:
        approval = db.get(Approval, body["approval_id"])
        assert approval.status == "approved"
        assert approval.session_id == session["id"]
        assert approval.proposal_id == proposal["id"]
        assert approval.target_id == target["id"]
        expected = action_protected_hash(
            ValidatedProposal(
                finding_ids=tuple(proposal["finding_ids"]),
                action_name=proposal["action_name"],
                arguments=proposal["arguments"],
                reason=proposal["reason"],
                learning_goal=proposal["learning_goal"],
                requires_approval=True,
            ),
            session_id=session["id"],
            target_id=target["id"],
            target_address=target["address"],
            proposal_id=proposal["id"],
        )
        assert approval.protected_hash == expected
        assert db.scalar(select(Action)) is None


def test_reject_returns_exact_contract_and_prevents_later_approval(client, app):
    session, _, recommendation = seed_recommendation(client, app)
    proposal_id = recommendation["proposal"]["id"]

    rejected = client.post(approval_route(session["id"], proposal_id, "reject"))

    assert rejected.status_code == 200, rejected.text
    assert rejected.json() == {
        "proposal_id": proposal_id,
        "status": "rejected",
        "approval_id": None,
        "expires_at": None,
    }
    duplicate = client.post(approval_route(session["id"], proposal_id, "approve"))
    assert duplicate.status_code == 409
    with app.state.session_factory() as db:
        decisions = db.scalars(
            select(Approval).where(Approval.proposal_id == proposal_id)
        ).all()
        assert len(decisions) == 1
        assert decisions[0].status == "rejected"
        assert db.scalar(select(Action)) is None


def test_approval_rejects_cross_session_policy_denial_and_duplicates(client, app):
    first_session, _, first_recommendation = seed_recommendation(client, app)
    second_session, _, second_recommendation = seed_recommendation(client, app)
    first_proposal_id = first_recommendation["proposal"]["id"]
    second_proposal_id = second_recommendation["proposal"]["id"]

    cross_session = client.post(
        approval_route(first_session["id"], second_proposal_id, "approve")
    )
    assert cross_session.status_code == 404

    with app.state.session_factory() as db:
        policy = db.scalar(
            select(PolicyDecision).where(
                PolicyDecision.proposal_id == first_proposal_id
            )
        )
        policy.allowed = False
        policy.code = "TEST_POLICY_DENIED"
        db.commit()
    denied = client.post(
        approval_route(first_session["id"], first_proposal_id, "approve")
    )
    assert denied.status_code == 409

    approved = client.post(
        approval_route(second_session["id"], second_proposal_id, "approve")
    )
    assert approved.status_code == 200
    duplicate = client.post(
        approval_route(second_session["id"], second_proposal_id, "approve")
    )
    assert duplicate.status_code == 409
    with app.state.session_factory() as db:
        assert len(db.scalars(select(Approval)).all()) == 1
        assert db.scalar(select(Action)) is None


def test_service_emergency_stop_blocks_approval_until_explicit_clear(client, app):
    session, _, recommendation = seed_recommendation(client, app)
    proposal_id = recommendation["proposal"]["id"]

    assert client.get("/api/v1/emergency-stop").json()["active"] is False
    activated = client.post("/api/v1/emergency-stop")
    assert activated.status_code == 200
    assert activated.json()["active"] is True
    assert activated.json()["activated_at"] is not None
    assert client.get("/api/v1/emergency-stop").json()["active"] is True

    blocked = client.post(approval_route(session["id"], proposal_id, "approve"))
    assert blocked.status_code == 409
    with app.state.session_factory() as db:
        assert db.scalar(select(Approval)) is None
        assert db.scalar(select(Action)) is None

    cleared = client.post("/api/v1/emergency-stop/clear")
    assert cleared.status_code == 200
    assert cleared.json()["active"] is False
    assert cleared.json()["cleared_at"] is not None
    assert client.post(
        approval_route(session["id"], proposal_id, "approve")
    ).status_code == 200
    with app.state.session_factory() as db:
        event_types = set(db.scalars(select(AuditEvent.event_type)).all())
        assert {"emergency_stop.activated", "emergency_stop.cleared"} <= event_types
    history = client.get(
        f"/api/v1/sessions/{session['id']}/audit-history?limit=100"
    ).json()["events"]
    stop_events = [event for event in history if event["event_type"].startswith("emergency_stop.")]
    assert {event["event_type"] for event in stop_events} == {
        "emergency_stop.activated",
        "emergency_stop.cleared",
    }
    assert all(event["session_id"] is None for event in stop_events)


def test_audit_history_is_bounded_structured_and_redacted(client, app):
    session, _, recommendation = seed_recommendation(client, app)
    proposal_id = recommendation["proposal"]["id"]
    client.post(approval_route(session["id"], proposal_id, "approve"))
    with app.state.session_factory() as db:
        db.add(AuditEvent(
            session_id=session["id"],
            event_type="unsafe.test",
            safe_details_json=json.dumps({
                "proposal_id": proposal_id,
                "password": "SECRET_MUST_NOT_LEAK",
                "raw_model_output": "MODEL_OUTPUT_MUST_NOT_LEAK",
                "code": "X" * 1_000,
            }),
        ))
        db.commit()

    limited = client.get(
        f"/api/v1/sessions/{session['id']}/audit-history?limit=2"
    )
    assert limited.status_code == 200
    assert len(limited.json()["events"]) == 2
    assert limited.json()["truncated"] is True

    full = client.get(f"/api/v1/sessions/{session['id']}/audit-history?limit=100")
    serialized = full.text
    assert full.status_code == 200
    assert "SECRET_MUST_NOT_LEAK" not in serialized
    assert "MODEL_OUTPUT_MUST_NOT_LEAK" not in serialized
    event = next(item for item in full.json()["events"] if item["event_type"] == "unsafe.test")
    assert set(event["details"]) <= {"proposal_id", "code"}
    assert len(event["details"]["code"]) <= 160


def test_learning_report_is_structured_bounded_and_contains_no_raw_output(client, app):
    session, _, recommendation = seed_recommendation(client, app)
    proposal_id = recommendation["proposal"]["id"]
    approved = client.post(approval_route(session["id"], proposal_id, "approve"))
    assert approved.status_code == 200
    with app.state.session_factory() as db:
        proposal = db.get(Proposal, proposal_id)
        proposal.reason = "RAW_MODEL_OUTPUT_MUST_NOT_LEAK"
        proposal.learning_goal = "SECRET_REPORT_VALUE_MUST_NOT_LEAK"
        db.commit()
    client.post(f"/api/v1/sessions/{session['id']}/close")

    response = client.get(f"/api/v1/sessions/{session['id']}/report")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == session["id"]
    assert body["session_state"] == "completed"
    assert body["evidence"] == {
        "total": 1,
        "observed": 1,
        "inferred": 0,
        "verified": 0,
    }
    assert body["proposals"] == [{
        "proposal_id": proposal_id,
        "action_name": "inspect_http_headers",
        "policy_allowed": True,
        "policy_code": "POLICY_VALIDATED_REQUIRES_APPROVAL",
    }]
    assert body["approvals"][0]["status"] == "approved"
    assert body["execution_authorized"] is False
    assert "RAW_MODEL_OUTPUT_MUST_NOT_LEAK" not in response.text
    assert "SECRET_REPORT_VALUE_MUST_NOT_LEAK" not in response.text
    with app.state.session_factory() as db:
        stored = db.scalar(select(Report).where(Report.session_id == session["id"]))
        assert stored is not None
        assert "RAW_MODEL_OUTPUT_MUST_NOT_LEAK" not in stored.content
        assert db.scalar(select(Action)) is None
