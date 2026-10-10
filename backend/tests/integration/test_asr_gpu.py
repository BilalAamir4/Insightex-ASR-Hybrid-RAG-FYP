"""Real large-v3 on the GPU: the 30 s Day 4 clip through the asr stage with language "hindi".

Deselected by default; run alone with `pytest -m gpu` (needs CUDA, the offline model cache, about 5.5 GB of free
VRAM and no Ollama model loaded). Skips if the clip is not on this machine.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from insightex.asr.stage import AsrStage
from insightex.core.config import load_settings
from insightex.jobs import db, store
from insightex.jobs.runner import run_job
from insightex.jobs.stages import KeyContext, Stage, StageContext, register_pipeline
from insightex.jobs.workspace import Workspaces

pytestmark = pytest.mark.gpu
CLIP = Path.home() / "insightex-data" / "eval" / "day04_batch_vs_online" / "eval" / "clip_30s.wav"


class ClipAudio(Stage):
    name = "normalise"
    version = "1"
    outputs = ("audio.wav",)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {}

    def run(self, ctx: StageContext) -> None:
        shutil.copyfile(CLIP, ctx.staging_dir / "audio.wav")


@pytest.mark.skipif(not CLIP.is_file(), reason=f"{CLIP} not found")
def test_clip_transcribes_for_real_with_hindi():
    register_pipeline("asr_gpu_test", [ClipAudio(), AsrStage()], replace=True)
    settings = load_settings()
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    job_id = store.enqueue(conn, "asr_gpu_test", {"language": "hindi"}, "gpu-test")
    run_job(conn, store.claim_next(conn, os.getpid()), settings, Workspaces(settings.jobs.workspaces_dir))
    job = store.get_job(conn, job_id)
    assert job.status == "succeeded", job.error
    out = Workspaces(settings.jobs.workspaces_dir).stage_output_dir("gpu-test", "asr")
    doc = json.loads((out / "transcript.json").read_text(encoding="utf-8"))
    assert doc["language"]["whisper_language"] == "ur" and doc["language"]["tier_at_processing"] == "tested"
    assert doc["model"]["revision"] == settings.asr.model_revision
    assert doc["segments"] and any(s["text"].strip() for s in doc["segments"])
    assert all(0 <= s["start"] <= s["end"] <= doc["audio"]["duration_s"] + 0.01 for s in doc["segments"])
    assert doc["stats"]["peak_vram_mib"] is not None and doc["stats"]["rtf"] > 0
    conn.close()
