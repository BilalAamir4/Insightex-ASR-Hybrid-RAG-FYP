"""FastAPI app factory. The API only enqueues and reads jobs; the worker process runs the stages."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from insightex.api.routers import ingest, jobs, lectures
from insightex.core.config import Settings, get_settings, repo_root
from insightex.ingest.settings import IngestSettings
from insightex.jobs import db
from insightex.jobs.workspace import Workspaces

log = logging.getLogger(__name__)


def create_app(app_settings: Settings | None = None, frontend_dir: Path | None = None) -> FastAPI:
    app_settings = app_settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = db.open_connection(app_settings.jobs.db_path, app_settings.jobs.busy_timeout_ms)
        try:
            db.migrate(conn)  # idempotent and safe next to a running worker
        finally:
            conn.close()
        yield
        db.close_thread_connections()

    app = FastAPI(title="Insightex", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.ingest_settings = IngestSettings.from_settings(app_settings)
    app.state.workspaces = Workspaces(app_settings.jobs.workspaces_dir)
    app.state.touch_times = {}  # workspace id -> time.monotonic() of the last cache touch
    app.state.touch_lock = threading.Lock()
    app.include_router(ingest.router)
    app.include_router(jobs.router)
    app.include_router(lectures.router)

    frontend = frontend_dir or repo_root() / "frontend"
    if frontend.is_dir():
        # Mounted last so /api/* routes win. Plain static files: no build step.
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
