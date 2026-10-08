"""Real worker processes: kill -9 resume and the singleton lock. Slow."""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time

import pytest

from insightex.core.config import load_settings
from insightex.jobs import db, store

pytestmark = pytest.mark.slow


def start_worker() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "insightex.cli", "worker"], stderr=subprocess.PIPE, text=True, env=os.environ.copy()
    )


def wait_for(predicate, timeout=30.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture
def conn():
    settings = load_settings()
    c = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(c)
    yield settings, c
    c.close()


def test_kill_dash_9_during_gpu_stage_then_resume(conn):
    settings, c = conn
    job_id = store.enqueue(c, "dummy", {"cpu_seconds": 1, "gpu_seconds": 6}, "killme")
    worker = start_worker()
    try:
        wait_for(lambda: store.get_job(c, job_id).stages[1].status == "running", what="dummy_gpu running")
        worker.send_signal(signal.SIGKILL)
        worker.wait(timeout=10)
    finally:
        if worker.poll() is None:
            worker.kill()
    assert store.get_job(c, job_id).status == "running"  # nothing noticed the death yet

    second = start_worker()
    try:
        wait_for(lambda: store.get_job(c, job_id).status in ("succeeded", "failed"), timeout=60, what="job to finish")
    finally:
        second.send_signal(signal.SIGTERM)
        assert second.wait(timeout=15) == 0
    job = store.get_job(c, job_id)
    assert job.status == "succeeded", job.error
    assert [s.status for s in job.stages] == ["cached", "succeeded"]
    assert job.attempts == 2
    staging = settings.jobs.workspaces_dir / "killme" / ".staging"
    assert not staging.exists() or not list(staging.iterdir())


def test_second_worker_exits_with_code_2(conn):
    first = start_worker()
    try:
        lock = conn[0].jobs.run_dir / "worker.lock"
        wait_for(lambda: lock.exists() and lock.read_text().strip() == str(first.pid), what="worker lock")
        second = start_worker()
        _, err = second.communicate(timeout=20)
        assert second.returncode == 2
        assert f"another worker is already running (pid {first.pid})" in err
    finally:
        first.send_signal(signal.SIGTERM)
        assert first.wait(timeout=15) == 0


def test_sigterm_while_blocked_on_a_held_lease_requeues_the_job(conn):
    settings, c = conn
    settings.gpu.lease_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(settings.gpu.lease_path, os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    job_id = store.enqueue(c, "dummy", {"cpu_seconds": 0.2, "gpu_seconds": 1}, "blocked")
    worker = start_worker()
    try:
        wait_for(lambda: store.get_job(c, job_id).stages[0].status == "succeeded", what="dummy_cpu done")
        time.sleep(0.5)  # the worker is now waiting for the lease
        job = store.get_job(c, job_id)
        assert job.status == "running" and job.stages[1].status == "pending"
        worker.send_signal(signal.SIGTERM)
        assert worker.wait(timeout=15) == 0
    finally:
        if worker.poll() is None:
            worker.kill()
        os.close(fd)
    job = store.get_job(c, job_id)
    assert job.status == "queued"
    assert job.attempts == 0
