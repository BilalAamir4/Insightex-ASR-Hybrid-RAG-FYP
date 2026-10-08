"""Cache index: register/touch, eviction order, delete, stale-key sweep, post-job maintenance."""

from __future__ import annotations

import logging

import pytest

from insightex.core.config import load_settings
from insightex.jobs import cache, db, store
from insightex.jobs.runner import run_job
from insightex.jobs.workspace import Workspaces


@pytest.fixture
def env(tmp_path):
    settings = load_settings({"jobs": {"progress_min_interval_s": 0.0}})
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    yield settings, conn, Workspaces(settings.jobs.workspaces_dir)
    conn.close()


def make_ws(conn, ws, wid, size, accessed, pinned=False):
    cache.register(conn, wid, "dummy", wid)
    (ws.path(wid)).mkdir(parents=True, exist_ok=True)
    (ws.path(wid) / "blob").write_bytes(b"x" * size)
    conn.execute(
        "UPDATE workspaces SET last_accessed_at=?, size_bytes=?, pinned=? WHERE id=?",
        (accessed, size, int(pinned), wid),
    )


def test_register_never_overwrites_created_at(env):
    _, conn, _ = env
    cache.register(conn, "w1", "youtube", "https://y")
    first = conn.execute("SELECT * FROM workspaces WHERE id='w1'").fetchone()
    cache.register(conn, "w1", "url", "other")
    again = conn.execute("SELECT * FROM workspaces WHERE id='w1'").fetchone()
    assert tuple(first) == tuple(again)
    cache.touch(conn, "w1")
    assert conn.execute("SELECT last_accessed_at FROM workspaces").fetchone()[0] >= first["last_accessed_at"]


def test_register_rejects_bad_kind_and_id(env):
    _, conn, _ = env
    with pytest.raises(ValueError):
        cache.register(conn, "w", "ftp", "x")
    with pytest.raises(ValueError):
        cache.register(conn, "../x", "dummy", "x")


def test_refresh_size_walks_the_directory(env):
    _, conn, ws = env
    make_ws(conn, ws, "w", 10, "2026-01-01T00:00:00.000Z")
    (ws.path("w") / "sub").mkdir()
    (ws.path("w") / "sub" / "b").write_bytes(b"y" * 5)
    assert cache.refresh_size(conn, ws, "w") == 15
    assert conn.execute("SELECT size_bytes FROM workspaces").fetchone()[0] == 15


def test_evict_is_lru_skips_pinned_and_busy_and_stops_under_cap(env, caplog):
    _, conn, ws = env
    make_ws(conn, ws, "oldest-pinned", 100, "2026-01-01T00:00:00.000Z", pinned=True)
    make_ws(conn, ws, "old-busy", 100, "2026-01-02T00:00:00.000Z")
    make_ws(conn, ws, "old", 100, "2026-01-03T00:00:00.000Z")
    make_ws(conn, ws, "mid", 100, "2026-01-04T00:00:00.000Z")
    make_ws(conn, ws, "new", 100, "2026-01-05T00:00:00.000Z")
    store.enqueue(conn, "dummy", {}, "old-busy")
    with caplog.at_level(logging.INFO, logger="insightex.jobs.cache"):
        removed = cache.evict(conn, ws, 300)  # total 500 -> must drop 200
    assert removed == ["old", "mid"]
    assert ws.path("oldest-pinned").exists() and ws.path("old-busy").exists() and ws.path("new").exists()
    assert not ws.path("old").exists() and not ws.path("mid").exists()
    assert "evicted workspace old (100 bytes, last accessed 2026-01-03" in caplog.text


def test_evict_noop_under_cap_and_never_touches_unindexed(env):
    _, conn, ws = env
    make_ws(conn, ws, "a", 100, "2026-01-01T00:00:00.000Z")
    (ws.root / "stray").mkdir()
    (ws.root / "stray" / "f").write_bytes(b"z" * 1000)
    assert cache.evict(conn, ws, 100) == []
    assert (ws.root / "stray").exists()


def test_evict_excludes_just_finished_and_warns_when_alone_over_cap(env, caplog):
    _, conn, ws = env
    make_ws(conn, ws, "big", 500, "2026-01-01T00:00:00.000Z")
    with caplog.at_level(logging.WARNING, logger="insightex.jobs.cache"):
        assert cache.evict(conn, ws, 100, exclude="big") == []
    assert ws.path("big").exists() and "alone" in caplog.text


def test_delete_refuses_busy_then_removes_and_keeps_job_rows(env):
    _, conn, ws = env
    make_ws(conn, ws, "w", 10, "2026-01-01T00:00:00.000Z")
    job_id = store.enqueue(conn, "dummy", {}, "w")
    with pytest.raises(cache.WorkspaceBusy):
        cache.delete(conn, ws, "w")
    assert ws.path("w").exists()
    store.finish(conn, job_id, "failed", "x")
    cache.delete(conn, ws, "w")
    assert not ws.path("w").exists()
    assert conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 0
    assert store.get_job(conn, job_id).status == "failed"


def test_delete_works_on_unindexed_dir_and_unknown_id_raises(env):
    _, conn, ws = env
    (ws.root / "stray").mkdir(parents=True)
    cache.delete(conn, ws, "stray")
    assert not (ws.root / "stray").exists()
    with pytest.raises(cache.WorkspaceNotFound):
        cache.delete(conn, ws, "nope")


def test_list_marks_unindexed_and_pinned(env):
    _, conn, ws = env
    make_ws(conn, ws, "a", 1, "2026-01-01T00:00:00.000Z")
    cache.pin(conn, "a")
    (ws.root / "stray").mkdir()
    rows = {r["id"]: r for r in cache.list_workspaces(conn, ws)}
    assert rows["a"]["indexed"] and rows["a"]["pinned"] and not rows["stray"]["indexed"]
    cache.unpin(conn, "a")
    with pytest.raises(cache.WorkspaceNotFound):
        cache.pin(conn, "stray")


def test_gc_stale_keys_keeps_current_and_removes_others(env):
    settings, conn, ws = env
    store.enqueue(conn, "dummy", {"cpu_seconds": 0, "gpu_seconds": 0, "step_seconds": 0.01}, "w")
    job = store.claim_next(conn, 1)
    assert run_job(conn, job, settings, ws) == "succeeded"
    manifest = ws.read_manifest("w")
    keep = manifest["stages"]["dummy_cpu"]["key"]
    stale = ws.path("w") / "stages" / "dummy_cpu" / ("0" * 16)
    stale.mkdir()
    (stale / "f").write_text("x")
    orphan_stage = ws.path("w") / "stages" / "gone_stage" / ("1" * 16)
    orphan_stage.mkdir(parents=True)
    assert cache.gc_stale_keys(ws, "w") == 2
    assert not stale.exists() and not orphan_stage.exists()
    assert ws.stage_dir("w", "dummy_cpu", keep).is_dir()


def test_runner_registers_dummy_and_runs_maintenance_in_order(env, monkeypatch):
    settings, conn, ws = env
    calls = []
    for name in ("gc_stale_keys", "refresh_size", "evict"):
        real = getattr(cache, name)
        monkeypatch.setattr(cache, name, lambda *a, _n=name, _r=real: (calls.append(_n), _r(*a))[1])
    store.enqueue(conn, "dummy", {"cpu_seconds": 0, "gpu_seconds": 0, "step_seconds": 0.01, "label": "lbl"}, "w")
    job = store.claim_next(conn, 1)
    assert run_job(conn, job, settings, ws) == "succeeded"
    assert calls == ["gc_stale_keys", "refresh_size", "evict"]
    row = conn.execute("SELECT * FROM workspaces WHERE id='w'").fetchone()
    assert (row["source_kind"], row["source_ref"]) == ("dummy", "lbl") and row["size_bytes"] > 0


def test_maintenance_failure_does_not_change_job_status(env, monkeypatch, caplog):
    settings, conn, ws = env

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    for name in ("gc_stale_keys", "refresh_size", "evict", "touch", "register"):
        monkeypatch.setattr(cache, name, boom)
    store.enqueue(conn, "dummy", {"cpu_seconds": 0, "gpu_seconds": 0, "step_seconds": 0.01}, "w")
    job = store.claim_next(conn, 1)
    with caplog.at_level(logging.WARNING):
        assert run_job(conn, job, settings, ws) == "succeeded"
    assert store.get_job(conn, job.id).status == "succeeded"
    assert "disk on fire" in caplog.text
