"""Job store, workspace, stage keys and runner. Temp dirs and a temp DB only."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import ClassVar

import pytest

from insightex.core.config import load_settings
from insightex.jobs import db, store
from insightex.jobs.runner import run_job
from insightex.jobs.stages import KeyContext, Stage, StageContext, register_pipeline, stage_key
from insightex.jobs.workspace import Workspaces, validate_workspace_id


@pytest.fixture
def env(tmp_path):
    settings = load_settings({"jobs": {"progress_min_interval_s": 0.0}})
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    yield settings, conn, Workspaces(settings.jobs.workspaces_dir)
    conn.close()


def run_next(env, **kwargs) -> tuple[store.Job, str]:
    settings, conn, ws = env
    job = store.claim_next(conn, 1234)
    assert job is not None
    return job, run_job(conn, job, settings, ws, **kwargs)


FAST = {"cpu_seconds": 0.1, "gpu_seconds": 0.1, "step_seconds": 0.05}


# -- database ---------------------------------------------------------------------------------------


def test_migrate_twice_is_a_noop_the_second_time(env):
    _, conn, _ = env
    assert db.schema_version(conn) == len(db.MIGRATIONS) == 3
    assert db.migrate(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 3


def test_migration_3_keeps_workspace_rows_and_allows_gdrive(tmp_path):
    conn = db.open_connection(tmp_path / "v2.db", 1000)
    with db.transaction(conn):
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL)")
        for n, script in enumerate(db.MIGRATIONS[:2], start=1):
            for statement in script.split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute("INSERT INTO schema_version VALUES (?, 'x')", (n,))
        conn.execute("INSERT INTO workspaces (id, source_kind, source_ref, created_at, last_accessed_at, size_bytes, pinned) "
                     "VALUES ('yt-abcdefghijk', 'youtube', 'u', 't1', 't2', 7, 1)")
    assert db.migrate(conn) == 1 and db.schema_version(conn) == 3
    row = conn.execute("SELECT * FROM workspaces").fetchone()
    assert (row["id"], row["source_kind"], row["size_bytes"], row["pinned"]) == ("yt-abcdefghijk", "youtube", 7, 1)
    conn.execute("INSERT INTO workspaces (id, source_kind, source_ref, created_at, last_accessed_at) "
                 "VALUES ('sha256-x', 'gdrive', 'u', 't', 't')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO workspaces (id, source_kind, source_ref, created_at, last_accessed_at) "
                     "VALUES ('z', 'bogus', 'u', 't', 't')")
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'idx_workspaces_accessed'").fetchone()


def test_connection_pragmas(env):
    settings, conn, _ = env
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == settings.jobs.busy_timeout_ms


def test_timestamps_are_utc_z(env):
    _, conn, _ = env
    job = store.get_job(conn, store.enqueue(conn, "dummy", {}, "ws1"))
    assert job.created_at.endswith("Z") and job.updated_at.endswith("Z")


def test_two_connections_claim_one_job_exactly_once(env):
    settings, conn, _ = env
    store.enqueue(conn, "dummy", {}, "ws1")
    barrier, results = threading.Barrier(2), []

    def claim(pid):
        c = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
        barrier.wait()
        results.append(store.claim_next(c, pid))
        c.close()

    threads = [threading.Thread(target=claim, args=(pid,)) for pid in (1, 2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r is not None for r in results) == [False, True]


def test_claim_is_oldest_first_and_counts_attempts(env):
    _, conn, _ = env
    first = store.enqueue(conn, "dummy", {}, "a")
    store.enqueue(conn, "dummy", {}, "b")
    job = store.claim_next(conn, 7)
    assert job.id == first and job.attempts == 1 and job.worker_pid == 7 and job.status == "running"


def test_enqueue_rejects_bad_workspace_ids(env):
    _, conn, _ = env
    for bad in ["", "../x", "a/b", ".hidden", "x" * 129, "a b"]:
        with pytest.raises(ValueError):
            store.enqueue(conn, "dummy", {}, bad)
        with pytest.raises(ValueError):
            validate_workspace_id(bad)
    assert validate_workspace_id("dummy-1a2b3c4d") and validate_workspace_id("a.b_c-d")


def test_recover_after_crash_requeues_below_max_and_fails_at_it(env):
    _, conn, _ = env
    a, b = store.enqueue(conn, "dummy", {}, "a"), store.enqueue(conn, "dummy", {}, "b")
    for _ in range(2):
        store.claim_next(conn, 1)  # a: attempts 1, b: attempts 1
    conn.execute("UPDATE jobs SET attempts = 3 WHERE id = ?", (b,))
    store.update_stage(conn, a, 0, status="running", progress=0.4)
    result = dict(store.recover_after_crash(conn, max_attempts=3))
    assert result == {a: "queued", b: "failed"}
    assert store.get_job(conn, a).stages[0].status == "pending"
    failed = store.get_job(conn, b)
    assert failed.error == "worker died during this job 3 times" and failed.finished_at


def test_retry_only_failed_or_cancelled(env):
    _, conn, _ = env
    job_id = store.enqueue(conn, "dummy", {}, "a")
    with pytest.raises(store.InvalidJobState):
        store.retry(conn, job_id)
    store.request_cancel(conn, job_id)
    store.retry(conn, job_id)
    assert store.get_job(conn, job_id).status == "queued"


# -- stage keys ---------------------------------------------------------------------------------------


def test_stage_key_is_stable_and_sensitive_to_every_input():
    base = stage_key("asr", "1", {"model": "m"}, "up")
    assert base == stage_key("asr", "1", {"model": "m"}, "up") and len(base) == 16
    assert len({base, stage_key("asr2", "1", {"model": "m"}, "up"), stage_key("asr", "2", {"model": "m"}, "up"),
                stage_key("asr", "1", {"model": "n"}, "up"), stage_key("asr", "1", {"model": "m"}, "other")}) == 5
    assert stage_key("a", "1", {"x": 1, "y": 2}, "u") == stage_key("a", "1", {"y": 2, "x": 1}, "u")


# -- runner -------------------------------------------------------------------------------------------


def test_full_dummy_job_succeeds_with_manifest(env):
    settings, conn, ws = env
    store.enqueue(conn, "dummy", FAST, "ws1")
    job, status = run_next(env)
    assert status == "succeeded"
    done = store.get_job(conn, job.id)
    assert done.status == "succeeded" and done.finished_at and done.worker_pid is None
    assert [s.status for s in done.stages] == ["succeeded", "succeeded"]
    assert all(s.progress == 1.0 and s.stage_key for s in done.stages)
    manifest = ws.read_manifest("ws1")
    cpu, gpu = manifest["stages"]["dummy_cpu"], manifest["stages"]["dummy_gpu"]
    assert cpu["key"] == done.stages[0].stage_key and gpu["key"] == done.stages[1].stage_key
    assert cpu["outputs"] == [f"stages/dummy_cpu/{cpu['key']}/cpu.txt"] and cpu["duration_s"] >= 0.1
    root = settings.jobs.workspaces_dir / "ws1"
    assert (root / cpu["outputs"][0]).is_file() and (root / gpu["outputs"][0]).is_file()
    assert "cpu_seconds" in (root / gpu["outputs"][0]).read_text()
    assert ws.stage_output_dir("ws1", "dummy_gpu") == root / "stages" / "dummy_gpu" / gpu["key"]
    assert not list((root / ".staging").iterdir())
    assert json.loads((root / "manifest.json").read_text())["workspace_id"] == "ws1"


def test_rerun_of_same_workspace_is_fully_cached(env):
    _, conn, _ = env
    store.enqueue(conn, "dummy", FAST, "ws1")
    run_next(env)
    again = store.enqueue(conn, "dummy", FAST, "ws1")
    _, status = run_next(env)
    assert status == "succeeded"
    assert [s.status for s in store.get_job(conn, again).stages] == ["cached", "cached"]


def test_changing_label_changes_both_keys_reruns_both_and_removes_old_key_dirs(env):
    settings, conn, _ws = env
    first = store.enqueue(conn, "dummy", {**FAST, "label": "a"}, "ws1")
    run_next(env)
    old = {s.name: s.stage_key for s in store.get_job(conn, first).stages}
    second = store.enqueue(conn, "dummy", {**FAST, "label": "b"}, "ws1")
    run_next(env)
    new_stages = store.get_job(conn, second).stages
    assert [s.status for s in new_stages] == ["succeeded", "succeeded"]
    for s in new_stages:
        assert s.stage_key != old[s.name]
        root = settings.jobs.workspaces_dir / "ws1" / "stages" / s.name
        assert [p.name for p in root.iterdir()] == [s.stage_key]  # old key dir is gone, new one exists


def test_changing_only_downstream_config_keeps_upstream_cached(env):
    _, conn, _ = env
    register_pipeline("two_part", [_Writer("part_a", "1"), _Writer("part_b", "1", fingerprint_key="b_cfg")])
    store.enqueue(conn, "two_part", {"b_cfg": 1}, "ws1")
    run_next(env)
    second = store.enqueue(conn, "two_part", {"b_cfg": 2}, "ws1")
    run_next(env)
    assert [s.status for s in store.get_job(conn, second).stages] == ["cached", "succeeded"]


class _Writer(Stage):
    outputs = ("out.txt",)

    def __init__(self, name, version, fingerprint_key=None, write=True, fail_when=None):
        self.name, self.version = name, version
        self.fingerprint_key, self.write, self.fail_when = fingerprint_key, write, fail_when

    def config_fingerprint(self, ctx: KeyContext):
        return {self.fingerprint_key: ctx.payload.get(self.fingerprint_key)} if self.fingerprint_key else {}

    def run(self, ctx: StageContext) -> None:
        ctx.progress(0.5)
        if self.fail_when and self.fail_when():
            raise RuntimeError("forced failure")
        if self.write:
            (ctx.staging_dir / "out.txt").write_text("x")


def test_retry_after_failure_in_stage_two_shows_stage_one_cached(env):
    _, conn, ws = env
    state = {"fail": True}
    register_pipeline("flaky", [_Writer("first", "1"), _Writer("second", "1", fail_when=lambda: state["fail"])])
    job_id = store.enqueue(conn, "flaky", {}, "ws1")
    _, status = run_next(env)
    failed = store.get_job(conn, job_id)
    assert status == "failed" and failed.status == "failed"
    assert [s.status for s in failed.stages] == ["succeeded", "failed"]
    assert "RuntimeError: forced failure" in failed.stages[1].error and "Traceback" in failed.stages[1].error
    assert "second failed" in failed.error
    assert ws.stage_output_dir("ws1", "second") is None
    state["fail"] = False
    store.retry(conn, job_id)
    _, status = run_next(env)
    retried = store.get_job(conn, job_id)
    assert status == "succeeded" and [s.status for s in retried.stages] == ["cached", "succeeded"]
    assert retried.attempts == 1


class _Consumer(_Writer):
    """Deletes the first stage's output once published, as normalise deletes an uploaded original."""

    def after_stage(self, ctx, upstream):
        (upstream["first"] / "out.txt").unlink(missing_ok=True)


def test_stage_whose_output_a_later_hook_consumed_counts_as_cached_when_the_next_stage_is_done(env):
    _, conn, ws = env
    state = {"fail": True}
    register_pipeline("consumed_by_next", [_Writer("first", "1"), _Consumer("second", "1"),
                                   _Writer("third", "1", fail_when=lambda: state["fail"])], replace=True)
    job_id = store.enqueue(conn, "consumed_by_next", {}, "ws1")
    run_next(env)
    assert not (ws.stage_output_dir("ws1", "first") / "out.txt").exists()  # consumed
    state["fail"] = False
    store.retry(conn, job_id)
    _, status = run_next(env)
    assert status == "succeeded"
    assert [s.status for s in store.get_job(conn, job_id).stages] == ["cached", "cached", "succeeded"]


def test_consumed_stage_reruns_when_the_next_stage_must_rerun(env):
    _, conn, _ = env
    register_pipeline("consumed_rerun", [_Writer("first", "1"), _Consumer("second", "1", fingerprint_key="v")], replace=True)
    store.enqueue(conn, "consumed_rerun", {"v": 1}, "ws1")
    run_next(env)
    store.enqueue(conn, "consumed_rerun", {"v": 2}, "ws1")  # second's key changes: first must produce its output again
    job, status = run_next(env)
    assert status == "succeeded"
    assert [s.status for s in store.get_job(conn, job.id).stages] == ["succeeded", "succeeded"]


class _CountingSource(_Writer):
    """First stage that reads an input file named in the payload (like fetch reading the staged upload)."""

    runs: ClassVar[list[str]] = []

    def run(self, ctx: StageContext) -> None:
        source = ctx.payload["input"]
        _CountingSource.runs.append(ctx.job_id)
        with open(source, encoding="utf-8") as f:  # FileNotFoundError when the input is gone
            (ctx.staging_dir / "out.txt").write_text(f.read())


def _consumed_pipeline(kind, third_fingerprint=None):
    register_pipeline(kind, [_CountingSource("first", "1"), _Consumer("second", "1", fingerprint_key=third_fingerprint),
                             _Writer("third", "1", fingerprint_key=third_fingerprint)], replace=True)


def test_consumed_stage_is_not_run_again_when_the_next_stage_is_complete(env, tmp_path):
    """(a) The earlier stage is recorded at its key, a later hook deleted its output, and the next stage is complete
    at the matching chained key: it counts as cached and its run (which needs the now-missing input) is skipped."""
    _, conn, ws = env
    source = tmp_path / "input.txt"
    source.write_text("data")
    _CountingSource.runs.clear()
    _consumed_pipeline("consumed_cached")
    store.enqueue(conn, "consumed_cached", {"input": str(source)}, "ws1")
    run_next(env)
    assert len(_CountingSource.runs) == 1 and not (ws.stage_output_dir("ws1", "first") / "out.txt").exists()
    source.unlink()  # the input is gone for good, as after an upload's staged copy is removed
    job_id = store.enqueue(conn, "consumed_cached", {"input": str(source)}, "ws1")
    _, status = run_next(env)
    job = store.get_job(conn, job_id)
    assert status == "succeeded" and [s.status for s in job.stages] == ["cached", "cached", "cached"]
    assert len(_CountingSource.runs) == 1  # not run again


def test_consumed_stage_reruns_when_the_next_stage_key_no_longer_matches(env, tmp_path):
    """(b) The next stage's chained key differs from the one in the manifest, so the next stage is not complete:
    the earlier stage is not counted as cached and runs again (its input still exists)."""
    _, conn, _ = env
    source = tmp_path / "input.txt"
    source.write_text("data")
    _CountingSource.runs.clear()
    _consumed_pipeline("consumed_stale_next")
    store.enqueue(conn, "consumed_stale_next", {"input": str(source)}, "ws1")
    run_next(env)
    # Same first stage; `second` and `third` now depend on payload["v"], so their keys change.
    _consumed_pipeline("consumed_stale_next", third_fingerprint="v")
    job_id = store.enqueue(conn, "consumed_stale_next", {"input": str(source), "v": 2}, "ws1")
    _, status = run_next(env)
    assert status == "succeeded"
    assert [s.status for s in store.get_job(conn, job_id).stages] == ["succeeded", "succeeded", "succeeded"]
    assert len(_CountingSource.runs) == 2


def test_consumed_stage_fails_with_the_stage_error_when_the_next_stage_is_incomplete_and_the_input_is_gone(env, tmp_path):
    """(b) The next stage's output is missing and the input is gone: the earlier stage is not treated as cached, so the
    job fails at it with its own clear error, exactly as before the change."""
    _, conn, ws = env
    source = tmp_path / "input.txt"
    source.write_text("data")
    _CountingSource.runs.clear()
    _consumed_pipeline("consumed_gone")
    store.enqueue(conn, "consumed_gone", {"input": str(source)}, "ws1")
    run_next(env)
    source.unlink()
    for path in ws.stage_output_dir("ws1", "second").iterdir():  # `second` is first's direct successor: now incomplete
        path.unlink()
    job_id = store.enqueue(conn, "consumed_gone", {"input": str(source)}, "ws1")
    _, status = run_next(env)
    job = store.get_job(conn, job_id)
    assert status == "failed" and [s.status for s in job.stages] == ["failed", "pending", "pending"]
    assert "FileNotFoundError" in job.stages[0].error and "first failed" in job.error
    assert len(_CountingSource.runs) == 2  # it was attempted again, not skipped


def test_the_last_stage_is_never_counted_as_cached_because_of_a_missing_next_stage(env):
    """There is no later stage to vouch for the last stage: lost outputs mean it reruns."""
    _, conn, ws = env
    register_pipeline("consumed_last", [_Writer("only", "1")], replace=True)
    store.enqueue(conn, "consumed_last", {}, "ws1")
    run_next(env)
    (ws.stage_output_dir("ws1", "only") / "out.txt").unlink()
    job_id = store.enqueue(conn, "consumed_last", {}, "ws1")
    _, status = run_next(env)
    assert status == "succeeded" and [s.status for s in store.get_job(conn, job_id).stages] == ["succeeded"]


def test_stage_missing_a_declared_output_fails_and_moves_nothing(env):
    settings, conn, ws = env
    register_pipeline("forgetful", [_Writer("only", "1", write=False)])
    job_id = store.enqueue(conn, "forgetful", {}, "ws1")
    _, status = run_next(env)
    job = store.get_job(conn, job_id)
    assert status == "failed" and "out.txt" in job.stages[0].error
    root = settings.jobs.workspaces_dir / "ws1"
    assert not (root / "stages").exists() or not any((root / "stages").rglob("*"))
    assert not list((root / ".staging").iterdir())
    assert ws.read_manifest("ws1")["stages"] == {}


def test_unknown_kind_and_pipeline_mismatch_fail_the_job(env):
    _settings, conn, _ws = env
    job_id = store.enqueue(conn, "dummy", FAST, "ws1")
    conn.execute("UPDATE job_stages SET name = 'renamed' WHERE job_id = ? AND idx = 1", (job_id,))
    _, status = run_next(env)
    assert status == "failed" and "do not match" in store.get_job(conn, job_id).error


def test_cancel_queued_job(env):
    _, conn, _ = env
    job_id = store.enqueue(conn, "dummy", FAST, "ws1")
    assert store.request_cancel(conn, job_id) == "cancelled"
    job = store.get_job(conn, job_id)
    assert job.status == "cancelled" and [s.status for s in job.stages] == ["cancelled", "cancelled"]
    assert store.claim_next(conn, 1) is None


class _SelfCancelling(Stage):
    name, version, outputs = "spin", "1", ("out.txt",)

    def config_fingerprint(self, ctx):
        return {}

    def run(self, ctx: StageContext) -> None:
        c = db.open_connection(ctx.settings.jobs.db_path, ctx.settings.jobs.busy_timeout_ms)
        store.request_cancel(c, ctx.job_id)
        c.close()
        for _ in range(100):
            ctx.progress(0.1)
            time.sleep(0.01)
        (ctx.staging_dir / "out.txt").write_text("never")


def test_cooperative_cancel_of_running_job(env):
    settings, conn, _ws = env
    register_pipeline("spinner", [_SelfCancelling(), _Writer("after", "1")])
    job_id = store.enqueue(conn, "spinner", {}, "ws1")
    _, status = run_next(env)
    job = store.get_job(conn, job_id)
    assert status == "cancelled" and job.status == "cancelled" and job.cancel_requested
    assert [s.status for s in job.stages] == ["cancelled", "cancelled"]
    assert not list((settings.jobs.workspaces_dir / "ws1" / ".staging").iterdir())


def test_cancel_is_noticed_between_stages(env):
    _, conn, _ = env
    job_id = store.enqueue(conn, "dummy", FAST, "ws1")
    job = store.claim_next(conn, 1)
    store.request_cancel(conn, job_id)  # running: sets the flag
    assert run_job(conn, job, env[0], env[2]) == "cancelled"
    assert [s.status for s in store.get_job(conn, job_id).stages] == ["cancelled", "cancelled"]


def test_worker_stop_requeues_job_and_restores_attempts(env):
    settings, conn, _ws = env
    job_id = store.enqueue(conn, "dummy", {**FAST, "cpu_seconds": 5}, "ws1")
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 3  # stop after the stage has started and made some progress

    _, status = run_next(env, should_stop=stop)
    job = store.get_job(conn, job_id)
    assert status == "queued" and job.status == "queued" and job.attempts == 0 and job.worker_pid is None
    assert job.stages[0].status == "pending"
    assert not list((settings.jobs.workspaces_dir / "ws1" / ".staging").iterdir())


def test_progress_is_throttled(env):
    settings, conn, _ = env
    throttled = load_settings({"jobs": {"progress_min_interval_s": 60}})
    store.enqueue(conn, "dummy", {**FAST, "cpu_seconds": 0.5, "gpu_seconds": 0.1}, "ws1")
    job = store.claim_next(conn, 1)
    writes = []
    conn.set_trace_callback(lambda sql: writes.append(sql) if "UPDATE job_stages SET progress" in sql else None)
    run_job(conn, job, throttled, Workspaces(settings.jobs.workspaces_dir))
    conn.set_trace_callback(None)
    # dummy_cpu: 10 progress calls, but only the 0 and 1 writes get through; dummy_gpu: 2 steps, same
    assert 2 <= len(writes) <= 8


def test_clean_staging_removes_abandoned_dirs(env):
    settings, _, ws = env
    leftover = settings.jobs.workspaces_dir / "ws1" / ".staging" / "dummy_cpu-0123456789abcdef-99"
    leftover.mkdir(parents=True)
    (leftover / "partial.txt").write_text("x")
    assert ws.clean_staging() == 1 and not leftover.exists()


def test_manifest_write_is_atomic_and_leaves_no_temp_files(env):
    settings, _, ws = env
    ws.write_manifest("ws1", ws.read_manifest("ws1"))
    ws.set_source("ws1", {"kind": "test"})
    names = sorted(p.name for p in (settings.jobs.workspaces_dir / "ws1").iterdir())
    assert names == ["manifest.json"] and ws.read_manifest("ws1")["source"] == {"kind": "test"}


class _Consumed(Stage):
    """Writes out.txt (a different body each run); a hook deletes it after publish, like an uploaded original."""

    name, version, outputs = "consume", "1", ("out.txt",)
    runs = 0
    seen: ClassVar[list[str]] = []

    def config_fingerprint(self, ctx: KeyContext):
        return {}

    def run(self, ctx: StageContext) -> None:
        type(self).runs += 1
        (ctx.staging_dir / "out.txt").write_text(f"run {type(self).runs}")

    def after_stage(self, ctx, upstream) -> None:
        path = upstream[self.name] / "out.txt"
        type(self).seen.append(path.read_text())  # raises (and is swallowed) if the fresh output was not published
        path.unlink()


def test_publish_replaces_a_same_key_directory_whose_output_was_deleted(env):
    """Regression (ADR-0036): the old _publish kept the existing same-key directory and threw the fresh output away,
    so the second run published a directory without out.txt and the next stage found nothing to read."""
    _, conn, ws = env
    _Consumed.runs, _Consumed.seen = 0, []
    register_pipeline("consumed", [_Consumed()])
    for expected in (1, 2):
        store.enqueue(conn, "consumed", {}, "ws1")
        _, status = run_next(env)
        assert status == "succeeded"
        directory = ws.stage_output_dir("ws1", "consume")
        assert _Consumed.runs == expected
        assert not (directory / "out.txt").exists()  # the hook deleted it again after publishing
    assert _Consumed.seen == ["run 1", "run 2"]  # the second run's fresh output was published
    manifest_key = ws.read_manifest("ws1")["stages"]["consume"]["key"]
    assert [p.name for p in (ws.path("ws1") / "stages" / "consume").iterdir()] == [manifest_key]


def test_publish_discards_staging_when_the_existing_directory_is_complete(env):
    from insightex.jobs.runner import _publish

    _, _, ws = env
    stage = _Writer("only", "1")
    final = ws.stage_dir("ws1", "only", "0123456789abcdef")
    final.mkdir(parents=True)
    (final / "out.txt").write_text("old")
    staging = ws.staging_dir("ws1", "only", "0123456789abcdef", 1)
    staging.mkdir(parents=True)
    (staging / "out.txt").write_text("new")
    _publish(ws, "ws1", stage, "0123456789abcdef", staging, 0.1)
    assert (final / "out.txt").read_text() == "old" and not staging.exists()


def test_failing_after_stage_hook_is_non_fatal_and_logged_with_stage_and_job(env, caplog):
    class Boom(_Writer):
        def after_stage(self, ctx, upstream) -> None:
            raise RuntimeError("hook exploded")

    _, conn, _ = env
    register_pipeline("boomhook", [Boom("only", "1")])
    job_id = store.enqueue(conn, "boomhook", {}, "ws1")
    with caplog.at_level("WARNING", logger="insightex.jobs.runner"):
        _, status = run_next(env)
    assert status == "succeeded"
    lines = [r for r in caplog.records if r.levelname == "WARNING" and "after_stage hook failed" in r.getMessage()]
    assert len(lines) == 1
    msg = lines[0].getMessage()
    assert "stage=only" in msg and f"job={job_id}" in msg and "RuntimeError: hook exploded" in msg


def test_failing_on_failure_hook_is_logged_with_stage_job_and_staged_path_and_job_stays_failed(env, caplog):
    class Fail(_Writer):
        def run(self, ctx) -> None:
            raise RuntimeError("stage broke")

    def bad_hook(conn, workspaces, job, settings, exc) -> None:
        raise OSError("cannot clean up")

    settings, conn, _ = env
    staged = settings.ingest.file.staging_dir / ("a" * 32 + ".part")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"x")
    register_pipeline("boomfail", [Fail("only", "1")], on_failure=bad_hook)
    job_id = store.enqueue(conn, "boomfail", {"staged": staged.name}, "ws1")
    with caplog.at_level("WARNING", logger="insightex.jobs.runner"):
        _, status = run_next(env)
    assert status == "failed" and store.get_job(conn, job_id).status == "failed"
    lines = [r for r in caplog.records if r.levelname == "WARNING" and "on_failure hook failed" in r.getMessage()]
    assert len(lines) == 1
    msg = lines[0].getMessage()
    assert "stage=only" in msg and f"job={job_id}" in msg and "OSError: cannot clean up" in msg
    assert f"staged file left behind: {staged}" in msg
