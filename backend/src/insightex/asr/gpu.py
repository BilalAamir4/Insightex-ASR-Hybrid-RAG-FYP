"""Free and used VRAM from nvidia-smi (no new dependencies). Used by the ASR pre-flight and the peak statistic."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


class GpuQueryError(RuntimeError):
    """nvidia-smi is missing, failed, or printed something unexpected."""


@dataclass(frozen=True)
class Vram:
    free_mib: int
    used_mib: int


def query_vram(device_index: int = 0, timeout_s: float = 10.0) -> Vram:
    """Free and used memory of one GPU, in MiB. Raises GpuQueryError."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        raise GpuQueryError("nvidia-smi was not found on PATH")
    try:
        out = subprocess.run(
            [exe, f"--id={device_index}", "--query-gpu=memory.free,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout_s, check=True,
        ).stdout
        free, used = (int(x.strip()) for x in out.strip().splitlines()[0].split(","))
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        raise GpuQueryError(f"nvidia-smi failed: {type(exc).__name__}: {exc}") from exc
    return Vram(free, used)
