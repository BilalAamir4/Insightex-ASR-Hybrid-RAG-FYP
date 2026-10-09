"""GPU lease: flock semantics, kill -9 release, Ollama unload (mocked HTTP), config derivation."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time

import httpx
import pytest

from insightex.core.config import ConfigError, load_settings
from insightex.jobs import gpu_lease as gl
from insightex.jobs.gpu_lease import FileGpuLease, GpuBusy, GpuUnavailable
from insightex.jobs.stages import WorkerStopping


@pytest.fixture
def settings(tmp_path):
    return load_settings({"gpu": {"lock_retry_interval_s": 0.01, "ollama_poll_interval_s": 0.01, "ollama_unload_timeout_s": 0.2}})


@pytest.fixture(autouse=True)
def no_ollama(monkeypatch):
    """Default: the unload succeeds at once. Tests of the unload itself override this."""
    monkeypatch.setattr(gl.ollama_client, "unload", lambda *a, **k: True)


def test_exclusive_blocks_exclusive_and_shared(settings):
    lease = FileGpuLease(settings)
    with lease.exclusive("a", None):
        with pytest.raises(GpuBusy), FileGpuLease(settings).exclusive("b", 0.05):
            pass
        with pytest.raises(GpuBusy), FileGpuLease(settings).shared("c", 0.05):
            pass
    with FileGpuLease(settings).exclusive("d", 0.05):
        pass


def test_shared_allows_shared_but_blocks_exclusive(settings):
    with FileGpuLease(settings).shared("q1", 0.1), FileGpuLease(settings).shared("q2", 0.1), pytest.raises(GpuBusy), FileGpuLease(settings).exclusive("w", 0.05):
        pass


def test_timeout_carries_holder_info(settings):
    with FileGpuLease(settings).exclusive("job1:stage", None), pytest.raises(GpuBusy) as err, FileGpuLease(settings).shared("q", 0.05):
        pass
    holder = err.value.holder
    assert holder["pid"] == os.getpid() and holder["mode"] == "exclusive" and holder["purpose"] == "job1:stage"
    assert holder["acquired_at"].endswith("Z")
    assert "job1:stage" in str(err.value)


def test_holder_file_cleared_on_release_and_status(settings):
    path = settings.gpu.lease_path
    assert gl.status(path)["state"] == "free"
    with FileGpuLease(settings).exclusive("x:y", None):
        st = gl.status(path)
        assert st["state"] == "busy" and st["holder"]["purpose"] == "x:y"
    assert not gl.holder_path(path).exists()
    assert gl.status(path) == {"lease_path": str(path), "state": "free", "holder": None}


def test_status_ignores_leftover_holder_file(settings):
    path = settings.gpu.lease_path
    path.parent.mkdir(parents=True, exist_ok=True)
    gl.holder_path(path).write_text(json.dumps({"pid": 1, "mode": "exclusive", "purpose": "dead", "acquired_at": "x"}))
    assert gl.status(path)["state"] == "free" and gl.status(path)["holder"] is None


def test_hold_goes_through_exclusive(settings):
    lease = FileGpuLease(settings)
    calls = []
    real = lease.exclusive
    lease.exclusive = lambda purpose, timeout_s: (calls.append((purpose, timeout_s)), real(purpose, timeout_s))[1]
    with lease.hold("job9", "gpu_stage"):
        assert gl.status(settings.gpu.lease_path)["holder"]["purpose"] == "job9:gpu_stage"
    assert calls == [("job9:gpu_stage", None)]


def test_kill_dash_9_releases_the_lease(settings):
    child_code = textwrap.dedent(
        """
        import fcntl, os, sys, time
        fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX)
        print("held", flush=True)
        time.sleep(60)
        """
    )
    path = settings.gpu.lease_path
    path.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen([sys.executable, "-I", "-c", child_code, str(path)], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        with pytest.raises(GpuBusy), FileGpuLease(settings).exclusive("p", 0.05):
            pass
        child.send_signal(signal.SIGKILL)
        child.wait(timeout=10)
        start = time.monotonic()
        with FileGpuLease(settings).exclusive("p", 0.0):
            pass
        assert time.monotonic() - start < 1
    finally:
        if child.poll() is None:
            child.kill()


def test_should_stop_interrupts_the_wait(settings):
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    with FileGpuLease(settings).exclusive("holder", None), pytest.raises(WorkerStopping), FileGpuLease(settings, should_stop=stop.is_set).exclusive("waiter", None):
        pass


# -- Ollama unload (mocked HTTP; the real client function runs) ------------------------------------


def _mock_ollama(monkeypatch, *, ps_models, post_ok=True):
    posts = []

    def post(url, json=None, timeout=None):
        posts.append((url, json))
        if not post_ok:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, request=httpx.Request("POST", url))

    def get(url, timeout=None):
        if not post_ok:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"models": [{"name": n} for n in ps_models()]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(gl.ollama_client.httpx, "post", post)
    monkeypatch.setattr(gl.ollama_client.httpx, "get", get)
    return posts


def test_unload_success_posts_keep_alive_zero(settings, monkeypatch):
    monkeypatch.undo()  # drop the autouse stub
    loaded = [settings.ollama.model]
    posts = _mock_ollama(monkeypatch, ps_models=lambda: loaded)
    threading.Timer(0.05, loaded.clear).start()
    with FileGpuLease(settings).exclusive("p", None):
        pass
    assert posts == [(f"{settings.ollama.base_url}/api/generate", {"model": settings.ollama.model, "keep_alive": 0})]


def test_model_still_loaded_raises_and_releases(settings, monkeypatch):
    monkeypatch.undo()
    _mock_ollama(monkeypatch, ps_models=lambda: [settings.ollama.model])
    with pytest.raises(GpuUnavailable, match="still loaded"), FileGpuLease(settings).exclusive("p", None):
        pytest.fail("body must not run")
    assert gl.status(settings.gpu.lease_path)["state"] == "free"
    assert not gl.holder_path(settings.gpu.lease_path).exists()


def test_unreachable_ollama_logs_and_continues(settings, monkeypatch, caplog):
    monkeypatch.undo()
    _mock_ollama(monkeypatch, ps_models=list, post_ok=False)
    ran = False
    with caplog.at_level("WARNING", logger="insightex.jobs.gpu_lease"), FileGpuLease(settings).exclusive("p", None):
        ran = True
    assert ran and "ollama unreachable" in caplog.text


# -- config ----------------------------------------------------------------------------------------


def test_lease_path_derives_from_run_dir(tmp_path):
    s = load_settings({"paths": {"data_dir": str(tmp_path)}})
    assert s.gpu.lease_path == tmp_path / "run" / "gpu.lock"
    s = load_settings({"paths": {"data_dir": str(tmp_path)}, "jobs": {"run_dir": str(tmp_path / "r2")}})
    assert s.gpu.lease_path == tmp_path / "r2" / "gpu.lock"


def test_lease_path_under_mnt_is_rejected():
    with pytest.raises(ConfigError, match=r"gpu\.lease_path.*under /mnt/"):
        load_settings({"gpu": {"lease_path": "/mnt/e/gpu.lock"}})


def test_runner_takes_the_lease_only_for_gpu_stages(settings):
    from contextlib import contextmanager

    from insightex.jobs import db, store
    from insightex.jobs.runner import run_job
    from insightex.jobs.stages import GpuLease
    from insightex.jobs.workspace import Workspaces

    held = []

    class Recording(GpuLease):
        @contextmanager
        def hold(self, job_id, stage_name):
            held.append(stage_name)
            yield

    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    store.enqueue(conn, "dummy", {"cpu_seconds": 0, "gpu_seconds": 0, "step_seconds": 0.01}, "w")
    job = store.claim_next(conn, 1)
    assert run_job(conn, job, settings, Workspaces(settings.jobs.workspaces_dir), gpu_lease=Recording()) == "succeeded"
    assert held == ["dummy_gpu"]
    conn.close()
