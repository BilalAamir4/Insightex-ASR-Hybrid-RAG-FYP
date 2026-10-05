"""Probe, ingest and job-status endpoints with the engine mocked."""

from __future__ import annotations

import time

import pytest

from insightex.core.manifest import read_manifest
from insightex.ingest import engine
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.jobs.ingest_jobs import INTERRUPTED_CODE, recover_interrupted

from api_helpers import YT_ID, YT_URL, YT_URL_2, make_lecture


def _probe_result(**kw):
    base = dict(canonical_id="yt:dQw4w9WgXcQ", lecture_id=YT_ID, source_type="youtube", normalized_url=YT_URL,
                title="T", uploader="U", duration_s=60.0, thumbnail_url="https://img.invalid/t.jpg",
                exists_locally=False)
    return engine.ProbeResult(**{**base, **kw})


def _wait_for(client, job_id, status, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/ingest/{job_id}").json()
        if job["status"] == status:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job never reached {status}: {job}")


def test_probe_success(client, monkeypatch):
    monkeypatch.setattr(engine, "probe", lambda url, settings=None: _probe_result())
    r = client.post("/api/ingest/probe", json={"url": YT_URL})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "T" and body["duration_s"] == 60.0 and body["exists_locally"] is False
    assert body["thumbnail_url"] == "https://img.invalid/t.jpg"


def test_probe_unknown_duration_passes_through_null(client, monkeypatch):
    monkeypatch.setattr(engine, "probe", lambda url, settings=None: _probe_result(duration_s=None))
    assert client.post("/api/ingest/probe", json={"url": YT_URL}).json()["duration_s"] is None


def test_probe_existing_lecture_points_at_local_thumbnail(client, monkeypatch):
    monkeypatch.setattr(engine, "probe",
                        lambda url, settings=None: _probe_result(exists_locally=True, thumbnail_url=None))
    body = client.post("/api/ingest/probe", json={"url": YT_URL}).json()
    assert body["exists_locally"] is True
    assert body["thumbnail_url"] == f"/api/lectures/{YT_ID}/thumbnail"


def test_probe_engine_error_is_4xx_with_code_and_message(client, monkeypatch):
    def boom(url, settings=None):
        raise IngestError(ErrorCode.PLAYLIST_NOT_SUPPORTED)
    monkeypatch.setattr(engine, "probe", boom)
    r = client.post("/api/ingest/probe", json={"url": YT_URL})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "PLAYLIST_NOT_SUPPORTED" and "Playlists" in err["message"]


def test_probe_unexpected_error_does_not_leak_details(client, monkeypatch):
    def boom(url, settings=None):
        raise RuntimeError("secret /home/x/traceback")
    monkeypatch.setattr(engine, "probe", boom)
    r = client.post("/api/ingest/probe", json={"url": YT_URL})
    assert r.status_code == 502
    assert "secret" not in r.text and r.json()["error"]["code"] == "NETWORK_ERROR"


def test_probe_real_parser_rejects_garbage_url(client):
    r = client.post("/api/ingest/probe", json={"url": "not a url"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNSUPPORTED_URL"


@pytest.mark.parametrize("body", [{"url": YT_URL}, {"url": YT_URL, "rights_confirmed": False}])
def test_rights_must_be_confirmed(client, runner, body):
    r = client.post("/api/ingest", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "RIGHTS_NOT_CONFIRMED"
    assert runner.calls == []


def test_rights_must_be_boolean_true(client, runner):
    r = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": "yes"})
    assert r.status_code in (400, 422) and runner.calls == []


def test_ingest_rejects_bad_url(client):
    r = client.post("/api/ingest", json={"url": "ftp://x", "rights_confirmed": True})
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNSUPPORTED_URL"


def test_job_lifecycle_to_done(client, runner):
    r = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True})
    assert r.status_code == 200
    job_id, lecture_id = r.json()["job_id"], r.json()["lecture_id"]
    assert job_id and lecture_id == YT_ID
    assert runner.started.wait(5)
    running = _wait_for(client, job_id, "running")
    assert running["stage"] == "downloading" and running["fraction"] == 0.5
    assert running["message"] == "half way" and running["lecture_id"] == YT_ID and running["error"] is None
    runner.release.set()
    done = _wait_for(client, job_id, "done")
    assert done["fraction"] == 1.0 and done["error"] is None


def test_second_job_waits_as_queued(client, runner):
    first = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True}).json()["job_id"]
    assert runner.started.wait(5)
    second = client.post("/api/ingest", json={"url": YT_URL_2, "rights_confirmed": True}).json()["job_id"]
    assert second != first
    queued = client.get(f"/api/ingest/{second}").json()
    assert queued["status"] == "queued" and queued["fraction"] is None
    assert runner.calls == [YT_URL]  # one at a time
    runner.release.set()
    _wait_for(client, second, "done")
    assert runner.calls == [YT_URL, YT_URL_2]


def test_job_lifecycle_to_failed_with_engine_message(client, runner):
    runner.block = False
    runner.raises = IngestError(ErrorCode.TOO_LONG, "This video is longer than the 3 hours limit.")
    job_id = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True}).json()["job_id"]
    failed = _wait_for(client, job_id, "failed")
    assert failed["error"] == {"code": "TOO_LONG", "message": "This video is longer than the 3 hours limit."}
    assert failed["message"] == failed["error"]["message"]


def test_unexpected_runner_exception_becomes_generic_failure(client, runner):
    runner.block = False
    runner.raises = RuntimeError("traceback with /secret/path")
    job_id = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True}).json()["job_id"]
    failed = _wait_for(client, job_id, "failed")
    assert "secret" not in str(failed) and failed["error"]["code"] == "DOWNLOAD_FAILED"


def test_duplicate_submission_returns_existing_job(client, runner):
    a = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True}).json()
    assert runner.started.wait(5)
    # Same lecture via a different spelling of the URL.
    b = client.post("/api/ingest", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                         "rights_confirmed": True}).json()
    assert b["job_id"] == a["job_id"]
    runner.release.set()
    _wait_for(client, a["job_id"], "done")
    assert len(runner.calls) == 1


def test_resubmission_after_failure_starts_a_new_job(client, runner):
    runner.block = False
    runner.raises = IngestError(ErrorCode.DOWNLOAD_FAILED)
    first = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True}).json()["job_id"]
    _wait_for(client, first, "failed")
    runner.raises = None
    second = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True}).json()["job_id"]
    assert second != first
    _wait_for(client, second, "done")


def test_already_ready_lecture_returns_null_job(client, settings, runner):
    make_lecture(settings, YT_ID)
    r = client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True})
    assert r.status_code == 200
    assert r.json() == {"job_id": None, "lecture_id": YT_ID, "status": "ready"}
    assert runner.calls == []


def test_ready_manifest_without_video_file_is_not_ready(client, settings, runner):
    make_lecture(settings, YT_ID, with_media=False)
    runner.block = False
    assert client.post("/api/ingest", json={"url": YT_URL, "rights_confirmed": True}).json()["job_id"]


def test_unknown_job_is_404(client):
    r = client.get("/api/ingest/deadbeef")
    assert r.status_code == 404 and r.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_startup_marks_interrupted_manifests_failed(settings, runner):
    from fastapi.testclient import TestClient

    from insightex.api.app import create_app

    make_lecture(settings, "yt_downloading1", status="downloading", with_media=False)
    make_lecture(settings, "yt_transcoding1", status="transcoding", with_media=False)
    make_lecture(settings, "yt_readyvideo1", status="ready")
    make_lecture(settings, "yt_alreadyfail1", status="failed", with_media=False)
    with TestClient(create_app(settings=settings, runner=runner)):
        pass
    for lid in ("yt_downloading1", "yt_transcoding1"):
        m = read_manifest(settings.lectures_dir / lid)
        assert m.status == "failed"
        assert m.error["code"] == INTERRUPTED_CODE and "interrupted" in m.error["message"]
    assert read_manifest(settings.lectures_dir / "yt_readyvideo1").status == "ready"
    assert read_manifest(settings.lectures_dir / "yt_alreadyfail1").error["code"] == "DOWNLOAD_FAILED"


def test_recovery_skips_odd_directories(settings):
    make_lecture(settings, "yt_downloading1", status="downloading", with_media=False)
    (settings.lectures_dir / ".locks").mkdir()
    (settings.lectures_dir / "not a lecture").mkdir()
    (settings.lectures_dir / "yt_nomanifest1").mkdir()
    assert recover_interrupted(settings.lectures_dir) == ["yt_downloading1"]


def test_recovery_with_missing_lectures_dir(settings):
    assert recover_interrupted(settings.lectures_dir) == []
