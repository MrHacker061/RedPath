import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import Event, Lock

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from redpath import __version__
from redpath.config import Settings, get_settings
from redpath.contracts import ComponentHealth, HealthResponse
from redpath.database import Base, create_database, migrate_database
from redpath.execution_api import router as execution_router
from redpath.execution_fence import ExecutionFence
from redpath.nmap_parser import parse_nmap_xml_bytes
from redpath.runtime import AppPaths
from redpath.approval_api import router as approval_router
from redpath.session_api import router as session_router
from redpath.setup_api import router as setup_router
from redpath.stop_api import router as stop_router
from redpath_ai import RuleBasedProvider
from redpath_kali.wsl_actions import WSLActionDispatcher
from redpath_setup.ollama import OllamaSetup
from redpath_setup.wsl import WslSetup
import redpath.models  # noqa: F401


def create_app(
    settings: Settings | None = None, paths: AppPaths | None = None
) -> FastAPI:
    config = settings or get_settings()
    app_paths = paths or AppPaths.from_environment()
    if not app_paths.frontend_dir.is_dir():
        raise RuntimeError("RedPath frontend directory is missing")
    app_paths.ensure()
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
    app.state.paths = app_paths
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.llm_provider = RuleBasedProvider()
    app.state.execution_fence = ExecutionFence()
    app.state.ollama_setup = OllamaSetup(app_paths.download_dir)
    app.state.wsl_setup = WslSetup(app_paths.wsl_dir)
    app.state.action_dispatcher = WSLActionDispatcher(app.state.wsl_setup)
    app.state.setup_lock = Lock()
    app.state.setup_cancellations = {
        "ollama": Event(), "model": Event(), "wsl": Event(), "kali": Event(),
    }
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
    app.include_router(stop_router)
    app.include_router(execution_router)
    app.include_router(setup_router)
    app.mount("/assets", StaticFiles(directory=app_paths.frontend_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def desktop_shell() -> FileResponse:
        return FileResponse(app_paths.frontend_dir / "index.html")

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
