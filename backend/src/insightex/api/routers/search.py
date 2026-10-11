"""POST /api/lectures/{id}/search: a question -> the best windows of one lecture (M5, ADR-0043, ADR-0044).

The question is encoded in this process on the CPU in float32 (`retrieval.query_*`): at query time the GPU belongs
to Ollama. The model loads on the first question and stays loaded; questions are encoded one at a time. Hits carry
times and scores only: window text is internal evidence and is never returned (ADR-0041).
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from insightex.api.deps import settings_of, workspaces_of
from insightex.api.errors import error_response
from insightex.index.stage import IndexStage
from insightex.index.store import LectureIndex, load_index
from insightex.jobs.workspace import validate_workspace_id
from insightex.retrieval import search as s

router = APIRouter(prefix="/api/lectures")

_MAX_K = 100


class SearchBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int | None = Field(default=None, ge=1, le=_MAX_K, description="windows to return (default: retrieval.candidates)")
    dedupe: bool = Field(default=True, description="drop windows overlapping a better one (ADR-0043)")


def make_query_encoder(settings) -> s.QueryEncoder:
    """The process-wide question encoder. Tests monkeypatch this name to avoid loading BGE-M3."""
    return s.QueryEncoder(settings)


class _State:
    """Per-app search state: the lazily created encoder, the lock that serialises encoding, an index cache."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.encoder = None
        self.indexes: dict[Path, LectureIndex] = {}  # keyed by the index directory, whose name holds the stage key


def _state(request: Request) -> _State:
    if not hasattr(request.app.state, "search"):
        request.app.state.search = _State()
    return request.app.state.search


@router.post("/{lecture_id}/search")
def search_lecture(lecture_id: str, body: SearchBody, request: Request):
    settings, workspaces = settings_of(request), workspaces_of(request)
    try:
        validate_workspace_id(lecture_id)
        directory = workspaces.stage_output_dir(lecture_id, IndexStage.name)
    except ValueError:
        return error_response("LECTURE_NOT_FOUND", "This lecture isn't in your library.", 404)
    if directory is None:
        if workspaces.stage_output_dir(lecture_id, "normalise") is None:
            return error_response("LECTURE_NOT_FOUND", "This lecture isn't in your library.", 404)
        return error_response("LECTURE_NOT_SEARCHABLE", "This lecture isn't ready for search yet.", 409)
    state = _state(request)
    with state.lock:
        index = state.indexes.get(directory)
        if index is None:
            index = state.indexes[directory] = load_index(directory)
        try:
            s.check_compatible(settings, index)
        except s.IndexModelMismatch:
            return error_response("LECTURE_NOT_SEARCHABLE", "This lecture's search index is out of date. Add it again.", 409)
        if state.encoder is None:
            state.encoder = make_query_encoder(settings)
        vectors = state.encoder.encode([body.question])
    k = body.k or settings.retrieval.candidates
    hits = s.search(index, vectors, k)[0]
    if body.dedupe:
        hits = s.dedupe(hits, settings.retrieval.dedupe_min_overlap_s)
    return {
        "lecture_id": lecture_id,
        "index_config_id": index.meta.get("config_id"),
        "hits": [{"rank": h.rank, "window_id": h.window_id, "start": h.start, "end": h.end, "score": h.score} for h in hits],
    }
