"""transcript.json / transcript.vtt building, atomic writes, warnings, progress throttling (ADR-0042)."""

from __future__ import annotations

import itertools
import json
import math
import os

import pytest

from insightex.asr import transcript as tr


def seg(i, start, end, text=" text", temperature=0.0, ratio=1.5, words=None):
    return {"id": i, "start": start, "end": end, "text": text, "avg_logprob": -0.2, "no_speech_prob": 0.01,
            "compression_ratio": ratio, "temperature": temperature, "words": words or []}


def test_clean_segment_rounds_times_to_ms_and_keeps_text_verbatim():
    text = " یہ machine learning ہے،  ok  "
    s = tr.clean_segment(seg(3, 1.23456, 2.0004, text, words=[{"start": 1.23449, "end": 1.5, "word": " یہ", "probability": 0.5}]))
    assert (s["start"], s["end"], s["text"]) == (1.235, 2.0, text)
    assert s["words"] == [{"start": 1.234, "end": 1.5, "word": " یہ", "probability": 0.5}]
    assert set(s) == {"id", "start", "end", "text", "avg_logprob", "no_speech_prob", "compression_ratio", "temperature", "words"}


def test_json_safe_replaces_infinity():
    assert tr.json_safe({"a": [math.inf, 1.0], "b": {"c": -math.inf}}) == {"a": ["inf", 1.0], "b": {"c": "-inf"}}


def test_empty_detection():
    assert tr.is_empty([]) and tr.is_empty([seg(1, 0, 1, "   "), seg(2, 1, 2, "")])
    assert not tr.is_empty([seg(1, 0, 1, " a")])


def test_warnings_for_fallback_and_high_compression():
    segs = [seg(1, 0, 1), seg(2, 1, 2, temperature=0.2), seg(3, 2, 3, ratio=2.5), seg(4, 3, 4, temperature=0.4, ratio=3.0)]
    w = {x["code"]: x for x in tr.find_warnings(segs, 2.4)}
    assert w["TEMPERATURE_FALLBACK"]["segment_ids"] == [2, 4]
    assert w["HIGH_COMPRESSION_RATIO"]["segment_ids"] == [3, 4]
    assert all(set(x) == {"code", "message", "segment_ids"} for x in w.values())
    assert tr.find_warnings([seg(1, 0, 1, ratio=2.4)], 2.4) == []  # the threshold itself is fine


def build(segs, duration=20.0):
    return tr.build_transcript(
        stage_version="1", language={"id": "hindi", "label": "Hindi", "whisper_language": "ur", "tier_at_processing": "tested"},
        model={"name": "large-v3", "repo": "r", "revision": "abc", "device": "cuda", "compute_type": "float16"},
        params={"language": "ur", "vad_parameters": {"max_speech_duration_s": math.inf}}, libraries={"faster_whisper": "1.2.1", "ctranslate2": "4.8.2"},
        audio={"path": "stages/normalise/k/audio.wav", "duration_s": duration, "sha256": "0" * 64},
        segments=[tr.clean_segment(s) for s in segs], wall_time_s=5.0, peak_vram_mib=4600, warn_compression_ratio=2.4)


def test_document_fields_and_stats():
    doc = build([seg(1, 0, 5), seg(2, 5, 10, temperature=0.2)])
    assert doc["schema_version"] == 1 and doc["stage_version"] == "1"
    assert doc["params"]["vad_parameters"]["max_speech_duration_s"] == "inf"
    assert doc["stats"] == {"segment_count": 2, "fallback_segment_count": 1, "high_compression_segment_count": 0,
                            "wall_time_s": 5.0, "rtf": 0.25, "peak_vram_mib": 4600}
    json.loads(tr.dumps(doc))  # strict JSON: no Infinity


def test_document_validates_against_the_contract_schema():
    jsonschema = pytest.importorskip("jsonschema")
    from insightex.core.config import repo_root

    schema = json.loads((repo_root() / "docs" / "contracts" / "transcript.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(json.loads(tr.dumps(build([seg(1, 0, 5, words=[{"start": 0, "end": 1, "word": " a", "probability": 1}])]))), schema)


def test_vtt_timestamps_including_over_one_hour():
    assert tr.vtt_timestamp(0) == "00:00:00.000"
    assert tr.vtt_timestamp(61.0006) == "00:01:01.001"
    assert tr.vtt_timestamp(3599.9996) == "01:00:00.000"
    assert tr.vtt_timestamp(3725.25) == "01:02:05.250"
    assert tr.vtt_timestamp(36000 + 59.999) == "10:00:59.999"


def test_vtt_one_cue_per_segment():
    segs = [tr.clean_segment(seg(1, 0.0, 2.5, " Hello  guys")), tr.clean_segment(seg(2, 3700.0, 3702.123, "اب --> x"))]
    vtt = tr.to_vtt(segs)
    assert vtt.startswith("WEBVTT\n\n")
    cues = vtt.strip().split("\n\n")[1:]
    assert len(cues) == 2
    assert cues[0] == "1\n00:00:00.000 --> 00:00:02.500\nHello guys"
    assert cues[1].splitlines()[1] == "01:01:40.000 --> 01:01:42.123" and "-->" not in cues[1].splitlines()[2]


def test_atomic_write_leaves_no_file_after_a_crash_mid_write(tmp_path, monkeypatch):
    target = tmp_path / tr.TRANSCRIPT_JSON

    def boom(fd):
        raise OSError("disk died during fsync")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        tr.write_atomic(target, "x" * 100_000)
    assert not target.exists() and list(tmp_path.iterdir()) == []


def test_atomic_write_replaces_whole_file(tmp_path):
    target = tmp_path / "t.json"
    tr.write_atomic(target, "first")
    tr.write_atomic(target, "second")
    assert target.read_text() == "second" and [p.name for p in tmp_path.iterdir()] == ["t.json"]


def test_progress_throttle_needs_both_thresholds():
    t = tr.ProgressThrottle(min_interval_s=2.0, min_step=0.02)
    t.start(0.0)
    assert not t.offer(0.5, 1.0)          # big step, too soon
    assert not t.offer(0.01, 3.0)         # late enough, step too small
    assert t.offer(0.5, 3.0)              # both
    assert not t.offer(0.51, 10.0)        # 1 pp only
    assert not t.offer(0.9, 4.0)          # 1 s only
    assert t.offer(0.52, 5.0) and t.last_value == 0.52


def test_progress_throttle_at_most_one_update_per_interval():
    t = tr.ProgressThrottle(2.0, 0.02)
    t.start(0.0)
    reported = [now for now in [x * 0.1 for x in range(1, 201)] if t.offer(now / 20.0, now)]
    assert all(b - a >= 2.0 - 1e-9 for a, b in itertools.pairwise(reported))
    assert len(reported) == 10
