import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    database_file: Path
    log_dir: Path
    download_dir: Path
    wsl_dir: Path
    frontend_dir: Path

    @classmethod
    def from_environment(
        cls, local_app_data: str | None = None, bundle_root: Path | None = None
    ) -> "AppPaths":
        data = Path(local_app_data or os.environ["LOCALAPPDATA"]) / "RedPath"
        bundle = Path(bundle_root or getattr(sys, "_MEIPASS", Path(__file__).parents[1]))
        return cls(
            data,
            data / "redpath.db",
            data / "logs",
            data / "downloads",
            data / "wsl",
            bundle / "frontend",
        )

    def ensure(self) -> None:
        for path in (self.data_dir, self.log_dir, self.download_dir, self.wsl_dir):
            path.mkdir(parents=True, exist_ok=True)
