"""rebind_workspace: a job that starts in `pending-<job id>` moves to its content-addressed workspace."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from insightex.core.config import get_settings
from insightex.jobs import cache, db, store
from insightex.jobs import runner as runner_mod
from insightex.jobs import stages as stages_mod
from insightex.jobs.runner import run_job
from insightex.jobs.stages import KeyContext, Stage, StageContext, register_pipeline
from insightex.jobs.workspace import Workspaces

FINAL = "sha256-0123456789abcdef0123456789abcdef"


class SimulatedKill(BaseException):
    """Not an Exception: the runner's failure handling must not see it, like a SIGKILL."""


class First(Stage):
    name = "first"
    version = "1"
    outputs = ("first.txt",)
    runs: list[str] = []

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {}

    def run(self, ctx: StageContext) -> None:
        First.runs.append(ctx.workspace_id)
        (ctx.staging_dir / "first.txt").write_text(ctx.payload["id"])
        ctx.progress(1.0)
        ctx.rebind_workspace(ctx.payload["id"])

    def workspace_id_after(self, stage_dir: Path) -> str | None:
        return (stage_dir / "first.txt").read_text()


class Second(Stage):
    name = "second"
    version = "1"
    outputs = ("second.txt",)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {}

    def run(self, ctx: StageContext) -> None:
        assert (ctx.upstream["first"] / "first.txt").is_file()
        assert "pending-" not in str(ctx.upstream["first"])  # upstream paths follow the rebind
        (ctx.staging_dir / "second.txt").write_text("2")


@pytest.fixture
def env():
    settings = get_settings()
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    First.runs = []
    register_pipeline("rebind_test", [First(), Second()], replace=True,
                      source_for=lambda p: ("url", "https://x.example/a.mp4"), chain_root=lambda p, ws: "fixed-root")
    yield settings, conn, Workspaces(settings.jobs.workspaces_dir)
    stages_mod._PIPELINES.pop("rebind_test", None)
    stages_mod._SOURCES.pop("rebind_test", None)
    stages_mod._CHAIN_ROOTS.pop("rebind_test", None)


def submit(conn, job_id=None, final=FINAL):
    job_id = job_id or os.urandom(8).hex()
    store.enqueue(conn, "rebind_test", {"id": final}, f"pending-{job_id}", job_id=job_id)
    return job_id


def run_next(settings, conn, workspaces):
    job = store.claim_next(conn, os.getpid())
    run_job(conn, job, settings, workspaces)
    return store.get_job(conn, job.id)


def statuses(job):
    return [s.status for s in job.stages]


def test_provisional_workspace_is_renamed_to_the_final_id(env):
    settings, conn, ws = env
    job_id = submit(conn, "aaaa")
    job = run_next(settings, conn, ws)
    assert job.status == "succeeded" and job.workspace_id == FINAL and statuses(job) == ["succeeded", "succeeded"]
    assert not ws.path("pending-aaaa").exists()
    assert (ws.stage_output_dir(FINAL, "second") / "second.txt").is_file()
    assert (ws.stage_output_dir(FINAL, "first") / "first.txt").is_file()
    assert ws.read_manifest(FINAL)["workspace_id"] == FINAL
    ids = [r["id"] for r in conn.execute("SELECT id FROM workspaces")]
    assert ids == [FINAL]
    assert job_id == job.id


def test_provisional_job_merges_into_an_existing_complete_workspace(env):
    settings, conn, ws = env
    submit(conn, "aaaa")
    first = run_next(settings, conn, ws)
    cache.pin(conn, FINAL)
    submit(conn, "bbbb")
    second = run_next(settings, conn, ws)
    assert second.status == "succeeded" and second.workspace_id == FINAL
    assert statuses(second) == ["succeeded", "cached"]  # fetch ran in the provisional dir; the rest was already done
    assert not ws.path("pending-bbbb").exists()
    assert [r["id"] for r in conn.execute("SELECT id FROM workspaces")] == [FINAL]
    assert conn.execute("SELECT pinned FROM workspaces WHERE id = ?", (FINAL,)).fetchone()["pinned"] == 1
    assert [s.stage_key for s in first.stages] == [s.stage_key for s in second.stages]  # keys do not depend on the id


def test_keys_do_not_depend_on_the_provisional_id(env):
    settings, conn, ws = env
    submit(conn, "aaaa")
    a = run_next(settings, conn, ws)
    submit(conn, "bbbb", final="sha256-fedcba9876543210fedcba9876543210")
    b = run_next(settings, conn, ws)
    assert [s.stage_key for s in a.stages] == [s.stage_key for s in b.stages]


def test_kill_after_fetch_publishes_and_before_the_rebind_then_resume(env, monkeypatch):
    settings, conn, ws = env
    job_id = submit(conn, "aaaa")
    with monkeypatch.context() as m:
        m.setattr(runner_mod, "rebind", lambda *a, **k: (_ for _ in ()).throw(SimulatedKill()))
        job = store.claim_next(conn, os.getpid())
        with pytest.raises(SimulatedKill):
            run_job(conn, job, settings, ws)
    # State left by the dead worker: still running, fetch published in the provisional workspace.
    assert store.get_job(conn, job_id).status == "running"
    assert ws.stage_output_dir("pending-aaaa", "first") is not None
    assert not ws.path(FINAL).exists()
    # Worker restart: startup recovery requeues the job; the stage is cached, the rebind is replayed.
    store.recover_after_crash(conn, settings.jobs.max_attempts)
    resumed = run_next(settings, conn, ws)
    assert resumed.status == "succeeded" and resumed.workspace_id == FINAL
    assert statuses(resumed) == ["cached", "succeeded"]
    assert First.runs == ["pending-aaaa"]  # the first stage ran once, not again
    assert not ws.path("pending-aaaa").exists()
    assert [r["id"] for r in conn.execute("SELECT id FROM workspaces")] == [FINAL]


def test_crash_between_the_directory_rename_and_the_database_update_is_consistent(env, monkeypatch):
    settings, conn, ws = env
    job_id = submit(conn, "aaaa")
    with monkeypatch.context() as m:
        m.setattr(store, "set_workspace", lambda *a, **k: (_ for _ in ()).throw(SimulatedKill()))
        job = store.claim_next(conn, os.getpid())
        with pytest.raises(SimulatedKill):
            run_job(conn, job, settings, ws)
    # Either-or, never a mix: the directory is at the final id, the job and its row still say provisional.
    assert ws.path(FINAL).is_dir() and not ws.path("pending-aaaa").exists()
    assert store.get_job(conn, job_id).workspace_id == "pending-aaaa"
    store.recover_after_crash(conn, settings.jobs.max_attempts)
    resumed = run_next(settings, conn, ws)  # re-fetches once, then merges into the surviving final workspace
    assert resumed.status == "succeeded" and resumed.workspace_id == FINAL
    assert statuses(resumed) == ["succeeded", "succeeded"] and First.runs == ["pending-aaaa", "pending-aaaa"]
    assert (ws.stage_output_dir(FINAL, "second") / "second.txt").is_file()
    assert not ws.path("pending-aaaa").exists()
    assert [r["id"] for r in conn.execute("SELECT id FROM workspaces")] == [FINAL]


def test_crash_during_merge_leaves_an_orphan_that_the_startup_sweep_removes(env, monkeypatch):
    settings, conn, ws = env
    submit(conn, "aaaa")
    run_next(settings, conn, ws)
    job_id = submit(conn, "bbbb")
    with monkeypatch.context() as m:
        boom = SimpleNamespace(rmtree=lambda *a, **k: (_ for _ in ()).throw(SimulatedKill()))
        m.setattr("insightex.jobs.rebind.shutil", boom)  # only rebind's own deletes; the runner keeps the real one
        job = store.claim_next(conn, os.getpid())
        with pytest.raises(SimulatedKill):
            run_job(conn, job, settings, ws)
    assert store.get_job(conn, job_id).workspace_id == FINAL  # the transaction committed before the crash
    assert ws.path("pending-bbbb").is_dir()  # the orphan
    store.recover_after_crash(conn, settings.jobs.max_attempts)
    assert cache.sweep_orphan_pending(conn, ws) == ["pending-bbbb"]
    assert not ws.path("pending-bbbb").exists()


def test_sweep_keeps_provisional_workspaces_that_a_job_still_references(env):
    settings, conn, ws = env
    submit(conn, "cccc")  # queued job, directory not created yet
    ws.path("pending-cccc").mkdir(parents=True)
    ws.path("pending-orphan").mkdir()
    cache.register(conn, "pending-orphan", "url", "https://x.example/o.mp4")
    assert cache.sweep_orphan_pending(conn, ws) == ["pending-orphan"]
    assert ws.path("pending-cccc").is_dir()
    assert conn.execute("SELECT 1 FROM workspaces WHERE id = 'pending-orphan'").fetchone() is None


def test_worker_startup_runs_the_sweep(env):
    from insightex.jobs.worker import Worker

    settings, conn, ws = env
    ws.path("pending-orphan").mkdir(parents=True)
    worker = Worker(settings)
    worker.startup()
    assert not ws.path("pending-orphan").exists()
