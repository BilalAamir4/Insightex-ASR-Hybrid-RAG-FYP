"""`insightex db`, `insightex worker` and `insightex jobs` commands. Output formats: docs/contracts/jobs-cli.md."""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from insightex.core.config import ConfigError, Settings, get_settings
from insightex.jobs import cache, db, store
from insightex.jobs.stages import UnknownJobKind
from insightex.jobs.workspace import Workspaces


def register(sub: argparse._SubParsersAction) -> None:
    """Add the db, worker and jobs subcommands to the top-level parser."""
    p_db = sub.add_parser("db", help="job database")
    p_db.add_argument("action", choices=["migrate"])
    p_db.set_defaults(func=_db)

    p_worker = sub.add_parser("worker", help="run the single job worker (exit 2 if one is already running)")
    p_worker.set_defaults(func=_worker)

    p_gpu = sub.add_parser("gpu", help="GPU lease")
    gpu_sub = p_gpu.add_subparsers(dest="gpu_command", required=True)
    p = gpu_sub.add_parser("status", help="report whether the GPU lease is free or busy, and who holds it")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_gpu_status)

    p_cache = sub.add_parser("cache", help="workspace cache")
    cache_sub = p_cache.add_subparsers(dest="cache_command", required=True)
    p = cache_sub.add_parser("list", help="list workspaces, most recently accessed first")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cache_list)
    for name, func, text in (
        ("delete", _cache_delete, "delete a workspace (refused while a job uses it)"),
        ("pin", _cache_pin, "never evict this workspace"),
        ("unpin", _cache_unpin, "allow eviction of this workspace"),
    ):
        p = cache_sub.add_parser(name, help=text)
        p.add_argument("workspace_id")
        p.set_defaults(func=func)
    p = cache_sub.add_parser("gc", help="sweep stale stage keys in every idle workspace, then evict")
    p.set_defaults(func=_cache_gc)

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


def _gpu_status(args: argparse.Namespace, settings: Settings) -> int:
    from insightex.jobs import gpu_lease

    result = {
        **gpu_lease.status(settings.gpu.lease_path),
        "run_dir": str(settings.jobs.run_dir),
        "workspaces_dir": str(settings.jobs.workspaces_dir),
        "ollama_base_url": settings.ollama.base_url,
        "ollama_model": settings.ollama.model,
    }
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"lease_path: {result['lease_path']}")
    holder = result["holder"]
    if result["state"] == "free":
        print("state: free")
    elif holder:
        print(f"state: busy (pid {holder['pid']}, {holder['mode']}, {holder['purpose']}, since {holder['acquired_at']})")
    else:
        print("state: busy (no exclusive holder recorded; shared holds or a holder starting up)")
    return 0


def _workspaces(settings: Settings) -> Workspaces:
    return Workspaces(settings.jobs.workspaces_dir)


def _cache_list(args: argparse.Namespace, settings: Settings) -> int:
    rows = cache.list_workspaces(_conn(settings), _workspaces(settings))
    if args.json:
        print(json.dumps({"workspaces": rows}, indent=2, ensure_ascii=False))
        return 0
    for r in rows:
        flags = ",".join(f for f, on in (("pinned", r["pinned"]), ("busy", r["busy"]), ("unindexed", not r["indexed"])) if on)
        print(f"{r['id']:<44} {r['size_bytes'] / 1e6:>10.1f} MB  {r['source_kind'] or '-':<8} {r['last_accessed_at'] or '-'}  {flags}")
    return 0


def _cache_delete(args: argparse.Namespace, settings: Settings) -> int:
    cache.delete(_conn(settings), _workspaces(settings), args.workspace_id)
    print("deleted")
    return 0


def _cache_pin(args: argparse.Namespace, settings: Settings) -> int:
    cache.pin(_conn(settings), args.workspace_id)
    print("pinned")
    return 0


def _cache_unpin(args: argparse.Namespace, settings: Settings) -> int:
    cache.unpin(_conn(settings), args.workspace_id)
    print("unpinned")
    return 0


def _cache_gc(args: argparse.Namespace, settings: Settings) -> int:
    swept, evicted = cache.gc_all(_conn(settings), _workspaces(settings), settings.cache.max_bytes)
    print(f"swept {swept} stale stage dir(s); evicted {len(evicted)} workspace(s)" + (f": {', '.join(evicted)}" if evicted else ""))
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
    except (ConfigError, store.JobNotFound, store.InvalidJobState, store.PipelineMismatch, UnknownJobKind, ValueError,
            cache.WorkspaceBusy, cache.WorkspaceNotFound) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
