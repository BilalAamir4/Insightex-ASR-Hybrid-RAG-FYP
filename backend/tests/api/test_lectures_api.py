"""Lecture library, manifest, video (Range) and thumbnail endpoints."""

from __future__ import annotations

import pytest

from api_helpers import VIDEO_BYTES, make_lecture

LID = "yt_readyvideo1"


@pytest.fixture
def lecture(settings):
    return make_lecture(settings, LID)


def test_list_only_ready_lectures(client, settings, lecture):
    make_lecture(settings, "yt_failedvideo1", status="failed", with_media=False)
    make_lecture(settings, "yt_downloading1", status="downloading", with_media=False)
    (settings.lectures_dir / ".locks").mkdir()
    body = client.get("/api/lectures").json()
    assert [i["lecture_id"] for i in body["lectures"]] == [LID]
    item = body["lectures"][0]
    assert item["title"] == "Ready lecture" and item["duration_s"] == 12.5
    assert item["thumbnail_url"] == f"/api/lectures/{LID}/thumbnail"


def test_list_empty_when_no_lectures_dir(client):
    assert client.get("/api/lectures").json() == {"lectures": []}


def test_manifest_has_no_absolute_paths(client, settings, lecture):
    r = client.get(f"/api/lectures/{LID}")
    assert r.status_code == 200
    body = r.json()
    assert body["external_timestamp_url_template"].endswith("&t={t}s")
    assert body["video_url"] == f"/api/lectures/{LID}/video"
    assert str(settings.lectures_dir) not in r.text and "/home/" not in r.text
    assert body["files"]["video"] == "video.mp4"  # relative


def test_not_ready_or_missing_lecture_is_404(client, settings):
    make_lecture(settings, "yt_failedvideo1", status="failed", with_media=False)
    for lid in ("yt_failedvideo1", "yt_doesnotexist"):
        for suffix in ("", "/video", "/thumbnail"):
            r = client.get(f"/api/lectures/{lid}{suffix}")
            assert r.status_code == 404 and r.json()["error"]["code"] == "LECTURE_NOT_FOUND"


@pytest.mark.parametrize("bad", ["..", "%2e%2e", "..%2Fetc", "yt_..%2F..%2Fetc", "yt_a.b", "other_abc",
                                 "yt_", "yt_" + "a" * 65, "%2Fetc%2Fpasswd", "yt_ok%00x"])
@pytest.mark.parametrize("suffix", ["", "/video", "/thumbnail"])
def test_invalid_lecture_ids_are_rejected(client, lecture, bad, suffix):
    r = client.get(f"/api/lectures/{bad}{suffix}")
    assert r.status_code in (404, 400)
    assert VIDEO_BYTES[:50] not in r.content


def test_traversal_to_another_lectures_dir_file_is_rejected(client, settings, lecture):
    (settings.lectures_dir.parent / "secret.txt").write_text("secret")
    r = client.get("/api/lectures/..%2Fsecret.txt")
    assert r.status_code == 404 and "secret" not in r.text


def test_thumbnail(client, lecture):
    r = client.get(f"/api/lectures/{LID}/thumbnail")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.content == b"\xff\xd8jpeg"


def test_video_full_response_advertises_ranges(client, lecture):
    r = client.get(f"/api/lectures/{LID}/video")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes" and r.headers["content-type"] == "video/mp4"
    assert r.content == VIDEO_BYTES


@pytest.mark.parametrize("header,start,end", [
    ("bytes=0-99", 0, 99),
    ("bytes=1000-1999", 1000, 1999),
    ("bytes=10000-", 10000, len(VIDEO_BYTES) - 1),   # open-ended
    ("bytes=-100", len(VIDEO_BYTES) - 100, len(VIDEO_BYTES) - 1),  # suffix
    ("bytes=10200-99999", 10200, len(VIDEO_BYTES) - 1),  # end clamped to file size
])
def test_video_range_returns_206_with_exact_bytes(client, lecture, header, start, end):
    r = client.get(f"/api/lectures/{LID}/video", headers={"Range": header})
    assert r.status_code == 206
    assert r.content == VIDEO_BYTES[start:end + 1]
    assert r.headers["content-range"] == f"bytes {start}-{end}/{len(VIDEO_BYTES)}"
    assert r.headers["content-length"] == str(end - start + 1)
    assert r.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize("header", ["bytes=99999-", "bytes=10240-10250"])
def test_video_unsatisfiable_or_inverted_range_is_416(client, lecture, header):
    r = client.get(f"/api/lectures/{LID}/video", headers={"Range": header})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(VIDEO_BYTES)}"


@pytest.mark.parametrize("header", ["bytes=abc", "bytes=5-2"])
def test_video_malformed_or_inverted_range_is_400(client, lecture, header):
    # Starlette 1.7 answers 400 (not 416) for syntactically invalid ranges; browsers never send these.
    r = client.get(f"/api/lectures/{LID}/video", headers={"Range": header})
    assert r.status_code == 400


def test_video_head_request(client, lecture):
    r = client.head(f"/api/lectures/{LID}/video")
    assert r.status_code == 200 and r.headers["content-length"] == str(len(VIDEO_BYTES)) and r.content == b""
