"""Question -> citations (ADR-0047): rewrite, search both ways, fuse, de-duplicate, take the top few.

Pure of the web layer: the caller supplies the encoder lock and the rewriter. Nothing here logs the question.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from insightex.core.config import Settings
from insightex.index.store import LectureIndex
from insightex.retrieval import search as s
from insightex.retrieval.rewrite import RewriteOutcome


@dataclass(frozen=True)
class Citation:
    rank: int
    start: float  # window start, seconds
    end: float  # window end, seconds
    seek_s: float  # start of the first transcript segment inside the window (ADR-0044)


@dataclass(frozen=True)
class AskResult:
    citations: list[Citation]
    rewrite: RewriteOutcome
    search_ms: float
    ranked: list[tuple[int, float]]  # the full ranking the citations come from: (window id, score), best first


def citations_from(settings: Settings, index: LectureIndex, ranked: list[tuple[int, float]]) -> list[Citation]:
    """De-duplicate the ranking, then take the top `retrieval.citations` (ADR-0043)."""
    hits = [s.Hit(r, wid, index.windows[wid]["start"], index.windows[wid]["end"], score) for r, (wid, score) in enumerate(ranked, start=1)]
    kept = s.dedupe(hits, settings.retrieval.dedupe_min_overlap_s)[: settings.retrieval.citations]
    out = []
    for h in kept:
        w = index.windows[h.window_id]
        out.append(Citation(h.rank, w["start"], w["end"], max(w["first_segment_start"], w["start"])))
    return out


def ask(settings: Settings, index: LectureIndex, question: str, *, encode: Callable[[str], Any],
        rewriter: Callable[[str], RewriteOutcome]) -> AskResult:
    """`encode(text)` returns a (1, dim) unit vector (the caller serialises access to the model); `rewriter(question)`
    returns the rewrite or the reason there is none."""
    outcome = rewriter(question)
    t0 = time.perf_counter()
    original = s.rank_all(index, encode(question))
    rankings = [[h.window_id for h in original]]
    scores = {h.window_id: h.score for h in original}
    if outcome.rewrite is not None:
        rewritten = s.rank_all(index, encode(outcome.rewrite))
        rankings.append([h.window_id for h in rewritten])
        ranked = s.fuse(rankings, settings.retrieval.rrf_k)
    else:
        ranked = [(wid, scores[wid]) for wid in rankings[0]]
    cites = citations_from(settings, index, ranked)
    return AskResult(cites, outcome, (time.perf_counter() - t0) * 1000, ranked)
