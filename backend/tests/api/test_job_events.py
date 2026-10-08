"""GET /api/jobs/{id}/events: the stream follows the database (the worker is another process)."""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from insightex.api.app import create_app
from insightex.core.config import load_settings
from insightex.jobs import db, store


@pytest.fixture
def fast_client():
    settings = load_settings({"api": {"sse_poll_interval_s": 0.03, "sse_keepalive_s": 0.25}})
    with TestClient(create_app(settings)) as c:
        yield c, settings


def _driver(settings, job_id, steps):
    """Change the job row from another thread/connection, like the worker process would."""

    def run():
        conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
        for delay, action in steps:
            time.sleep(delay)
            action(conn)
        conn.close()

    t = threading.Thread(target=run)
    t.start()
    return t


def _events(response):
    """(event, data-or-None) pairs; keepalive comments come back as ('keepalive', None)."""
    out, event = [], None
    for line in response.iter_lines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            out.append((event, json.loads(line.split(":", 1)[1])))
        elif line.startswith(": keepalive"):
            out.append(("keepalive", None))
    return out


def _enqueue(conn):
    return store.enqueue(conn, "ingest_link", {"url": "https://youtu.be/dQw4w9WgXcQ"}, "yt-dQw4w9WgXcQ")


def test_events_follow_the_database_in_order_and_close_after_the_terminal_event(fast_client):
    client, settings = fast_client
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    job_id = _enqueue(conn)

    def claim(c):
        store.claim_next(c, 99)

    steps = [
        (0.15, claim),
        (0.15, lambda c: store.update_stage(c, job_id, 0, status="running", progress=0.4, message="40%")),
        (0.15, lambda c: store.update_stage(c, job_id, 0, status="succeeded", progress=1.0)),
        (0.15, lambda c: store.update_stage(c, job_id, 1, status="succeeded", progress=1.0)),
        (0.15, lambda c: store.finish(c, job_id, "succeeded")),
    ]
    t = _driver(settings, job_id, steps)
    with client.stream("GET", f"/api/jobs/{job_id}/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
        events = [e for e in _events(r) if e[0] == "status"]  # iteration ends only because the server closed it
    t.join()
    docs = [d for _, d in events]
    assert docs[0]["status"] == "queued"
    assert docs[-1]["status"] == "succeeded" and [s["status"] for s in docs[-1]["stages"]] == ["succeeded", "succeeded"]
    statuses = [d["status"] for d in docs]
    assert statuses == sorted(statuses, key=["queued", "running", "succeeded"].index)
    assert any(d["stages"][0]["progress"] == 0.4 and d["stages"][0]["message"] == "40%" for d in docs)
    assert all(a != b for a, b in zip(docs, docs[1:]))  # only changes are sent


def test_a_finished_job_gets_exactly_one_event_then_the_stream_closes(fast_client):
    client, settings = fast_client
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    job_id = _enqueue(conn)
    store.request_cancel(conn, job_id)
    with client.stream("GET", f"/api/jobs/{job_id}/events") as r:
        events = _events(r)
    assert [(e, d["status"]) for e, d in events] == [("status", "cancelled")]


def test_keepalive_comment_while_nothing_changes(fast_client):
    client, settings = fast_client
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    job_id = _enqueue(conn)
    t = _driver(settings, job_id, [(0.8, lambda c: store.request_cancel(c, job_id))])
    with client.stream("GET", f"/api/jobs/{job_id}/events") as r:
        events = _events(r)
    t.join()
    kinds = [e for e, _ in events]
    assert "keepalive" in kinds and kinds[0] == "status" and kinds[-1] == "status"


@pytest.fixture
def live_server():
    """The app under a real uvicorn server on a free loopback port (TestClient buffers streamed bodies)."""
    import socket

    import uvicorn

    settings = load_settings({"api": {"sse_poll_interval_s": 0.03, "sse_keepalive_s": 0.25}})
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    yield f"http://127.0.0.1:{port}", settings
    server.should_exit = True
    thread.join(timeout=10)


def test_job_endpoint_answers_while_a_stream_is_open(live_server):
    import httpx

    base, settings = live_server
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    job_id = _enqueue(conn)
    t = _driver(settings, job_id, [(1.5, lambda c: store.request_cancel(c, job_id))])
    with httpx.Client(base_url=base, timeout=10) as http, http.stream("GET", f"/api/jobs/{job_id}/events") as r:
        lines = r.iter_lines()
        assert next(lines).startswith("event: status")  # open, and the first event arrived before the job ended
        started = time.monotonic()
        for _ in range(5):
            other = http.get(f"/api/jobs/{job_id}")
            assert other.status_code == 200 and other.json()["status"] == "queued"
        assert time.monotonic() - started < 1.0  # never waited for the stream to end
        rest = list(lines)
    t.join()
    assert any('"status":"cancelled"' in line for line in rest)
