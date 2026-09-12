"""Test harness defaults cannot use the developer's application-data store."""

import os
import socket
import subprocess
from pathlib import Path

import anyio
import pytest

from redpath.app import create_app
from redpath.config import Settings, get_settings
from redpath.runtime import AppPaths


def test_default_app_storage_is_confined_to_this_tests_temporary_directory(tmp_path, monkeypatch):
    paths = AppPaths.from_environment()
    # Fail before creating an app or directory if the isolation fixture is absent.
    assert paths.data_dir.is_relative_to(tmp_path)
    assert Path(os.environ["LOCALAPPDATA"]).is_relative_to(tmp_path)
    assert get_settings.cache_info().currsize == 0
    assert get_settings().database_url == f"sqlite:///{paths.database_file}"

    mkdir = Path.mkdir
    touched = []

    def temporary_mkdir(path, *args, **kwargs):
        assert path.resolve().is_relative_to(tmp_path.resolve())
        touched.append(path)
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", temporary_mkdir)
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("default app contacted the network"))
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pytest.fail("default app launched a host process"))
    app = create_app()

    async def startup_and_shutdown():
        async with app.router.lifespan_context(app):
            assert paths.database_file.is_file()
            assert Path(app.state.engine.url.database) == paths.database_file

    anyio.run(startup_and_shutdown)
    assert app.state.paths == paths
    assert {paths.data_dir, paths.log_dir, paths.download_dir, paths.wsl_dir} <= set(touched)


def test_test_specific_environment_overrides_are_preserved(tmp_path, monkeypatch):
    override = tmp_path / "explicit-local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(override))
    assert AppPaths.from_environment().data_dir == override / "RedPath"
    assert get_settings().database_url == f"sqlite:///{override / 'RedPath' / 'redpath.db'}"
    database = f"sqlite:///{tmp_path / 'explicit-database.db'}"
    monkeypatch.setenv("REDPATH_DATABASE_URL", database)
    assert Settings().database_url == database


def test_explicit_settings_and_paths_are_preserved(tmp_path):
    paths = AppPaths.from_environment(str(tmp_path / "explicit-paths"))
    database = f"sqlite:///{tmp_path / 'explicit-settings.db'}"
    app = create_app(Settings(database_url=database), paths)
    try:
        assert app.state.paths == paths
        assert str(app.state.engine.url) == database
    finally:
        app.state.engine.dispose()


def test_settings_cache_does_not_cross_test_boundaries(tmp_path):
    assert get_settings.cache_info().currsize == 0
    assert Path(get_settings().database_url.removeprefix("sqlite:///")).is_relative_to(tmp_path)


def test_implicit_dotenv_cannot_redirect_storage_but_explicit_file_is_supported(tmp_path, monkeypatch):
    database = f"sqlite:///{tmp_path / 'dotenv-override.db'}"
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"REDPATH_DATABASE_URL={database}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert Settings().database_url == f"sqlite:///{AppPaths.from_environment().database_file}"
    assert Settings(_env_file=dotenv).database_url == database
