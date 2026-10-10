"""The asr stage through the real runner, with a fake transcriber and a fake GPU (no Whisper, no CUDA).

A tiny two-stage pipeline stands in for ingest: `normalise` writes a silent audio.wav of `payload["duration"]` s.
"""

from __future__ import annotations

import hashlib
import json
import os
import wave
from contextlib import contextmanager
from typing import Any

import pytest
from asr_fakes import fake_segments

from insightex.api.models import job_out
from insightex.asr import stage as asr_stage
from insightex.asr.gpu import GpuQueryError
from insightex.asr.languages import languages_for
from insightex.asr.stage import AsrStage
from insightex.asr.transcriber import AsrError
from insightex.core.config import load_settings
from insightex.ingest.errors import ErrorCode
from insightex.jobs import db, store
from insightex.jobs.runner import run_job
from insightex.jobs.stages import GpuLease, KeyContext, Stage, StageContext, register_pipeline
from insightex.jobs.workspace import Workspaces

KIND = "asr_test"
WS = "sha256-" + "a" * 32


class FakeNormalise(Stage):
    name = "normalise"
    version = "1"
    outputs = ("audio.wav",)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {"duration": ctx.payload.get("duration", 20)}

    def run(self, ctx: StageContext) -> None:
        with wave.open(str(ctx.staging_dir / "audio.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\0\0" * int(16000 * ctx.payload.get("duration", 20)))


class RecordingLease(GpuLease):
    def __init__(self):
        self.held: list[str] = []

    @contextmanager
    def hold(self, job_id, stage_name):
        self.held.append(stage_name)
        yield


@pytest.fixture(autouse=True)
def pipeline():
    register_pipeline(KIND, [FakeNormalise(), AsrStage()], replace=True)


@pytest.fixture
def env():
    settings = load_settings({"jobs": {"progress_min_interval_s": 0.0}})
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    yield settings, conn, Workspaces(settings.jobs.workspaces_dir)
    conn.close()


def run(env, payload: dict[str, Any], lease: GpuLease | None = None, settings=None) -> store.Job:
    base, conn, ws = env
    job_id = store.enqueue(conn, KIND, payload, WS)
    claimed = store.claim_next(conn, os.getpid())
    run_job(conn, claimed, settings or base, ws, gpu_lease=lease)
    return store.get_job(conn, job_id)


def transcript(env) -> dict[str, Any]:
    directory = env[2].stage_output_dir(WS, "asr")
    return json.loads((directory / "transcript.json").read_text(encoding="utf-8"))


# -- success path -------------------------------------------------------------------------------------


def test_transcript_schema_and_field_types(env, fake_asr):
    job = run(env, {"language": "hindi", "duration": 25})
    assert job.status == "succeeded", job.error
    doc = transcript(env)
    assert doc["schema_version"] == 1 and doc["stage_version"] == AsrStage.version
    assert doc["language"] == {"id": "hindi", "label": "Hindi (including Hindi-English mixed)",
                               "whisper_language": "ur", "tier_at_processing": "tested"}
    assert doc["model"] == {"name": "large-v3", "repo": "Systran/faster-whisper-large-v3", "revision": "abc123",
                            "device": "cuda", "compute_type": "float16"}
    assert doc["params"]["language"] == "ur" and doc["params"]["beam_size"] == 5
    assert doc["params"]["temperature"] == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    assert doc["params"]["vad_parameters"]["max_speech_duration_s"] == "inf"
    assert set(doc["libraries"]) == {"faster_whisper", "ctranslate2"}
    audio = env[2].stage_output_dir(WS, "normalise") / "audio.wav"
    assert doc["audio"]["path"] == audio.relative_to(env[2].path(WS)).as_posix()
    assert doc["audio"]["duration_s"] == 25.0 and doc["audio"]["sha256"] == hashlib.sha256(audio.read_bytes()).hexdigest()
    assert doc["stats"] == {"segment_count": 3, "fallback_segment_count": 0, "high_compression_segment_count": 0,
                            "wall_time_s": 2.0, "rtf": 0.08, "peak_vram_mib": 4000}
    assert doc["warnings"] == []
    for s in doc["segments"]:
        assert isinstance(s["id"], int) and isinstance(s["start"], float) and isinstance(s["text"], str)
        assert all(isinstance(w["probability"], float) for w in s["words"])
    request = fake_asr[0].calls[0]
    assert request.language == "ur" and request.timeout_s == 600 and request.vram_baseline_mib == 1000
    assert "language" not in request.params


def test_vtt_written_next_to_json(env, fake_asr):
    run(env, {"language": "hindi", "duration": 25})
    vtt = (env[2].stage_output_dir(WS, "asr") / "transcript.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT") and vtt.count(" --> ") == 3


def test_text_passes_through_unchanged(env, fake_asr):
    text = " تو machine learning میں   batch learning کیا ہے؟ OK."
    fake_asr[0].segments = [{**fake_segments(10)[0], "text": text}]
    run(env, {"language": "hindi", "duration": 10})
    assert transcript(env)["segments"][0]["text"] == text


def test_untested_language_records_its_tier_and_code(env, fake_asr):
    run(env, {"language": "english", "duration": 10})
    doc = transcript(env)
    assert doc["language"]["tier_at_processing"] == "untested" and doc["language"]["whisper_language"] == "en"
    assert fake_asr[0].calls[0].language == "en"


def test_timeout_is_at_least_600_s_and_scales_with_duration(env, fake_asr):
    settings = load_settings({"jobs": {"progress_min_interval_s": 0.0}, "asr": {"timeout_min_s": 5}})
    run(env, {"language": "hindi", "duration": 12}, settings=settings)
    assert fake_asr[0].calls[0].timeout_s == 12.0


def test_manifest_records_language_and_warnings(env, fake_asr):
    fake_asr[0].segments = [{**s, "temperature": 0.4 if s["id"] == 2 else 0.0} for s in fake_segments(30)]
    run(env, {"language": "hindi", "duration": 30})
    entry = env[2].read_manifest(WS)["stages"]["asr"]
    assert entry["language"] == {"id": "hindi", "whisper_language": "ur"}
    assert [w["code"] for w in entry["warnings"]] == ["TEMPERATURE_FALLBACK"]


def test_warnings_for_fallback_and_high_compression_succeed_and_reach_the_job(env, fake_asr):
    segs = fake_segments(30)
    segs[0]["temperature"], segs[2]["compression_ratio"] = 0.2, 2.9
    fake_asr[0].segments = segs
    job = run(env, {"language": "hindi", "duration": 30})
    assert job.status == "succeeded"
    doc = transcript(env)
    assert {w["code"]: w["segment_ids"] for w in doc["warnings"]} == {"TEMPERATURE_FALLBACK": [1], "HIGH_COMPRESSION_RATIO": [3]}
    assert doc["stats"]["fallback_segment_count"] == 1 and doc["stats"]["high_compression_segment_count"] == 1
    out = job_out(job, env[2], languages_for(env[0]))
    assert [w["code"] for w in out.warnings] == ["TEMPERATURE_FALLBACK", "HIGH_COMPRESSION_RATIO"]
    assert out.language.model_dump() == {"id": "hindi", "label": "Hindi (including Hindi-English mixed)", "tier": "tested"}


# -- cache --------------------------------------------------------------------------------------------


def test_cache_hit_skips_the_lease_and_the_subprocess(env, fake_asr):
    first_lease, second_lease = RecordingLease(), RecordingLease()
    run(env, {"language": "hindi", "duration": 10}, first_lease)
    second = run(env, {"language": "hindi", "duration": 10}, second_lease)
    assert [s.status for s in second.stages] == ["cached", "cached"]
    assert first_lease.held == ["asr"] and second_lease.held == []
    assert len(fake_asr[0].calls) == 1 and fake_asr[1].queries == 1  # no pre-flight on the hit either


def test_a_different_language_reruns_and_replaces_the_transcript(env, fake_asr):
    run(env, {"language": "hindi", "duration": 10})
    second = run(env, {"language": "english", "duration": 10})
    assert [s.status for s in second.stages] == ["cached", "succeeded"]
    assert transcript(env)["language"]["id"] == "english"
    assert env[2].read_manifest(WS)["stages"]["asr"]["language"]["id"] == "english"
    assert len(list((env[2].path(WS) / "stages" / "asr").iterdir())) == 1  # one current transcript


def key(settings, payload=None, versions=None, monkeypatch=None) -> str:
    from insightex.jobs.stages import stage_key

    if versions is not None:
        monkeypatch.setattr(asr_stage, "library_versions", lambda: versions)
    ctx = KeyContext("j", payload or {"language": "hindi"}, WS, settings)
    stage = AsrStage()
    return stage_key(stage.name, stage.version, stage.config_fingerprint(ctx), "upstream")


def _changed(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 0.25
    if isinstance(value, str):
        return value + "x"
    if isinstance(value, list):
        return value[:1] if len(value) > 1 else [*value, 5]
    return None


NONE_REPLACEMENTS = {"initial_prompt": "hello", "prefix": "hi", "max_new_tokens": 100, "chunk_length": 20,
                     "hallucination_silence_threshold": 1.0, "hotwords": "bias", "neg_threshold": 0.3}


def _param_variants():
    defaults = load_settings().asr.transcribe.model_dump()
    for name, value in defaults.items():
        if name == "task":
            continue  # only "transcribe" is valid (ADR-0041); a change is rejected at config load
        if name == "vad_parameters":
            for sub, subvalue in value.items():
                new = NONE_REPLACEMENTS[sub] if subvalue is None else (60.0 if sub == "max_speech_duration_s" else _changed(subvalue))
                yield f"vad_parameters.{sub}", {"vad_parameters": {sub: new}}
            continue
        yield name, {name: NONE_REPLACEMENTS[name] if value is None else _changed(value)}


@pytest.mark.parametrize(("name", "override"), list(_param_variants()), ids=[n for n, _ in _param_variants()])
def test_every_transcribe_param_changes_the_key(name, override):
    base = key(load_settings())
    assert key(load_settings({"asr": {"transcribe": override}})) != base, name


@pytest.mark.parametrize("override", [{"model_revision": "0" * 40}, {"model": "large-v3-turbo"},
                                      {"model_repo": "other/repo"}, {"compute_type": "int8"}, {"device": "cpu"}])
def test_model_settings_change_the_key(override):
    assert key(load_settings({"asr": override})) != key(load_settings())


def test_language_id_changes_the_key_even_with_the_same_whisper_code():
    settings = load_settings()
    assert languages_for(settings).get("urdu").whisper_language == "ur"
    assert key(settings, {"language": "urdu"}) != key(settings, {"language": "hindi"})


def _langs_file(tmp_path, english_code="en", english_tier="untested", name="l.yaml"):
    path = tmp_path / name
    evidence = "\n    evidence: ADR-9999" if english_tier == "tested" else ""
    path.write_text(
        "languages:\n"
        "  - id: hindi\n    label: Hindi\n    whisper_language: ur\n    tier: tested\n    evidence: ADR-0039\n"
        f"  - id: english\n    label: English\n    whisper_language: \"{english_code}\"\n    tier: {english_tier}{evidence}\n",
        encoding="utf-8",
    )
    return load_settings({"asr": {"languages_file": str(path)}})


def test_whisper_language_changes_the_key_but_a_tier_change_does_not(tmp_path):
    payload = {"language": "english"}
    base = key(_langs_file(tmp_path, name="a.yaml"), payload)
    assert key(_langs_file(tmp_path, english_code="cy", name="b.yaml"), payload) != base
    assert key(_langs_file(tmp_path, english_tier="tested", name="c.yaml"), payload) == base


def test_library_versions_change_the_key(monkeypatch):
    settings = load_settings()
    a = key(settings, versions={"faster_whisper": "1.2.1", "ctranslate2": "4.8.2"}, monkeypatch=monkeypatch)
    b = key(settings, versions={"faster_whisper": "1.2.2", "ctranslate2": "4.8.2"}, monkeypatch=monkeypatch)
    c = key(settings, versions={"faster_whisper": "1.2.1", "ctranslate2": "4.9.0"}, monkeypatch=monkeypatch)
    assert len({a, b, c}) == 3


def test_schema_version_changes_the_key(monkeypatch):
    settings = load_settings()
    base = key(settings)
    monkeypatch.setattr(asr_stage.tr, "SCHEMA_VERSION", 2)
    assert key(settings) != base


# -- failures -----------------------------------------------------------------------------------------


def _failed_with(job: store.Job, code: str) -> str:
    assert job.status == "failed"
    stage = job.stages[1]
    assert stage.name == "asr" and stage.status == "failed"
    assert f"{code}:" in job.error and code in stage.error
    return job.error


@pytest.mark.parametrize("payload", [{"duration": 10}, {"duration": 10, "language": ""}, {"duration": 10, "language": None}])
def test_job_without_language_fails_with_missing_language_before_the_lease(env, fake_asr, payload):
    lease = RecordingLease()
    error = _failed_with(run(env, payload, lease), "MISSING_LANGUAGE")
    assert "Add it again and choose the lecture's language" in error
    assert lease.held == [] and fake_asr[0].calls == []


def test_unknown_language_at_asr_fails_with_unknown_language(env, fake_asr):
    _failed_with(run(env, {"duration": 10, "language": "klingon"}), "UNKNOWN_LANGUAGE")
    assert fake_asr[0].calls == []


def test_insufficient_vram_fails_at_once_and_names_both_numbers(env, fake_asr):
    fake_asr[1].free_mib = 1200
    error = _failed_with(run(env, {"language": "hindi", "duration": 10}), "INSUFFICIENT_VRAM")
    assert "1200 MiB" in error and "5500 MiB" in error
    assert fake_asr[0].calls == [] and fake_asr[1].queries == 1  # no wait, no retry


def test_required_free_vram_is_a_setting(env, fake_asr):
    fake_asr[1].free_mib = 1200
    settings = load_settings({"jobs": {"progress_min_interval_s": 0.0}, "asr": {"min_free_vram_mib": 1000}})
    assert run(env, {"language": "hindi", "duration": 10}, settings=settings).status == "succeeded"


def test_nvidia_smi_failure_is_gpu_not_available(env, fake_asr, monkeypatch):
    def broken(device_index=0):
        raise GpuQueryError("nvidia-smi was not found on PATH")

    monkeypatch.setattr(asr_stage, "gpu_vram", broken)
    _failed_with(run(env, {"language": "hindi", "duration": 10}), "GPU_NOT_AVAILABLE")


@pytest.mark.parametrize("code", [ErrorCode.MODEL_LOAD_FAILED, ErrorCode.GPU_OUT_OF_MEMORY,
                                  ErrorCode.TRANSCRIBE_CRASHED, ErrorCode.TRANSCRIBE_TIMEOUT])
def test_transcriber_failures_keep_their_code(env, fake_asr, code):
    fake_asr[0].error = AsrError(code, details="detail for the log")
    error = _failed_with(run(env, {"language": "hindi", "duration": 10}), str(code))
    assert "AsrError" in error
    assert not (env[2].path(WS) / "stages" / "asr").exists()


@pytest.mark.parametrize("text", [None, "  "])
def test_empty_transcript_over_30_s_fails(env, fake_asr, text):
    fake_asr[0].segments = [] if text is None else [{**fake_segments(10)[0], "text": text}]
    _failed_with(run(env, {"language": "hindi", "duration": 31}), "EMPTY_TRANSCRIPT")


def test_empty_transcript_of_short_audio_succeeds(env, fake_asr):
    fake_asr[0].segments = []
    assert run(env, {"language": "hindi", "duration": 30}).status == "succeeded"
    assert transcript(env)["segments"] == [] and transcript(env)["stats"]["rtf"] is not None


def test_crash_mid_write_leaves_no_transcript_anywhere(env, fake_asr, monkeypatch):
    import insightex.asr.transcript as tr

    def boom(fd):
        raise OSError("simulated crash during write")

    monkeypatch.setattr(tr.os, "fsync", boom)
    job = run(env, {"language": "hindi", "duration": 10})
    assert job.status == "failed"
    assert not list(env[2].path(WS).rglob("transcript.json")) and not list(env[2].path(WS).rglob(".transcript*"))


def test_progress_reported_through_the_stage(env, fake_asr, monkeypatch):
    """With the clock moving 3 s per segment, every 10 s segment of a 100 s file is reported (both thresholds pass)."""
    clock = iter(range(0, 10_000, 3))
    monkeypatch.setattr(asr_stage.time, "monotonic", lambda: float(next(clock)))
    reported: list[float] = []
    real = StageContext.progress

    def spy(self, fraction, message=None):
        if message:
            reported.append(round(fraction, 2))
        return real(self, fraction, message)

    monkeypatch.setattr(StageContext, "progress", spy)
    run(env, {"language": "hindi", "duration": 100})
    assert reported[1:] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
