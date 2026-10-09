"""Job store: the jobs and job_stages tables (ADR-0033).

All functions take an open connection from `insightex.jobs.db`. The database is the source of truth for
job state; the workspace manifest is the source of truth for finished stage outputs.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Any

from insightex.jobs.db import transaction, utcnow
from insightex.jobs.stages import get_pipeline
from insightex.jobs.workspace import validate_workspace_id

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
FINAL_STATUSES = ("succeeded", "failed", "cancelled")
_STAGE_FIELDS = ("status", "stage_key", "progress", "message", "error", "started_at", "finished_at")


class JobNotFound(KeyError):
    """No job with that id."""


class InvalidJobState(ValueError):
    """The requested change does not apply to the job's current status."""


class PipelineMismatch(RuntimeError):
    """The stage rows of a job do not match the registered pipeline for its kind (by idx and name)."""


@dataclass(frozen=True)
class StageRow:
    idx: int
    name: str
    status: str
    stage_key: str | None
    progress: float
    message: str | None
    error: str | None
    started_at: str | None
    finished_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    status: str
    cancel_requested: bool
    payload: dict[str, Any]
    workspace_id: str
    attempts: int
    worker_pid: int | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str
    stages: list[StageRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """The stable JSON shape documented in docs/contracts/jobs-cli.md."""
        out = {f: getattr(self, f) for f in self.__dataclass_fields__ if f != "stages"}
        out["stages"] = [s.to_dict() for s in self.stages]
        return out


def _job_from_row(row: sqlite3.Row, stages: list[StageRow] | None = None) -> Job:
    d = dict(row)
    d["cancel_requested"] = bool(d["cancel_requested"])
    d["payload"] = json.loads(d["payload"])
    return Job(**d, stages=stages or [])


def _stages_of(conn: sqlite3.Connection, job_id: str) -> list[StageRow]:
    rows = conn.execute("SELECT * FROM job_stages WHERE job_id = ? ORDER BY idx", (job_id,)).fetchall()
    return [StageRow(**{k: r[k] for k in r.keys() if k != "job_id"}) for r in rows]  # noqa: SIM118 - sqlite3.Row iterates values, not keys


def enqueue(
    conn: sqlite3.Connection,
    kind: str,
    payload: dict[str, Any],
    workspace_id: str,
    job_id: str | None = None,
    failed: tuple[str, str] | None = None,
) -> str:
    """Create a queued job and one pending stage row per stage of the kind's pipeline; return the job id.

    `job_id` lets a caller derive the workspace id from it (`pending-<job id>`); default is a fresh uuid.
    `failed=(job_error, first_stage_error)` records a job that was rejected before it could run: it is inserted
    as `failed` (never claimable), its first stage failed and the rest pending, as after a stage failure.
    Raises ValueError for a bad workspace id and UnknownJobKind for a kind with no registered pipeline.
    """
    validate_workspace_id(workspace_id)
    pipeline = get_pipeline(kind)
    job_id, now = job_id or uuid.uuid4().hex, utcnow()
    with transaction(conn):
        conn.execute(
            "INSERT INTO jobs (id, kind, status, payload, workspace_id, attempts, error, created_at, finished_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (job_id, kind, "failed" if failed else "queued", json.dumps(payload, sort_keys=True), workspace_id,
             failed[0] if failed else None, now, now if failed else None, now),
        )
        conn.executemany(
            "INSERT INTO job_stages (job_id, idx, name, status, error, finished_at) VALUES (?, ?, ?, ?, ?, ?)",
            [(job_id, i, s.name, "failed" if failed and i == 0 else "pending", failed[1] if failed and i == 0 else None,
              now if failed and i == 0 else None) for i, s in enumerate(pipeline)],
        )
    return job_id


def claim_next(conn: sqlite3.Connection, worker_pid: int) -> Job | None:
    """Atomically take the oldest queued job: status running, attempts + 1, worker_pid set. None if the queue is empty.

    Safe against concurrent claimers: the select and update run in one immediate transaction.
    """
    now = utcnow()
    with transaction(conn):
        row = conn.execute(
            "UPDATE jobs SET status = 'running', attempts = attempts + 1, worker_pid = ?, started_at = ?, "
            "finished_at = NULL, error = NULL, updated_at = ? "
            "WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at, rowid LIMIT 1) "
            "RETURNING *",
            (worker_pid, now, now),
        ).fetchone()
    return _job_from_row(row, _stages_of(conn, row["id"])) if row else None


def get_job(conn: sqlite3.Connection, job_id: str) -> Job:
    """The job with its stage rows; raises JobNotFound."""
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise JobNotFound(job_id)
    return _job_from_row(row, _stages_of(conn, job_id))


def list_jobs(conn: sqlite3.Connection, limit: int = 50, status: str | None = None) -> list[Job]:
    """Newest first, with stage rows. `status` filters; an unknown status raises ValueError."""
    if status is not None and status not in JOB_STATUSES:
        raise ValueError(f"unknown status {status!r}; use one of {', '.join(JOB_STATUSES)}")
    where, args = ("WHERE status = ?", [status]) if status else ("", [])
    rows = conn.execute(f"SELECT * FROM jobs {where} ORDER BY created_at DESC, rowid DESC LIMIT ?", [*args, limit])
    return [_job_from_row(r, _stages_of(conn, r["id"])) for r in rows.fetchall()]


def update_stage(conn: sqlite3.Connection, job_id: str, idx: int, **changes: Any) -> None:
    """Set columns of one stage row (status, stage_key, progress, message, error, started_at, finished_at)."""
    unknown = set(changes) - set(_STAGE_FIELDS)
    if unknown:
        raise ValueError(f"unknown stage columns: {sorted(unknown)}")
    if not changes:
        return
    sets = ", ".join(f"{col} = ?" for col in changes)
    now = utcnow()
    with transaction(conn):
        cur = conn.execute(f"UPDATE job_stages SET {sets} WHERE job_id = ? AND idx = ?", [*changes.values(), job_id, idx])
        if cur.rowcount != 1:
            raise JobNotFound(f"{job_id} stage {idx}")
        conn.execute("UPDATE jobs SET updated_at = ? WHERE id = ?", (now, job_id))


def finish(conn: sqlite3.Connection, job_id: str, status: str, error: str | None = None) -> None:
    """Move a job to a final status (succeeded, failed or cancelled) and clear its worker pid."""
    if status not in FINAL_STATUSES:
        raise ValueError(f"finish() needs one of {FINAL_STATUSES}, got {status!r}")
    now = utcnow()
    with transaction(conn):
        cur = conn.execute(
            "UPDATE jobs SET status = ?, error = ?, finished_at = ?, updated_at = ?, worker_pid = NULL WHERE id = ?",
            (status, error, now, now, job_id),
        )
        if cur.rowcount != 1:
            raise JobNotFound(job_id)


def is_cancel_requested(conn: sqlite3.Connection, job_id: str) -> bool:
    row = conn.execute("SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return bool(row and row["cancel_requested"])


def request_cancel(conn: sqlite3.Connection, job_id: str) -> str:
    """Cancel a job; return its resulting status.

    A queued job becomes cancelled at once (its pending stages too). A running job gets
    cancel_requested = 1 and the worker stops it at the next `ctx.progress` call or stage boundary.
    A finished job is left alone.
    """
    now = utcnow()
    with transaction(conn):
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFound(job_id)
        status = row["status"]
        if status == "queued":
            conn.execute(
                "UPDATE jobs SET status = 'cancelled', finished_at = ?, updated_at = ? WHERE id = ?", (now, now, job_id)
            )
            conn.execute(
                "UPDATE job_stages SET status = 'cancelled' WHERE job_id = ? AND status = 'pending'", (job_id,)
            )
            return "cancelled"
        if status == "running":
            conn.execute("UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE id = ?", (now, job_id))
        return status


def _reset_stages(conn: sqlite3.Connection, job_id: str, where: str = "") -> None:
    conn.execute(
        "UPDATE job_stages SET status = 'pending', stage_key = NULL, progress = 0, message = NULL, error = NULL, "
        f"started_at = NULL, finished_at = NULL WHERE job_id = ? {where}",
        (job_id,),
    )


def check_pipeline_matches(job: Job) -> None:
    """Raise PipelineMismatch unless the job's stage rows equal the registered pipeline, by idx and name."""
    expected = [s.name for s in get_pipeline(job.kind)]
    actual = [s.name for s in sorted(job.stages, key=lambda s: s.idx)]
    if [s.idx for s in job.stages] != list(range(len(expected))) or actual != expected:
        raise PipelineMismatch(
            f"job {job.id}: stage rows {actual} do not match the {job.kind!r} pipeline {expected}; "
            f"enqueue a new job"
        )


def retry(conn: sqlite3.Connection, job_id: str) -> None:
    """Requeue a failed or cancelled job: attempts 0, every stage row pending.

    Finished stages come back as `cached` when the worker reaches them. Raises InvalidJobState for any
    other status and PipelineMismatch if the registered pipeline changed since the job was enqueued.
    """
    job = get_job(conn, job_id)
    if job.status not in ("failed", "cancelled"):
        raise InvalidJobState(f"job {job_id} is {job.status}; only failed or cancelled jobs can be retried")
    check_pipeline_matches(job)
    now = utcnow()
    with transaction(conn):
        conn.execute(
            "UPDATE jobs SET status = 'queued', attempts = 0, cancel_requested = 0, error = NULL, worker_pid = NULL, "
            "started_at = NULL, finished_at = NULL, updated_at = ? WHERE id = ?",
            (now, job_id),
        )
        _reset_stages(conn, job_id)


def requeue_interrupted(conn: sqlite3.Connection, job_id: str) -> None:
    """Put a running job back in the queue after a clean worker shutdown, undoing its claim's attempt increment."""
    now = utcnow()
    with transaction(conn):
        conn.execute(
            "UPDATE jobs SET status = 'queued', attempts = MAX(attempts - 1, 0), worker_pid = NULL, "
            "updated_at = ? WHERE id = ? AND status = 'running'",
            (now, job_id),
        )
        _reset_stages(conn, job_id, "AND status IN ('running', 'cancelled')")


def recover_after_crash(conn: sqlite3.Connection, max_attempts: int) -> list[tuple[str, str]]:
    """Resolve every job left `running`; return (job_id, new_status) pairs.

    Call once at worker start. The worker is a singleton (flock on worker.lock), so a `running` row can
    only belong to a worker that died, and no heartbeat is needed. A job goes back to `queued` while
    attempts < max_attempts, otherwise to `failed`; a job with cancel_requested set becomes `cancelled`.
    Running stage rows go back to pending.
    """
    now = utcnow()
    result: list[tuple[str, str]] = []
    with transaction(conn):
        for row in conn.execute("SELECT id, attempts, cancel_requested FROM jobs WHERE status = 'running'").fetchall():
            if row["cancel_requested"]:
                status, error = "cancelled", None
            elif row["attempts"] < max_attempts:
                status, error = "queued", None
            else:
                status, error = "failed", f"worker died during this job {row['attempts']} times"
            finished = now if status != "queued" else None
            conn.execute(
                "UPDATE jobs SET status = ?, error = ?, finished_at = ?, worker_pid = NULL, updated_at = ? WHERE id = ?",
                (status, error, finished, now, row["id"]),
            )
            _reset_stages(conn, row["id"], "AND status = 'running'")
            result.append((row["id"], status))
    return result


def set_workspace(conn: sqlite3.Connection, job_id: str, workspace_id: str) -> None:
    """Point a job at another workspace. Call it inside the caller's transaction (see rebind)."""
    cur = conn.execute("UPDATE jobs SET workspace_id = ?, updated_at = ? WHERE id = ?", (workspace_id, utcnow(), job_id))
    if cur.rowcount != 1:
        raise JobNotFound(job_id)
