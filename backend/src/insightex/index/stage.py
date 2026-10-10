"""The `index` stage: transcript.json -> windows.json + dense.faiss + index.json (ADR-0044).

Fourth stage of `ingest_link` and `ingest_file`. Windows come from `insightex.windows.build`; the window texts are
encoded by BGE-M3 on the GPU in a child process while the worker holds the GPU lease, so the VRAM is back when the
stage ends. Query-time encoding is not here: it runs on the CPU in the API process (`insightex.retrieval`).
"""

from __future__ import annotations

import json
import logging
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from insightex.asr import transcript as tr
from insightex.asr.gpu import GpuQueryError, Vram, query_vram
from insightex.core.config import Settings
from insightex.index import store
from insightex.index.encoder import Encoder, EncodeRequest, IndexStageError, SubprocessEncoder
from insightex.ingest.errors import ErrorCode
from insightex.jobs.stages import KeyContext, Stage, StageContext
from insightex.windows.build import SCHEMA_VERSION as WINDOWS_SCHEMA_VERSION
from insightex.windows.build import build_snapped_windows, build_windows

log = logging.getLogger(__name__)


def make_encoder(settings: Settings) -> Encoder:
    """The production encoder. Tests monkeypatch this name to inject a fake."""
    i = settings.index
    return SubprocessEncoder(kill_grace_s=i.kill_grace_s, vram_poll_interval_s=i.vram_poll_interval_s,
                             vram_used=lambda: _used_or_none(i.device_index))


def gpu_vram(device_index: int) -> Vram:
    """Free/used VRAM for the pre-flight. Tests monkeypatch this name."""
    return query_vram(device_index)


def _used_or_none(device_index: int) -> int | None:
    try:
        return gpu_vram(device_index).used_mib
    except GpuQueryError:
        return None


def library_versions() -> dict[str, str]:
    """Installed versions of the packages that decide the vectors, read from package metadata (no heavy import)."""
    out = {}
    for dist in ("sentence-transformers", "transformers", "torch", "faiss-cpu", "faiss-gpu", "numpy"):
        try:
            out[dist] = version(dist)
        except PackageNotFoundError:
            continue
    return out


class IndexStage(Stage):
    name = "index"
    version = "1"
    needs_gpu = True
    outputs = (store.WINDOWS_JSON, store.DENSE_FAISS, store.INDEX_JSON)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        i = ctx.settings.index
        return {
            "model_repo": i.model_repo, "model_revision": i.model_revision, "device": i.device, "dtype": i.dtype,
            "max_seq_length": i.max_seq_length, "batch_size": i.batch_size, "window_s": i.window_s,
            "stride_s": i.stride_s, "snap_to_segments": i.snap_to_segments, "libraries": library_versions(), "windows_schema_version": WINDOWS_SCHEMA_VERSION,
        }

    def run(self, ctx: StageContext) -> None:
        import numpy as np

        i = ctx.settings.index
        doc = json.loads((ctx.upstream["asr"] / tr.TRANSCRIPT_JSON).read_text(encoding="utf-8"))
        if i.snap_to_segments:
            windows = build_snapped_windows(doc["segments"], window_s=i.window_s, stride_s=i.stride_s)
        else:
            windows = build_windows(doc["segments"], window_s=i.window_s, stride_s=i.stride_s,
                                    duration_s=float(doc["audio"]["duration_s"]))
        if not windows:
            raise IndexStageError(ErrorCode.NO_WINDOWS, details=f"{len(doc['segments'])} segments, none with text")

        try:
            vram = gpu_vram(i.device_index)
        except GpuQueryError as exc:
            raise IndexStageError(ErrorCode.GPU_NOT_AVAILABLE, details=str(exc)) from exc
        if vram.free_mib < i.min_free_vram_mib:
            raise IndexStageError(
                ErrorCode.INSUFFICIENT_VRAM,
                f"The graphics card has {vram.free_mib} MiB of free memory, but preparing the lecture for search needs "
                f"{i.min_free_vram_mib} MiB. Close other programs that use the graphics card, then retry the job.",
                details=f"free {vram.free_mib} MiB, used {vram.used_mib} MiB, required {i.min_free_vram_mib} MiB",
            )
        log.info("index pre-flight: %d MiB free (need %d), %d windows", vram.free_mib, i.min_free_vram_mib, len(windows))

        work = ctx.staging_dir / "_work"
        work.mkdir()
        try:
            texts_path, vectors_path = work / "texts.json", work / "vectors.npy"
            texts_path.write_text(json.dumps([w.text for w in windows], ensure_ascii=False), encoding="utf-8")
            ctx.progress(0.0, f"Encoding {len(windows)} windows")
            request = EncodeRequest(
                texts_path=texts_path, out_path=vectors_path, model_repo=i.model_repo, model_revision=i.model_revision,
                device=i.device, device_index=i.device_index, dtype=i.dtype, max_seq_length=i.max_seq_length,
                batch_size=i.batch_size, timeout_s=i.timeout_min_s,
                log_path=ctx.settings.paths.logs_dir / "index" / f"{ctx.job_id}.log", vram_baseline_mib=vram.used_mib,
            )
            result = make_encoder(ctx.settings).encode(request, lambda: ctx.progress(0.0, None))
            vectors = np.load(vectors_path, allow_pickle=False)
        finally:
            shutil.rmtree(work, ignore_errors=True)

        meta = {
            "schema_version": WINDOWS_SCHEMA_VERSION, "stage_version": self.version,
            "model": {"repo": i.model_repo, "revision": i.model_revision, "dtype": i.dtype, "device": i.device,
                      "max_seq_length": i.max_seq_length, "dim": result.dim},
            "windows": {"window_s": i.window_s, "stride_s": i.stride_s, "snap_to_segments": i.snap_to_segments, "count": len(windows), "n_truncated": result.n_truncated},
            "transcript": {"language": doc["language"], "segments": len(doc["segments"]),
                           "audio_sha256": doc["audio"]["sha256"]},
            "libraries": library_versions(),
            "stats": {"load_s": result.load_s, "encode_s": result.encode_s, "peak_allocated_mib": result.peak_allocated_mib,
                      "peak_vram_mib": result.peak_vram_mib},
        }
        store.write_index(ctx.staging_dir, windows, vectors, meta)
        ctx.progress(1.0, "Search index ready")
        log.info("index done: %d windows, dim %d, encode %.2fs, peak %s MiB allocated, %d truncated", len(windows),
                 result.dim, result.encode_s, result.peak_allocated_mib, result.n_truncated)

    def manifest_extra(self, stage_dir: Path) -> dict[str, Any]:
        meta = json.loads((stage_dir / store.INDEX_JSON).read_text(encoding="utf-8"))
        return {"windows": meta["windows"]["count"], "model_revision": meta["model"]["revision"]}
