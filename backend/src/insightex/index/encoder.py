"""Run the window encoder in a child process per job (ADR-0044).

Same contract as `insightex.asr.transcriber`: the child gets PR_SET_PDEATHSIG, so a worker killed with SIGKILL
takes it (and its VRAM) along, it does not inherit the worker's descriptors (so it never holds the GPU lease's
flock), and the process exit is what returns the VRAM. Tests replace `insightex.index.stage.make_encoder`.
"""

from __future__ import annotations

import json
import logging
import os
import selectors
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from insightex.asr.gpu import GpuQueryError, query_vram
from insightex.asr.transcriber import _die_with_parent, _tail
from insightex.ingest.errors import ErrorCode, IngestError

log = logging.getLogger(__name__)


class IndexStageError(IngestError):
    """An index-stage failure: `code` and a user-facing `message`; `details` goes to the stage error and the log only."""

    def __init__(self, code: ErrorCode | str, message: str | None = None, details: str = "") -> None:
        super().__init__(code, message)
        self.details = details


@dataclass(frozen=True)
class EncodeRequest:
    texts_path: Path  # JSON list of strings
    out_path: Path  # .npy written by the child
    model_repo: str
    model_revision: str
    device: str
    device_index: int
    dtype: str
    max_seq_length: int
    batch_size: int
    timeout_s: float
    log_path: Path
    vram_baseline_mib: int | None = None


@dataclass
class EncodeResult:
    load_s: float
    encode_s: float
    count: int
    dim: int
    n_truncated: int
    peak_allocated_mib: float | None
    peak_vram_mib: int | None  # nvidia-smi peak minus the reading before the child started


class Encoder(Protocol):
    def encode(self, request: EncodeRequest, tick: Callable[[], None]) -> EncodeResult:
        """Encode the texts into `request.out_path`. Calls `tick` at least once a second (it may raise JobCancelled
        or WorkerStopping, which must propagate). Raises IndexStageError on failure."""


class SubprocessEncoder:
    def __init__(self, *, kill_grace_s: float, vram_poll_interval_s: float, command: list[str] | None = None,
                 vram_used: Callable[[], int | None] | None = None) -> None:
        self.kill_grace_s = kill_grace_s
        self.vram_poll_interval_s = vram_poll_interval_s
        self.command = command or [sys.executable, "-m", "insightex.index.child"]
        self.vram_used = vram_used or self._nvidia_smi_used

    @staticmethod
    def _nvidia_smi_used() -> int | None:
        try:
            return query_vram().used_mib
        except GpuQueryError:
            return None

    def encode(self, request: EncodeRequest, tick: Callable[[], None]) -> EncodeResult:
        payload = json.dumps({
            "texts_path": str(request.texts_path), "out_path": str(request.out_path), "model_repo": request.model_repo,
            "model_revision": request.model_revision, "device": request.device, "device_index": request.device_index,
            "dtype": request.dtype, "max_seq_length": request.max_seq_length, "batch_size": request.batch_size,
        }).encode("utf-8")
        request.log_path.parent.mkdir(parents=True, exist_ok=True)
        with request.log_path.open("ab") as errf:
            proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errf,
                close_fds=True, preexec_fn=_die_with_parent,  # noqa: PLW1509 - the worker is single-threaded
            )
        log.info("index subprocess started (pid %d, timeout %.0fs)", proc.pid, request.timeout_s)
        state: dict[str, Any] = {"ready": None, "done": None, "error": None}
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
                        raise IndexStageError(ErrorCode.ENCODE_TIMEOUT, details=f"no result after {request.timeout_s:.0f} s; subprocess killed")
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
                            event = json.loads(line)
                            kind = event.pop("type", None)
                            if kind in state:
                                state[kind] = event
            try:
                proc.wait(timeout=self.kill_grace_s)
            except subprocess.TimeoutExpired:
                raise IndexStageError(ErrorCode.ENCODE_CRASHED, details="the subprocess closed its output but did not exit") from None
        except BaseException:
            self._stop(proc)
            raise
        finally:
            proc.stdout.close()
        return self._result(proc.returncode, state, peak, request)

    def _result(self, returncode: int, state, peak, request: EncodeRequest) -> EncodeResult:
        error, done, ready = state["error"], state["done"], state["ready"]
        tail = _tail(request.log_path)
        if error is not None:
            code = error.get("code")
            if code not in ErrorCode.__members__:
                code = ErrorCode.ENCODE_CRASHED
            raise IndexStageError(code, details=f"{error.get('detail', '')}\nexit code {returncode}\nstderr tail:\n{tail}")
        if returncode != 0 or done is None:
            code = ErrorCode.GPU_OUT_OF_MEMORY if "out of memory" in tail.lower() else ErrorCode.ENCODE_CRASHED
            raise IndexStageError(code, details=f"exit code {returncode}, no result\nstderr tail:\n{tail}")
        baseline = request.vram_baseline_mib
        return EncodeResult(
            load_s=float((ready or {}).get("load_s", 0.0)), encode_s=float(done["encode_s"]), count=int(done["count"]),
            dim=int(done["dim"]), n_truncated=int(done["n_truncated"]), peak_allocated_mib=done.get("peak_allocated_mib"),
            peak_vram_mib=(peak - baseline) if peak is not None and baseline is not None else None,
        )

    def _stop(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=self.kill_grace_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log.info("index subprocess stopped (pid %d, exit %s)", proc.pid, proc.returncode)
