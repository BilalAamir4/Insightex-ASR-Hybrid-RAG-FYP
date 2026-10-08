"""The library, media serving (Range), and DELETE /api/lectures/{id}."""

from __future__ import annotations

import pytest

from insightex.jobs import cache, store

LID = "yt-readyvideo1"


def test_library_lists_only_workspaces_with_a_completed_normalise(client, make_lecture, workspaces):
    make_lecture(LID, title="Ready lecture")
    make_lecture("yt-halfdoneabc", with_normalise=False)
    (workspaces.root / "stray-dir").mkdir()
    body = client.get("/api/lectures").json()
    assert [i["lecture_id"] for i in body["lectures"]] == [LID]
    item = body["lectures"][0]
    assert item["title"] == "Ready lecture" and item["duration_s"] == 60.5
    assert item["thumbnail_url"] == f"/api/lectures/{LID}/thumbnail"
    assert set(item) == {"lecture_id", "title", "duration_s", "thumbnail_url", "created_at"}


def test_empty_library(client):
    assert client.get("/api/lectures").json() == {"lectures": []}


def test_lecture_detail(client, make_lecture, app_settings):
    make_lecture(LID)
    r = client.get(f"/api/lectures/{LID}")
    body = r.json()
    assert r.status_code == 200 and body["video_url"] == f"/api/lectures/{LID}/video"
    assert body["external_timestamp_url_template"].endswith("&t={t}s")
    assert str(app_settings.jobs.workspaces_dir) not in r.text and "/home/" not in r.text


@pytest.mark.parametrize("suffix", ["", "/video", "/thumbnail"])
def test_unknown_or_incomplete_lecture_is_404(client, make_lecture, suffix):
    make_lecture("yt-halfdoneabc", with_normalise=False)
    for lid in ("yt-doesnotexist", "yt-halfdoneabc"):
        r = client.get(f"/api/lectures/{lid}{suffix}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "LECTURE_NOT_FOUND"


@pytest.mark.parametrize("bad", ["..%2Fsecret.txt", ".hidden", "a%2Fb", "%2e%2e"])
def test_malformed_ids_never_reach_the_filesystem(client, app_settings, make_lecture, bad):
    make_lecture(LID)
    (app_settings.jobs.workspaces_dir.parent / "secret.txt").write_text("secret")
    r = client.get(f"/api/lectures/{bad}/video")
    assert r.status_code == 404 and "secret" not in r.text


def test_video_is_found_through_the_manifest_and_serves_ranges(client, make_lecture):
    make_lecture(LID, video=bytes(range(256)) * 20)
    full = client.get(f"/api/lectures/{LID}/video")
    assert full.status_code == 200 and full.headers["accept-ranges"] == "bytes"
    assert full.headers["content-type"] == "video/mp4" and len(full.content) == 5120
    part = client.get(f"/api/lectures/{LID}/video", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert part.headers["content-range"] == "bytes 0-99/5120"
    assert part.content == full.content[:100]
    tail = client.get(f"/api/lectures/{LID}/video", headers={"Range": "bytes=5000-"})
    assert tail.status_code == 206 and tail.content == full.content[5000:]
    assert client.get(f"/api/lectures/{LID}/video", headers={"Range": "bytes=9999-"}).status_code == 416
    assert client.head(f"/api/lectures/{LID}/video").status_code == 200


def test_media_requests_touch_the_cache_at_most_once_per_interval(client, make_lecture, monkeypatch):
    make_lecture(LID)
    calls = []
    monkeypatch.setattr(cache, "touch", lambda conn, wid: calls.append(wid))
    for _ in range(3):
        client.get(f"/api/lectures/{LID}/video", headers={"Range": "bytes=0-9"})
    client.get(f"/api/lectures/{LID}/thumbnail")
    assert calls == [LID]


def test_touch_interval_elapsed_touches_again(client, make_lecture, monkeypatch):
    make_lecture(LID)
    calls = []
    monkeypatch.setattr(cache, "touch", lambda conn, wid: calls.append(wid))
    client.get(f"/api/lectures/{LID}/thumbnail")
    client.app.state.touch_times[LID] -= 61
    client.get(f"/api/lectures/{LID}/thumbnail")
    assert calls == [LID, LID]


def test_delete_removes_directory_row_and_library_entry(client, make_lecture, workspaces, conn):
    make_lecture(LID)
    assert client.delete(f"/api/lectures/{LID}").status_code == 204
    assert not workspaces.path(LID).exists()
    assert conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (LID,)).fetchone() is None
    assert client.get("/api/lectures").json() == {"lectures": []}
    assert client.get(f"/api/lectures/{LID}/video").status_code == 404


def test_delete_unknown_is_404(client):
    assert client.delete("/api/lectures/yt-doesnotexist").status_code == 404
    assert client.delete("/api/lectures/.bad").status_code == 404


def test_delete_is_409_while_a_job_is_queued_or_running(client, make_lecture, conn, workspaces):
    make_lecture(LID)
    job_id = client.post("/api/ingest/link", json={"url": "https://youtu.be/readyvideo1", "rights_confirmed": True}).json()["job_id"]
    r = client.delete(f"/api/lectures/{LID}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "LECTURE_BUSY"
    assert workspaces.path(LID).exists()
    store.claim_next(conn, 1)
    assert client.delete(f"/api/lectures/{LID}").status_code == 409
    store.finish(conn, job_id, "succeeded")
    assert client.delete(f"/api/lectures/{LID}").status_code == 204
