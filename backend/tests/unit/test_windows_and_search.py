"""Windowing (pure), overlap de-duplication and FAISS search over a tiny index (no model, no GPU)."""

from __future__ import annotations

import numpy as np
import pytest

from insightex.index.store import load_index, write_index
from insightex.retrieval.search import Hit, dedupe, search
from insightex.windows.build import build_snapped_windows, build_windows


def seg(i, start, end, text):
    return {"id": i, "start": start, "end": end, "text": text}


SEGS = [seg(1, 0.0, 10.0, " one "), seg(2, 10.0, 29.9, "two"), seg(3, 30.0, 45.0, " three"), seg(4, 45.0, 50.0, "   "),
        seg(5, 95.0, 99.0, "five")]


def test_fixed_windows_assign_segments_by_start_time():
    w = build_windows(SEGS, window_s=30, stride_s=30, duration_s=100)
    assert [(x.id, x.start, x.end, x.first_segment, x.last_segment, x.text) for x in w] == [
        (0, 0.0, 30.0, 1, 2, "one two"), (1, 30.0, 60.0, 3, 3, "three"), (2, 90.0, 100.0, 5, 5, "five")]


def test_windows_record_where_a_citation_seeks_to():
    segs = [seg(1, 1.5, 9.0, "a"), seg(2, 12.0, 29.0, "b"), seg(3, 33.25, 40.0, "c")]
    grid = build_windows(segs, window_s=30, stride_s=30, duration_s=60)
    assert [(w.start, w.first_segment_start) for w in grid] == [(0.0, 1.5), (30.0, 33.25)]  # not the grid start
    snapped = build_snapped_windows(segs, window_s=30, stride_s=30)
    assert [(w.start, w.first_segment_start) for w in snapped] == [(1.5, 1.5), (33.25, 33.25)]
    assert grid[0].to_json()["first_segment_start"] == 1.5


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


def test_dedupe_drops_any_overlap_with_a_better_kept_window_but_not_touching_edges():
    kept = dedupe([hit(1, 30, 60), hit(2, 45, 75), hit(3, 60, 90), hit(4, 0, 30), hit(5, 85, 115)], 0)
    # 45-75 overlaps 30-60: dropped; 60-90 only touches 30-60: kept; 0-30 only touches: kept; 85-115 overlaps 60-90: dropped
    assert [(h.window_id, h.rank) for h in kept] == [(1, 1), (3, 2), (4, 3)]  # ranks renumbered
    # a dropped window does not shadow later ones: 45-75 is dropped, so 70-100 is judged against the kept 30-60 and 60-90
    assert [h.window_id for h in dedupe([hit(1, 30, 60), hit(2, 45, 75), hit(3, 100, 130)], 0)] == [1, 3]
    assert [h.window_id for h in dedupe([hit(1, 30, 60), hit(2, 55, 85)], 10)] == [1, 2]  # 5 s overlap is within the allowance


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


def uniform(n, length=10.0):
    return [seg(i + 1, i * length, (i + 1) * length - 0.5, f"s{i + 1}") for i in range(n)]


def test_snapped_windows_end_on_the_segment_boundary_closest_to_the_target_length():
    w = build_snapped_windows(uniform(7), window_s=30, stride_s=30)
    # ends 9.5, 19.5, 29.5, ... : the third segment ends closest to 30
    assert [(x.start, x.end, x.first_segment, x.last_segment) for x in w] == [(0.0, 29.5, 1, 3), (30.0, 59.5, 4, 6), (60.0, 69.5, 7, 7)]
    assert "".join(x.text for x in w).replace(" ", "") == "s1s2s3s4s5s6s7"  # every segment lands in exactly one window


def test_snapped_windows_with_a_stride_overlap_and_stop_at_the_end():
    w = build_snapped_windows(uniform(7), window_s=30, stride_s=15)
    # next start is the segment start closest to start + 15 (10 and 20 tie: the later one, 20)
    assert [(x.first_segment, x.last_segment) for x in w] == [(1, 3), (3, 5), (5, 7)]


def test_snapped_windows_keep_a_long_segment_whole_and_skip_empty_text():
    segs = [seg(1, 0, 40, "long"), seg(2, 40, 50, "  "), seg(3, 50, 55, "tail")]
    w = build_snapped_windows(segs, window_s=30, stride_s=30)
    assert [(x.first_segment, x.last_segment, x.end) for x in w] == [(1, 1, 40.0), (3, 3, 55.0)]
    assert build_snapped_windows([], window_s=30, stride_s=30) == []
