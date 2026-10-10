"""SubprocessTranscriber against a fake child script: event protocol, failure codes, timeout, stop on cancel."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from insightex.asr.transcriber import AsrError, SubprocessTranscriber, TranscribeRequest
from insightex.ingest.errors import ErrorCode
from insightex.jobs.stages import JobCancelled

CHILD = Path(__file__).parents[1] / "fake_whisper_child.py"


def request(tmp_path, timeout_s=20.0, baseline=1000):
    return TranscribeRequest(
        audio=tmp_path / "audio.wav", language="ur", params={"beam_size": 5}, model_repo="Systran/x",
        model_revision="abc", device="cuda", device_index=0, compute_type="float16", cpu_threads=0, num_workers=1,
        timeout_s=timeout_s, log_path=tmp_path / "logs" / "job.log", vram_baseline_mib=baseline,
    )


def transcriber(mode, used=(1000, 5000, 3000)):
    readings = iter(list(used) + [None] * 1000)
    return SubprocessTranscriber(kill_grace_s=2, vram_poll_interval_s=0.0,
                                 command=[sys.executable, str(CHILD), mode], vram_used=lambda: next(readings))


def test_ok_run_streams_segments_and_reports_peak_above_baseline(tmp_path):
    seen, ticks = [], []
    result = transcriber("slow").transcribe(request(tmp_path), seen.append, lambda: ticks.append(1))
    assert [s["id"] for s in result.segments] == [1, 2, 3] == [s["id"] for s in seen]
    assert result.snapshot_path.endswith("/snapshots/feedbeef") and result.transcribe_s == 1.5
    assert result.peak_vram_mib == 4000  # max reading 5000 minus baseline 1000
    assert ticks


@pytest.mark.parametrize(("mode", "code"), [
    ("load_fail", ErrorCode.MODEL_LOAD_FAILED),
    ("oom_event", ErrorCode.GPU_OUT_OF_MEMORY),
    ("oom_stderr", ErrorCode.GPU_OUT_OF_MEMORY),
    ("crash", ErrorCode.TRANSCRIBE_CRASHED),
    ("exit_after_ready", ErrorCode.TRANSCRIBE_CRASHED),
    ("garbage_code", ErrorCode.TRANSCRIBE_CRASHED),
])
def test_failures_map_to_their_codes(tmp_path, mode, code):
    with pytest.raises(AsrError) as exc:
        transcriber(mode).transcribe(request(tmp_path), lambda s: None, lambda: None)
    assert exc.value.code == code
    assert "exit code" in exc.value.details


def test_crash_details_carry_the_stderr_tail(tmp_path):
    with pytest.raises(AsrError) as exc:
        transcriber("crash").transcribe(request(tmp_path), lambda s: None, lambda: None)
    assert "Segmentation fault (simulated)" in exc.value.details


def test_timeout_kills_the_child(tmp_path):
    t0 = time.monotonic()
    with pytest.raises(AsrError) as exc:
        transcriber("hang").transcribe(request(tmp_path, timeout_s=1.0), lambda s: None, lambda: None)
    assert exc.value.code == ErrorCode.TRANSCRIBE_TIMEOUT
    assert time.monotonic() - t0 < 10


def test_cancel_from_tick_stops_the_child_and_propagates(tmp_path, monkeypatch):
    started = []
    real_popen = __import__("subprocess").Popen

    def spy(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        started.append(proc)
        return proc

    monkeypatch.setattr("insightex.asr.transcriber.subprocess.Popen", spy)
    calls = {"n": 0}

    def tick():
        calls["n"] += 1
        if calls["n"] >= 2:
            raise JobCancelled()

    with pytest.raises(JobCancelled):
        transcriber("hang").transcribe(request(tmp_path), lambda s: None, tick)
    assert started and started[0].poll() is not None  # reaped, not left running


def test_no_vram_reading_gives_no_peak(tmp_path):
    result = transcriber("ok", used=()).transcribe(request(tmp_path), lambda s: None, lambda: None)
    assert result.peak_vram_mib is None
