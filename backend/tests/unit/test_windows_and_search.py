"""Windowing (pure), overlap de-duplication and FAISS search over a tiny index (no model, no GPU)."""

from __future__ import annotations

import numpy as np
import pytest

from insightex.index.store import load_index, write_index
from insightex.retrieval.search import Hit, dedupe, search
from insightex.windows.build import build_windows


def seg(i, start, end, text):
    return {"id": i, "start": start, "end": end, "text": text}


SEGS = [seg(1, 0.0, 10.0, " one "), seg(2, 10.0, 29.9, "two"), seg(3, 30.0, 45.0, " three"), seg(4, 45.0, 50.0, "   "),
        seg(5, 95.0, 99.0, "five")]


def test_fixed_windows_assign_segments_by_start_time():
    w = build_windows(SEGS, window_s=30, stride_s=30, duration_s=100)
    assert [(x.id, x.start, x.end, x.first_segment, x.last_segment, x.text) for x in w] == [
        (0, 0.0, 30.0, 1, 2, "one two"), (1, 30.0, 60.0, 3, 3, "three"), (2, 90.0, 100.0, 5, 5, "five")]


def test_window_end_is_clipped_to_the_audio_duration_and_empty_windows_are_dropped():
    w = build_windows(SEGS[:1], window_s=30, stride_s=30, duration_s=12.5)
    assert [(x.start, x.end) for x in w] == [(0.0, 12.5)]
    assert build_windows([seg(1, 0, 5, "  ")], window_s=30, stride_s=30, duration_s=60) == []


def test_stride_smaller_than_window_overlaps():
    w = build_windows(SEGS[:3], window_s=30, stride_s=15, duration_s=50)
    assert [(x.start, x.first_segment, x.last_segment) for x in w] == [(0.0, 1, 2), (15.0, 3, 3), (30.0, 3, 3)]


def test_text_is_nfc_normalised_and_otherwise_untouched():
    w = build_windows([seg(1, 0, 5, " é تو  batch ")], window_s=30, stride_s=30, duration_s=10)
    assert w[0].text == "é تو  batch"


def hit(rank, start, end, score=0.5):
    return Hit(rank, rank, start, end, score)


def test_dedupe_drops_windows_overlapping_a_better_one_by_more_than_half():
    hits = [hit(1, 30, 60), hit(2, 45, 75), hit(3, 60, 90), hit(4, 10, 40)]
    kept = dedupe(hits, 0.5)
    # 45-75 overlaps 30-60 by 15 s = exactly 50%: kept; 60-90 touches 45-75 by 15 s: kept; 10-40 overlaps 30-60 by 10 s: kept
    assert [h.window_id for h in kept] == [1, 2, 3, 4]
    kept = dedupe([hit(1, 30, 60), hit(2, 40, 70), hit(3, 0, 30)], 0.5)
    assert [(h.window_id, h.rank) for h in kept] == [(1, 1), (3, 2)]  # 40-70 overlaps 20 s of 30 = 67%: dropped; ranks renumbered


def test_search_ranks_by_inner_product(tmp_path):
    windows = build_windows(SEGS, window_s=30, stride_s=30, duration_s=100)
    vectors = np.eye(3, 4, dtype=np.float32)
    write_index(tmp_path, windows, vectors, {"model": {"repo": "x", "revision": "y"}})
    index = load_index(tmp_path)
    q = np.array([[0.0, 0.9, 0.1, 0.0], [1.0, 0, 0, 0]], dtype=np.float32)
    res = search(index, q, 2)
    assert [h.window_id for h in res[0]] == [1, 2] and res[0][0].start == 30.0 and res[0][0].rank == 1
    assert res[1][0].window_id == 0 and res[1][0].score == pytest.approx(1.0)
    assert len(search(index, q, 10)[0]) == 3  # k larger than the index
