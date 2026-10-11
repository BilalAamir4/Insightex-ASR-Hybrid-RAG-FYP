"""POST /api/lectures/{id}/search with a fake question encoder (no BGE-M3 is loaded)."""

from __future__ import annotations

import numpy as np
import pytest

from insightex.api.routers import search as search_router
from insightex.index.stage import config_id, index_fingerprint
from insightex.index.store import write_index
from insightex.windows.build import build_windows

SEGS = [{"id": i + 1, "start": i * 10.0, "end": i * 10.0 + 9.5, "text": f"segment {i}"} for i in range(9)]


class FakeQueryEncoder:
    instances = 0

    def __init__(self, settings):
        FakeQueryEncoder.instances += 1
        self.calls: list[list[str]] = []

    def encode(self, questions):
        self.calls.append(questions)
        v = np.zeros((len(questions), 4), dtype=np.float32)
        v[:, 1] = 1.0  # always closest to window 1
        return v


@pytest.fixture
def searchable(make_lecture, workspaces, app_settings, monkeypatch):
    FakeQueryEncoder.instances = 0
    monkeypatch.setattr(search_router, "make_query_encoder", FakeQueryEncoder)
    lecture = make_lecture()
    wid = lecture if isinstance(lecture, str) else "yt-readyvideo1"
    windows = build_windows(SEGS, window_s=30, stride_s=15, duration_s=90)  # overlapping windows: dedupe matters
    key = "c" * 16
    directory = workspaces.stage_dir(wid, "index", key)
    directory.mkdir(parents=True)
    vectors = np.stack([np.eye(4, dtype=np.float32)[i % 4] for i in range(len(windows))])
    fp = index_fingerprint(app_settings)
    write_index(directory, windows, vectors, {"stage_version": "1", "fingerprint": fp, "config_id": config_id(fp),
                                              "model": {"repo": app_settings.index.model_repo,
                                                        "revision": app_settings.index.model_revision}})
    workspaces.record_stage(wid, "index", key, 1.0, ["windows.json", "dense.faiss", "index.json"])
    return wid, len(windows)


def test_search_returns_ranked_windows_without_text(client, searchable):
    wid, _ = searchable
    r = client.post(f"/api/lectures/{wid}/search", json={"question": "what is batch learning?", "k": 3, "dedupe": False})
    assert r.status_code == 200
    body = r.json()
    assert body["lecture_id"] == wid and len(body["index_config_id"]) == 12
    assert [h["rank"] for h in body["hits"]] == [1, 2, 3] and body["hits"][0]["window_id"] % 4 == 1
    assert set(body["hits"][0]) == {"rank", "window_id", "start", "end", "score"}  # no text (ADR-0041)
    assert "segment" not in r.text


def test_dedupe_drops_overlapping_windows_and_the_encoder_is_created_once(client, searchable):
    wid, _ = searchable
    raw = client.post(f"/api/lectures/{wid}/search", json={"question": "q", "k": 10, "dedupe": False}).json()["hits"]
    kept = client.post(f"/api/lectures/{wid}/search", json={"question": "q", "k": 10}).json()["hits"]
    assert len(kept) < len(raw)
    for i, a in enumerate(kept):
        assert all(min(a["end"], b["end"]) - max(a["start"], b["start"]) <= 0 for b in kept[:i])
    assert FakeQueryEncoder.instances == 1


def test_errors(client, searchable, make_lecture):
    wid, _ = searchable
    assert client.post("/api/lectures/yt-nothere/search", json={"question": "q"}).status_code == 404
    assert client.post("/api/lectures/.hidden/search", json={"question": "q"}).status_code == 404
    make_lecture(workspace_id="yt-noindexvid1")
    r = client.post("/api/lectures/yt-noindexvid1/search", json={"question": "q"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LECTURE_NOT_SEARCHABLE"
    assert client.post(f"/api/lectures/{wid}/search", json={"question": ""}).status_code == 422
    assert client.post(f"/api/lectures/{wid}/search", json={"question": "q", "k": 1000}).status_code == 422
