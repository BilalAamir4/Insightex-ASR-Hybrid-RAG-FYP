"""Run Whisper in a child process per job (ADR-0042).

`SubprocessTranscriber` starts `python -m insightex.asr.child`, feeds it one request, reads its NDJSON events,
enforces the timeout and stops the child on cancel, worker shutdown or any error. The child gets
PR_SET_PDEATHSIG, so a worker killed with SIGKILL takes its child (and the child's VRAM) with it, and it does
not inherit the worker's file descriptors, so it never holds the GPU lease's flock.

Tests replace the transcriber (`insightex.asr.stage.make_transcriber`) with a fake; no GPU is needed.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from insightex.asr.gpu import GpuQueryError, query_vram
from insightex.ingest.errors import ErrorCode, IngestError

log = logging.getLogger(__name__)

_PR_SET_PDEATHSIG = 1
_STDERR_TAIL_BYTES = 4000


class AsrError(IngestError):
    """An ASR failure: `code` and a user-facing `message`; `details` goes to the stage error and the log only."""

    def __init__(self, code: ErrorCode | str, message: str | None = None, details: str = "") -> None:
        super().__init__(code, message)
        self.details = details


@dataclass(frozen=True)
class TranscribeRequest:
    audio: Path
    language: str  # the Whisper code
    params: dict[str, Any]  # JSON-safe transcribe() keyword arguments, without `language`
    model_repo: str
    model_revision: str
    device: str
    device_index: int
    compute_type: str
    cpu_threads: int
    num_workers: int
    timeout_s: float
    log_path: Path
    vram_baseline_mib: int | None = None  # memory.used before the child starts, for the peak statistic


@dataclass
class TranscribeResult:
    segments: list[dict[str, Any]]
    snapshot_path: str | None
    load_s: float | None
    transcribe_s: float
    peak_vram_mib: int | None
    extra: dict[str, Any] = field(default_factory=dict)


class Transcriber(Protocol):
    def transcribe(
        self, request: TranscribeRequest, on_segment: Callable[[dict[str, Any]], None], tick: Callable[[], None]
    ) -> TranscribeResult:
        """Transcribe `request.audio`. Calls `on_segment` per segment and `tick` at least once a second
        (it may raise JobCancelled or WorkerStopping, which must propagate). Raises AsrError on failure."""


def _die_with_parent() -> None:  # runs in the child between fork and exec
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)
    except OSError:
        pass


def _tail(path: Path) -> str:
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - _STDERR_TAIL_BYTES))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


class SubprocessTranscriber:
    """Starts one child per call. `command` and `vram_used` are replaceable for tests."""

    def __init__(
        self,
        *,
        kill_grace_s: float,
        vram_poll_interval_s: float,
        command: list[str] | None = None,
        vram_used: Callable[[], int | None] | None = None,
    ) -> None:
        self.kill_grace_s = kill_grace_s
        self.vram_poll_interval_s = vram_poll_interval_s
        self.command = command or [sys.executable, "-m", "insightex.asr.child"]
        self.vram_used = vram_used or self._nvidia_smi_used

    @staticmethod
    def _nvidia_smi_used() -> int | None:
        try:
            return query_vram().used_mib
        except GpuQueryError:
            return None

    def transcribe(self, request, on_segment, tick) -> TranscribeResult:
        payload = json.dumps({
            "audio": str(request.audio), "language": request.language, "params": request.params,
            "model_repo": request.model_repo, "model_revision": request.model_revision, "device": request.device,
            "device_index": request.device_index, "compute_type": request.compute_type,
            "cpu_threads": request.cpu_threads, "num_workers": request.num_workers,
        }, allow_nan=False).encode("utf-8")
        request.log_path.parent.mkdir(parents=True, exist_ok=True)
        with request.log_path.open("ab") as errf:
            proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errf,
                close_fds=True, preexec_fn=_die_with_parent,  # noqa: PLW1509 - the worker is single-threaded
            )
        log.info("asr subprocess started (pid %d, timeout %.0fs)", proc.pid, request.timeout_s)
        state: dict[str, Any] = {"ready": None, "done": None, "error": None}
        segments: list[dict[str, Any]] = []
        peak: int | None = None
        try:
            try:
                proc.stdin.write(payload)
                proc.stdin.close()
            except BrokenPipeError:
                pass  # the child died at once; its exit code says why
            deadline = time.monotonic() + request.timeout_s
            next_vram = 0.0
            buf = b""
            fd = proc.stdout.fileno()
            with selectors.DefaultSelector() as sel:
                sel.register(fd, selectors.EVENT_READ)
                eof = False
                while not eof:
                    now = time.monotonic()
                    if now >= deadline:
                        raise AsrError(ErrorCode.TRANSCRIBE_TIMEOUT,
                                       details=f"no result after {request.timeout_s:.0f} s; subprocess killed")
                    if now >= next_vram:
                        next_vram = now + self.vram_poll_interval_s
                        used = self.vram_used()
                        if used is not None:
                            peak = used if peak is None else max(peak, used)
                    tick()
                    if not sel.select(timeout=min(1.0, max(0.01, deadline - now))):
                        continue
                    chunk = os.read(fd, 1 << 16)
                    if not chunk:
                        eof = True
                    buf += chunk
                    *lines, buf = buf.split(b"\n")
                    for line in lines:
                        if line.strip():
                            self._event(json.loads(line), state, segments, on_segment)
            try:
                proc.wait(timeout=self.kill_grace_s)
            except subprocess.TimeoutExpired:
                raise AsrError(ErrorCode.TRANSCRIBE_CRASHED, details="the subprocess closed its output but did not exit") from None
        except BaseException:
            self._stop(proc)
            raise
        finally:
            proc.stdout.close()
        return self._result(proc.returncode, state, segments, peak, request)

    @staticmethod
    def _event(event: dict[str, Any], state, segments, on_segment) -> None:
        kind = event.pop("type", None)
        if kind == "segment":
            segments.append(event)
            on_segment(event)
        elif kind in ("ready", "done", "error"):
            state[kind] = event

    def _result(self, returncode: int, state, segments, peak, request) -> TranscribeResult:
        error, done, ready = state["error"], state["done"], state["ready"]
        tail = _tail(request.log_path)
        if error is not None:
            code = error.get("code")
            if code not in ErrorCode.__members__:
                code = ErrorCode.TRANSCRIBE_CRASHED
            raise AsrError(code, details=f"{error.get('detail', '')}\nexit code {returncode}\nstderr tail:\n{tail}")
        if returncode != 0 or done is None:
            code = ErrorCode.GPU_OUT_OF_MEMORY if "out of memory" in tail.lower() else ErrorCode.TRANSCRIBE_CRASHED
            raise AsrError(code, details=f"exit code {returncode}, no result\nstderr tail:\n{tail}")
        baseline = request.vram_baseline_mib
        return TranscribeResult(
            segments=segments,
            snapshot_path=(ready or {}).get("snapshot_path"),
            load_s=(ready or {}).get("load_s"),
            transcribe_s=float(done["transcribe_s"]),
            peak_vram_mib=(peak - baseline) if peak is not None and baseline is not None else None,
            extra={"detected_language": done.get("detected_language")},
        )

    def _stop(self, proc: subprocess.Popen) -> None:
        """SIGTERM, then SIGKILL after the grace period. Always reaps the child."""
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=self.kill_grace_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log.info("asr subprocess stopped (pid %d, exit %s)", proc.pid, proc.returncode)
