from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from redpath.runtime import AppPaths
from redpath_ai.models import DEFAULT_MODEL, selected_model
from redpath_ai.providers import DOCKER_HOST_OLLAMA_URL, LOOPBACK_OLLAMA_URL


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
    # Which local AI model to use: REDPATH_MODEL in .env. Choices are in redpath_ai/models.py.
    model: str = DEFAULT_MODEL
    # Where Ollama is: REDPATH_OLLAMA_URL. Leave it unset for the native app.
    # Only docker-compose.yml sets it, to the Docker host address, which the
    # provider accepts only when a container marker exists (redpath_ai/providers.py).
    ollama_url: str = LOOPBACK_OLLAMA_URL

    @field_validator("host")
    @classmethod
    def require_loopback(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("RedPath must bind to a loopback address")
        return value

    @field_validator("model")
    @classmethod
    def require_known_model(cls, value: str) -> str:
        selected_model(value)  # raises with the list of valid choices
        return value

    @field_validator("ollama_url")
    @classmethod
    def require_known_ollama_url(cls, value: str) -> str:
        # Catches typos at startup. The provider still makes the final
        # container check, so this list alone does not allow the Docker address.
        if value not in (LOOPBACK_OLLAMA_URL, DOCKER_HOST_OLLAMA_URL):
            raise ValueError(
                f"REDPATH_OLLAMA_URL must be {LOOPBACK_OLLAMA_URL} or {DOCKER_HOST_OLLAMA_URL}"
            )
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

