"""Browser security regressions, using an in-process loopback client only."""

import pytest
from fastapi.testclient import TestClient

from redpath.app import create_app
from redpath.config import Settings
from redpath.runtime import AppPaths


@pytest.fixture
def client(tmp_path):
    paths = AppPaths.from_environment(str(tmp_path))
    app = create_app(Settings(database_url=f"sqlite:///{paths.database_file}"), paths)
    with TestClient(app, base_url="http://127.0.0.1:8000") as value:
        yield value


@pytest.mark.parametrize("host", ["attacker.test:8000", "localhost:8000", "127.0.0.1", "127.0.0.1:8001", "127.0.0.1:8000.attacker.test"])
def test_dns_rebinding_host_cannot_read_shell_health_or_token(client, host):
    for path in ["/", "/api/v1/health", "/api/v1/desktop-session"]:
        response = client.get(path, headers={"Host": host, "X-RedPath-Bootstrap": "1"})
        assert response.status_code == 403


@pytest.mark.parametrize("headers", [
    {}, {"Origin": "http://127.0.0.1:8000"},
    {"Origin": "http://attacker.test", "X-RedPath-Session": "a" * 43},
    {"Origin": "null", "X-RedPath-Session": "a" * 43},
    {"Origin": "http://127.0.0.1:8001", "X-RedPath-Session": "a" * 43},
    {"Origin": "http://127.0.0.1:8000", "X-RedPath-Session": "wrong"},
])
def test_untrusted_mutations_do_not_change_stop_state(client, headers):
    response = client.post("/api/v1/emergency-stop", headers=headers)
    assert response.status_code == 403
    assert client.get("/api/v1/emergency-stop").json()["active"] is False


def test_same_origin_bootstrap_then_mutation(client):
    response = client.get("/api/v1/desktop-session", headers={"X-RedPath-Bootstrap": "1", "Sec-Fetch-Site": "same-origin"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["csrf_token"]
    assert len(token) >= 43
    assert "access-control-allow-origin" not in response.headers
    assert client.post("/api/v1/emergency-stop", headers={"Origin": "http://127.0.0.1:8000", "X-RedPath-Session": token}).status_code == 200
    assert client.get("/api/v1/emergency-stop").json()["active"] is True
    assert client.post("/api/v1/emergency-stop/clear", headers={"X-RedPath-Session": token}).status_code == 403


@pytest.mark.parametrize("headers", [
    {}, {"X-RedPath-Bootstrap": "1", "Origin": "http://attacker.test"},
    {"X-RedPath-Bootstrap": "1", "Sec-Fetch-Site": "cross-site"},
    {"X-RedPath-Bootstrap": "1", "Sec-Fetch-Site": "same-site"},
])
def test_bootstrap_rejects_navigation_and_foreign_fetch(client, headers):
    assert client.get("/api/v1/desktop-session", headers=headers).status_code == 403


def test_cors_preflight_does_not_grant_foreign_access(client):
    response = client.options("/api/v1/desktop-session", headers={
        "Origin": "http://attacker.test", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-RedPath-Bootstrap",
    })
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_duplicate_host_headers_fail_closed(client):
    response = client.get("/api/v1/health", headers=[("Host", "127.0.0.1:8000"), ("Host", "attacker.test:8000")])
    assert response.status_code == 403


def test_native_top_level_navigation_can_load_shell_without_bootstrap_access(client):
    # Chromium marks an initial address/navigation with Sec-Fetch-Site: none.
    headers = {"Sec-Fetch-Site": "none"}
    assert client.get("/", headers=headers).status_code == 200
    assert client.get("/api/v1/desktop-session", headers=headers | {"X-RedPath-Bootstrap": "1"}).status_code == 403


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_mutating_method_requires_origin_and_session_token(client, method):
    assert client.request(method, "/api/v1/emergency-stop").status_code == 403


def test_old_process_token_cannot_authorize_a_new_app(client, tmp_path):
    old_token = client.get("/api/v1/desktop-session", headers={"X-RedPath-Bootstrap": "1"}).json()["csrf_token"]
    paths = AppPaths.from_environment(str(tmp_path / "next-process"))
    app = create_app(Settings(database_url=f"sqlite:///{paths.database_file}"), paths)
    with TestClient(app, base_url="http://127.0.0.1:8000") as next_client:
        new_token = next_client.get("/api/v1/desktop-session", headers={"X-RedPath-Bootstrap": "1"}).json()["csrf_token"]
        assert old_token != new_token
        assert next_client.post("/api/v1/emergency-stop", headers={"Origin": "http://127.0.0.1:8000", "X-RedPath-Session": old_token}).status_code == 403
