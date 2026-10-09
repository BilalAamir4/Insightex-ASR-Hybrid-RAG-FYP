"""POST /api/ingest/upload: streamed raw body, pre-body checks, interruption clean-up, one active upload (M2 session 2)."""

from __future__ import annotations

import hashlib
import os
import threading
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from ingest_helpers import open_db
from media_corpus import Corpus

from insightex.api.app import create_app
from insightex.core.config import clear_settings_cache, get_settings
from insightex.ingest import staging
from insightex.ingest.errors import DEFAULT_MESSAGES, ErrorCode
from insightex.jobs import store
from insightex.jobs.runner import run_job
from insightex.jobs.workspace import Workspaces

PATH = "/api/ingest/upload"
BLOB = os.urandom(300_000)  # not a video: the HTTP layer neither knows nor cares


def headers(length, *, rights="true", name="Lecture 1.mp4") -> dict[str, str]:
    h = {"Content-Type": "application/octet-stream", "X-Insightex-Filename": quote(name)}
    if length is not None:
        h["Content-Length"] = str(length)
    if rights is not None:
        h["X-Insightex-Rights-Confirmed"] = rights
    return h


def chunks(data: bytes, size: int = 40_000):
    for i in range(0, len(data), size):
        yield data[i:i + size]


def upload(client, data: bytes, **kw):
    return client.post(PATH, content=chunks(data), headers=headers(len(data), **kw))


def staging_files(settings) -> list[str]:
    directory = staging.staging_dir(settings)
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


def error_of(response) -> tuple[str, str]:
    body = response.json()["error"]
    return body["code"], body["message"]


@pytest.fixture
def app_settings():
    return get_settings()


@pytest.fixture
def client(app_settings):
    with TestClient(create_app(app_settings)) as c:
        yield c


@pytest.fixture
def conn(client, app_settings):
    c = open_db(app_settings)
    yield c
    c.close()


def client_with(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(f"INSIGHTEX__INGEST__{key}", str(value))
    clear_settings_cache()
    return TestClient(create_app(get_settings()))


# -- success and de-duplication ----------------------------------------------------------------------


def test_upload_is_staged_hashed_and_queued_as_an_http_ingest_file_job(client, conn, app_settings):
    r = upload(client, BLOB)
    assert r.status_code == 202
    body = r.json()
    sha = hashlib.sha256(BLOB).hexdigest()
    assert body == {"lecture_id": f"sha256-{sha[:32]}", "job_id": body["job_id"], "deduplicated": False}
    job = store.get_job(conn, body["job_id"])
    assert job.kind == "ingest_file" and job.status == "queued" and job.workspace_id == body["lecture_id"]
    assert job.payload["via"] == "http" and job.payload["sha256"] == sha and job.payload["size_bytes"] == len(BLOB)
    assert job.payload["original_filename"] == "Lecture 1.mp4"
    staged = staging.staged_path(app_settings, job.payload["staged"])
    assert staged.read_bytes() == BLOB
    assert staging_files(app_settings) == [staged.name]  # no .tmp left over


def test_filename_is_display_text_only(client, conn):
    r = client.post(PATH, content=chunks(BLOB), headers=headers(len(BLOB), name="../../etc/pass\x00wd.mp4"))
    assert r.status_code == 202
    assert store.get_job(conn, r.json()["job_id"]).payload["original_filename"] == "passwd.mp4"


def test_same_bytes_while_the_job_is_active_return_that_job_and_stage_nothing_new(client, app_settings):
    first = upload(client, BLOB).json()
    second = upload(client, BLOB)
    assert second.status_code == 202
    assert second.json() == {"lecture_id": first["lecture_id"], "job_id": first["job_id"], "deduplicated": True}
    assert len(staging_files(app_settings)) == 1


def test_reupload_of_an_up_to_date_lecture_is_200_without_a_job(client, conn, app_settings, monkeypatch):
    first = upload(client, BLOB).json()
    from insightex.ingest import file_jobs

    monkeypatch.setattr(file_jobs, "_current_lecture", lambda workspaces, workspace_id: True)
    store.finish(conn, first["job_id"], "succeeded")
    again = upload(client, BLOB)
    assert again.status_code == 200
    assert again.json() == {"lecture_id": first["lecture_id"], "job_id": None, "deduplicated": True}
    assert len(staging_files(app_settings)) == 1  # the first copy; the duplicate's was deleted


# -- checks before the body, in order ------------------------------------------------------------------


@pytest.mark.parametrize("rights", [None, "false", "True", ""])
def test_rights_header_must_be_exactly_true(client, app_settings, rights):
    r = client.post(PATH, content=chunks(BLOB), headers=headers(len(BLOB), rights=rights))
    assert r.status_code == 400
    assert error_of(r) == ("RIGHTS_NOT_CONFIRMED", DEFAULT_MESSAGES[ErrorCode.RIGHTS_NOT_CONFIRMED])
    assert staging_files(app_settings) == []


def test_missing_content_length_is_411(client, app_settings):
    r = client.post(PATH, content=chunks(BLOB), headers=headers(None))  # httpx falls back to chunked encoding
    assert r.status_code == 411 and error_of(r)[0] == "LENGTH_REQUIRED"
    r = client.post(PATH, content=b"x", headers={**headers(1), "Content-Length": "abc"})
    assert r.status_code == 411 and error_of(r)[0] == "LENGTH_REQUIRED"
    assert staging_files(app_settings) == []


def test_empty_body_is_400(client):
    r = client.post(PATH, content=b"", headers=headers(0))
    assert r.status_code == 400 and error_of(r)[0] == "EMPTY_FILE"


def test_oversize_content_length_is_413_before_any_body_is_read(monkeypatch, app_settings):
    with client_with(monkeypatch, URL__MAX_DOWNLOAD_BYTES=1000) as c:
        read = []

        def body():
            read.append(1)
            yield b"x" * 10

        r = c.post(PATH, content=body(), headers=headers(5000))
        assert r.status_code == 413 and error_of(r)[0] == "TOO_LARGE"
        assert staging_files(app_settings) == []
        assert c.get("/api/ingest/limits").json() == {"max_upload_bytes": 1000}


def test_not_enough_disk_is_507(monkeypatch, app_settings):
    with client_with(monkeypatch, DISK_FREE_RESERVE_BYTES=10**18) as c:
        r = upload(c, BLOB)
        assert r.status_code == 507 and error_of(r)[0] == "INSUFFICIENT_DISK"
        assert staging_files(app_settings) == []


def test_checks_run_in_the_documented_order(monkeypatch):
    with client_with(monkeypatch, URL__MAX_DOWNLOAD_BYTES=1000, DISK_FREE_RESERVE_BYTES=10**18) as c:
        assert c.post(PATH, content=b"", headers=headers(None, rights=None)).status_code == 400  # rights first
        assert c.post(PATH, content=chunks(BLOB), headers=headers(None)).status_code == 411  # then length
        assert c.post(PATH, content=b"", headers=headers(0)).status_code == 400  # then empty
        assert c.post(PATH, content=b"x", headers=headers(5000)).status_code == 413  # then size, before disk
        assert c.post(PATH, content=b"x" * 10, headers=headers(10)).status_code == 507


def test_error_messages_are_the_fixed_per_code_text(client):
    r = client.post(PATH, content=b"", headers=headers(0))
    assert error_of(r) == ("EMPTY_FILE", DEFAULT_MESSAGES[ErrorCode.EMPTY_FILE])
    assert r.headers["connection"] == "close"


# -- while streaming --------------------------------------------------------------------------------------


def test_more_bytes_than_content_length_deletes_the_copy_and_frees_the_slot(client, app_settings):
    r = client.post(PATH, content=chunks(BLOB), headers=headers(len(BLOB) - 1000))
    assert r.status_code == 400 and error_of(r)[0] == "UPLOAD_INTERRUPTED"
    assert staging_files(app_settings) == []
    assert upload(client, BLOB).status_code == 202


def test_a_body_that_fails_midway_leaves_nothing_and_frees_the_busy_slot(client, app_settings):
    def broken():
        yield BLOB[:100_000]
        raise ConnectionResetError("client went away")

    r = client.post(PATH, content=broken(), headers=headers(len(BLOB)))
    assert r.status_code == 400 and error_of(r)[0] == "UPLOAD_INTERRUPTED"
    assert staging_files(app_settings) == []
    assert upload(client, BLOB).status_code == 202  # the slot was released


def test_a_short_body_is_interrupted_and_leaves_nothing(client, app_settings):
    r = client.post(PATH, content=chunks(BLOB[:50_000]), headers=headers(len(BLOB)))
    assert r.status_code == 400 and error_of(r)[0] == "UPLOAD_INTERRUPTED"
    assert staging_files(app_settings) == []
    assert upload(client, BLOB).status_code == 202


def test_second_upload_while_one_is_in_progress_gets_409_and_the_first_still_succeeds(app_settings):
    first_chunk_in, release = threading.Event(), threading.Event()

    def slow():
        yield BLOB[:100_000]
        first_chunk_in.set()
        assert release.wait(20)
        yield BLOB[100_000:]

    results = {}

    def first():
        with TestClient(create_app(app_settings)) as c1:
            results["first"] = c1.post(PATH, content=slow(), headers=headers(len(BLOB)))

    t = threading.Thread(target=first)
    t.start()
    try:
        assert first_chunk_in.wait(20)
        with TestClient(create_app(app_settings)) as c2:
            busy = c2.post(PATH, content=b"other", headers=headers(5))
        assert busy.status_code == 409 and error_of(busy)[0] == "UPLOAD_BUSY"
    finally:
        release.set()
        t.join(30)
    assert results["first"].status_code == 202


# -- browser safety ---------------------------------------------------------------------------------------


def test_preflight_from_a_foreign_origin_gets_no_cors_headers(client):
    r = client.options(PATH, headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-insightex-rights-confirmed,x-insightex-filename,content-type",
    })
    assert not any(name.lower().startswith("access-control-") for name in r.headers)
    assert r.status_code in (400, 404, 405)
    posted = client.post(PATH, content=b"x", headers={**headers(1), "Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in posted.headers}


# -- end to end: the job outcome over HTTP -----------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Corpus:
    return Corpus(tmp_path_factory.mktemp("upload_corpus"))


def run_claimed_job(conn, settings, job_id):
    claimed = store.claim_next(conn, os.getpid())
    assert claimed is not None and claimed.id == job_id
    run_job(conn, claimed, settings, Workspaces(settings.jobs.workspaces_dir))
    return store.get_job(conn, job_id)


@pytest.mark.media
def test_accepted_fixture_becomes_a_lecture_with_http_provenance(client, conn, app_settings, corpus):
    data = corpus.get("h264_aac_mp4").read_bytes()
    r = upload(client, data, name="lecture.mp4")
    assert r.status_code == 202
    job = run_claimed_job(conn, app_settings, r.json()["job_id"])
    assert job.status == "succeeded", job.error
    lecture = client.get(f"/api/lectures/{r.json()['lecture_id']}")
    assert lecture.status_code == 200
    assert lecture.json()["title"] == "lecture" and lecture.json()["warnings"] == []
    source = Workspaces(app_settings.jobs.workspaces_dir).stage_output_dir(r.json()["lecture_id"], "fetch")
    import json

    meta = json.loads((source / "source.json").read_text())
    assert meta["kind"] == "upload" and meta["via"] == "http" and meta["sha256"] == hashlib.sha256(data).hexdigest()
    assert staging_files(app_settings) == []  # adopted copy deleted after the stage
    again = upload(client, data)
    assert again.status_code == 200 and again.json()["job_id"] is None and again.json()["deduplicated"] is True


@pytest.mark.media
def test_rejected_fixture_fails_with_its_code_and_leaves_no_lecture_or_staging(client, conn, app_settings, corpus):
    data = corpus.get("audio_only_m4a").read_bytes()
    r = upload(client, data, name="talk.m4a")
    assert r.status_code == 202
    job = run_claimed_job(conn, app_settings, r.json()["job_id"])
    assert job.status == "failed" and "NO_VIDEO_STREAM" in job.error
    assert client.get(f"/api/jobs/{job.id}").json()["stages"][1]["status"] == "failed"
    assert client.get(f"/api/lectures/{r.json()['lecture_id']}").status_code == 404
    assert staging_files(app_settings) == []
    assert not Workspaces(app_settings.jobs.workspaces_dir).path(r.json()["lecture_id"]).exists()
