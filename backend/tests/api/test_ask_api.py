"""POST /api/lectures/{id}/ask and /warm-up with a fake question encoder and a fake rewrite (no BGE-M3, no Ollama)."""

from __future__ import annotations

import json
import logging
import threading

import numpy as np
import pytest

from insightex.api.routers import ask as ask_router
from insightex.api.routers import search as search_router
from insightex.index.stage import config_id, index_fingerprint
from insightex.index.store import write_index
from insightex.retrieval.rewrite import FallbackReason, RewriteOutcome
from insightex.windows.build import SCHEMA_VERSION, build_windows

SEGS = [{"id": i + 1, "start": i * 10.0 + 2.0, "end": i * 10.0 + 9.5, "text": f"segment {i}"} for i in range(12)]
SECRET_Q = "zzz secret question about batch learning zzz"
SECRET_RW = "yyy secret rewrite yyy"


class FakeEncoder:
    def __init__(self, settings):
        pass

    def encode(self, questions):
        v = np.zeros((len(questions), 4), dtype=np.float32)
        v[:, 1] = 1.0
        return v


@pytest.fixture
def lecture(make_lecture, workspaces, app_settings, monkeypatch):
    monkeypatch.setattr(search_router, "make_query_encoder", FakeEncoder)
    wid = make_lecture()
    wid = wid if isinstance(wid, str) else "yt-readyvideo1"
    windows = build_windows(SEGS, window_s=30, stride_s=30, duration_s=120)
    key = "d" * 16
    directory = workspaces.stage_dir(wid, "index", key)
    directory.mkdir(parents=True)
    vectors = np.stack([np.eye(4, dtype=np.float32)[i % 4] for i in range(len(windows))])
    fp = index_fingerprint(app_settings)
    write_index(directory, windows, vectors, {"stage_version": "1", "fingerprint": fp, "config_id": config_id(fp),
                                              "model": {"repo": app_settings.index.model_repo, "revision": app_settings.index.model_revision}})
    workspaces.record_stage(wid, "index", key, 1.0, ["windows.json", "dense.faiss", "index.json"])
    return wid


@pytest.fixture
def fake_rewrite(monkeypatch):
    calls = []

    def rewrite_question(settings, system, question, **kw):
        calls.append(question)
        return RewriteOutcome(SECRET_RW, None, 412.3)

    monkeypatch.setattr(ask_router.rw, "rewrite_question", rewrite_question)
    monkeypatch.setattr(ask_router.rw, "load_prompt", lambda settings: "system prompt")
    return calls


def test_ask_returns_citations_without_text_scores_or_ids(client, lecture, fake_rewrite):
    r = client.post(f"/api/lectures/{lecture}/ask", json={"question": SECRET_Q})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"lecture_id", "index_config_id", "citations", "rewrite"}
    assert body["rewrite"] == {"used": True, "fallback_reason": None}
    cites = body["citations"]
    assert 1 <= len(cites) <= 3 and [c["rank"] for c in cites] == list(range(1, len(cites) + 1))
    assert set(cites[0]) == {"rank", "start", "end", "seek_s"}
    assert all(c["start"] <= c["seek_s"] < c["end"] for c in cites) and cites[0]["seek_s"] == cites[0]["start"] + 2.0
    assert "segment" not in r.text and fake_rewrite == [SECRET_Q]


def test_the_fallback_reason_is_reported(client, lecture, monkeypatch):
    monkeypatch.setattr(ask_router.rw, "load_prompt", lambda settings: "p")
    monkeypatch.setattr(ask_router.rw, "rewrite_question",
                        lambda settings, system, q, **kw: RewriteOutcome(None, FallbackReason.LLM_NOT_LOADED, None))
    body = client.post(f"/api/lectures/{lecture}/ask", json={"question": "q"}).json()
    assert body["rewrite"] == {"used": False, "fallback_reason": "llm_not_loaded"} and body["citations"]


def test_validation(client, lecture, fake_rewrite):
    url = f"/api/lectures/{lecture}/ask"
    for text in ("", "   \n"):
        r = client.post(url, json={"question": text})
        assert r.status_code == 400 and r.json()["error"]["code"] == "QUESTION_EMPTY"
    assert client.post(url, json={"question": "q" * 300}).status_code == 200  # exactly the limit
    long = "ل" * 301
    r = client.post(url, json={"question": long})
    assert r.status_code == 400 and r.json()["error"]["code"] == "QUESTION_TOO_LONG" and long not in r.text
    assert client.post(url, json={"question": 5}).status_code == 422
    assert client.post(url, json={}).status_code == 422


def test_unknown_and_unsearchable_lectures(client, lecture, make_lecture, fake_rewrite):
    assert client.post("/api/lectures/yt-nothere/ask", json={"question": "q"}).status_code == 404
    assert client.post("/api/lectures/.hidden/ask", json={"question": "q"}).status_code == 404
    make_lecture(workspace_id="yt-noindexvid1")
    r = client.post("/api/lectures/yt-noindexvid1/ask", json={"question": "q"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LECTURE_NOT_SEARCHABLE"
    assert client.post("/api/lectures/yt-noindexvid1/warm-up").status_code == 409


def test_one_json_line_per_question_and_no_question_or_rewrite_text_anywhere(client, lecture, fake_rewrite, caplog):
    caplog.set_level(logging.DEBUG)
    r = client.post(f"/api/lectures/{lecture}/ask", json={"question": SECRET_Q})
    assert r.status_code == 200
    lines = [json.loads(rec.getMessage()) for rec in caplog.records if rec.name == "insightex.ask"]
    assert len(lines) == 1
    line = lines[0]
    assert set(line) == {"event", "total_ms", "rewrite_ms", "search_ms", "rewrite_used", "fallback_reason", "citations"}
    assert line["event"] == "ask" and line["rewrite_used"] is True and line["rewrite_ms"] == 412.3 and line["citations"] == len(r.json()["citations"])
    assert "zzz" not in caplog.text and "yyy" not in caplog.text
    client.post(f"/api/lectures/{lecture}/ask", json={"question": "x" * 400})  # refused: still nothing logged
    assert "xxxx" not in caplog.text


def test_warm_up_runs_once_in_the_background(client, lecture, monkeypatch):
    started, release, calls = threading.Event(), threading.Event(), []

    def slow_warm_up(settings, **kw):
        calls.append(1)
        started.set()
        release.wait(5)
        return "loaded", None

    monkeypatch.setattr(ask_router.rw, "warm_up", slow_warm_up)
    first = client.post(f"/api/lectures/{lecture}/warm-up")
    assert first.status_code == 202 and first.json() == {"state": "started", "reason": None}
    assert started.wait(5)
    assert client.post(f"/api/lectures/{lecture}/warm-up").json() == {"state": "skipped", "reason": "already_warming"}
    release.set()
    for _ in range(50):
        if client.post(f"/api/lectures/{lecture}/warm-up").json()["state"] == "started":
            break
        threading.Event().wait(0.05)
    assert len(calls) >= 2  # once the first finished, a new one was accepted


def test_the_lecture_document_says_whether_a_question_can_be_asked(client, lecture, make_lecture):
    make_lecture(workspace_id="yt-noindexvid1")
    docs = {i["lecture_id"]: i for i in client.get("/api/lectures").json()["lectures"]}
    assert docs[lecture]["searchable"] is True and docs["yt-noindexvid1"]["searchable"] is False
    assert client.get(f"/api/lectures/{lecture}").json()["searchable"] is True
    assert SCHEMA_VERSION == 2
