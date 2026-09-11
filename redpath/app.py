import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from redpath import __version__
from redpath.config import Settings, get_settings
from redpath.contracts import ComponentHealth, HealthResponse
from redpath.database import Base, create_database
from redpath.session_api import router as session_router
import redpath.models  # noqa: F401


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    engine, session_factory = create_database(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title=config.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = config
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.nmap_parser = None
    app.include_router(session_router)

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return HealthResponse(
                status="ok",
                service="redpath-api",
                version=__version__,
                database="ok",
                services={
                    "fastapi": ComponentHealth(status="healthy"),
                    "ollama": ComponentHealth(status="unknown"),
                    "kali": ComponentHealth(status="unknown"),
                },
            )
        except Exception:
            logging.getLogger(__name__).exception("Database health check failed")
            return HealthResponse(
                status="degraded",
                service="redpath-api",
                version=__version__,
                database="unavailable",
                services={
                    "fastapi": ComponentHealth(status="degraded"),
                    "ollama": ComponentHealth(status="unknown"),
                    "kali": ComponentHealth(status="unknown"),
                },
            )

    return app


app = create_app()
