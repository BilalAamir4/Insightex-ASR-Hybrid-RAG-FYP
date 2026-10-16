"""Grid reimplementation and the seeded stratified sample (ADR-0045, ADR-0048)."""

import pytest
from grid import build_grid
from lc_fixtures import segment, toy_segments
from sampling import (
    accepted_manifest_sha256,
    build_manifest,
    reassign_manifest,
    stratified_pick,
    windows_for,
)

INFO = {"asr_key": "a1", "duration_s": 0, "language_id": "hindi", "language_tier_at_processing": "tested",
        "segment_count": 0}


def manifest(windows, **kw):
    args = {"lecture_id": "L", "windows": windows, "transcript_info": INFO, "index_check": "no index", "seed": 7,
            "n": 40, "n_shared": 10, "labellers": ["bilal", "fatima"], "excluded": {}, "created_at": "t"}
    args.update(kw)
    return build_manifest(**args)


def test_grid_assigns_segments_by_start_drops_empty_and_clips_to_duration():
    segs = [segment(0, 1, 40, " a "), segment(1, 29.9, 31, "b"), segment(2, 30, 33, "c"), segment(3, 65, 66, "   "),
            segment(4, 95, 99, "d")]
    w = build_grid(segs, duration_s=100)
    assert [(x.index, x.start_s, x.end_s, x.text) for x in w] == [
        (0, 0.0, 30.0, "a b"), (1, 30.0, 60.0, "c"), (2, 90.0, 100.0, "d")]  # 60-90 holds only blank text: dropped


def test_grid_unicode_is_nfc():
    decomposed = "é"
    assert build_grid([segment(0, 0, 1, decomposed)], 10)[0].text == "é"


def test_stratified_pick_one_per_stratum_and_census():
    import random
    items = list(range(100))
    picks = stratified_pick(items, 10, random.Random(1))
    assert [p // 10 for p in picks] == list(range(10))
    assert stratified_pick(items[:5], 10, random.Random(1)) == items[:5]


def test_sample_is_deterministic_for_a_seed_and_changes_with_it():
    w = build_grid(toy_segments(120), 3600)
    a, b = manifest(w), manifest(w)
    assert a == b
    c = manifest(w, seed=8)
    assert [r["window_index"] for r in a["windows"]] != [r["window_index"] for r in c["windows"]]


def test_sample_spreads_over_the_timeline_with_shared_first():
    w = build_grid(toy_segments(120), 3600)
    m = manifest(w)
    assert m["n_sampled"] == 40 and not m["census"] and m["census_note"] is None
    picked = sorted(r["window_index"] for r in m["windows"])
    assert [i // 3 for i in picked] == list(range(40))  # 120 windows, 40 strata of 3
    rows = m["windows"]
    assert [r["shared"] for r in rows] == [True] * 10 + [False] * 30
    assert [r["order"] for r in rows] == list(range(40))
    shared = [r["window_index"] for r in rows[:10]]
    assert shared == sorted(shared)
    assert [picked.index(i) // 4 for i in shared] == list(range(10))  # one shared per 4 sampled
    assert all(r["assigned_to"] == ["bilal", "fatima"] for r in rows[:10])
    assert [r["assigned_to"] for r in rows[10:14]] == [["bilal"], ["fatima"], ["bilal"], ["fatima"]]
    assert len(windows_for(m, "bilal")) == 25 and len(windows_for(m, "fatima")) == 25
    assert len(windows_for(m, "consensus")) == 10


def test_census_with_excluded_windows_is_recorded():
    w = build_grid(toy_segments(23), 688.03)
    m = manifest(w, excluded={0: "passing mention", 3: "importance cue", 5: "stated relation"})
    assert m["census"] and m["n_eligible"] == 20 and m["n_sampled"] == 20
    assert "20 eligible" in m["census_note"]
    assert m["excluded"] == [{"window_index": 0, "reason": "passing mention"},
                             {"window_index": 3, "reason": "importance cue"},
                             {"window_index": 5, "reason": "stated relation"}]
    assert {r["window_index"] for r in m["windows"]} == set(range(23)) - {0, 3, 5}
    assert m["grid"]["window_s"] == 30 and m["grid"]["stride_s"] == 30 and m["seed"] == 7
    assert m["windows"][-1]["end_s"] == 688.03


def test_bad_arguments_are_refused():
    w = build_grid(toy_segments(5), 150)
    with pytest.raises(ValueError):
        manifest(w, excluded={9: "x"})
    with pytest.raises(ValueError):
        manifest(w, n_shared=6)
    with pytest.raises(ValueError):
        manifest(w, labellers=["bilal", "bilal"])
    with pytest.raises(ValueError):
        manifest(w, labellers=[])
    for reserved in ("consensus", "bilal_repeat"):
        with pytest.raises(ValueError):
            manifest(w, labellers=["bilal", reserved])
    with pytest.raises(SystemExit):
        windows_for(manifest(w, n_shared=2), "someone")


def test_single_labeller_gets_every_window_and_the_repeat_gets_the_shared_ones():
    w = build_grid(toy_segments(120), 3600)
    m = manifest(w, labellers=["bilal"])
    two = manifest(w)
    assert [r["window_index"] for r in m["windows"]] == [r["window_index"] for r in two["windows"]]
    assert all(r["assigned_to"] == ["bilal"] for r in m["windows"])
    assert len(windows_for(m, "bilal")) == 40
    assert [r["window_index"] for r in windows_for(m, "bilal_repeat")] == \
        [r["window_index"] for r in m["windows"] if r["shared"]]
    assert len(windows_for(two, "fatima_repeat")) == 10


def test_reassign_manifest_records_the_change_and_keeps_the_old_sha_accepted():
    w = build_grid(toy_segments(120), 3600)
    two = manifest(w)
    one = reassign_manifest(two, "a" * 64, ["bilal"], "single labeller", "2026-10-17T00:00:00Z")
    assert one == {**manifest(w, labellers=["bilal"]), "amendments": one["amendments"]}
    assert two["labellers"] == ["bilal", "fatima"] and "amendments" not in two  # input untouched
    assert one["amendments"][0]["newly_assigned"]["bilal"] == [r["window_index"] for r in two["windows"]
                                                              if r["assigned_to"] == ["fatima"]]
    assert accepted_manifest_sha256(one, "b" * 64) == {"a" * 64, "b" * 64}
    assert accepted_manifest_sha256(two, "b" * 64) == {"b" * 64}
