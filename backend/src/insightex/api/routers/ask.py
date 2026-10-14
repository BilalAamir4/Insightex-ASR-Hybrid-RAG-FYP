"""POST /api/lectures/{id}/ask and /warm-up (M6, ADR-0047, ADR-0046).

`ask` turns a question into at most `retrieval.citations` citations: rank, window time range and the time to seek to.
No transcript text, scores or window ids are returned. The question and its rewrite are never logged or stored: one
JSON line with timings and the fallback reason is written per question (logger `insightex.ask`).
"""

from __future__ import annotations

import json
import logging
import threading
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from insightex.api.deps import settings_of, workspaces_of
from insightex.api.errors import error_response
from insightex.api.routers import search as search_router
from insightex.index.stage import IndexStage, index_searchable
from insightex.jobs.workspace import validate_workspace_id
from insightex.retrieval import ask as ask_flow
from insightex.retrieval import rewrite as rw
from insightex.retrieval import search as s

router = APIRouter(prefix="/api/lectures")
metrics = logging.getLogger("insightex.ask")  # JSON lines of counts and timings only
log = logging.getLogger(__name__)

_NOT_FOUND = ("LECTURE_NOT_FOUND", "This lecture isn't in your library.", 404)
_NOT_SEARCHABLE = ("LECTURE_NOT_SEARCHABLE", "This lecture isn't ready for search yet.", 409)


class AskBody(BaseModel):
    question: str


class _Warm:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False


def _warm_state(app) -> _Warm:
    if not hasattr(app.state, "warm"):
        app.state.warm = _Warm()
    return app.state.warm


def _prompt(app):
    """The pinned rewrite prompt, read once per app (None: rewrite disabled)."""
    if not hasattr(app.state, "rewrite_prompt"):
        app.state.rewrite_prompt = rw.load_prompt(app.state.settings)
    return app.state.rewrite_prompt


def _index_dir(request: Request, lecture_id: str):
    """The lecture's index directory when it is searchable, else the (code, message, status) of the error."""
    settings, workspaces = settings_of(request), workspaces_of(request)
    try:
        validate_workspace_id(lecture_id)
        directory = workspaces.stage_output_dir(lecture_id, IndexStage.name)
        known = workspaces.stage_output_dir(lecture_id, "normalise") is not None
    except ValueError:
        return None, _NOT_FOUND
    if not known:
        return None, _NOT_FOUND
    if directory is None or not index_searchable(directory, settings):
        return None, _NOT_SEARCHABLE
    return directory, None


@router.post("/{lecture_id}/ask")
def ask_lecture(lecture_id: str, body: AskBody, request: Request):
    t0 = time.perf_counter()
    settings = settings_of(request)
    question = body.question.strip()
    if not question:
        return error_response("QUESTION_EMPTY", "Type a question first.", 400)
    if len(question) > settings.retrieval.max_question_chars:
        return error_response("QUESTION_TOO_LONG", f"Keep the question under {settings.retrieval.max_question_chars} characters.", 400)
    directory, err = _index_dir(request, lecture_id)
    if err:
        return error_response(*err)
    index = search_router.load_cached_index(request.app, directory)
    try:
        s.check_compatible(settings, index)
    except s.IndexModelMismatch:
        return error_response(*_NOT_SEARCHABLE)
    result = ask_flow.ask(
        settings, index, question,
        encode=lambda text: search_router.encode_text(request.app, text),
        rewriter=lambda q: rw.rewrite_question(settings, _prompt(request.app), q),
    )
    r = result.rewrite
    metrics.info(json.dumps({
        "event": "ask", "total_ms": round((time.perf_counter() - t0) * 1000, 1),
        "rewrite_ms": None if r.ms is None else round(r.ms, 1), "search_ms": round(result.search_ms, 1),
        "rewrite_used": r.rewrite is not None, "fallback_reason": None if r.fallback_reason is None else str(r.fallback_reason),
        "citations": len(result.citations)}))
    return {
        "lecture_id": lecture_id,
        "index_config_id": index.meta.get("config_id"),
        "citations": [{"rank": c.rank, "start": c.start, "end": c.end, "seek_s": c.seek_s} for c in result.citations],
        "rewrite": {"used": r.rewrite is not None, "fallback_reason": None if r.fallback_reason is None else str(r.fallback_reason)},
    }


def _run_warm_up(app) -> None:
    state = _warm_state(app)
    t0 = time.perf_counter()
    try:
        result, reason = rw.warm_up(app.state.settings)
    except Exception:  # a background thread must not die silently
        log.exception("warm-up failed")
        result, reason = "skipped", "error"
    finally:
        with state.lock:
            state.running = False
    metrics.info(json.dumps({"event": "warm_up", "result": result, "reason": None if reason is None else str(reason),
                             "ms": round((time.perf_counter() - t0) * 1000, 1)}))


@router.post("/{lecture_id}/warm-up", status_code=202)
def warm_up_lecture(lecture_id: str, request: Request):
    """Called when the player opens a searchable lecture: load the rewrite model in the background."""
    _, err = _index_dir(request, lecture_id)
    if err:
        return error_response(*err)
    state = _warm_state(request.app)
    with state.lock:
        if state.running:
            return {"state": "skipped", "reason": "already_warming"}
        state.running = True
    threading.Thread(target=_run_warm_up, args=(request.app,), daemon=True, name="warm-up").start()
    return {"state": "started", "reason": None}
