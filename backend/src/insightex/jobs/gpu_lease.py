"""The GPU lease: an `fcntl.flock` on `gpu.lease_path` (ADR-0033).

Two modes share one lock file. `exclusive` is for worker stages that load models onto the GPU; it also
unloads the Ollama model once acquired, so the stage starts with free VRAM. `shared` is for interactive
Q&A calls to Ollama from the API process, so several questions run together while ingestion GPU work
waits. The kernel drops a flock when its holder dies, including `kill -9`; no stale lease can exist.

Every hold opens its own file descriptor, because flock belongs to the open file description. That makes
holds conflict correctly across processes and inside one process.

Known limits:
- Anything that talks to Ollama without taking the lease (for example the Ollama app used directly)
  bypasses it.
- A continuous stream of shared holders can starve an exclusive holder. That is acceptable for a
  single-user system.

`<lease_path>.holder` is JSON describing the current exclusive holder. It is diagnostic only; the lock
is the truth, and a leftover file after a crash is ignored by `status`.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from insightex.core.config import Settings
from insightex.jobs.stages import GpuLease, WorkerStopping
from insightex.llm import ollama_client

log = logging.getLogger(__name__)


class GpuBusy(Exception):
    """The lease was not free within the timeout. `holder` is the exclusive holder's info, or None."""

    def __init__(self, holder: dict[str, Any] | None, purpose: str = "") -> None:
        self.holder = holder
        who = f"pid {holder['pid']} ({holder['purpose']})" if holder else "unknown holder (shared holds, or none recorded)"
        super().__init__(f"GPU lease is busy: held by {who}")


class GpuUnavailable(Exception):
    """The Ollama model stayed loaded after the unload timeout, so the GPU cannot be handed over."""


def holder_path(lease_path: Path) -> Path:
    return lease_path.with_name(lease_path.name + ".holder")


def read_holder(lease_path: Path) -> dict[str, Any] | None:
    """The recorded exclusive holder, or None if there is none or the file is unreadable."""
    try:
        data = json.loads(holder_path(lease_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def status(lease_path: Path) -> dict[str, Any]:
    """Probe the lease with a non-blocking exclusive lock, released at once.

    Returns `{"lease_path", "state": "free"|"busy", "holder": dict|None}`. The holder is reported only
    while the lock is held, so a file left behind by a crash never shows as live.
    """
    lease_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lease_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"lease_path": str(lease_path), "state": "busy", "holder": read_holder(lease_path)}
        fcntl.flock(fd, fcntl.LOCK_UN)
        return {"lease_path": str(lease_path), "state": "free", "holder": None}
    finally:
        os.close(fd)


def _gpu_memory_used_mib() -> int | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


class FileGpuLease(GpuLease):
    """flock-based lease. `hold` (the worker's call) is an exclusive hold that waits forever."""

    def __init__(self, settings: Settings, should_stop: Callable[[], bool] | None = None) -> None:
        self.settings = settings
        self.path = settings.gpu.lease_path
        self.should_stop = should_stop

    # -- public API -------------------------------------------------------------------------------

    @contextmanager
    def hold(self, job_id: str, stage_name: str) -> Iterator[None]:
        with self.exclusive(f"{job_id}:{stage_name}", None):
            yield

    @contextmanager
    def exclusive(self, purpose: str, timeout_s: float | None) -> Iterator[None]:
        """Exclusive hold: waits for every other holder, unloads the Ollama model, writes holder info.

        Raises GpuBusy on timeout, GpuUnavailable if the model will not unload, WorkerStopping if
        `should_stop` turns true while waiting.
        """
        fd = self._acquire(fcntl.LOCK_EX, purpose, timeout_s)
        try:
            self._write_holder("exclusive", purpose)
            before = _gpu_memory_used_mib()
            log.info("gpu lease exclusive acquired: %s (memory.used before: %s MiB)", purpose, before)
            self._unload_ollama()
            try:
                yield
            finally:
                log.info("gpu lease exclusive released: %s (memory.used after: %s MiB)", purpose, _gpu_memory_used_mib())
        finally:
            self._clear_holder()
            os.close(fd)

    @contextmanager
    def shared(self, purpose: str, timeout_s: float | None) -> Iterator[None]:
        """Shared hold for Q&A calls: many at once, none alongside an exclusive hold. Raises GpuBusy on timeout."""
        fd = self._acquire(fcntl.LOCK_SH, purpose, timeout_s)
        try:
            log.info("gpu lease shared acquired: %s", purpose)
            yield
        finally:
            log.info("gpu lease shared released: %s", purpose)
            os.close(fd)

    # -- internals --------------------------------------------------------------------------------

    def _acquire(self, mode: int, purpose: str, timeout_s: float | None) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        interval = self.settings.gpu.lock_retry_interval_s
        try:
            while True:
                try:
                    fcntl.flock(fd, mode | fcntl.LOCK_NB)
                    return fd
                except BlockingIOError:
                    pass
                if self.should_stop is not None and self.should_stop():
                    raise WorkerStopping()
                if deadline is not None and time.monotonic() >= deadline:
                    raise GpuBusy(read_holder(self.path), purpose)
                time.sleep(interval)
        except BaseException:
            os.close(fd)
            raise

    def _write_holder(self, mode: str, purpose: str) -> None:
        info = {
            "pid": os.getpid(),
            "mode": mode,
            "purpose": purpose,
            "acquired_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        target = holder_path(self.path)
        tmp = target.with_name(target.name + f".{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(info), encoding="utf-8")
            os.replace(tmp, target)
        except OSError as exc:
            log.warning("could not write gpu holder info: %s", exc)

    def _clear_holder(self) -> None:
        holder_path(self.path).unlink(missing_ok=True)

    def _unload_ollama(self) -> None:
        gpu = self.settings.gpu
        try:
            gone = ollama_client.unload(
                self.settings.ollama,
                poll_interval_s=gpu.ollama_poll_interval_s,
                timeout_s=gpu.ollama_unload_timeout_s,
            )
        except httpx.HTTPError as exc:
            log.warning("ollama unreachable or refused unload, continuing: %s", exc)
            return
        if not gone:
            raise GpuUnavailable(
                f"Ollama model {self.settings.ollama.model!r} is still loaded {gpu.ollama_unload_timeout_s:g}s "
                f"after an unload request; refusing to start a GPU stage"
            )
