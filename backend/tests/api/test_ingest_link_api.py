"""POST /api/ingest/link, probe, and the job endpoints other than the event stream."""

from __future__ import annotations

import pytest

from insightex.api.models import JobOut
from insightex.jobs import store

YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
YT_OTHER = "https://www.youtube.com/watch?v=abcdefghijk"


def post(client, url, rights=True):
    return client.post("/api/ingest/link", json={"url": url, "rights_confirmed": rights})


def test_youtube_link_is_enqueued_with_its_workspace_id(client, conn):
    r = post(client, YT)
    assert r.status_code == 202
    body = r.json()
    assert body["workspace_id"] == "yt-dQw4w9WgXcQ" and body["deduplicated"] is False
    job = store.get_job(conn, body["job_id"])
    assert job.kind == "ingest_link" and job.status == "queued" and job.payload == {"url": YT}
    assert [s.name for s in job.stages] == ["fetch", "normalise"]


def test_same_youtube_workspace_while_active_returns_the_existing_job(client):
    first = post(client, YT).json()
    second = post(client, "https://youtu.be/dQw4w9WgXcQ?t=5").json()
    assert second["job_id"] == first["job_id"] and second["deduplicated"] is True
    assert post(client, YT_OTHER).json()["job_id"] != first["job_id"]


def test_running_job_is_also_deduplicated(client, conn):
    first = post(client, YT).json()
    store.claim_next(conn, 1234)
    assert store.get_job(conn, first["job_id"]).status == "running"
    again = post(client, YT).json()
    assert again["job_id"] == first["job_id"] and again["deduplicated"] is True


def test_finished_job_is_not_deduplicated(client):
    first = post(client, YT).json()
    assert client.post(f"/api/jobs/{first['job_id']}/cancel").json()["status"] == "cancelled"
    second = post(client, YT).json()
    assert second["job_id"] != first["job_id"] and second["deduplicated"] is False


def test_direct_link_starts_in_a_provisional_workspace_and_dedupes_on_the_normalised_url(client):
    a = post(client, "https://videos.example/a.mp4").json()
    assert a["workspace_id"] == f"pending-{a['job_id']}"
    b = post(client, "HTTPS://Videos.Example:443/a.mp4#frag").json()
    assert b["job_id"] == a["job_id"] and b["deduplicated"] is True
    c = post(client, "https://videos.example/b.mp4").json()
    assert c["job_id"] != a["job_id"]


@pytest.mark.parametrize("url,code", [
    ("ftp://videos.example/a.mp4", "UNSUPPORTED_URL"),
    ("not a url", "UNSUPPORTED_URL"),
    ("https://www.youtube.com/playlist?list=PLabc", "PLAYLIST_NOT_SUPPORTED"),
    ("https://canvas.instructure.com/courses/1", "UNSUPPORTED_URL"),
])
def test_unsupported_url_is_rejected_with_400_and_nothing_is_enqueued(client, conn, url, code):
    r = post(client, url)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == code and r.json()["error"]["message"]
    assert store.list_jobs(conn) == []


def test_rights_must_be_confirmed(client, conn):
    r = post(client, YT, rights=False)
    assert r.status_code == 400 and r.json()["error"]["code"] == "RIGHTS_NOT_CONFIRMED"
    assert client.post("/api/ingest/link", json={"url": YT, "rights_confirmed": "yes"}).status_code == 400
    assert client.post("/api/ingest/link", json={"url": YT}).status_code == 400
    assert store.list_jobs(conn) == []


def test_job_document_matches_the_model(client):
    job_id = post(client, YT).json()["job_id"]
    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    doc = r.json()
    assert set(doc) == set(JobOut.model_fields)
    JobOut.model_validate(doc)
    assert doc["status"] == "queued" and doc["workspace_deleted"] is False and doc["workspace_id"] == "yt-dQw4w9WgXcQ"
    assert [s["name"] for s in doc["stages"]] == ["fetch", "normalise"]
    assert set(doc["stages"][0]) == {"name", "status", "progress", "message", "error"}
    assert doc["stages"][0]["status"] == "pending" and doc["stages"][0]["progress"] == 0


def test_unknown_job_is_404(client):
    for path in ("/api/jobs/nope", "/api/jobs/nope/events"):
        assert client.get(path).status_code == 404
    assert client.post("/api/jobs/nope/cancel").status_code == 404
    assert client.post("/api/jobs/nope/retry").status_code == 404


def test_job_list_and_status_filter(client):
    a = post(client, YT).json()["job_id"]
    b = post(client, YT_OTHER).json()["job_id"]
    client.post(f"/api/jobs/{a}/cancel")
    ids = [j["id"] for j in client.get("/api/jobs?limit=20").json()]
    assert ids == [b, a]
    assert [j["id"] for j in client.get("/api/jobs?status=cancelled").json()] == [a]
    assert client.get("/api/jobs?limit=1").json()[0]["id"] == b
    assert client.get("/api/jobs?status=bogus").status_code == 400


def test_cancel_and_retry_transitions(client):
    job_id = post(client, YT).json()["job_id"]
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 409  # queued: nothing to retry
    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409  # already final
    retried = client.post(f"/api/jobs/{job_id}/retry")
    assert retried.status_code == 200 and retried.json()["status"] == "queued"


def test_cancel_of_running_job_sets_the_request_flag(client, conn):
    job_id = post(client, YT).json()["job_id"]
    store.claim_next(conn, 1234)
    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "running"
    assert store.is_cancel_requested(conn, job_id)


def test_workspace_deleted_flag(client, conn, workspaces):
    job_id = post(client, YT).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["workspace_deleted"] is False  # waiting jobs never report it
    client.post(f"/api/jobs/{job_id}/cancel")
    assert client.get(f"/api/jobs/{job_id}").json()["workspace_deleted"] is True  # finished and no directory


def test_probe_reports_existing_youtube_lecture_without_network(client, make_lecture):
    make_lecture("yt-dQw4w9WgXcQ", title="Seen before")
    r = client.post("/api/ingest/probe", json={"url": YT})
    assert r.status_code == 200
    body = r.json()
    assert body["exists_locally"] is True and body["title"] == "Seen before"
    assert body["workspace_id"] == "yt-dQw4w9WgXcQ"
    assert body["thumbnail_url"] == "/api/lectures/yt-dQw4w9WgXcQ/thumbnail"
