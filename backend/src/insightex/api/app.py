"""FastAPI app factory. Later features add routers under insightex.api.routers and include them here."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from insightex.api.routers import ingest, lectures
from insightex.core.config import repo_root
from insightex.ingest.settings import IngestSettings
from insightex.jobs.ingest_jobs import IngestJobs, Runner, recover_interrupted

log = logging.getLogger(__name__)


def create_app(
    settings: IngestSettings | None = None,
    runner: Runner | None = None,
    frontend_dir: Path | None = None,
) -> FastAPI:
    settings = settings or IngestSettings.from_config()
    jobs = IngestJobs(settings, runner=runner)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        recover_interrupted(settings.lectures_dir)
        try:
            yield
        finally:
            jobs.shutdown()

    app = FastAPI(title="Insightex", lifespan=lifespan)
    app.state.settings = settings
    app.state.jobs = jobs
    app.include_router(ingest.router)
    app.include_router(lectures.router)

    frontend = frontend_dir or repo_root() / "frontend"
    if frontend.is_dir():
        # Mounted last so /api/* routes win. Plain static files: no build step.
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
