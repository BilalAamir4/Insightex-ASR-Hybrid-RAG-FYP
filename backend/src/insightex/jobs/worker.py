"""The single job worker process (ADR-0033).

At most one runs per machine: it holds an exclusive flock on `<run_dir>/worker.lock`, which the kernel
drops when the process dies. `Worker.run` loops: claim the oldest queued job, run its pipeline, sleep when
the queue is empty. SIGINT/SIGTERM finish nothing new: the running stage stops at its next
`ctx.progress` call, the job returns to the queue, and the worker exits 0. A second signal exits at once.
"""

from __future__ import annotations

import fcntl
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import IO

from insightex.core.config import Settings
from insightex.jobs import db, store
from insightex.jobs.runner import LOG_CONTEXT, run_job
from insightex.jobs.stages import GpuLease, NullGpuLease
from insightex.jobs.workspace import Workspaces

log = logging.getLogger(__name__)

EXIT_LOCKED = 2


class _ContextFilter(logging.Filter):
    """Adds job id and stage name to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.job, record.stage = LOG_CONTEXT.get()
        return True


def setup_logging(logs_dir: Path) -> None:
    """Log to stderr and `<logs_dir>/worker.log`; every line carries `job=<id> stage=<name>`."""
    fmt = logging.Formatter("%(asctime)s %(levelname)s job=%(job)s stage=%(stage)s %(name)s: %(message)s")
    root = logging.getLogger("insightex")
    root.setLevel(logging.INFO)
    logs_dir.mkdir(parents=True, exist_ok=True)
    for handler in (logging.StreamHandler(sys.stderr), logging.FileHandler(logs_dir / "worker.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        handler.addFilter(_ContextFilter())
        root.addHandler(handler)


class WorkerLocked(RuntimeError):
    """Another worker holds the lock; `pid` is the pid it wrote, or None."""

    def __init__(self, pid: int | None) -> None:
        super().__init__(f"another worker is already running (pid {pid if pid is not None else 'unknown'})")
        self.pid = pid


def acquire_worker_lock(run_dir: Path) -> IO[str]:
    """Take the exclusive, non-blocking worker lock and write our pid into it. Keep the returned file open."""
    run_dir.mkdir(parents=True, exist_ok=True)
    f = open(run_dir / "worker.lock", "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.seek(0)
        text = f.read().strip()
        f.close()
        raise WorkerLocked(int(text) if text.isdigit() else None) from None
    f.seek(0)
    f.truncate()
    f.write(f"{os.getpid()}\n")
    f.flush()
    return f


class Worker:
    """Claims and runs jobs one at a time. Construct after taking the worker lock."""

    def __init__(self, settings: Settings, gpu_lease: GpuLease | None = None) -> None:
        self.settings = settings
        self.gpu_lease = gpu_lease or NullGpuLease()
        self.workspaces = Workspaces(settings.jobs.workspaces_dir)
        self.stop_event = threading.Event()
        self.conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)

    def startup(self) -> None:
        """Migrate, delete abandoned staging directories, and resolve jobs left `running` by a dead worker."""
        db.migrate(self.conn)
        removed = self.workspaces.clean_staging()
        if removed:
            log.info("removed %d abandoned staging directories", removed)
        for job_id, status in store.recover_after_crash(self.conn, self.settings.jobs.max_attempts):
            LOG_CONTEXT.set((job_id, "-"))
            log.warning("recovered job after worker crash: now %s", status)
        LOG_CONTEXT.set(("-", "-"))

    def run_one(self) -> bool:
        """Claim and run one job; False if the queue was empty."""
        job = store.claim_next(self.conn, os.getpid())
        if job is None:
            return False
        LOG_CONTEXT.set((job.id, "-"))
        log.info("claimed %s job (attempt %d)", job.kind, job.attempts)
        try:
            run_job(self.conn, job, self.settings, self.workspaces, gpu_lease=self.gpu_lease, should_stop=self.stop_event.is_set)
        except Exception as exc:  # a bug or database error outside any stage: fail the job rather than loop on it
            log.exception("job crashed the runner")
            store.finish(self.conn, job.id, "failed", f"runner error: {type(exc).__name__}: {exc}")
        LOG_CONTEXT.set(("-", "-"))
        return True

    def run(self) -> int:
        """Loop until a stop signal. Returns the process exit code (0)."""
        self.startup()
        log.info("worker started (pid %d)", os.getpid())
        while not self.stop_event.is_set():
            if not self.run_one():
                self.stop_event.wait(self.settings.jobs.poll_interval_s)
        log.info("worker stopped")
        return 0

    def install_signal_handlers(self) -> None:
        def handler(signum, _frame) -> None:
            if self.stop_event.is_set():
                os._exit(1)  # second signal: leave now; startup cleans staging and requeues the job
            log.info("signal %s: finishing up, send it again to exit immediately", signal.Signals(signum).name)
            self.stop_event.set()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)


def main(settings: Settings) -> int:
    """Entry point of `insightex worker`: exit 2 if another worker holds the lock, else run until signalled."""
    try:
        lock = acquire_worker_lock(settings.jobs.run_dir)
    except WorkerLocked as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_LOCKED
    setup_logging(settings.paths.logs_dir)
    worker = Worker(settings)
    worker.install_signal_handlers()
    try:
        return worker.run()
    finally:
        lock.close()
