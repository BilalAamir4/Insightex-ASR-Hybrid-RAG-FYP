"""The `dummy` job kind: two stages (CPU, then GPU) that only sleep. Used to exercise the engine and by tests.

Payload fields, all optional: `cpu_seconds` (5), `gpu_seconds` (20), `step_seconds` (0.25, progress
interval), `label` (changes both stage keys).
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

from insightex.jobs.stages import KeyContext, Stage, StageContext, register_pipeline


def _sleep_with_progress(ctx: StageContext, seconds: float) -> None:
    step = float(ctx.payload.get("step_seconds", 0.25))
    steps = max(1, math.ceil(seconds / step))
    for i in range(steps):
        time.sleep(min(step, seconds))
        ctx.progress((i + 1) / steps, f"{i + 1}/{steps}")


class DummyCpu(Stage):
    name = "dummy_cpu"
    version = "1"
    needs_gpu = False
    outputs = ("cpu.txt",)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {"label": ctx.payload.get("label", "")}

    def run(self, ctx: StageContext) -> None:
        _sleep_with_progress(ctx, float(ctx.payload.get("cpu_seconds", 5)))
        body = {"payload": ctx.payload, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        (ctx.staging_dir / "cpu.txt").write_text(json.dumps(body, sort_keys=True) + "\n", encoding="utf-8")


class DummyGpu(Stage):
    name = "dummy_gpu"
    version = "1"
    needs_gpu = True
    outputs = ("gpu.txt",)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {"label": ctx.payload.get("label", "")}

    def run(self, ctx: StageContext) -> None:
        cpu_text = (ctx.upstream["dummy_cpu"] / "cpu.txt").read_text(encoding="utf-8")
        _sleep_with_progress(ctx, float(ctx.payload.get("gpu_seconds", 20)))
        (ctx.staging_dir / "gpu.txt").write_text(f"gpu stage saw: {cpu_text}", encoding="utf-8")


def _source_for(payload: dict[str, Any]) -> tuple[str, str]:
    return "dummy", str(payload.get("label", ""))


register_pipeline("dummy", [DummyCpu(), DummyGpu()], source_for=_source_for)
