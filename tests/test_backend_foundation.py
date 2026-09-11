import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect

from redpath.app import create_app
from redpath.config import Settings
from redpath.contracts import AIProposal, NormalizedFinding


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'redpath-test.db'}"))


def test_health_endpoint_and_schema_creation(app):
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "redpath-api", "version": "0.1.0", "database": "ok"}
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

