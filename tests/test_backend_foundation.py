from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from redpath.action_registry import (
    action_protected_hash,
    revalidate_approval_before_execution,
    validate_untrusted_proposal,
)
from redpath.app import create_app
from redpath.config import Settings
from redpath.contracts import AIProposal, ActionResultContract, NormalizedFinding
from redpath.database import Base
from redpath.models import Action, Approval, AuthorizedTarget, Finding, LabSession, Proposal, ScanImport


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'redpath-test.db'}"))


def test_health_endpoint_and_schema_creation(app):
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert {key: payload[key] for key in ("status", "service", "version", "database")} == {"status": "ok", "service": "redpath-api", "version": "0.1.0", "database": "ok"}
    assert payload["services"] == {
        "fastapi": {"status": "healthy"},
        "ollama": {"status": "unknown"},
        "kali": {"status": "unknown"},
    }
    assert {"lab_sessions", "authorized_targets", "proposals", "policy_decisions"} <= set(inspect(app.state.engine).get_table_names())


def test_config_rejects_network_exposure_and_non_sqlite_database():
    with pytest.raises(ValidationError, match="loopback"):
        Settings(host="0.0.0.0")
    with pytest.raises(ValidationError, match="SQLite only"):
        Settings(database_url="postgresql://example")


def test_normalized_finding_is_strict():
    finding = {"id": "finding-12", "session_id": "session-1", "target_id": "target-3", "state": "observed", "category": "open_port", "protocol": "tcp", "port": 80, "service_hint": "http", "evidence_source": "scan-7"}
    assert NormalizedFinding.model_validate(finding).port == 80
    with pytest.raises(ValidationError):
        NormalizedFinding.model_validate(finding | {"port": 70000})
    with pytest.raises(ValidationError):
        NormalizedFinding.model_validate(finding | {"command": "anything"})


def test_ai_proposal_always_requires_approval():
    proposal = {"finding_ids": ["finding-12"], "action_name": "inspect_http_headers", "arguments": {"target_id": "target-3", "port": 80}, "reason": "Inspect an observed service.", "learning_goal": "Understand HTTP headers.", "requires_approval": True}
    assert AIProposal.model_validate(proposal).requires_approval is True
    with pytest.raises(ValidationError):
        AIProposal.model_validate(proposal | {"requires_approval": False})
    with pytest.raises(ValidationError):
        AIProposal.model_validate(proposal | {"shell": "arbitrary"})


def test_action_result_contract_rejects_raw_or_unregistered_evidence():
    result = {
        "action_id": "action-1",
        "status": "completed",
        "exit_code": 0,
        "parser": "http_headers_v1",
        "cleanup_status": "completed",
    }
    with pytest.raises(ValidationError):
        ActionResultContract.model_validate(
            result | {"evidence": [{"kind": "stdout", "text": "SECRET"}]}
        )


def test_registry_validates_untrusted_action_values_and_backend_references():
    proposal = AIProposal.model_validate({"finding_ids": ["finding-12"], "action_name": "inspect_http_headers", "arguments": {"target_id": "target-3", "port": 80}, "reason": "Inspect an observed service.", "learning_goal": "Understand HTTP headers.", "requires_approval": True})
    validated = validate_untrusted_proposal(
        proposal,
        authorized_target_id="target-3",
        available_finding_ids={"finding-12"},
    )
    assert validated.arguments == {"target_id": "target-3", "port": 80}
    with pytest.raises(ValueError, match="authorized session target"):
        validate_untrusted_proposal(proposal, authorized_target_id="other", available_finding_ids={"finding-12"})
    with pytest.raises(ValueError, match="outside the session"):
        validate_untrusted_proposal(proposal, authorized_target_id="target-3", available_finding_ids=set())
    bad_port = proposal.model_copy(update={"arguments": {"target_id": "target-3", "port": "80"}})
    with pytest.raises(ValidationError):
        validate_untrusted_proposal(bad_port, authorized_target_id="target-3", available_finding_ids={"finding-12"})
    unknown = proposal.model_copy(update={"action_name": "free_form_shell"})
    with pytest.raises(ValueError, match="unknown registered action"):
        validate_untrusted_proposal(unknown, authorized_target_id="target-3", available_finding_ids={"finding-12"})
    extra = proposal.model_copy(update={"arguments": {"target_id": "target-3", "port": 80, "command": "anything"}})
    with pytest.raises(ValidationError):
        validate_untrusted_proposal(extra, authorized_target_id="target-3", available_finding_ids={"finding-12"})

    scope = {
        "session_id": "session-1",
        "target_id": "target-3",
        "target_address": "192.168.56.20",
        "proposal_id": "proposal-1",
    }
    approval_state = {
        "approval_status": "approved",
        "approval_expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        "approval_used_at": None,
        "emergency_stop_active": False,
    }
    approved_hash = action_protected_hash(validated, **scope)
    revalidate_approval_before_execution(
        validated, approved_protected_hash=approved_hash, **scope, **approval_state
    )
    changed = validated.model_copy(
        update={"arguments": {"target_id": "target-3", "port": 443}}
    )
    with pytest.raises(ValueError, match="exact approved name and arguments"):
        revalidate_approval_before_execution(
            changed,
            approved_protected_hash=approved_hash,
            **scope,
            **approval_state,
        )
    changed_name = validated.model_copy(update={"action_name": "check_tcp_connection"})
    with pytest.raises(ValueError, match="exact approved name and arguments"):
        revalidate_approval_before_execution(
            changed_name,
            approved_protected_hash=approved_hash,
            **scope,
            **approval_state,
        )
    with pytest.raises(ValueError, match="already been used"):
        revalidate_approval_before_execution(
            validated,
            approved_protected_hash=approved_hash,
            **scope,
            **(approval_state | {"approval_used_at": datetime.now(timezone.utc)}),
        )
    with pytest.raises(ValueError, match="Emergency stop"):
        revalidate_approval_before_execution(
            validated,
            approved_protected_hash=approved_hash,
            **scope,
            **(approval_state | {"emergency_stop_active": True}),
        )
    with pytest.raises(ValueError, match="expired"):
        revalidate_approval_before_execution(
            validated,
            approved_protected_hash=approved_hash,
            **scope,
            **(
                approval_state
                | {"approval_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
            ),
        )


def test_sqlite_foreign_keys_reject_missing_and_cross_session_references(app):
    Base.metadata.create_all(app.state.engine)
    with app.state.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    with app.state.session_factory() as db:
        db.add_all([LabSession(id="session-1"), LabSession(id="session-2")])
        db.commit()
        db.add_all([
            AuthorizedTarget(id="target-1", session_id="session-1", address="192.168.56.10", authorization_source="private_lab", expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc)),
            AuthorizedTarget(id="target-2", session_id="session-2", address="192.168.56.20", authorization_source="private_lab", expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc)),
        ])
        db.add(ScanImport(id="scan-1", session_id="session-1", source_type="nmap_xml", content_hash="a" * 64))
        db.add(Proposal(id="proposal-1", session_id="session-1", action_name="inspect_http_headers", arguments_json='{"target_id":"target-1","port":80}', finding_ids_json='["finding-1"]', reason="test", learning_goal="test"))
        db.commit()
        db.add(Finding(id="finding-cross-session", session_id="session-2", target_id="target-1", scan_import_id="scan-1", category="open_port", protocol="tcp", port=80))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Approval(id="approval-cross-session", session_id="session-1", proposal_id="proposal-1", target_id="target-2", protected_hash="b" * 64, expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc)))
        with pytest.raises(IntegrityError):
            db.commit()


def test_action_rejects_approval_for_different_proposal_in_same_session(app):
    Base.metadata.create_all(app.state.engine)
    expires = datetime(2030, 1, 1, tzinfo=timezone.utc)
    with app.state.session_factory() as db:
        db.add(LabSession(id="session-1"))
        db.commit()
        db.add(AuthorizedTarget(id="target-1", session_id="session-1", address="192.168.56.10", authorization_source="private_lab", expires_at=expires))
        db.add_all([
            Proposal(id="proposal-1", session_id="session-1", action_name="inspect_http_headers", arguments_json='{"target_id":"target-1","port":80}', finding_ids_json='["finding-1"]', reason="test", learning_goal="test"),
            Proposal(id="proposal-2", session_id="session-1", action_name="inspect_tls_certificate", arguments_json='{"target_id":"target-1","port":443}', finding_ids_json='["finding-2"]', reason="test", learning_goal="test"),
        ])
        db.commit()
        db.add(Approval(id="approval-1", session_id="session-1", proposal_id="proposal-1", target_id="target-1", protected_hash="c" * 64, expires_at=expires))
        db.commit()
        db.add(Action(id="action-invalid", session_id="session-1", proposal_id="proposal-2", approval_id="approval-1", name="inspect_tls_certificate", arguments_json='{"target_id":"target-1","port":443}'))
        with pytest.raises(IntegrityError):
            db.commit()
