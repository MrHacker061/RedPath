from pathlib import Path

import pytest

from redpath.app import create_app
from redpath.config import Settings
from redpath.runtime import AppPaths


def test_app_paths_keep_mutable_data_outside_bundle(tmp_path):
    paths = AppPaths.from_environment(str(tmp_path / "Local"), tmp_path / "bundle")

    paths.ensure()

    assert paths.data_dir == tmp_path / "Local" / "RedPath"
    assert paths.database_file.parent == paths.data_dir
    assert paths.frontend_dir == tmp_path / "bundle" / "frontend"
    assert paths.log_dir.is_dir()
    assert paths.download_dir.is_dir()
    assert paths.wsl_dir.is_dir()


def test_create_app_rejects_missing_frontend_directory(tmp_path):
    paths = AppPaths.from_environment(str(tmp_path / "Local"), tmp_path / "bundle")

    with pytest.raises(RuntimeError, match="RedPath frontend directory is missing"):
        create_app(Settings(database_url=f"sqlite:///{tmp_path / 'redpath.db'}"), paths)
