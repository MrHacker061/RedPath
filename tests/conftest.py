"""Isolated storage and explicit security for in-process application tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from redpath.config import Settings, get_settings
from redpath.local_security import LocalSecurityConfig


@pytest.fixture(autouse=True)
def isolated_application_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # LOCALAPPDATA is the sole Windows environment input read by AppPaths.
    # Test-local monkeypatches and explicit Settings/AppPaths arguments still win.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.delenv("REDPATH_DATABASE_URL", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture
def security_config():
    return LocalSecurityConfig(port=43210, csrf_token="a" * 43)


@pytest.fixture
def client_options(security_config):
    return {"base_url": security_config.origin, "headers": {
        "Origin": security_config.origin, "X-RedPath-Session": security_config.csrf_token,
    }}
