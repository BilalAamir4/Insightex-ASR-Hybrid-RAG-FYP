"""`insightex db`, `insightex worker` and `insightex jobs` commands. Output formats: docs/contracts/jobs-cli.md."""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from insightex.core.config import ConfigError, Settings, get_settings
from insightex.jobs import db, store
from insightex.jobs.stages import UnknownJobKind


def register(sub: argparse._SubParsersAction) -> None:
    """Add the db, worker and jobs subcommands to the top-level parser."""
    p_db = sub.add_parser("db", help="job database")
    p_db.add_argument("action", choices=["migrate"])
    p_db.set_defaults(func=_db)

    p_worker = sub.add_parser("worker", help="run the single job worker (exit 2 if one is already running)")
    p_worker.set_defaults(func=_worker)

    p_jobs = sub.add_parser("jobs", help="enqueue, inspect, cancel and retry jobs")
    jobs_sub = p_jobs.add_subparsers(dest="jobs_command", required=True)

    p = jobs_sub.add_parser("enqueue-dummy", help="enqueue the two-stage dummy job; prints the job id")
    p.add_argument("--cpu-seconds", type=float, default=5)
    p.add_argument("--gpu-seconds", type=float, default=20)
    p.add_argument("--label", default="", help="part of both stage keys; change it to force a rerun")
    p.add_argument("--workspace", help="workspace id (default: dummy-<8 hex>)")
    p.set_defaults(func=_enqueue_dummy)

    p = jobs_sub.add_parser("list", help="list jobs, newest first")
    p.add_argument("--status", choices=store.JOB_STATUSES)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_list)

    p = jobs_sub.add_parser("show", help="show one job with its stages")
    p.add_argument("job_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_show)

    p = jobs_sub.add_parser("cancel", help="cancel a job (a running job stops at its next progress call)")
    p.add_argument("job_id")
    p.set_defaults(func=_cancel)

    p = jobs_sub.add_parser("retry", help="requeue a failed or cancelled job; finished stages are reused")
    p.add_argument("job_id")
    p.set_defaults(func=_retry)


def _conn(settings: Settings):
    conn = db.connect(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    return conn


def _db(args: argparse.Namespace, settings: Settings) -> int:
    conn = db.connect(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    applied = db.migrate(conn)
    print(f"{settings.jobs.db_path}: schema version {db.schema_version(conn)} ({applied} migration(s) applied)")
    return 0


def _worker(args: argparse.Namespace, settings: Settings) -> int:
    from insightex.jobs.worker import main as worker_main

    return worker_main(settings)


def _enqueue_dummy(args: argparse.Namespace, settings: Settings) -> int:
    payload = {"cpu_seconds": args.cpu_seconds, "gpu_seconds": args.gpu_seconds, "label": args.label}
    workspace = args.workspace or f"dummy-{uuid.uuid4().hex[:8]}"
    print(store.enqueue(_conn(settings), "dummy", payload, workspace))
    return 0


def _line(job: store.Job) -> str:
    stages = " ".join(f"{s.name}={s.status}" for s in job.stages)
    return f"{job.id}  {job.status:<9} {job.kind:<6} {job.workspace_id:<20} attempts={job.attempts}  {stages}"


def _list(args: argparse.Namespace, settings: Settings) -> int:
    jobs = store.list_jobs(_conn(settings), args.limit, args.status)
    if args.json:
        print(json.dumps({"jobs": [j.to_dict() for j in jobs]}, indent=2, ensure_ascii=False))
    else:
        for job in jobs:
            print(_line(job))
    return 0


def _show(args: argparse.Namespace, settings: Settings) -> int:
    job = store.get_job(_conn(settings), args.job_id)
    if args.json:
        print(json.dumps(job.to_dict(), indent=2, ensure_ascii=False))
        return 0
    print(_line(job))
    for key in ("payload", "error", "created_at", "started_at", "finished_at", "worker_pid", "cancel_requested"):
        print(f"  {key}: {getattr(job, key)}")
    for s in job.stages:
        print(f"  [{s.idx}] {s.name:<12} {s.status:<9} {s.progress:>4.0%} key={s.stage_key} {s.message or ''}")
        if s.error:
            print("      " + s.error.strip().replace("\n", "\n      "))
    return 0


def _cancel(args: argparse.Namespace, settings: Settings) -> int:
    status = store.request_cancel(_conn(settings), args.job_id)
    print("cancelled" if status == "cancelled" else f"job is {status}" + (" (cancel requested)" if status == "running" else ""))
    return 0


def _retry(args: argparse.Namespace, settings: Settings) -> int:
    store.retry(_conn(settings), args.job_id)
    print("queued")
    return 0


def run(args: argparse.Namespace) -> int:
    """Load settings once and run the chosen command; user errors become `error: ...` and exit 1."""
    try:
        return args.func(args, get_settings())
    except (ConfigError, store.JobNotFound, store.InvalidJobState, store.PipelineMismatch, UnknownJobKind, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
