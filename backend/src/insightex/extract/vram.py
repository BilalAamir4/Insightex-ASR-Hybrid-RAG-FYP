"""VRAM peak sampling for M7 runs and measurements (ADR-0048 section 8: every arm records its VRAM peak).

nvidia-smi `memory.used` is the whole GPU, including the Windows desktop, so the report keeps the baseline (sampled
before the model is loaded) next to the peak and their difference. `phase(name)` starts a named phase; the report
then also gives each phase's own peak (C2 arm B: translation and extraction, ADR-0048 section 8).
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
        self._phase: str | None = None
        self.phase_peaks: dict[str, int | None] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        v = self.read()
        with self._lock:
            if v is not None:
                self.samples += 1
                self.peak_mib = v if self.peak_mib is None else max(self.peak_mib, v)
                if self._phase is not None:
                    old = self.phase_peaks.get(self._phase)
                    self.phase_peaks[self._phase] = v if old is None else max(old, v)

    def phase(self, name: str) -> None:
        """Start phase `name` (samples taken from now on count towards it). One sample is taken at the boundary so
        the closing phase sees the current reading and the new one starts from it."""
        self._sample()
        with self._lock:
            self._phase = name
            self.phase_peaks.setdefault(name, None)
        self._sample()

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
        phases = {name: {"peak_mib": peak,
                         "peak_above_baseline_mib": (peak - self.baseline_mib)
                         if None not in (peak, self.baseline_mib) else None}
                  for name, peak in self.phase_peaks.items()}
        return {"baseline_mib": self.baseline_mib, "peak_mib": self.peak_mib, "peak_above_baseline_mib": above,
                "phases": phases, "samples": self.samples, "interval_s": self.interval_s,
                "note": "nvidia-smi memory.used of the whole GPU (includes the Windows desktop)"}
