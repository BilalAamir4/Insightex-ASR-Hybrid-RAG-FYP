"""Question -> citations: fusion identical to gate G5's, de-duplication before the top 3, seek times, fallback."""

from __future__ import annotations

import importlib.util
import json
import random
from pathlib import Path

import numpy as np
import pytest

from insightex.core.config import load_settings
from insightex.index.store import load_index, write_index
from insightex.retrieval import ask as ask_flow
from insightex.retrieval import search as s
from insightex.retrieval.rewrite import FallbackReason, RewriteOutcome
from insightex.windows.build import build_windows

ROOT = Path(__file__).resolve().parents[3]


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "eval_retrieval" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fuse_equals_the_g5_harness_rrf_including_ties():
    tool_rrf = _tool("sparse").rrf
    rng = random.Random(7)
    for _ in range(200):
        n = rng.randint(1, 30)
        a, b = rng.sample(range(n), n), rng.sample(range(n), n)
        assert [w for w, _ in s.fuse([a, b], 60)] == tool_rrf([a, b], k=60)
    assert [w for w, _ in s.fuse([[2, 1], [1, 2]], 60)] == [1, 2]


def test_fuse_scores_are_the_g5_harness_scores():
    a, b = [3, 1, 2, 0], [0, 1, 3, 2]
    expected = {w: 0.0 for w in a}
    for ranking in (a, b):  # the harness summed in this order
        for r, w in enumerate(ranking, start=1):
            expected[w] += 1.0 / (60 + r)
    assert dict(s.fuse([a, b], 60)) == expected  # bit for bit


SEGS = [{"id": i + 1, "start": i * 10.0 + 1.5, "end": i * 10.0 + 9.5, "text": f"seg {i}"} for i in range(12)]


@pytest.fixture
def index(tmp_path):
    windows = build_windows(SEGS, window_s=30, stride_s=15, duration_s=120)  # overlapping windows
    vectors = np.stack([np.eye(8, dtype=np.float32)[i % 8] for i in range(len(windows))])
    write_index(tmp_path, windows, vectors, {"model": {"repo": "x", "revision": "y"}})
    return load_index(tmp_path)


def _encoder(index_dim=8, hot=1):
    def encode(text):
        v = np.zeros((1, index_dim), dtype=np.float32)
        v[0, hot if text != "rewrite" else 3] = 1.0
        return v
    return encode


def test_citations_are_deduplicated_before_the_top_3_and_seek_to_the_first_segment(index):
    settings = load_settings()
    out = ask_flow.ask(settings, index, "q", encode=_encoder(), rewriter=lambda q: RewriteOutcome(None, FallbackReason.LLM_NOT_LOADED, None))
    assert 1 <= len(out.citations) <= 3 and [c.rank for c in out.citations] == list(range(1, len(out.citations) + 1))
    spans = [(c.start, c.end) for c in out.citations]
    assert all(min(a[1], b[1]) - max(a[0], b[0]) <= 0 for i, a in enumerate(spans) for b in spans[:i])  # no overlaps
    for c in out.citations:
        w = next(w for w in index.windows if w["start"] == c.start)
        assert c.seek_s == w["first_segment_start"] >= c.start  # 1.5 s into the grid window, not the grid start
    assert len(out.ranked) == index.size and out.rewrite.rewrite is None


def test_with_a_rewrite_both_rankings_are_fused(index):
    settings = load_settings()
    out = ask_flow.ask(settings, index, "q", encode=_encoder(), rewriter=lambda q: RewriteOutcome("rewrite", None, 400.0))
    first = s.rank_all(index, _encoder()("q"))
    second = s.rank_all(index, _encoder()("rewrite"))
    assert out.ranked == s.fuse([[h.window_id for h in first], [h.window_id for h in second]], settings.retrieval.rrf_k)
    only = ask_flow.ask(settings, index, "q", encode=_encoder(), rewriter=lambda q: RewriteOutcome(None, None, None))
    assert [w for w, _ in only.ranked] == [h.window_id for h in first]  # fallback = the original ranking, untouched


def test_each_question_is_encoded_alone(index):
    calls = []
    ask_flow.ask(load_settings(), index, "q", encode=lambda t: calls.append(t) or _encoder()(t), rewriter=lambda q: RewriteOutcome("rewrite", None, 1.0))
    assert calls == ["q", "rewrite"]


# -- replay of the recorded G5 rewrites through production code (needs the real Day 4 workspace and BGE-M3) -----------


@pytest.mark.replay
@pytest.mark.real_env
def test_replay_g5_rewrites_through_production_fusion():
    from insightex.core.config import get_settings
    from insightex.index.stage import index_searchable
    from insightex.jobs.workspace import Workspaces

    settings = get_settings()
    ws = Workspaces(settings.jobs.workspaces_dir)
    lecture = "sha256-de27cb67c2acbedebd0c2c7416932b8a"
    directory = ws.stage_output_dir(lecture, "index")
    if directory is None or not index_searchable(directory, settings):
        pytest.skip("Day 4 workspace with a current index is not present")
    index = load_index(directory)
    evidence = ROOT / "docs" / "evidence" / "m6"
    rows = json.loads((evidence / "g5_rewrites.json").read_text(encoding="utf-8"))["rewrites"]
    fused = {r["id"]: r["hits"] for r in json.loads((evidence / "g5_B_fused.json").read_text(encoding="utf-8"))["results"]}
    encoder = s.QueryEncoder(settings)
    for row in rows:
        out = ask_flow.ask(settings, index, row["original"], encode=lambda t: encoder.encode([t]),
                           rewriter=lambda q, row=row: RewriteOutcome(row["rewrite"], None, row["rewrite_s"]))
        want = fused[row["id"]]
        got = out.ranked[: len(want)]
        assert [w for w, _ in got] == [h["window_id"] for h in want], row["id"]
        assert [sc for _, sc in got] == pytest.approx([h["score"] for h in want], abs=1e-12), row["id"]
