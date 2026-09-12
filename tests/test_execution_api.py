import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import redpath.execution_api as execution_api
from redpath.app import create_app
from redpath.config import Settings
from redpath.models import (
    Action,
    ActionResult as StoredActionResult,
    Approval,
    AuditEvent,
    AuthorizedTarget,
    LabSession,
    PolicyDecision,
    Proposal,
)
from redpath_kali import ActionResult, ActionStatus

@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'execution.db'}"))


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value

def future(minutes: int = 60) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()

def seed_approved_http_action(client, app):
    session = client.post(
        "/api/v1/sessions",
        json={"authorization_confirmed": True, "expires_at": future(120)},
    ).json()
    target = client.post(
        f"/api/v1/sessions/{session['id']}/target",
        json={
            "address": "192.168.56.20",
            "authorization_source": "owned_training_lab",
            "expires_at": future(),
        },
    ).json()

    def parser(_xml, session_id, target_id, _scan_id, _address):
        return [{
            "id": f"finding-{target_id}",
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
    assert client.post(
        f"/api/v1/sessions/{session['id']}/scan-import",
        json={"filename": "owned.xml", "xml_text": "<nmaprun/>"},
    ).status_code == 201
    recommendation = client.post(
        f"/api/v1/sessions/{session['id']}/recommendation"
    ).json()
    proposal = recommendation["proposal"]
    approval = client.post(
        f"/api/v1/sessions/{session['id']}/proposals/{proposal['id']}/approve"
    ).json()
    return session, target, proposal, approval


class RecordingDispatcher:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def dispatch(self, action_name, arguments, **scope):
        self.calls.append((action_name, arguments, scope))
        return self.result


def run_route(session_id: str, proposal_id: str) -> str:
    return f"/api/v1/sessions/{session_id}/proposals/{proposal_id}/run"


def test_run_uses_only_the_approved_stored_action_and_persists_result(client, app):
    session, target, proposal, approval = seed_approved_http_action(client, app)
    dispatcher = RecordingDispatcher(ActionResult(
        action_name="inspect_http_headers",
        target_id=target["id"],
        target_address=target["address"],
        port=80,
        status=ActionStatus.SUCCEEDED,
        exit_code=0,
        stdout="HTTP/1.1 200 OK\nServer: lab\n",
        stderr="",
        output_truncated=False,
    ))
    app.state.action_dispatcher = dispatcher

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "action_id", "status", "exit_code", "parser", "evidence", "cleanup_status"
    }
    assert body["status"] == "completed"
    assert body["exit_code"] == 0
    assert body["parser"] == "http_headers_v1"
    assert body["cleanup_status"] == "completed"
    assert body["evidence"] == [
        {
            "kind": "http_headers",
            "action_name": "inspect_http_headers",
            "target_id": target["id"],
            "target_address": "192.168.56.20",
            "port": 80,
            "outcome": "succeeded",
            "output_truncated": False,
            "http_status": 200,
            "failure_category": None,
        },
    ]
    assert "Server: lab" not in response.text
    assert dispatcher.calls == [(
        "inspect_http_headers",
        {"target_id": target["id"], "port": 80},
        {
            "authorized_target_id": target["id"],
            "authorized_target_address": "192.168.56.20",
        },
    )]
    with app.state.session_factory() as db:
        stored_approval = db.get(Approval, approval["approval_id"])
        action = db.get(Action, body["action_id"])
        result = db.scalar(
            select(StoredActionResult).where(StoredActionResult.action_id == action.id)
        )
        assert stored_approval.used_at is not None
        assert action.status == "completed"
        assert action.name == "inspect_http_headers"
        assert result.status == "completed"
        assert result.exit_code == 0
        assert {event.event_type for event in db.scalars(select(AuditEvent)).all()} >= {
            "action.started", "action.completed"
        }


def test_run_rejects_any_caller_supplied_action_body_without_claiming(client, app):
    session, _, proposal, approval = seed_approved_http_action(client, app)
    dispatcher = RecordingDispatcher(None)
    app.state.action_dispatcher = dispatcher

    response = client.post(
        run_route(session["id"], proposal["id"]),
        json={
            "action_name": "check_tcp_connection",
            "arguments": {"target_id": "other", "port": 22},
            "command": "id",
        },
    )

    assert response.status_code == 422
    assert dispatcher.calls == []
    with app.state.session_factory() as db:
        assert db.get(Approval, approval["approval_id"]).used_at is None
        assert db.scalar(select(Action)) is None
        assert db.scalar(select(StoredActionResult)) is None


def test_claim_is_durable_before_dispatch_and_cannot_be_reused(client, app):
    session, target, proposal, approval = seed_approved_http_action(client, app)

    class DurableClaimDispatcher(RecordingDispatcher):
        def dispatch(self, action_name, arguments, **scope):
            with app.state.session_factory() as db:
                stored_approval = db.get(Approval, approval["approval_id"])
                action = db.scalar(
                    select(Action).where(Action.proposal_id == proposal["id"])
                )
                assert stored_approval.used_at is not None
                assert action.status == "running"
                assert db.scalar(select(StoredActionResult)) is None
                assert "action.started" in set(
                    db.scalars(select(AuditEvent.event_type)).all()
                )
            return super().dispatch(action_name, arguments, **scope)

    dispatcher = DurableClaimDispatcher(ActionResult(
        action_name="inspect_http_headers",
        target_id=target["id"],
        target_address=target["address"],
        port=80,
        status=ActionStatus.SUCCEEDED,
        exit_code=0,
        stdout="ok",
        stderr="",
        output_truncated=False,
    ))
    app.state.action_dispatcher = dispatcher

    first = client.post(run_route(session["id"], proposal["id"]))
    second = client.post(run_route(session["id"], proposal["id"]))

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(dispatcher.calls) == 1
    with app.state.session_factory() as db:
        assert len(db.scalars(select(Action)).all()) == 1
        assert len(db.scalars(select(StoredActionResult)).all()) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "expired_approval",
        "used_approval",
        "rejected_approval",
        "policy_denied",
        "proposal_changed",
        "target_locked",
        "target_expired",
        "target_address_changed",
        "authorization_revoked",
    ],
)
def test_execution_revalidates_all_authorization_state_before_claim(
    client, app, mutation
):
    session, target, proposal, approval = seed_approved_http_action(client, app)
    with app.state.session_factory() as db:
        stored_approval = db.get(Approval, approval["approval_id"])
        if mutation == "expired_approval":
            stored_approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif mutation == "used_approval":
            stored_approval.used_at = datetime.now(timezone.utc)
        elif mutation == "rejected_approval":
            stored_approval.status = "rejected"
        elif mutation == "policy_denied":
            policy = db.scalar(
                select(PolicyDecision).where(PolicyDecision.proposal_id == proposal["id"])
            )
            policy.allowed = False
        elif mutation == "proposal_changed":
            stored_proposal = db.get(Proposal, proposal["id"])
            stored_proposal.arguments_json = json.dumps(
                {"target_id": target["id"], "port": 8080}
            )
        elif mutation == "target_locked":
            db.get(AuthorizedTarget, target["id"]).locked = True
        elif mutation == "target_expired":
            db.get(AuthorizedTarget, target["id"]).expires_at = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            )
        elif mutation == "target_address_changed":
            db.get(AuthorizedTarget, target["id"]).address = "192.168.56.99"
        else:
            db.get(LabSession, session["id"]).authorization_confirmed = False
        db.commit()
    dispatcher = RecordingDispatcher(None)
    app.state.action_dispatcher = dispatcher

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 409
    assert dispatcher.calls == []
    with app.state.session_factory() as db:
        assert db.scalar(select(Action)) is None
        assert db.scalar(select(StoredActionResult)) is None


def test_emergency_stop_is_rechecked_before_an_approval_is_claimed(client, app):
    session, _, proposal, approval = seed_approved_http_action(client, app)
    assert client.post("/api/v1/emergency-stop").status_code == 200
    dispatcher = RecordingDispatcher(None)
    app.state.action_dispatcher = dispatcher

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 409
    assert dispatcher.calls == []
    with app.state.session_factory() as db:
        assert db.get(Approval, approval["approval_id"]).used_at is None
        assert db.scalar(select(Action)) is None


def test_cross_session_or_missing_approval_never_dispatches(client, app):
    first, _, first_proposal, first_approval = seed_approved_http_action(client, app)
    second, _, second_proposal, _ = seed_approved_http_action(client, app)
    with app.state.session_factory() as db:
        db.delete(db.get(Approval, first_approval["approval_id"]))
        db.commit()
    dispatcher = RecordingDispatcher(None)
    app.state.action_dispatcher = dispatcher

    cross_session = client.post(run_route(first["id"], second_proposal["id"]))
    missing = client.post(run_route(first["id"], first_proposal["id"]))

    assert cross_session.status_code == 404
    assert missing.status_code == 409
    assert dispatcher.calls == []


@pytest.mark.parametrize(
    ("dispatcher_status", "exit_code", "expected_status"),
    [
        (ActionStatus.FAILED, 7, "failed"),
        (ActionStatus.TIMED_OUT, None, "timed_out"),
    ],
)
def test_terminal_failures_are_persisted_and_returned(
    client, app, dispatcher_status, exit_code, expected_status
):
    session, target, proposal, approval = seed_approved_http_action(client, app)
    app.state.action_dispatcher = RecordingDispatcher(ActionResult(
        action_name="inspect_http_headers",
        target_id=target["id"],
        target_address=target["address"],
        port=80,
        status=dispatcher_status,
        exit_code=exit_code,
        stdout="partial",
        stderr="failed safely",
        output_truncated=False,
        error="bounded failure",
    ))

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    assert response.json()["exit_code"] == exit_code
    with app.state.session_factory() as db:
        action = db.scalar(select(Action))
        result = db.scalar(select(StoredActionResult))
        assert db.get(Approval, approval["approval_id"]).used_at is not None
        assert action.status == expected_status
        assert result.status == expected_status


@pytest.mark.parametrize("mode", ["missing", "raises", "wrong_scope"])
def test_dispatcher_unavailability_fails_closed_after_consuming_claim(
    client, app, mode
):
    session, target, proposal, approval = seed_approved_http_action(client, app)
    if mode == "missing":
        app.state.action_dispatcher = None
    elif mode == "raises":
        class RaisingDispatcher:
            def dispatch(self, *_args, **_kwargs):
                raise RuntimeError("SECRET_INTERNAL_DETAIL")

        app.state.action_dispatcher = RaisingDispatcher()
    else:
        app.state.action_dispatcher = RecordingDispatcher(ActionResult(
            action_name="check_tcp_connection",
            target_id=target["id"],
            target_address=target["address"],
            port=22,
            status=ActionStatus.SUCCEEDED,
            exit_code=0,
            stdout="wrong action",
            stderr="",
            output_truncated=False,
        ))

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 503
    assert "SECRET_INTERNAL_DETAIL" not in response.text
    with app.state.session_factory() as db:
        action = db.scalar(select(Action))
        result = db.scalar(select(StoredActionResult))
        assert db.get(Approval, approval["approval_id"]).used_at is not None
        assert action.status == "failed"
        assert result.status == "failed"
        assert "SECRET_INTERNAL_DETAIL" not in result.evidence_json
        if mode == "raises":
            assert json.loads(result.evidence_json) == [
                {"category": "dispatcher_error", "kind": "failure"}
            ]


def test_persisted_evidence_is_redacted_bounded_and_marks_backend_truncation(
    client, app
):
    session, target, proposal, _ = seed_approved_http_action(client, app)
    app.state.action_dispatcher = RecordingDispatcher(ActionResult(
        action_name="inspect_http_headers",
        target_id=target["id"],
        target_address=target["address"],
        port=80,
        status=ActionStatus.SUCCEEDED,
        exit_code=0,
        stdout=(
            "Set-Cookie: SECRET_COOKIE\nAuthorization: SECRET_TOKEN\n"
            + "💥" * 20_000
        ),
        stderr="界" * 20_000,
        output_truncated=False,
    ))

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 200
    assert "SECRET_COOKIE" not in response.text
    assert "SECRET_TOKEN" not in response.text
    metadata = response.json()["evidence"][0]
    assert metadata["output_truncated"] is True
    assert set(metadata) == {
        "kind", "action_name", "target_id", "target_address", "port",
        "outcome", "output_truncated", "http_status", "failure_category",
    }
    assert "💥" not in response.text
    assert "界" not in response.text
    with app.state.session_factory() as db:
        result = db.scalar(select(StoredActionResult))
        assert len(result.evidence_json) <= 16_384
        assert all(value not in result.evidence_json for value in ("SECRET", "💥", "界"))
        audits = "".join(db.scalars(select(AuditEvent.safe_details_json)).all())
        assert "SECRET_COOKIE" not in audits
        assert "SECRET_TOKEN" not in audits


def test_proposal_is_revalidated_again_after_durable_claim_before_dispatch(
    client, app, monkeypatch
):
    session, target, proposal, approval = seed_approved_http_action(client, app)
    original_revalidate = execution_api._revalidate_claimed_action

    def mutate_before_revalidation(db, **kwargs):
        with app.state.session_factory() as other_db:
            stored = other_db.get(Proposal, proposal["id"])
            stored.arguments_json = json.dumps(
                {"target_id": target["id"], "port": 8080}
            )
            other_db.commit()
        return original_revalidate(db, **kwargs)

    monkeypatch.setattr(
        execution_api, "_revalidate_claimed_action", mutate_before_revalidation
    )
    dispatcher = RecordingDispatcher(None)
    app.state.action_dispatcher = dispatcher

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 409
    assert dispatcher.calls == []
    with app.state.session_factory() as db:
        assert db.get(Approval, approval["approval_id"]).used_at is not None
        assert db.scalar(select(Action)).status == "cancelled"
        assert db.scalar(select(StoredActionResult)).status == "cancelled"


def test_dispatch_exception_details_are_not_logged_or_returned(client, app, caplog):
    session, _, proposal, _ = seed_approved_http_action(client, app)

    class RaisingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            raise RuntimeError("SECRET_DISPATCH_DETAIL")

    app.state.action_dispatcher = RaisingDispatcher()

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 503
    assert "SECRET_DISPATCH_DETAIL" not in response.text
    assert "SECRET_DISPATCH_DETAIL" not in caplog.text


def test_malformed_dispatcher_result_is_persisted_as_failure(client, app):
    session, target, proposal, approval = seed_approved_http_action(client, app)
    app.state.action_dispatcher = RecordingDispatcher(ActionResult(
        action_name="inspect_http_headers",
        target_id=target["id"],
        target_address=target["address"],
        port=80,
        status="unexpected",  # type: ignore[arg-type]
        exit_code=0,
        stdout="not trusted",
        stderr="",
        output_truncated=False,
    ))

    response = client.post(run_route(session["id"], proposal["id"]))

    assert response.status_code == 503
    with app.state.session_factory() as db:
        assert db.get(Approval, approval["approval_id"]).used_at is not None
        assert db.scalar(select(Action)).status == "failed"
        assert db.scalar(select(StoredActionResult)).status == "failed"
