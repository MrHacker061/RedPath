from threading import Event

import pytest
from fastapi.testclient import TestClient

from redpath.app import create_app
from redpath.config import Settings
from redpath_setup.state import SetupStage


class FakeOllamaSetup:
    def __init__(self) -> None:
        self.installs: list[tuple[bool, Event]] = []
        self.pulls: list[tuple[bool, Event]] = []

    def inspect(self) -> SetupStage:
        return SetupStage("ollama", "ready", "OK", "Local Ollama is ready.")

    def install(self, consent: bool, _progress, cancelled: Event) -> SetupStage:
        self.installs.append((consent, cancelled))
        return SetupStage("ollama", "ready", "OK", "Local Ollama is ready.")

    def pull_model(self, consent: bool, _progress, cancelled: Event) -> SetupStage:
        self.pulls.append((consent, cancelled))
        return SetupStage("ollama", "ready", "OK", "Pinned model is ready.")


class FakeWslSetup:
    def __init__(self) -> None:
        self.enables: list[bool] = []
        self.installs: list[tuple[bool, Event]] = []

    def inspect(self) -> SetupStage:
        return SetupStage("wsl", "ready", "KALI_READY", "Managed Kali is ready.")

    def enable(self, consent: bool) -> SetupStage:
        self.enables.append(consent)
        return SetupStage("wsl", "ready", "KALI_READY", "WSL2 is ready.")

    def install_kali(self, consent: bool, _progress, cancelled: Event) -> SetupStage:
        self.installs.append((consent, cancelled))
        return SetupStage("kali", "ready", "KALI_READY", "Managed Kali is ready.")


@pytest.fixture
def app(tmp_path):
    value = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'setup.db'}"))
    value.state.ollama_setup = FakeOllamaSetup()
    value.state.wsl_setup = FakeWslSetup()
    return value


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


def test_setup_returns_only_fixed_component_states(client):
    response = client.get("/api/v1/setup")

    assert response.status_code == 200
    assert set(response.json()["components"]) == {"ollama", "model", "wsl", "kali"}


def test_setup_repair_requires_exact_consent_for_fixed_component(client, app):
    accepted = client.post("/api/v1/setup/model/repair", json={"consent": True})

    assert accepted.status_code == 200
    assert app.state.ollama_setup.pulls[0][0] is True
    for body in ({}, {"consent": False}, {"consent": 1}, {"consent": True, "extra": "no"}):
        assert client.post("/api/v1/setup/model/repair", json=body).status_code == 422


def test_setup_repair_rejects_unknown_component(client):
    response = client.post("/api/v1/setup/shell/repair", json={"consent": True})

    assert response.status_code == 404


def test_setup_cancel_only_targets_fixed_component_event(client, app):
    response = client.post("/api/v1/setup/kali/cancel")

    assert response.status_code == 200
    assert app.state.setup_cancellations["kali"].is_set()
    assert not app.state.setup_cancellations["ollama"].is_set()
    assert client.post("/api/v1/setup/shell/cancel").status_code == 404
    assert client.post("/api/v1/setup/kali/cancel", json={"component": "shell"}).status_code == 422


def test_setup_repair_fails_closed_while_another_local_operation_holds_lock(client, app):
    assert app.state.setup_lock.acquire(blocking=False)
    try:
        response = client.post("/api/v1/setup/ollama/repair", json={"consent": True})
    finally:
        app.state.setup_lock.release()

    assert response.status_code == 409
    assert app.state.ollama_setup.installs == []


def test_diagnostics_exclude_raw_component_output(client, app):
    app.state.ollama_setup.inspect = lambda: SetupStage(
        "ollama", "failed", "OLLAMA_UNAVAILABLE", "SECRET_INSTALLER_OUTPUT"
    )

    payload = client.get("/api/v1/diagnostics").json()

    assert set(payload) == {"version", "components", "data_path", "codes"}
    assert set(payload["components"]) == {"ollama", "model", "wsl", "kali"}
    assert "SECRET_INSTALLER_OUTPUT" not in str(payload)
    assert "output" not in str(payload).lower()
