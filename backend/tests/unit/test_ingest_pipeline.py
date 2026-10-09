"""The ingest_link pipeline end to end on a local HTTP server and a synthetic clip (no internet)."""

from __future__ import annotations

import json

import pytest
from ingest_helpers import open_db, run_link_job

from insightex.core.config import get_settings
from insightex.ingest import netguard
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.jobs.workspace import Workspaces
from insightex.media import ffmpeg


def test_fetch_and_normalise_produce_valid_outputs(video_server):
    settings = get_settings()
    ws = Workspaces(settings.jobs.workspaces_dir)
    job = run_link_job(video_server.url, settings)
    assert job.status == "succeeded", [s.error for s in job.stages]
    assert [s.status for s in job.stages] == ["succeeded", "succeeded"]
    assert job.workspace_id.startswith("sha256-") and len(job.workspace_id) == len("sha256-") + 32
    assert [p.name for p in ws.root.iterdir()] == [job.workspace_id]  # the provisional workspace is gone

    fetched = ws.stage_output_dir(job.workspace_id, "fetch")
    source = json.loads((fetched / "source.json").read_text())
    assert source["url"] == video_server.url and source["source_type"] == "direct"
    assert source["downloader"] == "httpx" and source["size_bytes"] == video_server.size == (fetched / "source").stat().st_size
    assert job.workspace_id == f"sha256-{source['sha256'][:32]}"

    out = ws.stage_output_dir(job.workspace_id, "normalise")
    video, audio = ffmpeg.ffprobe(out / "video.mp4"), ffmpeg.ffprobe(out / "audio.wav")
    assert video.video.codec == "h264" and video.audio.codec == "aac" and 11.5 < video.duration_s < 12.5
    assert (audio.audio.sample_rate, audio.audio.channels, audio.audio.codec) == (16000, 1, "pcm_s16le")
    assert (out / "thumbnail.jpg").stat().st_size > 0
    info = json.loads((out / "normalise.json").read_text())
    assert info["decision"]["video"] == "copy" and info["decision"]["audio"] == "copy" and info["schema"] == 2
    assert info["probe"]["audio"]["sample_rate"] == 44100 and info["source"]["sha256"] == source["sha256"]
    assert info["source"]["kind"] == "link" and info["normaliser_version"] == "2" and info["warnings"] == []
    assert (out / "video.mp4").read_bytes()[4:8] == b"ftyp"
    conn = open_db(settings)
    assert [(r["id"], r["source_kind"], r["source_ref"]) for r in conn.execute("SELECT * FROM workspaces")] == [
        (job.workspace_id, "url", video_server.url)]


def test_progress_is_reported_by_both_stages(video_server, monkeypatch):
    from insightex.core.config import clear_settings_cache
    from insightex.jobs import runner

    monkeypatch.setenv("INSIGHTEX__JOBS__PROGRESS_MIN_INTERVAL_S", "0")  # write every call; the clip is tiny
    clear_settings_cache()
    settings = get_settings()
    seen = []
    real = runner.store.update_stage

    def spy(conn_, job_id, idx, **changes):
        if "progress" in changes:
            seen.append((idx, changes["progress"], changes.get("message")))
        return real(conn_, job_id, idx, **changes)

    monkeypatch.setattr(runner.store, "update_stage", spy)
    job = run_link_job(video_server.url, settings)
    assert job.status == "succeeded"
    fetch = [p for i, p, _ in seen if i == 0]
    normalise = [(p, m) for i, p, m in seen if i == 1]
    assert fetch[0] == 0.0 and fetch[-1] == 1.0 and fetch == sorted(fetch)
    values = [p for p, _ in normalise]
    assert values[0] == 0.0 and values[-1] == 1.0 and values == sorted(values)
    messages = {m for _, m in normalise}
    assert {"Copying video", "Extracting audio for transcription", "Saving thumbnail"} <= messages
    assert any(0.0 < p < 1.0 for p in values)


def test_second_run_of_the_same_link_reuses_everything_it_can(video_server):
    settings = get_settings()
    conn = open_db(settings)
    first = run_link_job(video_server.url, settings, conn)
    second = run_link_job(video_server.url, settings, conn)
    assert second.status == "succeeded" and second.workspace_id == first.workspace_id
    # A direct link's bytes are unknown until downloaded, so fetch runs again; the key chain makes normalise cached.
    assert [s.status for s in second.stages] == ["succeeded", "cached"]
    assert [s.stage_key for s in second.stages] == [s.stage_key for s in first.stages]
    ws = Workspaces(settings.jobs.workspaces_dir)
    assert sorted(p.name for p in ws.root.iterdir()) == [first.workspace_id]
    assert len(video_server.hits) >= 2


def test_a_different_url_with_identical_bytes_lands_in_the_same_workspace(video_server):
    settings = get_settings()
    conn = open_db(settings)
    first = run_link_job(video_server.url, settings, conn)
    second = run_link_job(video_server.url + "?mirror=2", settings, conn)
    assert second.workspace_id == first.workspace_id
    assert [s.status for s in second.stages] == ["succeeded", "succeeded"]  # different fetch key, so normalise reruns


def test_resubmitting_a_finished_youtube_workspace_is_all_cached(video_server, monkeypatch):
    """Same code path for YouTube ids, with the downloader replaced by a local copy of the clip."""
    from insightex.ingest import pipeline
    from insightex.ingest.sources import youtube

    settings = get_settings()
    conn = open_db(settings)
    calls = []

    def fake_probe(parsed, cfg):
        from insightex.ingest.sources.base import SourceMeta

        return SourceMeta(title="Lecture 1", uploader="Prof", duration_s=12.0, size_bytes=video_server.size, ext="mp4")

    def fake_download(parsed, dest, cfg, meta, on_bytes):
        import httpx

        calls.append(1)
        out = dest / "source.mp4"
        with httpx.stream("GET", video_server.url) as r, out.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
                on_bytes(f.tell(), video_server.size)
        return out

    monkeypatch.setattr(youtube, "probe", fake_probe)
    monkeypatch.setattr(youtube, "download", fake_download)
    pipeline.SOURCES["youtube"].probe, pipeline.SOURCES["youtube"].download = fake_probe, fake_download
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    first = run_link_job(url, settings, conn)
    assert first.status == "succeeded" and first.workspace_id == "yt-dQw4w9WgXcQ"
    second = run_link_job(url, settings, conn)
    assert [s.status for s in second.stages] == ["cached", "cached"] and len(calls) == 1
    assert second.workspace_id == first.workspace_id


def test_unreachable_download_fails_the_fetch_stage_with_the_reason(allow_loopback):
    settings = get_settings()
    job = run_link_job("http://127.0.0.1:9/none.mp4", settings)
    assert job.status == "failed" and job.stages[0].status == "failed" and job.stages[1].status == "pending"
    assert "IngestError" in job.stages[0].error


def test_not_a_video_fails_normalise_and_keeps_fetch(serve_bytes, media):
    settings = get_settings()
    job = run_link_job(serve_bytes(media["garbage"].read_bytes()).url, settings)
    assert job.status == "failed" and [s.status for s in job.stages] == ["succeeded", "failed"]
    assert "NOT_A_VIDEO" in job.stages[1].error and "NOT_A_VIDEO" in job.error
    assert job.workspace_id.startswith("sha256-")  # fetch is kept in the content-addressed workspace, ready for retry


def test_production_ssrf_guard_still_rejects_loopback():
    """No fixture here: the guard as shipped must refuse localhost and private addresses."""
    for url in ("http://127.0.0.1:8000/a.mp4", "http://localhost/a.mp4", "http://10.0.0.5/a.mp4", "http://[::1]/a.mp4"):
        with pytest.raises(IngestError) as exc:
            netguard.check_url(url)
        assert exc.value.code == ErrorCode.BLOCKED_ADDRESS


def test_job_pointing_at_loopback_fails_without_the_test_allowance():
    job = run_link_job("http://127.0.0.1:9/lecture.mp4", get_settings())
    assert job.status == "failed" and job.stages[0].status == "failed"
    assert "BLOCKED_ADDRESS" in job.stages[0].error
