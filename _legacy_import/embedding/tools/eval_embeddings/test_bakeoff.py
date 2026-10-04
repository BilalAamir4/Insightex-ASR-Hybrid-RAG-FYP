import pytest
import os
import tempfile
from tools.eval_embeddings.embed_bakeoff import (
    parse_timestamp_srt,
    parse_time_str,
    format_timestamp,
    parse_srt,
    create_windows,
    load_and_validate_queries,
    check_overlap,
    SRTCue,
    Query,
)


def test_srt_timestamp_parsing():
    assert parse_timestamp_srt("00:00:00,000") == 0.0
    assert parse_timestamp_srt("00:01:05,500") == 65.5
    assert parse_timestamp_srt("01:10:02,123") == 3600 + 600 + 2 + 0.123
    with pytest.raises(ValueError):
        parse_timestamp_srt("invalid_time")


def test_time_str_parsing():
    assert parse_time_str("01:30") == 90.0
    assert parse_time_str("00:45") == 45.0
    assert parse_time_str("1:05:10") == 3600 + 300 + 10.0
    assert parse_time_str("0:15") == 15.0
    assert parse_time_str("01:30.5") == 90.5
    assert parse_time_str("01:30,5") == 90.5
    with pytest.raises(ValueError):
        parse_time_str("")
    with pytest.raises(ValueError):
        parse_time_str("bad:time:string:extra")
    with pytest.raises(ValueError):
        parse_time_str("abc:def")


def test_srt_parsing():
    content = """1
00:00:01,000 --> 00:00:04,500
Hello world

2
00:00:05,000 --> 00:00:08,200
This is a multi-line
transcript test cue.

3
00:00:09,000 --> 00:00:10,000


4
00:00:10,000 --> 00:00:12,000
Final cue.
"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".srt") as f:
        f.write(content)
        temp_path = f.name

    try:
        cues = parse_srt(temp_path)
        assert len(cues) == 3  # cue 3 was empty and skipped
        assert cues[0].start == 1.0
        assert cues[0].end == 4.5
        assert cues[0].text == "Hello world"

        assert cues[1].start == 5.0
        assert cues[1].end == 8.2
        assert cues[1].text == "This is a multi-line transcript test cue."

        assert cues[2].start == 10.0
        assert cues[2].end == 12.0
        assert cues[2].text == "Final cue."
    finally:
        os.remove(temp_path)


def test_window_grouping():
    cues = [
        SRTCue(index=1, start=5.0, end=15.0, text="First concept"),
        SRTCue(index=2, start=25.0, end=35.0, text="Second concept"),
        SRTCue(index=3, start=40.0, end=50.0, text="Third concept"),
        SRTCue(index=4, start=70.0, end=75.0, text="Last concept"),
    ]
    # Total duration = 75.0s
    # Window W=30s, non-overlapping stride=30s
    windows = create_windows(cues, window_sec=30.0, stride_sec=30.0)
    # Window 0: [0, 30) -> cues with start in [0, 30): cue 1 (5s), cue 2 (25s)
    # Window 1: [30, 60) -> cue 3 (40s)
    # Window 2: [60, 90) clipped to srt_duration 75.0s -> cue 4 (70s)
    assert len(windows) == 3

    assert windows[0].start_sec == 0.0
    assert windows[0].end_sec == 30.0
    assert windows[0].n_cues == 2
    assert windows[0].text == "First concept Second concept"

    assert windows[1].start_sec == 30.0
    assert windows[1].end_sec == 60.0
    assert windows[1].n_cues == 1
    assert windows[1].text == "Third concept"

    assert windows[2].start_sec == 60.0
    assert windows[2].end_sec == 75.0  # clipped to srt_duration
    assert windows[2].n_cues == 1
    assert windows[2].text == "Last concept"


def test_overlap_hit_rule():
    # Strict overlap: win_start < q_end and win_end > q_start
    # Window [30, 60]
    win_start, win_end = 30.0, 60.0

    # Query strictly inside: [40, 50]
    assert check_overlap(win_start, win_end, 40.0, 50.0) is True

    # Query overlapping left boundary: [20, 35]
    assert check_overlap(win_start, win_end, 20.0, 35.0) is True

    # Query overlapping right boundary: [55, 70]
    assert check_overlap(win_start, win_end, 55.0, 70.0) is True

    # Query strictly enclosing window: [10, 80]
    assert check_overlap(win_start, win_end, 10.0, 80.0) is True

    # Non-overlapping before: [10, 30] (touches boundary at 30, not strict)
    assert check_overlap(win_start, win_end, 10.0, 30.0) is False

    # Non-overlapping after: [60, 80] (touches boundary at 60, not strict)
    assert check_overlap(win_start, win_end, 60.0, 80.0) is False

    # Completely disjoint
    assert check_overlap(win_start, win_end, 5.0, 15.0) is False
    assert check_overlap(win_start, win_end, 70.0, 90.0) is False


def test_query_validation_and_failures():
    srt_duration = 100.0

    # Valid CSV
    valid_csv = "query,start,end,kind\nWhat is gradient?,00:10,00:30,concept\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
        f.write(valid_csv)
        path = f.name
    try:
        queries = load_and_validate_queries(path, srt_duration)
        assert len(queries) == 1
        assert queries[0].query == "What is gradient?"
        assert queries[0].start == 10.0
        assert queries[0].end == 30.0
        assert queries[0].kind == "concept"
    finally:
        os.remove(path)

    # Missing column
    invalid_csv = "query,start,end\nWhat is gradient?,00:10,00:30\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
        f.write(invalid_csv)
        path = f.name
    try:
        with pytest.raises(ValueError, match="Invalid CSV header"):
            load_and_validate_queries(path, srt_duration)
    finally:
        os.remove(path)

    # Start >= End and overshoot
    invalid_rows_csv = (
        "query,start,end,kind\n"
        "Bad start end,00:30,00:20,fact\n"
        "Overshoot,01:30,02:10,fact\n"  # 130s > 100s + 5s = 105s
        ",00:10,00:20,fact\n"  # empty query
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
        f.write(invalid_rows_csv)
        path = f.name
    try:
        with pytest.raises(ValueError) as excinfo:
            load_and_validate_queries(path, srt_duration)
        msg = str(excinfo.value)
        assert "Row 2: start" in msg
        assert "Row 3: end time" in msg
        assert "Row 4: 'query' field is empty" in msg
    finally:
        os.remove(path)


def test_recall_and_mrr_metrics():
    # Simulate first_hit_ranks for 4 queries
    # ranks: [1, 2, 4, None]
    ranks = [1, 2, 4, None]
    hit_at_1 = [1 if r is not None and r <= 1 else 0 for r in ranks]
    hit_at_3 = [1 if r is not None and r <= 3 else 0 for r in ranks]
    hit_at_5 = [1 if r is not None and r <= 5 else 0 for r in ranks]
    mrr_contributions = [1.0 / r if r is not None else 0.0 for r in ranks]

    assert hit_at_1 == [1, 0, 0, 0]
    assert hit_at_3 == [1, 1, 0, 0]
    assert hit_at_5 == [1, 1, 1, 0]

    n = len(ranks)
    recall_1 = sum(hit_at_1) / n
    recall_3 = sum(hit_at_3) / n
    recall_5 = sum(hit_at_5) / n
    avg_mrr = sum(mrr_contributions) / n

    assert recall_1 == 0.25
    assert recall_3 == 0.50
    assert recall_5 == 0.75
    # MRR = (1/1 + 1/2 + 1/4 + 0) / 4 = (1.75) / 4 = 0.4375
    assert avg_mrr == pytest.approx(0.4375)
