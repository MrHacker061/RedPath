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

    def inspect_service(self) -> SetupStage:
        return SetupStage("ollama", "ready", "OLLAMA_READY", "Local Ollama is ready.")

    def inspect_model(self) -> SetupStage:
        return SetupStage("model", "needs_attention", "MODEL_MISSING", "Pinned model is missing.")

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

    def inspect_wsl(self) -> SetupStage:
        return SetupStage("wsl", "ready", "WSL_READY", "WSL2 is ready.")

    def inspect_kali(self) -> SetupStage:
        return SetupStage("kali", "needs_attention", "KALI_NOT_INSTALLED", "Managed Kali is missing.")

    def enable(self, consent: bool, cancelled: Event) -> SetupStage:
        self.enables.append(consent)
        assert not cancelled.is_set()
        return SetupStage("wsl", "ready", "KALI_READY", "WSL2 is ready.")

    def install_kali(self, consent: bool, _progress, cancelled: Event) -> SetupStage:
        self.installs.append((consent, cancelled))
        return SetupStage("kali", "ready", "KALI_READY", "Managed Kali is ready.")


@pytest.fixture
def app(tmp_path, security_config):
    value = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'setup.db'}"), security=security_config)
    value.state.ollama_setup = FakeOllamaSetup()
    value.state.wsl_setup = FakeWslSetup()
    return value


@pytest.fixture
def client(app, client_options):
    with TestClient(app, **client_options) as value:
        yield value


def test_setup_returns_only_fixed_component_states(client):
    response = client.get("/api/v1/setup")

    assert response.status_code == 200
    assert set(response.json()["components"]) == {"ollama", "model", "wsl", "kali"}
    assert response.json()["components"]["ollama"]["code"] == "OLLAMA_READY"
    assert response.json()["components"]["model"]["code"] == "MODEL_MISSING"
    assert response.json()["components"]["wsl"]["code"] == "WSL_READY"
    assert response.json()["components"]["kali"]["code"] == "KALI_NOT_INSTALLED"


def test_setup_discloses_pinned_downloads_before_consent(client, app):
    response = client.get("/api/v1/setup")

    assert response.status_code == 200
    components = response.json()["components"]
    assert {
        name: (stage["version"], stage["download_size_bytes"])
        for name, stage in components.items()
    } == {
        "ollama": ("0.34.0", 1_574_272_976),
        "model": ("qwen2.5:7b-instruct-q4_K_M", 4_683_087_332),
        "kali": ("2026.2", 247_857_686),
        "wsl": (None, None),
    }
    assert app.state.ollama_setup.installs == []
    assert app.state.ollama_setup.pulls == []
    assert app.state.wsl_setup.enables == []
    assert app.state.wsl_setup.installs == []


@pytest.mark.parametrize("component", ["ollama", "model", "wsl", "kali"])
def test_setup_metadata_stays_fixed_for_repair_and_cancel(client, app, component):
    expected = client.get("/api/v1/setup").json()["components"][component]
    responses = [client.post(f"/api/v1/setup/{component}/repair", json={"consent": True}),
                 client.post(f"/api/v1/setup/{component}/cancel")]
    active = app.state.setup_operations.begin(component)
    assert active is not None
    try:
        responses.append(client.post(f"/api/v1/setup/{component}/cancel"))
    finally:
        app.state.setup_operations.finish(component, active)

    for response in responses:
        assert response.status_code == 200
        assert response.json()["version"] == expected["version"]
        assert response.json()["download_size_bytes"] == expected["download_size_bytes"]


def test_setup_repair_requires_exact_consent_for_fixed_component(client, app):
    accepted = client.post("/api/v1/setup/model/repair", json={"consent": True})

    assert accepted.status_code == 200
    assert app.state.ollama_setup.pulls[0][0] is True
    for body in ({}, {"consent": False}, {"consent": 1}, {"consent": True, "extra": "no"}):
        assert client.post("/api/v1/setup/model/repair", json=body).status_code == 422


def test_setup_repair_routes_wsl_and_kali_to_their_independent_services(client, app):
    assert client.post("/api/v1/setup/wsl/repair", json={"consent": True}).status_code == 200
    assert client.post("/api/v1/setup/kali/repair", json={"consent": True}).status_code == 200

    assert app.state.wsl_setup.enables == [True]
    assert len(app.state.wsl_setup.installs) == 1


def test_setup_repair_rejects_unknown_component(client):
    response = client.post("/api/v1/setup/shell/repair", json={"consent": True})

    assert response.status_code == 404


def test_setup_cancel_only_targets_fixed_component_event(client, app):
    response = client.post("/api/v1/setup/kali/cancel")

    assert response.status_code == 200
    assert response.json()["code"] == "NO_ACTIVE_OPERATION"
    assert client.post("/api/v1/setup/shell/cancel").status_code == 404
    assert client.post("/api/v1/setup/kali/cancel", json={"component": "shell"}).status_code == 422


def test_setup_operation_controller_binds_cancellation_to_only_the_active_event():
    from redpath.setup_api import SetupOperationController

    controller = SetupOperationController()
    first = controller.begin("ollama")
    assert first is not None
    assert controller.cancel("model") is False
    assert controller.cancel("ollama") is True
    assert first.is_set()
    controller.finish("ollama", first)

    second = controller.begin("ollama")
    assert second is not None
    assert second is not first
    assert not second.is_set()
    controller.finish("ollama", first)
    assert controller.cancel("ollama") is True
    assert second.is_set()
    controller.finish("ollama", second)


def test_setup_operation_completion_reports_when_cancel_wins_the_same_generation():
    from redpath.setup_api import SetupOperationController

    controller = SetupOperationController()
    event = controller.begin("ollama")
    assert event is not None
    assert controller.cancel("ollama") is True

    assert controller.complete("ollama", event) is True
    assert controller.cancel("ollama") is False


def test_setup_operation_completion_wins_before_a_later_cancel_request():
    from redpath.setup_api import SetupOperationController

    controller = SetupOperationController()
    event = controller.begin("ollama")
    assert event is not None

    assert controller.complete("ollama", event) is False
    assert controller.cancel("ollama") is False


def test_cancel_route_sets_only_the_current_active_event(client, app):
    active = app.state.setup_operations.begin("model")
    assert active is not None
    try:
        response = client.post("/api/v1/setup/model/cancel")
    finally:
        app.state.setup_operations.finish("model", active)

    assert response.status_code == 200
    assert response.json()["code"] == "CANCEL_REQUESTED"
    assert active.is_set()


def test_repair_returns_cancelled_when_active_cancel_wins_just_before_ready(client, app):
    def install(_consent, _progress, _event):
        assert app.state.setup_operations.cancel("ollama") is True
        return SetupStage("ollama", "ready", "OLLAMA_READY", "Local Ollama is ready.")

    app.state.ollama_setup.install = install
    response = client.post("/api/v1/setup/ollama/repair", json={"consent": True})

    assert response.status_code == 200
    assert response.json()["status"] == "needs_attention"
    assert response.json()["code"] == "CANCELLED"


def test_diagnostics_exclude_raw_component_output(client, app):
    app.state.ollama_setup.inspect_service = lambda: SetupStage(
        "ollama", "failed", "OLLAMA_UNAVAILABLE", "SECRET_INSTALLER_OUTPUT"
    )

    payload = client.get("/api/v1/diagnostics").json()

    assert set(payload) == {"version", "components", "data_path", "codes"}
    assert set(payload["components"]) == {"ollama", "model", "wsl", "kali"}
    assert "SECRET_INSTALLER_OUTPUT" not in str(payload)
    assert "output" not in str(payload).lower()


def test_diagnostics_maps_unknown_component_codes_to_a_stable_generic_code(client, app):
    app.state.ollama_setup.inspect_service = lambda: SetupStage(
        "ollama", "failed", "UNTRUSTED_SECRET_CODE", "SECRET_COMPONENT_TEXT"
    )

    payload = client.get("/api/v1/diagnostics").json()

    assert payload["components"]["ollama"]["code"] == "COMPONENT_STATUS_UNAVAILABLE"
    assert "UNTRUSTED_SECRET_CODE" not in str(payload)
    assert "SECRET_COMPONENT_TEXT" not in str(payload)
