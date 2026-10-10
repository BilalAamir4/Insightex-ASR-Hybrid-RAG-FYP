"""The `asr` stage: normalised audio.wav -> transcript.json + transcript.vtt with faster-whisper (ADR-0042).

Third stage of `ingest_link` and `ingest_file`. The lecture's language comes from the job payload
(`payload["language"]`, an id from the language config, ADR-0040); every other Whisper option comes from
`asr.transcribe` and is the same for every language. Whisper runs in a child process per job while the
worker holds the GPU lease, so its VRAM is released when the stage ends.
"""

from __future__ import annotations

import json
import logging
import time
import wave
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from insightex.asr import transcript as tr
from insightex.asr.gpu import GpuQueryError, Vram, query_vram
from insightex.asr.languages import Language, LanguageConfigError, languages_for
from insightex.asr.transcriber import AsrError, SubprocessTranscriber, TranscribeRequest, Transcriber
from insightex.core.config import Settings
from insightex.ingest.errors import ErrorCode
from insightex.jobs.stages import KeyContext, Stage, StageContext
from insightex.sources.identity import sha256_file

log = logging.getLogger(__name__)

AUDIO_NAME = "audio.wav"
MISSING_LANGUAGE_MESSAGE = (
    "This lecture was added before language selection existed. Add it again and choose the lecture's language."
)


def make_transcriber(settings: Settings) -> Transcriber:
    """The production transcriber. Tests monkeypatch this name to inject a fake."""
    a = settings.asr
    return SubprocessTranscriber(
        kill_grace_s=a.kill_grace_s, vram_poll_interval_s=a.vram_poll_interval_s,
        vram_used=lambda: _used_or_none(a.device_index),
    )


def gpu_vram(device_index: int) -> Vram:
    """Free/used VRAM for the pre-flight. Tests monkeypatch this name."""
    return query_vram(device_index)


def _used_or_none(device_index: int) -> int | None:
    try:
        return gpu_vram(device_index).used_mib
    except GpuQueryError:
        return None


def library_versions() -> dict[str, str]:
    """Installed faster-whisper and ctranslate2 versions, read from package metadata (no heavy import)."""
    out = {}
    for dist, key in (("faster-whisper", "faster_whisper"), ("ctranslate2", "ctranslate2")):
        try:
            out[key] = version(dist)
        except PackageNotFoundError:
            out[key] = "not installed"
    return out


def transcribe_params(settings: Settings) -> dict[str, Any]:
    """The complete transcribe() keyword arguments except `language`, JSON-safe ("inf" for infinity)."""
    return tr.json_safe(settings.asr.transcribe.model_dump())


def resolve_language(settings: Settings, payload: dict[str, Any]) -> Language:
    """The job's language entry. Raises AsrError(MISSING_LANGUAGE | UNKNOWN_LANGUAGE)."""
    language_id = payload.get("language")
    if not isinstance(language_id, str) or not language_id:
        raise AsrError(ErrorCode.MISSING_LANGUAGE, MISSING_LANGUAGE_MESSAGE, details="the job payload has no language")
    try:
        entry = languages_for(settings).get(language_id)
    except LanguageConfigError as exc:
        raise AsrError(ErrorCode.UNKNOWN_LANGUAGE, details=str(exc)) from exc
    if entry is None:
        raise AsrError(ErrorCode.UNKNOWN_LANGUAGE, details=f"language id {language_id!r} is not in the language config")
    return entry


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class AsrStage(Stage):
    name = "asr"
    version = "1"
    needs_gpu = True
    outputs = (tr.TRANSCRIPT_JSON, tr.TRANSCRIPT_VTT)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        """Everything that changes the transcript. The tier is not in it: promoting a language reprocesses nothing."""
        lang = resolve_language(ctx.settings, ctx.payload)
        a = ctx.settings.asr
        return {
            "language_id": lang.id,
            "whisper_language": lang.whisper_language,
            "model": a.model,
            "model_repo": a.model_repo,
            "model_revision": a.model_revision,
            "device": a.device,
            "compute_type": a.compute_type,
            "params": transcribe_params(ctx.settings),
            "warn_compression_ratio": a.warn_compression_ratio,
            "libraries": library_versions(),
            "schema_version": tr.SCHEMA_VERSION,
        }

    def run(self, ctx: StageContext) -> None:
        a = ctx.settings.asr
        lang = resolve_language(ctx.settings, ctx.payload)
        audio = ctx.upstream["normalise"] / AUDIO_NAME
        duration = wav_duration(audio)

        try:
            vram = gpu_vram(a.device_index)
        except GpuQueryError as exc:
            raise AsrError(ErrorCode.GPU_NOT_AVAILABLE, details=str(exc)) from exc
        if vram.free_mib < a.min_free_vram_mib:
            raise AsrError(
                ErrorCode.INSUFFICIENT_VRAM,
                f"The graphics card has {vram.free_mib} MiB of free memory, but transcription needs "
                f"{a.min_free_vram_mib} MiB. Close other programs that use the graphics card, then retry the job.",
                details=f"free {vram.free_mib} MiB, used {vram.used_mib} MiB, required {a.min_free_vram_mib} MiB",
            )
        log.info("asr pre-flight: %d MiB free (need %d), language %s -> %s", vram.free_mib, a.min_free_vram_mib,
                 lang.id, lang.whisper_language)

        throttle = tr.ProgressThrottle(a.progress_min_interval_s, a.progress_min_step)
        ctx.progress(0.0, "Loading the speech recognition model")
        throttle.start(time.monotonic())

        def on_segment(seg: dict[str, Any]) -> None:
            fraction = min(1.0, max(0.0, float(seg["end"]) / duration)) if duration > 0 else 0.0
            if throttle.offer(fraction, time.monotonic()):
                ctx.progress(fraction, f"Transcribed {_clock(float(seg['end']))} of {_clock(duration)}")

        def tick() -> None:  # cancel/stop checks between updates; the value is unchanged, so no new event is sent
            ctx.progress(throttle.last_value, None)

        params = transcribe_params(ctx.settings)
        request = TranscribeRequest(
            audio=audio, language=lang.whisper_language, params=params, model_repo=a.model_repo,
            model_revision=a.model_revision, device=a.device, device_index=a.device_index,
            compute_type=a.compute_type, cpu_threads=a.cpu_threads, num_workers=a.num_workers,
            timeout_s=max(a.timeout_min_s, a.timeout_factor * duration),
            log_path=ctx.settings.paths.logs_dir / "asr" / f"{ctx.job_id}.log",
            vram_baseline_mib=vram.used_mib,
        )
        result = make_transcriber(ctx.settings).transcribe(request, on_segment, tick)

        segments = [tr.clean_segment(s) for s in result.segments]
        if duration > a.empty_min_duration_s and tr.is_empty(segments):
            raise AsrError(ErrorCode.EMPTY_TRANSCRIPT,
                           details=f"{len(segments)} segments with no text for {duration:.1f} s of audio")

        snapshot = Path(result.snapshot_path) if result.snapshot_path else None
        revision = snapshot.name if snapshot is not None and snapshot.parent.name == "snapshots" else a.model_revision
        workspace_dir = ctx.upstream["normalise"].parents[2]
        doc = tr.build_transcript(
            stage_version=self.version,
            language={"id": lang.id, "label": lang.label, "whisper_language": lang.whisper_language,
                      "tier_at_processing": lang.tier},
            model={"name": a.model, "repo": a.model_repo, "revision": revision, "device": a.device,
                   "compute_type": a.compute_type},
            params={"language": lang.whisper_language, **params},
            libraries=library_versions(),
            audio={"path": audio.relative_to(workspace_dir).as_posix(), "duration_s": round(duration, 3),
                   "sha256": sha256_file(audio, ctx.settings.sources.hash_chunk_bytes)},
            segments=segments,
            wall_time_s=result.transcribe_s,
            peak_vram_mib=result.peak_vram_mib,
            warn_compression_ratio=a.warn_compression_ratio,
        )
        tr.write_atomic(ctx.staging_dir / tr.TRANSCRIPT_JSON, tr.dumps(doc))
        tr.write_atomic(ctx.staging_dir / tr.TRANSCRIPT_VTT, tr.to_vtt(segments))
        for w in doc["warnings"]:
            log.warning("asr warning %s: %s", w["code"], w["message"])
        log.info("asr done: %d segments, rtf %s, peak %s MiB", len(segments), doc["stats"]["rtf"], result.peak_vram_mib)

    def manifest_extra(self, stage_dir: Path) -> dict[str, Any]:
        """Language and warnings of the published transcript, so the library and job status can show them."""
        doc = json.loads((stage_dir / tr.TRANSCRIPT_JSON).read_text(encoding="utf-8"))
        return {
            "language": {"id": doc["language"]["id"], "whisper_language": doc["language"]["whisper_language"]},
            "warnings": doc["warnings"],
        }
