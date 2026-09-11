import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from redpath import __version__
from redpath.config import Settings, get_settings
from redpath.contracts import ComponentHealth, HealthResponse
from redpath.database import Base, create_database, migrate_database
from redpath.execution_api import router as execution_router
from redpath.nmap_parser import parse_nmap_xml_bytes
from redpath.approval_api import router as approval_router
from redpath.session_api import router as session_router
from redpath_ai import RuleBasedProvider
from redpath_kali import KaliActionDispatcher, KaliVMError, KaliVMManager
import redpath.models  # noqa: F401


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    engine, session_factory = create_database(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        migrate_database(engine)
        yield
        engine.dispose()

    app = FastAPI(title=config.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = config
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.llm_provider = RuleBasedProvider()
    try:
        app.state.action_dispatcher = KaliActionDispatcher(
            KaliVMManager(Path(__file__).resolve().parents[1])
        )
    except KaliVMError:
        logging.getLogger(__name__).exception("Kali action dispatcher is unavailable")
        app.state.action_dispatcher = None
    def parse_import(xml_text: str, session_id: str, target_id: str, scan_import_id: str, target_address: str):
        result = parse_nmap_xml_bytes(
            xml_text.encode("utf-8"), scan_id=scan_import_id,
            session_id=session_id, target_id=target_id,
            max_bytes=1_000_000,
        )
        if len(result.hosts) != 1 or target_address not in result.hosts[0].addresses:
            raise ValueError("Imported evidence must contain exactly the authorized target")
        return result.findings

    app.state.nmap_parser = parse_import
    app.include_router(session_router)
    app.include_router(approval_router)
    app.include_router(execution_router)

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
