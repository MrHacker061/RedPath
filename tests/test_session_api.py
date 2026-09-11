from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from redpath.app import create_app
from redpath.config import Settings
from redpath.models import AuditEvent, Finding, ScanImport


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'sessions.db'}"))


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


def future(hours=2):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def create_session(client, confirmed=True):
    response = client.post("/api/v1/sessions", json={"authorization_confirmed": confirmed, "expires_at": future()})
    assert response.status_code == 201
    return response.json()


def add_target(client, session_id, address="192.168.56.20"):
    return client.post(f"/api/v1/sessions/{session_id}/target", json={"address": address, "authorization_source": "owned_training_lab", "expires_at": future(1)})


def test_session_create_list_view_and_close(client, app):
    created = create_session(client)
    assert created["state"] == "authorized"
    lesson = client.post(f"/api/v1/sessions/{created['id']}/lesson-source", json={"url": "https://tryhackme.com/room/example", "title": "Example room"})
    assert lesson.status_code == 201
    target = add_target(client, created["id"])
    assert target.status_code == 201
    viewed = client.get(f"/api/v1/sessions/{created['id']}").json()
    assert viewed["state"] == "ready"
    assert viewed["lesson_source"]["url"].startswith("https://tryhackme.com/")
    assert viewed["target"]["address"] == "192.168.56.20"
    assert client.get("/api/v1/sessions").json()[0]["id"] == created["id"]
    closed = client.post(f"/api/v1/sessions/{created['id']}/close")
    assert closed.status_code == 200
    assert closed.json()["state"] == "completed"
    assert closed.json()["target"]["locked"] is True
    assert add_target(client, created["id"]).status_code == 409
    with app.state.session_factory() as db:
        event_types = set(db.scalars(select(AuditEvent.event_type)).all())
    assert {"session.created", "lesson_source.registered", "target.registered", "session.closed"} <= event_types


@pytest.mark.parametrize("address", ["8.8.8.8", "127.0.0.1", "169.254.1.2", "224.0.0.1", "192.0.2.1", "not-an-ip"])
def test_target_rejects_non_private_or_special_addresses(client, address):
    session = create_session(client)
    response = add_target(client, session["id"], address)
    assert response.status_code == 422


@pytest.mark.parametrize("address", ["10.0.0.8", "172.16.5.2", "192.168.1.9", "fd00::20"])
def test_target_accepts_rfc1918_and_ipv6_ula(client, address):
    session = create_session(client)
    assert add_target(client, session["id"], address).status_code == 201


def test_target_requires_explicit_authorization(client):
    session = create_session(client, confirmed=False)
    response = add_target(client, session["id"])
    assert response.status_code == 409
    assert "Authorization" in response.json()["detail"]


def test_expired_and_invalid_session_inputs_are_rejected(client):
    expired = client.post("/api/v1/sessions", json={"authorization_confirmed": True, "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()})
    assert expired.status_code == 422
    session = create_session(client)
    assert client.post(f"/api/v1/sessions/{session['id']}/lesson-source", json={"url": "file:///tmp/lesson"}).status_code == 422
    assert client.post(f"/api/v1/sessions/{session['id']}/target", json={"address": "192.168.1.2", "authorization_source": "lab", "expires_at": future(3)}).status_code == 422


def test_scan_import_requires_parser_and_active_target(client, app):
    session = create_session(client)
    payload = {"filename": "scan.xml", "xml_text": "<nmaprun/>"}
    assert client.post(f"/api/v1/sessions/{session['id']}/scan-import", json=payload).status_code == 409
    assert add_target(client, session["id"]).status_code == 201
    app.state.nmap_parser = None
    assert client.post(f"/api/v1/sessions/{session['id']}/scan-import", json=payload).status_code == 503


def test_real_parser_completes_evidence_only_flow(client):
    session = create_session(client)
    client.post(f"/api/v1/sessions/{session['id']}/lesson-source", json={"url": "https://tryhackme.com/room/example"})
    target = add_target(client, session["id"]).json()
    xml = (Path(__file__).parent / "fixtures" / "nmap_sample.xml").read_text(encoding="utf-8")
    response = client.post(f"/api/v1/sessions/{session['id']}/scan-import", json={"filename": "owned-lab.xml", "xml_text": xml})
    assert response.status_code == 201, response.text
    finding = response.json()["findings"][0]
    assert finding["session_id"] == session["id"]
    assert finding["target_id"] == target["id"]
    assert finding["state"] == "observed"
    assert finding["evidence_source"] == response.json()["scan_import"]["id"]
    explanation = client.get(f"/api/v1/sessions/{session['id']}/explanation")
    assert explanation.status_code == 200
    assert explanation.json()["execution_authorized"] is False
    assert explanation.json()["explanations"][0]["finding_id"] == finding["id"]


def test_scan_import_uses_bounded_parser_contract_and_persists_findings(client, app):
    session = create_session(client)
    target = add_target(client, session["id"]).json()
    calls = []

    def parser(xml_text, session_id, target_id, scan_import_id):
        calls.append((xml_text, session_id, target_id, scan_import_id))
        return [{"id": "finding-1", "session_id": session_id, "target_id": target_id, "state": "observed", "category": "open_port", "protocol": "tcp", "port": 80, "service_hint": "http", "evidence_source": scan_import_id}]

    app.state.nmap_parser = parser
    response = client.post(f"/api/v1/sessions/{session['id']}/scan-import", json={"filename": "owned-lab.xml", "xml_text": "<nmaprun/>"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["findings"][0]["evidence_source"] == body["scan_import"]["id"]
    assert calls[0][1:3] == (session["id"], target["id"])
    with app.state.session_factory() as db:
        assert len(db.scalars(select(ScanImport)).all()) == 1
        assert len(db.scalars(select(Finding)).all()) == 1


def test_scan_import_rejects_bad_filename_oversize_and_invalid_parser_output(client, app):
    session = create_session(client)
    add_target(client, session["id"])
    route = f"/api/v1/sessions/{session['id']}/scan-import"
    assert client.post(route, json={"filename": "../scan.xml", "xml_text": "<x/>"}).status_code == 422
    assert client.post(route, json={"filename": "scan.xml", "xml_text": "x" * 1_000_001}).status_code == 422
    app.state.nmap_parser = lambda *_: [{"command": "whoami"}]
    assert client.post(route, json={"filename": "scan.xml", "xml_text": "<x/>"}).status_code == 422
    app.state.nmap_parser = lambda _xml, _session, target, scan: [{"id": "finding-2", "session_id": "different-session", "target_id": target, "state": "observed", "category": "open_port", "protocol": "tcp", "port": 22, "service_hint": "ssh", "evidence_source": scan}]
    assert client.post(route, json={"filename": "scan.xml", "xml_text": "<x/>"}).status_code == 422
    with app.state.session_factory() as db:
        assert db.scalar(select(ScanImport)) is None
