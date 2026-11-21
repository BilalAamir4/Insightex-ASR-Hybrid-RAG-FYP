"""The extraction hold at enqueue time and on the command line (ADR-0054 decision 8, Amendment 1 items 1, 2, 5).
No media, no worker: jobs are only enqueued and checked."""

from __future__ import annotations

import hashlib
import json

import pytest

from insightex.core.config import get_settings
from insightex.extract import hold, hold_cli
from insightex.ingest import cli as ingest_cli
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.file_jobs import enqueue_file
from insightex.ingest.link_jobs import enqueue_link
from insightex.jobs import db, store
from insightex.jobs.workspace import Workspaces
from insightex.sources.identity import workspace_id_for_bytes

YT = "https://www.youtube.com/watch?v=abcdefghijk"
YT_WS = "yt-abcdefghijk"


@pytest.fixture
def env():
    settings = get_settings()
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    yield settings, conn, Workspaces(settings.jobs.workspaces_dir)
    conn.close()


def jobs(conn):
    return store.list_jobs(conn, limit=100)


def publish_extract(workspaces: Workspaces, ws_id: str) -> None:
    (workspaces.path(ws_id) / "stages" / "extract" / "0123456789abcdef").mkdir(parents=True)


def test_hold_on_a_youtube_link_puts_the_flag_in_the_payload(env):
    settings, conn, _ = env
    job_id, ws_id, dedup = enqueue_link(conn, settings, YT, "hindi", hold_extract=True)
    assert ws_id == YT_WS and not dedup and store.get_job(conn, job_id).payload["hold_extract"] is True
    other, _, _ = enqueue_link(conn, settings, "https://www.youtube.com/watch?v=bbbbbbbbbbb", "hindi")
    assert "hold_extract" not in store.get_job(conn, other).payload


def test_hold_on_a_non_youtube_link_refuses_before_any_job(env, capsys):
    settings, conn, _ = env
    with pytest.raises(hold.HoldRefused) as exc:
        enqueue_link(conn, settings, "https://example.com/lecture.mp4", "hindi", hold_extract=True)
    assert str(exc.value) == hold.NON_YOUTUBE_MESSAGE and jobs(conn) == []
    code = ingest_cli.main(["ingest", "https://example.com/lecture.mp4", "--confirm-rights", "--language", "hindi",
                            "--hold-extract"])
    err = capsys.readouterr().err
    assert code == 2 and hold.NON_YOUTUBE_MESSAGE in err and '"code"' not in err and jobs(conn) == []


def test_hold_with_an_active_job_refuses(env, capsys):
    settings, conn, _ = env
    first, _, _ = enqueue_link(conn, settings, YT, "hindi")
    with pytest.raises(IngestError) as exc:
        enqueue_link(conn, settings, YT, "hindi", hold_extract=True)
    assert exc.value.code == ErrorCode.EXTRACT_HOLD_JOB_ACTIVE and [j.id for j in jobs(conn)] == [first]
    assert exc.value.message == ("A job for this lecture is already queued or running, so a hold could not stop it "
                                 "from extracting. Wait for it to finish, then ingest again with --hold-extract.")
    code = ingest_cli.main(["ingest", YT, "--confirm-rights", "--language", "hindi", "--hold-extract"])
    assert code == 2 and "EXTRACT_HOLD_JOB_ACTIVE" in capsys.readouterr().err and len(jobs(conn)) == 1


def test_hold_after_extraction_refuses_and_creates_no_job(env):
    settings, conn, workspaces = env
    publish_extract(workspaces, YT_WS)
    with pytest.raises(IngestError) as exc:
        enqueue_link(conn, settings, YT, "hindi", hold_extract=True)
    assert exc.value.code == ErrorCode.EXTRACT_HOLD_AFTER_EXTRACTION and jobs(conn) == []
    assert exc.value.message.startswith("This lecture has already been through extraction")


def _file(tmp_path, content=b"not really a video, only bytes for hashing"):
    p = tmp_path / "lecture.mp4"
    p.write_bytes(content)
    return p


def test_ingest_file_hold_after_extraction_and_with_an_active_job(env, tmp_path):
    settings, conn, workspaces = env
    path = _file(tmp_path)
    ws_id = workspace_id_for_bytes(hashlib.sha256(path.read_bytes()).hexdigest())
    publish_extract(workspaces, ws_id)
    with pytest.raises(IngestError) as exc:
        enqueue_file(conn, settings, path, language="hindi", hold_extract=True)
    assert exc.value.code == ErrorCode.EXTRACT_HOLD_AFTER_EXTRACTION and jobs(conn) == []
    assert list(settings.ingest.file.staging_dir.glob("*")) == []  # the staged copy is deleted

    (tmp_path / "second").mkdir()
    other = _file(tmp_path / "second", b"other bytes")
    first = enqueue_file(conn, settings, other, language="hindi")
    with pytest.raises(IngestError) as exc:
        enqueue_file(conn, settings, other, language="hindi", hold_extract=True)
    assert exc.value.code == ErrorCode.EXTRACT_HOLD_JOB_ACTIVE and [j.id for j in jobs(conn)] == [first.job_id]


def test_ingest_file_hold_flag_reaches_the_payload(env, tmp_path):
    settings, conn, _ = env
    result = enqueue_file(conn, settings, _file(tmp_path), language="hindi", hold_extract=True)
    assert store.get_job(conn, result.job_id).payload["hold_extract"] is True


def test_release_refuses_without_a_hold_and_creates_no_job(env, capsys):
    _, conn, workspaces = env
    assert hold_cli.main(["release", YT_WS]) == 2
    assert hold.NO_HOLD_MESSAGE in capsys.readouterr().err and jobs(conn) == []
    workspaces.write_manifest(YT_WS, {"stages": {}, "extract_hold": {"set_at": "t", "job_id": "j", "released_at": "u"}})
    assert hold_cli.main(["release", YT_WS]) == 2 and jobs(conn) == []  # already released


def test_release_enqueues_a_job_and_never_writes_the_manifest(env, capsys):
    _, conn, workspaces = env
    manifest = {"stages": {}, "extract_hold": {"set_at": "t", "job_id": "j"}}
    workspaces.write_manifest(YT_WS, manifest)
    before = (workspaces.path(YT_WS) / "manifest.json").read_bytes()
    assert hold_cli.main(["release", YT_WS]) == 0
    out = json.loads(capsys.readouterr().out)
    job = store.get_job(conn, out["job_id"])
    assert job.kind == hold.RELEASE_KIND and job.workspace_id == YT_WS and job.stages == [] and job.status == "queued"
    assert (workspaces.path(YT_WS) / "manifest.json").read_bytes() == before


def test_list_shows_held_workspaces(env, capsys):
    _, _, workspaces = env
    workspaces.write_manifest(YT_WS, {"stages": {}, "extract_hold": {"set_at": "t", "job_id": "j"}})
    workspaces.write_manifest("yt-bbbbbbbbbbb", {"stages": {}, "extract_hold": {"set_at": "t", "job_id": "j",
                                                                                 "released_at": "u"}})
    workspaces.write_manifest("yt-ccccccccccc", {"stages": {}})
    assert hold_cli.main(["list"]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows == [{"workspace_id": YT_WS, "set_at": "t", "job_id": "j"}]
