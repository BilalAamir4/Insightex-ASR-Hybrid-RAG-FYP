"""The index stage through the real runner, with a fake encoder and a fake GPU (no BGE-M3, no CUDA)."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from asr_fakes import FakeEncoder

from insightex.asr.gpu import GpuQueryError
from insightex.core.config import load_settings
from insightex.index import stage as index_stage
from insightex.index.encoder import IndexStageError
from insightex.index.stage import IndexStage
from insightex.index.store import load_index
from insightex.ingest.errors import ErrorCode
from insightex.jobs import db, store
from insightex.jobs.runner import run_job
from insightex.jobs.stages import KeyContext, Stage, StageContext, register_pipeline
from insightex.jobs.workspace import Workspaces

KIND = "index_test"
WS = "sha256-" + "b" * 32


class FakeAsr(Stage):
    name = "asr"
    version = "1"
    outputs = ("transcript.json",)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {"n": ctx.payload.get("n", 7)}

    def run(self, ctx: StageContext) -> None:
        n = ctx.payload.get("n", 7)
        segs = [{"id": i + 1, "start": i * 10.0, "end": i * 10.0 + 9.5, "text": f" segment {i}" if n else " "}
                for i in range(n)]
        doc = {"segments": segs, "language": {"id": "hindi"}, "audio": {"duration_s": n * 10.0, "sha256": "ab"}}
        (ctx.staging_dir / "transcript.json").write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture(autouse=True)
def pipeline():
    register_pipeline(KIND, [FakeAsr(), IndexStage()], replace=True)


@pytest.fixture
def env():
    settings = load_settings({"jobs": {"progress_min_interval_s": 0.0}})
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    yield settings, conn, Workspaces(settings.jobs.workspaces_dir)
    conn.close()


def run(env, payload, settings=None):
    base, conn, ws = env
    job_id = store.enqueue(conn, KIND, payload, WS)
    run_job(conn, store.claim_next(conn, os.getpid()), settings or base, ws)
    return store.get_job(conn, job_id)


def test_index_files_and_meta(env):
    job = run(env, {"n": 7})
    assert job.status == "succeeded", job.error
    directory = env[2].stage_output_dir(WS, "index")
    assert sorted(p.name for p in directory.iterdir()) == ["dense.faiss", "index.json", "windows.json"]  # no scratch left over
    index = load_index(directory)
    assert index.size == 3 and index.faiss_index.d == 8  # 70 s of audio -> windows 0-30, 30-60, 60-70
    assert [(w["start"], w["end"]) for w in index.windows] == [(0.0, 30.0), (30.0, 60.0), (60.0, 70.0)]
    assert index.meta["model"]["revision"] == env[0].index.model_revision and index.meta["windows"]["count"] == 3
    assert env[2].read_manifest(WS)["stages"]["index"]["windows"] == 3


def test_request_carries_the_configured_model_and_limits(env, fake_asr, monkeypatch):
    enc = FakeEncoder()
    monkeypatch.setattr(index_stage, "make_encoder", lambda settings: enc)
    run(env, {"n": 3})
    r = enc.calls[0]
    assert (r.model_repo, r.device, r.dtype, r.max_seq_length, r.batch_size) == ("BAAI/bge-m3", "cuda", "float16", 1024, 16)
    assert r.vram_baseline_mib == 1000


def test_second_run_is_cached_and_a_window_change_rekeys(env, monkeypatch):
    enc = FakeEncoder()
    monkeypatch.setattr(index_stage, "make_encoder", lambda settings: enc)
    run(env, {"n": 3})
    run(env, {"n": 3})
    assert len(enc.calls) == 1
    run(env, {"n": 3}, settings=load_settings({"jobs": {"progress_min_interval_s": 0.0}, "index": {"stride_s": 15}}))
    assert len(enc.calls) == 2


def test_no_text_fails_with_no_windows(env):
    job = run(env, {"n": 0})
    assert job.status == "failed" and "NO_WINDOWS" in job.error


def test_low_vram_and_missing_gpu_fail_before_the_encoder_starts(env, fake_asr, monkeypatch):
    enc = FakeEncoder()
    monkeypatch.setattr(index_stage, "make_encoder", lambda settings: enc)
    fake_asr[1].free_mib = 1000
    job = run(env, {"n": 3})
    assert job.status == "failed" and "INSUFFICIENT_VRAM" in job.error and not enc.calls

    def broken(device_index=0):
        raise GpuQueryError("no nvidia-smi")

    monkeypatch.setattr(index_stage, "gpu_vram", broken)
    job = run(env, {"n": 4})
    assert job.status == "failed" and "GPU_NOT_AVAILABLE" in job.error


def test_encoder_error_fails_the_job(env, monkeypatch):
    enc = FakeEncoder(error=IndexStageError(ErrorCode.ENCODE_CRASHED, details="boom"))
    monkeypatch.setattr(index_stage, "make_encoder", lambda settings: enc)
    job = run(env, {"n": 3})
    assert job.status == "failed" and "ENCODE_CRASHED" in job.error
