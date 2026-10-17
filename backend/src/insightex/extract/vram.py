"""VRAM peak sampling for M7 runs and measurements (ADR-0048 section 8: every arm records its VRAM peak).

nvidia-smi `memory.used` is the whole GPU, including the Windows desktop, so the report keeps the baseline (sampled
before the model is loaded) next to the peak and their difference.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from insightex.jobs.gpu_lease import gpu_memory_used_mib


class VramSampler:
    def __init__(self, interval_s: float, read: Callable[[], int | None] = gpu_memory_used_mib) -> None:
        self.interval_s, self.read = interval_s, read
        self.baseline_mib: int | None = None
        self.peak_mib: int | None = None
        self.samples = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        v = self.read()
        if v is not None:
            self.samples += 1
            self.peak_mib = v if self.peak_mib is None else max(self.peak_mib, v)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            self._sample()

    def start(self) -> None:
        self.baseline_mib = self.read()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="vram-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._sample()

    def report(self) -> dict[str, Any]:
        above = (self.peak_mib - self.baseline_mib) if None not in (self.peak_mib, self.baseline_mib) else None
        return {"baseline_mib": self.baseline_mib, "peak_mib": self.peak_mib, "peak_above_baseline_mib": above,
                "samples": self.samples, "interval_s": self.interval_s,
                "note": "nvidia-smi memory.used of the whole GPU (includes the Windows desktop)"}
