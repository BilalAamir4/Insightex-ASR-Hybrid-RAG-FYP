"""Stage runner: runs one job's pipeline with caching, atomic outputs and cooperative cancel (ADR-0033, ADR-0034).

Per stage: compute the chained key; if the manifest already holds it with all outputs, mark the stage
`cached`; otherwise take the GPU lease (if needed), run into a fresh staging directory, verify the
declared outputs, move the directory into place, record it in the manifest, and mark the stage done.
"""

from __future__ import annotations

import contextvars
import dataclasses
import logging
import os
import shutil
import sqlite3
import time
import traceback
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

from insightex.core.config import Settings
from insightex.jobs import cache, store
from insightex.jobs.db import utcnow
from insightex.jobs.rebind import rebind
from insightex.jobs.stages import (
    PENDING_PREFIX,
    GpuLease,
    JobCancelled,
    KeyContext,
    NullGpuLease,
    Stage,
    StageContext,
    UnknownJobKind,
    WorkerStopping,
    get_chain_root,
    get_failure_hook,
    get_pipeline,
    get_source_for,
    stage_key,
)
from insightex.jobs.workspace import Workspaces

log = logging.getLogger(__name__)

# (job id, stage name) shown in every worker log line; the worker is single-threaded.
LOG_CONTEXT: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar("job_log_context", default=("-", "-"))


class MissingOutput(RuntimeError):
    """A stage finished without creating a declared output file."""


def _fail_message(exc: BaseException, limit: int) -> str:
    tb = "".join(traceback.format_exception(exc))
    details = getattr(exc, "details", "")  # IngestRejected: the ffmpeg stderr tail or the failed check
    extra = f"\ndetails:\n{details}" if details else ""
    return f"{type(exc).__name__}: {exc}{extra}\n{tb[-limit:]}"


class _Progress:
    """The `ctx.progress` implementation for one running stage."""

    def __init__(self, conn: sqlite3.Connection, job_id: str, idx: int, min_interval_s: float, stop: Callable[[], bool]):
        self.conn, self.job_id, self.idx = conn, job_id, idx
        self.min_interval_s, self.stop = min_interval_s, stop
        self._last_write = float("-inf")

    def __call__(self, fraction: float, message: str | None) -> None:
        if self.stop():
            raise WorkerStopping()
        if store.is_cancel_requested(self.conn, self.job_id):
            raise JobCancelled()
        now = time.monotonic()
        if fraction in (0.0, 1.0) or now - self._last_write >= self.min_interval_s:
            self._last_write = now
            changes: dict = {"progress": fraction}
            if message is not None:
                changes["message"] = message
            store.update_stage(self.conn, self.job_id, self.idx, **changes)


def run_job(
    conn: sqlite3.Connection,
    job: store.Job,
    settings: Settings,
    workspaces: Workspaces,
    *,
    gpu_lease: GpuLease | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> str:
    """Run a claimed job to its end; return the job's resulting status.

    The result is `succeeded`, `failed`, `cancelled`, or `queued` when the worker was told to stop and
    the job was put back. Never raises for job-level problems; those become a failed job.

    Cache bookkeeping (ADR-0034): the workspace is registered and touched at start and touched at the
    end; after a success the stale-key sweep, size refresh and eviction run in that order. A failure in
    any of them logs a warning and never changes the job's status.
    """
    _cache_step("register", _cache_register, conn, job)
    status = _run_pipeline(conn, job, settings, workspaces, gpu_lease, should_stop)
    LOG_CONTEXT.set((job.id, "-"))
    workspace_id = store.get_job(conn, job.id).workspace_id  # a rebind may have changed it
    _cache_step("touch", cache.touch, conn, workspace_id)
    if status == "succeeded":
        _cache_step("stale-key sweep", cache.gc_stale_keys, workspaces, workspace_id)
        _cache_step("size refresh", cache.refresh_size, conn, workspaces, workspace_id)
        _cache_step("eviction", cache.evict, conn, workspaces, settings.cache.max_bytes, workspace_id)
    return status


def _cache_step(what: str, fn, *args) -> None:
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001 - cache bookkeeping must never change a job's outcome
        log.warning("cache %s failed: %s: %s", what, type(exc).__name__, exc)


def _cache_register(conn: sqlite3.Connection, job: store.Job) -> None:
    source_for = get_source_for(job.kind)
    if source_for is not None:
        kind, ref = source_for(job.payload)
        cache.register(conn, job.workspace_id, kind, ref)
    cache.touch(conn, job.workspace_id)


def _run_pipeline(conn, job, settings, workspaces, gpu_lease, should_stop) -> str:
    lease = gpu_lease or NullGpuLease()
    LOG_CONTEXT.set((job.id, "-"))
    try:
        pipeline = get_pipeline(job.kind)
        store.check_pipeline_matches(job)
    except (UnknownJobKind, store.PipelineMismatch) as exc:
        log.error("%s", exc)
        store.finish(conn, job.id, "failed", str(exc))
        return "failed"

    chain_root = get_chain_root(job.kind)
    upstream_key = chain_root(job.payload, job.workspace_id) if chain_root else job.workspace_id
    upstream_keys: dict[str, str] = {}
    upstream_dirs: dict[str, Path] = {}
    for idx, stage in enumerate(pipeline):
        LOG_CONTEXT.set((job.id, stage.name))
        if should_stop():
            return _stop(conn, job)
        if store.is_cancel_requested(conn, job.id):
            return _cancel(conn, job, idx)

        key_ctx = KeyContext(job.id, job.payload, job.workspace_id, settings)
        try:
            key = stage_key(stage.name, stage.version, stage.config_fingerprint(key_ctx), upstream_key)
        except Exception as exc:  # noqa: BLE001 - a bad fingerprint fails the job, not the worker
            return _fail(conn, job, idx, exc, settings, workspaces)
        store.update_stage(conn, job.id, idx, stage_key=key)
        outputs = list(stage.outputs)

        requested: list[str | None] = []
        if workspaces.stage_is_complete(job.workspace_id, stage.name, key, outputs):
            store.update_stage(
                conn, job.id, idx, status="cached", progress=1.0, message=None, error=None, finished_at=utcnow()
            )
            log.info("stage cached (key %s)", key)
            _after_stage(stage, key_ctx, job, key, workspaces, upstream_dirs)
        else:
            outcome = _run_stage(
                conn, job, idx, stage, key, settings, workspaces, lease, should_stop, upstream_dirs, requested
            )
            if outcome is not None:
                return outcome
            _after_stage(stage, key_ctx, job, key, workspaces, upstream_dirs)
        upstream_keys[stage.name] = key
        if job.workspace_id.startswith(PENDING_PREFIX):
            try:
                target = (requested[0] if requested else None) or stage.workspace_id_after(
                    workspaces.stage_dir(job.workspace_id, stage.name, key)
                )
                if target and target != job.workspace_id:
                    LOG_CONTEXT.set((job.id, stage.name))
                    rebind(conn, workspaces, job.id, job.workspace_id, target, stage.name)
                    job = dataclasses.replace(job, workspace_id=target)
            except Exception as exc:  # noqa: BLE001 - a failed rebind fails the job, not the worker
                return _fail(conn, job, idx, exc, settings, workspaces)
        upstream_dirs = {n: workspaces.stage_dir(job.workspace_id, n, k) for n, k in upstream_keys.items()}
        upstream_key = key

    store.finish(conn, job.id, "succeeded")
    LOG_CONTEXT.set((job.id, "-"))
    log.info("job succeeded")
    return "succeeded"


def _run_stage(
    conn, job, idx, stage: Stage, key, settings, workspaces: Workspaces, lease, should_stop, upstream_dirs, requested
) -> str | None:
    """Run one uncached stage. Returns None on success, else the job's resulting status.

    `requested` receives the workspace id the stage asked for with `ctx.rebind_workspace`, if any.
    """
    staging = workspaces.staging_dir(job.workspace_id, stage.name, key, os.getpid())
    started = time.monotonic()
    try:
        with lease.hold(job.id, stage.name) if stage.needs_gpu else nullcontext():
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True)
            store.update_stage(
                conn, job.id, idx, status="running", progress=0.0, message=None, error=None,
                started_at=utcnow(), finished_at=None,
            )
            log.info("stage started (key %s)", key)
            progress = _Progress(conn, job.id, idx, settings.jobs.progress_min_interval_s, should_stop)
            ctx = StageContext(
                job_id=job.id, payload=job.payload, workspace_id=job.workspace_id, settings=settings,
                staging_dir=staging, upstream=dict(upstream_dirs), reporter=progress,
            )
            progress(0.0, None)
            stage.run(ctx)
            requested.append(ctx.rebind_request)
        _verify_outputs(stage, staging)
        _publish(workspaces, job.workspace_id, stage, key, staging, time.monotonic() - started)
    except JobCancelled:
        shutil.rmtree(staging, ignore_errors=True)
        return _cancel(conn, job, idx)
    except WorkerStopping:
        shutil.rmtree(staging, ignore_errors=True)
        return _stop(conn, job)
    except Exception as exc:  # noqa: BLE001 - any stage error fails the job and is recorded
        shutil.rmtree(staging, ignore_errors=True)
        return _fail(conn, job, idx, exc, settings, workspaces)
    store.update_stage(conn, job.id, idx, status="succeeded", progress=1.0, finished_at=utcnow())
    log.info("stage succeeded in %.1fs", time.monotonic() - started)
    return None


def _after_stage(stage: Stage, key_ctx: KeyContext, job, key: str, workspaces: Workspaces, upstream_dirs) -> None:
    try:
        own = {**upstream_dirs, stage.name: workspaces.stage_dir(job.workspace_id, stage.name, key)}
        stage.after_stage(key_ctx, own)
    except Exception as exc:  # noqa: BLE001 - a clean-up hook must never fail a job
        log.warning("after_stage hook failed (non-fatal): stage=%s job=%s: %s: %s", stage.name, job.id, type(exc).__name__, exc)


def _verify_outputs(stage: Stage, staging: Path) -> None:
    missing = [name for name in stage.outputs if not (staging / name).exists()]
    if missing:
        raise MissingOutput(f"stage {stage.name} did not create declared outputs: {', '.join(missing)}")


def _publish(workspaces: Workspaces, workspace_id: str, stage: Stage, key: str, staging: Path, duration_s: float) -> None:
    """Move finished outputs into stages/<name>/<key>/, record them in the manifest, drop the superseded key's dir."""
    for name in stage.outputs:  # make file contents durable before they become visible under their final name
        path = staging / name
        if path.is_file():
            fd = os.open(path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    final = workspaces.stage_dir(workspace_id, stage.name, key)
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists() and all((final / name).exists() for name in stage.outputs):
        shutil.rmtree(staging)  # a crash between this move and the manifest write left it; same key means same content
    else:
        # Absent, or present but missing a declared output (an input a later hook deleted, such as an uploaded
        # original): the fresh outputs win.
        shutil.rmtree(final, ignore_errors=True)
        os.replace(staging, final)
    previous = workspaces.record_stage(workspace_id, stage.name, key, duration_s, list(stage.outputs))
    if previous and previous != key:  # only after the new manifest is durable
        workspaces.remove_stage_key_dir(workspace_id, stage.name, previous)


def _fail(conn, job, idx: int, exc: BaseException, settings: Settings, workspaces: Workspaces) -> str:
    detail = _fail_message(exc, settings.jobs.error_traceback_chars)
    log.error("stage failed: %s: %s%s", type(exc).__name__, exc, f" ({exc.details})" if getattr(exc, "details", "") else "")
    store.update_stage(conn, job.id, idx, status="failed", error=detail, finished_at=utcnow())
    store.finish(conn, job.id, "failed", f"{job.stages[idx].name} failed: {type(exc).__name__}: {exc}")
    try:
        hook = get_failure_hook(job.kind)
        if hook is not None:
            hook(conn, workspaces, job, settings, exc)
    except Exception as hook_exc:  # noqa: BLE001 - a failure hook must never mask the original failure
        log.warning("failure hook for %s failed: %s: %s", job.kind, type(hook_exc).__name__, hook_exc)
    return "failed"


def _cancel(conn, job, idx: int) -> str:
    """Mark the stage at `idx` and every later stage cancelled, then the job."""
    for i in range(idx, len(job.stages)):
        store.update_stage(conn, job.id, i, status="cancelled", finished_at=utcnow())
    store.finish(conn, job.id, "cancelled")
    log.info("job cancelled")
    return "cancelled"


def _stop(conn, job) -> str:
    store.requeue_interrupted(conn, job.id)
    log.info("worker stopping: job returned to the queue")
    return "queued"
