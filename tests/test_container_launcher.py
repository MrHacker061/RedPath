"""The container launcher binds all interfaces only inside a container."""

from types import SimpleNamespace

import pytest
import uvicorn

from redpath import app as app_module
from redpath import container


def test_container_launcher_refuses_to_run_outside_a_container(monkeypatch, tmp_path):
    monkeypatch.setattr(container, "CONTAINER_MARKERS", (tmp_path / ".dockerenv",))
    monkeypatch.setattr(app_module, "create_app", lambda *_a, **_k: pytest.fail("app built outside a container"))
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: pytest.fail("bound outside a container"))
    with pytest.raises(SystemExit, match="must run inside a container"):
        container.main()


def test_container_launcher_serves_the_configured_port_on_all_container_interfaces(monkeypatch, tmp_path):
    marker = tmp_path / ".dockerenv"
    marker.touch()
    settings = SimpleNamespace(port=8123)
    built, served = object(), {}
    monkeypatch.setattr(container, "CONTAINER_MARKERS", (marker,))
    monkeypatch.setattr(container, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "create_app", lambda config: built if config is settings else pytest.fail("wrong settings"))
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: served.update(app=app, **options))
    container.main()
    assert served["app"] is built
    assert (served["host"], served["port"], served["workers"]) == ("0.0.0.0", 8123, 1)
