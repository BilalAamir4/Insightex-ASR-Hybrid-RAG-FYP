"""M2 normalise engine on a synthetic corpus: real ffmpeg, in-process job runs (ADR-0036).

Run alone with `pytest -m media`. Every accepted clip must satisfy the post-verify rules (step 8) when
checked independently of the engine; every rejected clip must leave nothing behind.
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import pytest

from insightex.core.config import clear_settings_cache, get_settings
from insightex.ingest.errors import ErrorCode, IngestRejected
from insightex.jobs.workspace import Workspaces
from ingest_helpers import open_db, run_file_job
from media_corpus import FLASH_AT, Corpus, probe

pytestmark = pytest.mark.media


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> Corpus:
    return Corpus(tmp_path_factory.mktemp("corpus"))


# -- helpers ---------------------------------------------------------------------------------------

def ingest(corpus: Corpus, name: str):
    settings = get_settings()
    result, job = run_file_job(corpus.get(name), settings)
    return settings, result, job


def normalised(settings, workspace_id: str) -> tuple[Path, dict]:
    directory = Workspaces(settings.jobs.workspaces_dir).stage_output_dir(workspace_id, "normalise")
    assert directory is not None, "normalise did not complete"
    return directory, json.loads((directory / "normalise.json").read_text())


def staging_files(settings) -> list[Path]:
    d = settings.ingest.file.staging_dir
    return sorted(d.iterdir()) if d.is_dir() else []


def check_step8(directory: Path) -> None:
    """Independent re-check of validation rule 8 on the published outputs (does not call the engine)."""
    video, wav_path = directory / "video.mp4", directory / "audio.wav"
    info = probe(video)
    vs = [s for s in info["streams"] if s["codec_type"] == "video"]
    au = [s for s in info["streams"] if s["codec_type"] == "audio"]
    assert len(vs) == 1 and vs[0]["codec_name"] == "h264" and vs[0]["pix_fmt"] in ("yuv420p", "yuvj420p")
    assert len(au) == 1 and au[0]["codec_name"] == "aac"
    assert vs[0]["width"] % 2 == 0 and vs[0]["height"] % 2 == 0
    data = video.read_bytes()
    assert 0 <= data.find(b"moov") < data.find(b"mdat"), "moov must precede mdat"
    starts = [float(s.get("start_time", 0)) for s in (vs[0], au[0])]
    assert abs(min(starts)) <= 0.1, starts
    with wave.open(str(wav_path)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        wav_dur = w.getnframes() / w.getframerate()
    a_dur = float(au[0].get("duration") or float(info["format"]["duration"]) - starts[1])
    assert abs((wav_dur - a_dur) - starts[1]) <= 0.1, (wav_dur, a_dur, starts)
    assert (directory / "thumbnail.jpg").read_bytes()[:2] == b"\xff\xd8"


def flash_time(video: Path) -> float:
    """pts (s) of the first frame whose mean luma is above mid-grey, from signalstats."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi", "-i", f"movie=filename='{video}',signalstats",
         "-show_entries", "frame=pts_time:frame_tags=lavfi.signalstats.YAVG", "-of", "json"],
        capture_output=True, text=True, check=True).stdout
    for frame in json.loads(out)["frames"]:
        if float(frame["tags"]["lavfi.signalstats.YAVG"]) > 128:
            return float(frame["pts_time"])
    raise AssertionError("no flash found in video.mp4")


def beep_time(wav_path: Path, threshold: float = 0.25) -> float:
    with wave.open(str(wav_path)) as w:
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())
    import array

    samples = array.array("h")
    samples.frombytes(raw)
    limit = threshold * 32767
    for i, s in enumerate(samples):
        if abs(s) > limit:
            return i / rate
    raise AssertionError("no beep found in audio.wav")


# -- accepted clips: decision, warnings and rule 8 ---------------------------------------------------

ACCEPTED = [
    # name, video decision, audio decision, warning codes that must be present
    ("h264_aac_mp4", "copy", "copy", set()),
    ("h264_aac_mp4_moov_at_end", "copy", "copy", set()),
    ("h264_opus_mkv", "copy", "transcode", set()),
    ("hevc_aac_mp4", "transcode", "copy", set()),
    ("vp9_opus_webm", "transcode", "transcode", set()),
    ("av1_mkv", "transcode", "copy", set()),
    ("mpeg2_interlaced_mpg", "transcode", "transcode", set()),
    ("wmv2_wmav2", "transcode", "transcode", set()),
    ("h264_high10", "transcode", "copy", set()),
    ("h264_yuv444", "transcode", "copy", set()),
    ("odd_dimensions", "transcode", "copy", set()),
    ("uhd_hevc", "transcode", "copy", set()),
    ("vfr_h264", "copy", "copy", {"VFR_SOURCE"}),
    ("sync_audio_delayed_mp4", "copy", "copy", {"START_OFFSET_CORRECTED"}),
    ("sync_ts_offset_mpegts", "copy", "copy", {"START_OFFSET_CORRECTED"}),
    ("sync_hevc_opus_delayed_mkv", "transcode", "transcode", set()),
    ("surround_51", "copy", "transcode", set()),
    ("two_audio_and_subtitles", "copy", "copy", {"MULTIPLE_AUDIO_STREAMS"}),
    ("rotated_90", "copy", "copy", {"ROTATED"}),
    ("near_silent", "copy", "copy", {"AUDIO_NEAR_SILENT"}),
]


@pytest.mark.parametrize("name,video,audio,warnings", ACCEPTED, ids=[a[0] for a in ACCEPTED])
def test_accepted_clip(corpus, name, video, audio, warnings, record_property):
    settings, result, job = ingest(corpus, name)
    assert job.status == "succeeded", job.error
    directory, info = normalised(settings, result.workspace_id)
    record_property("decision", f"{info['decision']['video']}/{info['decision']['audio']}")
    record_property("warnings", ",".join(w["code"] for w in info["warnings"]))
    assert (info["decision"]["video"], info["decision"]["audio"]) == (video, audio), info["decision"]["reasons"]
    codes = {w["code"] for w in info["warnings"]}
    assert warnings <= codes, codes
    if name == "h264_aac_mp4":
        assert codes == set()
    check_step8(directory)
    assert staging_files(settings) == []
    # the user's file is only ever read
    assert corpus.get(name).is_file()


def test_manifest_fields(corpus):
    settings, result, job = ingest(corpus, "h264_aac_mp4")
    directory, info = normalised(settings, result.workspace_id)
    assert info["schema"] == 2 and info["normaliser_version"] == "2" and info["ffmpeg_version"].startswith("ffmpeg version")
    src = info["source"]
    assert src["kind"] == "upload" and src["via"] == "cli" and src["original_filename"] == "h264_aac.mp4"
    assert src["size_bytes"] == corpus.get("h264_aac_mp4").stat().st_size and len(src["sha256"]) == 64 and src["received_at"]
    p = info["probe"]
    assert p["container"] and p["duration_s"] > 11 and p["video"]["codec"] == "h264" and p["audio"]["codec"] == "aac"
    assert {"video_stream_index", "audio_stream_index"} <= set(p)
    assert set(info["timings_s"]) >= {"probe", "video", "audio", "verify", "thumbnail", "total"}
    assert info["verify"]["moov_before_mdat"] is True and "padding_s" in info["verify"]
    assert result.workspace_id == f"sha256-{src['sha256'][:32]}"


def test_interlaced_clip_is_detected_and_deinterlaced(corpus):
    src = probe(corpus.get("mpeg2_interlaced_mpg"))
    order = next(s for s in src["streams"] if s["codec_type"] == "video").get("field_order")
    if order not in ("tt", "bb", "tb", "bt"):
        pytest.skip(f"ffprobe reports field_order={order!r} for the mpeg2 fixture")
    settings, result, job = ingest(corpus, "mpeg2_interlaced_mpg")
    _, info = normalised(settings, result.workspace_id)
    assert info["probe"]["video"]["field_order"] == order
    assert any("interlaced" in r for r in info["decision"]["reasons"])


def test_output_dimensions(corpus):
    settings, result, _ = ingest(corpus, "odd_dimensions")
    d, _ = normalised(settings, result.workspace_id)
    v = next(s for s in probe(d / "video.mp4")["streams"] if s["codec_type"] == "video")
    assert (v["width"] % 2, v["height"] % 2) == (0, 0)
    settings, result, _ = ingest(corpus, "uhd_hevc")
    d, _ = normalised(settings, result.workspace_id)
    v = next(s for s in probe(d / "video.mp4")["streams"] if s["codec_type"] == "video")
    assert v["height"] == 1080 and v["width"] == 1920


def test_copied_video_keeps_its_resolution(corpus):
    settings, result, _ = ingest(corpus, "h264_aac_mp4")
    d, _ = normalised(settings, result.workspace_id)
    v = next(s for s in probe(d / "video.mp4")["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (320, 240)


def test_audio_is_downmixed_and_mono_16k(corpus):
    settings, result, _ = ingest(corpus, "surround_51")
    d, _ = normalised(settings, result.workspace_id)
    a = next(s for s in probe(d / "video.mp4")["streams"] if s["codec_type"] == "audio")
    assert a["channels"] == 2
    with wave.open(str(d / "audio.wav")) as w:
        assert (w.getnchannels(), w.getframerate()) == (1, 16000)


def test_default_audio_stream_is_chosen_and_subtitles_dropped(corpus):
    src = probe(corpus.get("two_audio_and_subtitles"))
    audios = [s for s in src["streams"] if s["codec_type"] == "audio"]
    default = next(s for s in audios if s["disposition"]["default"] == 1)
    settings, result, _ = ingest(corpus, "two_audio_and_subtitles")
    d, info = normalised(settings, result.workspace_id)
    assert info["probe"]["audio_stream_index"] == default["index"] != audios[0]["index"]
    detail = next(w["detail"] for w in info["warnings"] if w["code"] == "MULTIPLE_AUDIO_STREAMS")
    assert str(default["index"]) in detail
    assert {s["codec_type"] for s in probe(d / "video.mp4")["streams"]} == {"video", "audio"}


def test_rotated_clip_is_flagged_with_degrees(corpus):
    settings, result, _ = ingest(corpus, "rotated_90")
    _, info = normalised(settings, result.workspace_id)
    assert info["probe"]["video"]["rotation"] in (90, 270)
    assert next(w for w in info["warnings"] if w["code"] == "ROTATED")["detail"].endswith("degrees")


# -- A/V sync: the test that proves audio.wav shares the player's timeline ---------------------------

def frame_duration_s(path: Path) -> float:
    """One video frame of the fixture, from its own r_frame_rate (not hard-coded)."""
    from fractions import Fraction

    v = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
    return float(1 / Fraction(v["r_frame_rate"]))


@pytest.mark.parametrize("name", ["sync_audio_delayed_mp4", "sync_ts_offset_mpegts", "sync_hevc_opus_delayed_mkv"])
def test_flash_and_beep_coincide(corpus, name, record_property):
    """Regression note: re-introducing `-avoid_negative_ts make_zero` must make the hevc/opus case fail.

    make_zero moves the decoder delay of B-frame video into presentation time: measured 57.6 ms
    (flash 5.080 s, beep 5.022 s) against 1.1 ms without it (ADR-0036, departure from D3). The bar is one frame
    of the fixture (40 ms at 25 fps), so the 57.6 ms case fails.
    """
    source = corpus.get(name)
    tolerance = frame_duration_s(source)
    src_info = probe(source)
    if name != "sync_ts_offset_mpegts":
        a_start = float(next(s for s in src_info["streams"] if s["codec_type"] == "audio")["start_time"])
        assert a_start == pytest.approx(1.5 if name == "sync_audio_delayed_mp4" else 0.7, abs=0.06), a_start
    settings, result, job = ingest(corpus, name)
    assert job.status == "succeeded", job.error
    d, _ = normalised(settings, result.workspace_id)
    flash, beep = flash_time(d / "video.mp4"), beep_time(d / "audio.wav")
    record_property("flash_s", f"{flash:.3f}")
    record_property("beep_s", f"{beep:.3f}")
    record_property("offset_ms", f"{(beep - flash) * 1000:.1f}")
    print(f"\n[sync] {name}: flash={flash:.3f}s beep={beep:.3f}s offset={(beep - flash) * 1000:+.1f} ms (limit {tolerance * 1000:.0f} ms)")
    assert abs(flash - FLASH_AT) <= tolerance, f"flash at {flash:.3f} s, expected about {FLASH_AT} s"
    assert abs(flash - beep) <= tolerance, f"{name}: flash={flash:.3f}s beep={beep:.3f}s (limit {tolerance * 1000:.0f} ms)"


# -- rejected clips ---------------------------------------------------------------------------------

REJECTED = [
    ("audio_only_m4a", ErrorCode.NO_VIDEO_STREAM),
    ("mp3_with_cover", ErrorCode.NO_VIDEO_STREAM),
    ("video_only_mp4", ErrorCode.NO_AUDIO_STREAM),
    ("empty_mp4", ErrorCode.EMPTY_FILE),
    ("text_as_mp4", ErrorCode.NOT_A_VIDEO),
    ("truncated_mp4_moov_at_end", ErrorCode.NOT_A_VIDEO),
    ("short_5s", ErrorCode.TOO_SHORT),
]


def assert_rejected(settings, result, job, code):
    assert job.status == "failed" and job.kind == "ingest_file"
    assert f"IngestRejected: {code}" in job.error, job.error
    assert not Workspaces(settings.jobs.workspaces_dir).path(result.workspace_id).exists(), "no lecture directory"
    assert staging_files(settings) == []
    conn = open_db(settings)
    assert conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 0, "no library entry"


@pytest.mark.parametrize("name,code", REJECTED, ids=[r[0] for r in REJECTED])
def test_rejected_clip(corpus, name, code):
    settings, result, job = ingest(corpus, name)
    assert_rejected(settings, result, job, code)
    assert corpus.get(name).exists()


def test_truncated_mkv_is_rejected_as_truncated_or_decode_failed(corpus, record_property):
    settings, result, job = ingest(corpus, "truncated_mkv")
    assert job.status == "failed"
    code = next((c for c in (ErrorCode.TRUNCATED, ErrorCode.TRANSCODE_FAILED) if f"IngestRejected: {c}" in job.error), None)
    record_property("code", str(code))
    print(f"\n[truncated mkv] rejected as {code}")
    assert code is not None, job.error
    assert_rejected(settings, result, job, code)


def test_too_long_by_config_override(corpus, monkeypatch):
    monkeypatch.setenv("INSIGHTEX__INGEST__URL__MAX_DURATION_S", "11")
    clear_settings_cache()
    settings, result, job = ingest(corpus, "h264_aac_mp4")
    assert_rejected(settings, result, job, ErrorCode.TOO_LONG)
    assert "longer than" in job.error  # the message names the limit; the details hold the measured duration


def test_too_large_by_config_override(corpus, monkeypatch):
    monkeypatch.setenv("INSIGHTEX__INGEST__URL__MAX_DOWNLOAD_BYTES", "100000")
    clear_settings_cache()
    settings, result, job = ingest(corpus, "h264_aac_mp4")
    assert_rejected(settings, result, job, ErrorCode.TOO_LARGE)


def test_insufficient_disk_is_refused_before_anything_is_copied(corpus, monkeypatch):
    import shutil
    from collections import namedtuple

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: usage(10**12, 10**12 - 1000, 1000))
    settings = get_settings()
    with pytest.raises(IngestRejected) as exc:
        run_file_job(corpus.get("h264_aac_mp4"), settings)
    assert exc.value.code == ErrorCode.INSUFFICIENT_DISK and "required" in exc.value.details
    assert staging_files(settings) == []


def test_decode_failure_keeps_ffmpeg_text_out_of_the_message(corpus, monkeypatch):
    from insightex.media import engine, ffmpeg

    def broken(*a, **k):
        raise ffmpeg.FFmpegError("ffmpeg exited with 1", "\n".join(f"line {i}" for i in range(50)))

    monkeypatch.setattr(engine.ffmpeg, "run_ffmpeg", broken)
    settings, result, job = ingest(corpus, "h264_aac_mp4")
    assert_rejected(settings, result, job, ErrorCode.TRANSCODE_FAILED)
    stage_error = job.stages[1].error
    assert "line 49" in stage_error and "line 29" not in stage_error  # last 20 lines only, in the stage details
    assert "line" not in job.error  # never in the job's user-facing message


# -- identity, dedupe, originals ----------------------------------------------------------------------

def test_same_file_twice_is_deduplicated_then_renormalised_on_a_new_version(corpus, monkeypatch):
    from insightex.ingest import pipeline
    from insightex.media import engine

    settings, first, job = ingest(corpus, "h264_aac_mp4")
    assert job.status == "succeeded" and not first.deduplicated
    conn = open_db(settings)
    jobs_before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    manifest_before = Workspaces(settings.jobs.workspaces_dir).read_manifest(first.workspace_id)["stages"]["normalise"]

    second, job2 = run_file_job(corpus.get("h264_aac_mp4"), settings)
    assert second.deduplicated and second.job_id is None and second.workspace_id == first.workspace_id and job2 is None
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == jobs_before
    assert Workspaces(settings.jobs.workspaces_dir).read_manifest(first.workspace_id)["stages"]["normalise"] == manifest_before
    assert staging_files(settings) == []

    monkeypatch.setattr(engine, "NORMALISER_VERSION", "3")
    monkeypatch.setattr(pipeline.NormaliseStage, "version", "3")
    third, job3 = run_file_job(corpus.get("h264_aac_mp4"), settings)
    assert not third.deduplicated and third.workspace_id == first.workspace_id and job3.status == "succeeded"
    _, info = normalised(settings, first.workspace_id)
    assert info["normaliser_version"] == "3"
    assert Workspaces(settings.jobs.workspaces_dir).read_manifest(first.workspace_id)["stages"]["normalise"]["key"] != manifest_before["key"]
    assert len(list(settings.jobs.workspaces_dir.iterdir())) == 1


def test_a_queued_job_for_the_same_bytes_is_returned(corpus):
    from insightex.ingest.file_jobs import enqueue_file

    settings = get_settings()
    conn = open_db(settings)
    a = enqueue_file(conn, settings, corpus.get("h264_aac_mp4"))
    b = enqueue_file(conn, settings, corpus.get("h264_aac_mp4"))
    assert not a.deduplicated and b.deduplicated and b.job_id == a.job_id
    assert len(staging_files(settings)) == 1  # the duplicate's copy was removed


def test_original_is_deleted_after_success_by_default(corpus):
    settings, result, job = ingest(corpus, "h264_aac_mp4")
    ws = Workspaces(settings.jobs.workspaces_dir)
    assert job.status == "succeeded" and not (ws.stage_output_dir(result.workspace_id, "fetch") / "source").exists()
    assert (ws.stage_output_dir(result.workspace_id, "fetch") / "source.json").is_file()


def test_original_is_kept_when_configured(corpus, monkeypatch):
    monkeypatch.setenv("INSIGHTEX__INGEST__FILE__KEEP_ORIGINAL", "true")
    clear_settings_cache()
    settings, result, job = ingest(corpus, "h264_aac_mp4")
    ws = Workspaces(settings.jobs.workspaces_dir)
    assert job.status == "succeeded"
    assert (ws.stage_output_dir(result.workspace_id, "fetch") / "source").stat().st_size == corpus.get("h264_aac_mp4").stat().st_size


def test_filename_is_display_only(corpus, tmp_path):
    from insightex.ingest.staging import sanitise_filename

    assert sanitise_filename("../../etc/passwd") == "passwd"
    assert sanitise_filename("a\\b\\lecture 1.mp4") == "lecture 1.mp4"
    assert sanitise_filename("x\x00y\n.mp4") == "xy.mp4"
    assert sanitise_filename("") is None and len(sanitise_filename("é" * 500)) == 200
    odd = tmp_path / "ل ec‮tu re ; $(rm -rf).mp4"
    odd.write_bytes(corpus.get("h264_aac_mp4").read_bytes())
    settings, result, job = ingest_path(odd)
    assert job.status == "succeeded"
    assert result.workspace_id.startswith("sha256-") and ";" not in result.workspace_id


def ingest_path(path):
    settings = get_settings()
    result, job = run_file_job(path, settings)
    return settings, result, job


# -- CLI --------------------------------------------------------------------------------------------

def test_cli_requires_rights_confirmation_and_copies_nothing(corpus, capsys):
    from insightex.ingest.cli import main

    code = main(["ingest-file", str(corpus.get("h264_aac_mp4"))])
    assert code == 2
    assert json.loads(capsys.readouterr().err.splitlines()[0])["error"]["code"] == "RIGHTS_NOT_CONFIRMED"
    assert staging_files(get_settings()) == []


def test_cli_enqueues_and_reports_duplicates(corpus, capsys):
    from insightex.ingest.cli import main

    path = str(corpus.get("h264_aac_mp4"))
    assert main(["ingest-file", path, "--confirm-rights"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["deduplicated"] is False and first["job_id"] and first["lecture_id"].startswith("sha256-")
    assert main(["ingest-file", path, "--confirm-rights"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["deduplicated"] is True and second["job_id"] == first["job_id"]
    assert main(["ingest-file", "/nonexistent/video.mp4", "--confirm-rights"]) == 1


# -- size refusals before staging -----------------------------------------------------------------------

def assert_refused_before_staging(settings, result, code):
    from insightex.jobs import store

    conn = open_db(settings)
    assert result.rejected is not None and result.rejected.code == code and not result.deduplicated
    job = store.get_job(conn, result.job_id)
    assert job.status == "failed" and job.kind == "ingest_file" and job.finished_at
    assert job.error.startswith(f"fetch failed: IngestRejected: {code}:")
    assert [s.status for s in job.stages] == ["failed", "pending"] and f"IngestRejected: {code}" in job.stages[0].error
    assert store.claim_next(conn, 1) is None, "a refused job must not be claimable"
    assert not settings.ingest.file.staging_dir.exists(), "nothing was written to staging"
    assert not settings.jobs.workspaces_dir.exists() or list(settings.jobs.workspaces_dir.iterdir()) == []
    assert conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 0


def test_empty_file_is_refused_before_staging_with_a_failed_job(corpus):
    from insightex.ingest.file_jobs import enqueue_file

    settings = get_settings()
    result = enqueue_file(open_db(settings), settings, corpus.get("empty_mp4"))
    assert_refused_before_staging(settings, result, ErrorCode.EMPTY_FILE)


def test_oversized_file_is_refused_before_staging_with_a_failed_job(corpus, monkeypatch):
    from insightex.ingest.file_jobs import enqueue_file

    monkeypatch.setenv("INSIGHTEX__INGEST__URL__MAX_DOWNLOAD_BYTES", "100000")
    clear_settings_cache()
    settings = get_settings()
    result = enqueue_file(open_db(settings), settings, corpus.get("h264_aac_mp4"))
    assert_refused_before_staging(settings, result, ErrorCode.TOO_LARGE)


@pytest.mark.parametrize("name,code,env", [
    ("empty_mp4", "EMPTY_FILE", {}),
    ("h264_aac_mp4", "TOO_LARGE", {"INSIGHTEX__INGEST__URL__MAX_DOWNLOAD_BYTES": "100000"}),
])
def test_cli_refuses_by_size_with_exit_2_and_writes_nothing_to_staging(corpus, capsys, monkeypatch, name, code, env):
    from insightex.ingest.cli import main

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    clear_settings_cache()
    assert main(["ingest-file", str(corpus.get(name)), "--confirm-rights"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["code"] == code and out["status"] == "rejected" and out["lecture_id"] is None and out["job_id"]
    settings = get_settings()
    assert not settings.ingest.file.staging_dir.exists()
    job = __import__("insightex.jobs.store", fromlist=["store"]).get_job(open_db(settings), out["job_id"])
    assert job.status == "failed" and f"IngestRejected: {code}" in job.error
