from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest
from fastapi.testclient import TestClient

from redpath.app import create_app
from redpath.config import Settings
from redpath.execution_evidence import structured_evidence
from redpath_kali import ActionResult, ActionStatus


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'fence.db'}"))


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


def _future(minutes: int = 60) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _seed_approved_action(client, app):
    session = client.post(
        "/api/v1/sessions",
        json={"authorization_confirmed": True, "expires_at": _future(120)},
    ).json()
    target = client.post(
        f"/api/v1/sessions/{session['id']}/target",
        json={
            "address": "192.168.56.20",
            "authorization_source": "owned_training_lab",
            "expires_at": _future(),
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
    proposal = client.post(
        f"/api/v1/sessions/{session['id']}/recommendation"
    ).json()["proposal"]
    assert client.post(
        f"/api/v1/sessions/{session['id']}/proposals/{proposal['id']}/approve"
    ).status_code == 200
    return session, target, proposal


def _route(session, proposal) -> str:
    return f"/api/v1/sessions/{session['id']}/proposals/{proposal['id']}/run"


def _success(target) -> ActionResult:
    return ActionResult(
        action_name="inspect_http_headers",
        target_id=target["id"],
        target_address=target["address"],
        port=80,
        status=ActionStatus.SUCCEEDED,
        exit_code=0,
        stdout="HTTP/1.1 200 OK\n",
        stderr="",
        output_truncated=False,
    )


def test_stop_activation_that_wins_dispatch_start_fence_blocks_the_action(
    client, app, monkeypatch
):
    session, target, proposal = _seed_approved_action(client, app)
    fence = app.state.execution_fence
    reached_fence = Event()
    release_start = Event()
    original_try_start = fence.try_start

    def paused_try_start(check):
        reached_fence.set()
        assert release_start.wait(3)
        return original_try_start(check)

    monkeypatch.setattr(fence, "try_start", paused_try_start)
    calls = []

    class Dispatcher:
        def dispatch(self, *_args, **_kwargs):
            calls.append(True)
            return _success(target)

    app.state.action_dispatcher = Dispatcher()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, _route(session, proposal))
        assert reached_fence.wait(3)
        stopped = client.post("/api/v1/emergency-stop")
        release_start.set()
        response = pending.result(timeout=3)

    assert stopped.status_code == 200
    assert "already-started work may continue" in stopped.json()["execution_notice"]
    assert response.status_code == 409
    assert calls == []


def test_stop_activation_commits_while_an_already_started_dispatch_continues(
    client, app
):
    session, target, proposal = _seed_approved_action(client, app)
    dispatch_started = Event()
    release_dispatch = Event()

    class Dispatcher:
        def dispatch(self, *_args, **_kwargs):
            dispatch_started.set()
            assert release_dispatch.wait(3)
            return _success(target)

    app.state.action_dispatcher = Dispatcher()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, _route(session, proposal))
        assert dispatch_started.wait(3)
        try:
            stopped = client.post("/api/v1/emergency-stop")
        finally:
            release_dispatch.set()
        response = pending.result(timeout=3)

    assert stopped.status_code == 200
    assert stopped.json()["active"] is True
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("action_name", "stdout", "stderr", "expected"),
    [
        (
            "check_tcp_connection",
            "SECRET connection text",
            "SECRET stderr",
            {"kind": "tcp_connection", "reachable": True},
        ),
        (
            "inspect_http_headers",
            "HTTP/1.1 204 No Content\nAuthorization: SECRET_TOKEN\n",
            "SECRET stderr",
            {"kind": "http_headers", "http_status": 204},
        ),
        (
            "inspect_tls_certificate",
            "Protocol version: TLSv1.3\nCiphersuite: TLS_AES_256_GCM_SHA384\n",
            "Verification: OK\nSECRET stderr",
            {
                "kind": "tls_certificate",
                "protocol": "TLSv1.3",
                "cipher_suite": "TLS_AES_256_GCM_SHA384",
                "verification": "verified",
            },
        ),
    ],
)
def test_fixed_action_evidence_exposes_only_allowlisted_facts(
    action_name, stdout, stderr, expected
):
    result = ActionResult(
        action_name=action_name,
        target_id="target-1",
        target_address="192.168.56.20",
        port=443,
        status=ActionStatus.SUCCEEDED,
        exit_code=0,
        stdout=stdout,
        stderr=stderr,
        output_truncated=False,
        error="SECRET error",
    )

    evidence = structured_evidence(result)

    assert expected.items() <= evidence[0].items()
    assert "SECRET" not in str(evidence)
