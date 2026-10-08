"""Per-request helpers: the settings, the workspaces root and this thread's database connection."""

from __future__ import annotations

import sqlite3

from fastapi import Request

from insightex.core.config import Settings
from insightex.jobs import db
from insightex.jobs.workspace import Workspaces


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def workspaces_of(request: Request) -> Workspaces:
    return request.app.state.workspaces


def connection(settings: Settings) -> sqlite3.Connection:
    """The calling thread's connection (sync handlers and `run_in_threadpool` bodies each get their own)."""
    return db.connect(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
