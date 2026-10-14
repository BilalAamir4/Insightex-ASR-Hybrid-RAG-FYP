"""Question -> ranked windows (M5, ADR-0043, ADR-0044).

`QueryEncoder` loads BGE-M3 once, on the CPU in float32 by default (`retrieval.query_*`): at query time the GPU
belongs to Ollama. `search` is an exact inner-product search over one lecture's FAISS index. `dedupe` drops a
window that overlaps a higher-ranked kept one by more than `retrieval.dedupe_min_overlap_s` seconds (0: any overlap).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from insightex.core.config import Settings
from insightex.index import model as m
from insightex.index.store import LectureIndex


@dataclass(frozen=True)
class Hit:
    rank: int  # 1 = best
    window_id: int
    start: float
    end: float
    score: float  # cosine similarity


class IndexModelMismatch(Exception):
    """The lecture's index was built with a different model revision than the one configured for queries."""


class QueryEncoder:
    def __init__(self, settings: Settings, *, device: str | None = None, dtype: str | None = None) -> None:
        self.settings = settings
        self.device = device or settings.retrieval.query_device
        self.dtype = dtype or settings.retrieval.query_dtype
        self._model: Any = None

    @property
    def model(self) -> Any:
        if self._model is None:
            i = self.settings.index
            self._model = m.load_model(i.model_repo, i.model_revision, device=self.device, device_index=i.device_index,
                                       dtype=self.dtype, max_seq_length=i.max_seq_length)
        return self._model

    def encode(self, questions: list[str]):
        """Unit-length float32 vectors, one row per question."""
        return m.encode(self.model, questions, self.settings.index.batch_size)


def check_compatible(settings: Settings, index: LectureIndex) -> None:
    from insightex.windows.build import SCHEMA_VERSION as WINDOWS_SCHEMA

    if index.meta.get("fingerprint", {}).get("windows_schema_version") != WINDOWS_SCHEMA:
        raise IndexModelMismatch("index built with an older windows format; re-run the lecture to rebuild its index")
    built = index.meta["model"]
    if built["repo"] != settings.index.model_repo or built["revision"] != settings.index.model_revision:
        raise IndexModelMismatch(
            f"index built with {built['repo']}@{built['revision'][:8]}, queries configured for "
            f"{settings.index.model_repo}@{settings.index.model_revision[:8]}; re-run the lecture to rebuild its index"
        )


def search(index: LectureIndex, vectors, k: int) -> list[list[Hit]]:
    """Top-`k` windows per query vector, best first (all windows if k is larger)."""
    k = min(k, index.size)
    scores, ids = index.faiss_index.search(vectors, k)
    out = []
    for row_scores, row_ids in zip(scores, ids, strict=True):
        hits = []
        for rank, (s, wid) in enumerate(zip(row_scores, row_ids, strict=True), start=1):
            w = index.windows[int(wid)]
            hits.append(Hit(rank, int(wid), float(w["start"]), float(w["end"]), float(s)))
        out.append(hits)
    return out


def rank_all(index: LectureIndex, vector) -> list[Hit]:
    """Every window of the lecture for one question vector (shape (1, dim)), best first."""
    return search(index, vector, index.size)[0]


def fuse(rankings: list[list[int]], k: int) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion of rankings of window ids: score = sum of 1 / (k + rank) over the rankings, summed in
    list order, rank counting from 1; best first, ties by smaller window id. The function and parameters of gate G5."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, wid in enumerate(ranking, start=1):
            scores[wid] = scores.get(wid, 0.0) + 1.0 / (k + rank)
    return [(wid, scores[wid]) for wid in sorted(scores, key=lambda w: (-scores[w], w))]


def dedupe(hits: list[Hit], min_overlap_s: float) -> list[Hit]:
    """Keep hits in rank order, dropping any that overlap an already kept (higher-ranked) hit by more than
    `min_overlap_s` seconds (0: any overlap; windows that only touch are distinct). Ranks are renumbered."""
    kept: list[Hit] = []
    for h in hits:
        if any(min(h.end, k.end) - max(h.start, k.start) > min_overlap_s for k in kept):
            continue
        kept.append(h)
    return [Hit(r, h.window_id, h.start, h.end, h.score) for r, h in enumerate(kept, start=1)]
