from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from redpath.runtime import AppPaths


def _default_database_url() -> str:
    return f"sqlite:///{AppPaths.from_environment().database_file}"


class Settings(BaseSettings):
    """Local-only backend configuration. Secrets have no defaults."""

    model_config = SettingsConfigDict(env_prefix="REDPATH_", env_file=".env", extra="ignore")
    app_name: str = "RedPath"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    database_url: str = Field(default_factory=_default_database_url)
    log_level: str = "INFO"

    @field_validator("host")
    @classmethod
    def require_loopback(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("RedPath must bind to a loopback address")
        return value

    @field_validator("database_url")
    @classmethod
    def require_sqlite(cls, value: str) -> str:
        if not value.startswith("sqlite:///"):
            raise ValueError("Milestone 1 supports SQLite only")
        return value

    def ensure_local_directories(self) -> None:
        path = self.database_url.removeprefix("sqlite:///")
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

