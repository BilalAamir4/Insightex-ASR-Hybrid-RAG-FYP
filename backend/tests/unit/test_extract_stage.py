"""The `extract` stage (ADR-0054, Amendment 1) through the real runner, with a fake model client or a fake Ollama HTTP
server, synthetic windows and no GPU. No Day 4 text, no held-out lecture, no Ollama."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from extract_fakes import FROZEN_DIGEST, FakeOllamaHTTP, metrics, record, reply

from insightex.core.config import load_settings
from insightex.extract import stage as extract_stage
from insightex.extract.calls import OllamaModelClient
from insightex.extract.stage import EXTRACT_JSON, EXTRACTION_JSON, ExtractStage, extraction_summary
from insightex.jobs import db, store
from insightex.jobs.runner import pipeline_is_current, run_job
from insightex.jobs.stages import (
    KeyContext,
    Stage,
    StageContext,
    WorkerStopping,
    register_pipeline,
    stage_key,
)
from insightex.jobs.workspace import Workspaces

KIND = "extract_test"
WS = "sha256-" + "e" * 32

# Synthetic native-script windows (not from any lecture).
TEXTS = ["یہ پہلی مصنوعی ونڈو ہے، اس میں ایک تصور ہے۔", "یہ دوسری مصنوعی ونڈو ہے، gradient descent کے ساتھ۔",
         "تیسری مصنوعی ونڈو، loss function۔", "چوتھی مصنوعی ونڈو۔"]


class FakeAsr(Stage):
    name = "asr"
    version = "1"
    outputs = ("transcript.json",)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {"language": ctx.payload.get("language", "hindi")}

    def run(self, ctx: StageContext) -> None:
        tier = "tested" if ctx.payload.get("language", "hindi") == "hindi" else "untested"
        doc = {"segments": [], "language": {"id": ctx.payload.get("language", "hindi"), "tier_at_processing": tier}}
        (ctx.staging_dir / "transcript.json").write_text(json.dumps(doc), encoding="utf-8")


class FakeIndex(Stage):
    name = "index"
    version = "1"
    outputs = ("windows.json",)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {"texts": ctx.payload.get("texts", TEXTS)}

    def run(self, ctx: StageContext) -> None:
        texts = ctx.payload.get("texts", TEXTS)
        doc = {"windows": [{"id": i, "start": 30.0 * i, "end": 30.0 * i + 30, "text": t} for i, t in enumerate(texts)]}
        (ctx.staging_dir / "windows.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(autouse=True)
def pipeline():
    register_pipeline(KIND, [FakeAsr(), FakeIndex(), ExtractStage()], replace=True)


class RecordingLease:
    def __init__(self):
        self.held: list[str] = []

    @contextmanager
    def hold(self, job_id, purpose):
        self.held.append(purpose)
        yield


def make_env(overrides: dict | None = None):
    base = {"jobs": {"progress_min_interval_s": 0.0}, "extract": {"stage": {"heartbeat_interval_s": 0.01},
                                                                  "vram_poll_interval_s": 0.01}}
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merged = {**base[k], **v}
            if "stage" in v and "stage" in base[k]:
                merged["stage"] = {**base[k]["stage"], **v["stage"]}
            base[k] = merged
        else:
            base[k] = v
    return load_settings(base)


@pytest.fixture
def env():
    settings = make_env()
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    yield settings, conn, Workspaces(settings.jobs.workspaces_dir)
    conn.close()


def run(env, payload=None, settings=None, lease=None, kind=KIND, ws=WS):
    base, conn, workspaces = env
    job_id = store.enqueue(conn, kind, payload if payload is not None else {}, ws)
    run_job(conn, store.claim_next(conn, os.getpid()), settings or base, workspaces, gpu_lease=lease)
    return store.get_job(conn, job_id)


def resume(env, settings=None, lease=None):
    """Run the next claimable job (the one a stop put back in the queue) and return it."""
    base, conn, workspaces = env
    job = store.claim_next(conn, os.getpid())
    run_job(conn, job, settings or base, workspaces, gpu_lease=lease)
    return store.get_job(conn, job.id)


def outputs(env, ws=WS):
    d = env[2].stage_output_dir(ws, "extract")
    return (json.loads((d / EXTRACTION_JSON).read_text(encoding="utf-8")),
            json.loads((d / EXTRACT_JSON).read_text(encoding="utf-8")))


def stage_row(job, name="extract"):
    return next(s for s in job.stages if s.name == name)


def manifest_entry(env, ws=WS):
    return env[2].read_manifest(ws)["stages"]["extract"]


# -- a normal run --------------------------------------------------------------------------------------------------


def test_every_window_is_extracted_and_the_outputs_are_valid(env, fake_extract):
    lease = RecordingLease()
    job = run(env, lease=lease)
    assert job.status == "succeeded", job.error
    doc, meta = outputs(env)
    assert [r["window"]["window_index"] for r in doc["windows"]] == [0, 1, 2, 3]
    assert doc["producer"] == {"kind": "model", "name": "extract stage v1 (gemma4:e4b)"}
    assert doc["windows"][1]["window"] == {"lecture_id": WS, "window_index": 1, "start_s": 30.0, "end_s": 60.0}
    assert meta["totals"] == {"windows": 4, "ok": 4, "ok_after_retry": 0, "failed": 0, "empty_after_retry": 0,
                              "dropped_relations": 0, "calls": 4, "reused_from_store": 0}
    assert meta["model"] == {"tag": "gemma4:e4b", "digest_served": FROZEN_DIGEST}
    assert meta["ollama_version_served"] == "0.40.2" and meta["allow_other_ollama_version_used"] is False
    assert meta["self_test"]["refused"] is True and meta["language"] == {"id": "hindi", "tier_at_processing": "tested"}
    assert meta["cost"]["vram"]["peak_mib"] == 1000 and meta["cost"]["max_prompt_eval_count"] == 900
    assert all(w["status"] == "ok" for w in meta["windows"])
    assert lease.held == ["extract"]  # the runner held the GPU lease for the stage
    assert manifest_entry(env)["warnings"] == [] and manifest_entry(env)["windows"] == 4
    assert not (env[2].path(WS) / ".resume").exists()  # the resume store is deleted after publish
    assert "raw" not in json.dumps(meta)  # raw replies are not published
    assert stage_row(job).message == "Concepts found in 4 of 4 parts"


def test_one_window_per_call_with_the_frozen_settings(env, fake_extract):
    run(env)
    settings = env[0]
    assert [c["window_index"] for c in fake_extract.chats] == [0, 1, 2, 3]
    for c in fake_extract.chats:
        assert c["model"] == "gemma4:e4b" and c["num_ctx"] == settings.extract.num_ctx
        assert c["num_predict"] == settings.extract.num_predict_per_window
        user = json.loads(c["messages"][-1]["content"])
        assert user == {"windows": [{"window_index": c["window_index"], "text": TEXTS[c["window_index"]]}]}


def test_start_checks_run_in_order_and_the_model_is_unloaded_at_the_end(env, fake_extract):
    fake_extract.resident_models = [{"name": "qwen3.5:latest"}, {"name": "other:7b"}]
    run(env)
    order = fake_extract.order
    assert order[:6] == ["resident", "unload:qwen3.5:latest", "unload:other:7b", "version", "digest", "self_test"]
    assert order[6] == "chat:0" and order[-1] == "unload:gemma4:e4b"


def test_untested_language_is_extracted_and_flagged(env, fake_extract):
    job = run(env, {"language": "english"})
    assert job.status == "succeeded", job.error
    assert outputs(env)[1]["language"] == {"id": "english", "tier_at_processing": "untested"}


def test_dangling_relations_are_dropped_and_counted(env, fake_extract):
    def respond(i, attempt, messages):
        rec = record(i, concepts=[{"label": "a", "aliases": []}, {"label": "b", "aliases": []}],
                     relations=[{"head": "a", "type": "part_of", "tail": "b"},
                                {"head": "a", "type": "part_of", "tail": "ghost"}])
        return reply(rec), metrics()

    fake_extract.respond = respond
    run(env)
    doc, meta = outputs(env)
    assert all(r["relations"] == [{"head": "a", "type": "part_of", "tail": "b"}] for r in doc["windows"])
    assert meta["totals"]["dropped_relations"] == 4 and manifest_entry(env)["dropped_relations"] == 4


def test_progress_message_counts_windows_and_failures(env, fake_extract):
    seen = []
    real = extract_stage._Run.message

    def spy(self):
        text = real(self)
        seen.append(text)
        return text

    fake_extract.respond = lambda i, a, m: ("not json", metrics()) if i == 1 else (reply(record(i)), metrics())
    extract_stage._Run.message = spy
    try:
        run(env)
    finally:
        extract_stage._Run.message = real
    assert "Finding concepts: window 1 of 4" in seen
    assert "Finding concepts: window 3 of 4, 1 failed" in seen


# -- invalid windows (decision 4) ----------------------------------------------------------------------------------


@pytest.mark.parametrize("bad,category", [
    ("not json", "not_json"),
    (json.dumps({"other": []}), "missing_record"),
    (json.dumps({"windows": []}), "missing_record"),
    (reply(record(1, important="yes")), "schema_invalid"),
])
def test_each_reply_error_category_fails_the_window_after_one_retry(env, fake_extract, bad, category):
    fake_extract.respond = lambda i, a, m: (bad, metrics()) if i == 1 else (reply(record(i)), metrics())
    job = run(env)
    assert job.status == "succeeded", job.error
    doc, meta = outputs(env)
    assert [r["window"]["window_index"] for r in doc["windows"]] == [0, 2, 3]  # the failed window is left out
    failed = meta["windows"][1]
    assert failed["status"] == "failed" and failed["error_category"] == category and failed["attempts"] == 2
    assert len(failed["errors"]) == 2 and all(len(e) <= env[0].extract.retry_error_chars for a in failed["errors"]
                                              for e in a)
    assert [c["attempt"] for c in fake_extract.chats if c["window_index"] == 1] == [1, 2]
    assert meta["totals"]["failed"] == 1 and meta["totals"]["calls"] == 5


def test_truncated_prompt_too_long_and_overflow_categories(env, fake_extract):
    from insightex.llm.ollama_client import OutputTruncated, PromptTooLong

    def respond(i, attempt, messages):
        if i == 0:
            raise OutputTruncated(1024, 1024)
        if i == 1:
            raise PromptTooLong(9000, 8192, "too long")
        if i == 2:
            return reply(record(i)), metrics(prompt_eval_count=7500)  # 7500 + 1024 > 8192
        return reply(record(i)), metrics()

    fake_extract.respond = respond
    run(env)
    meta = outputs(env)[1]
    assert [w.get("error_category") for w in meta["windows"]] == ["truncated", "prompt_too_long", "prompt_overflow",
                                                                    None]


def test_the_retry_quotes_the_errors_in_the_frozen_template(env, fake_extract):
    fake_extract.respond = lambda i, a, m: ("not json", metrics()) if a == 1 else (reply(record(i)), metrics())
    run(env)
    second = next(c for c in fake_extract.chats if c["window_index"] == 0 and c["attempt"] == 2)
    first = next(c for c in fake_extract.chats if c["window_index"] == 0 and c["attempt"] == 1)
    assert second["messages"][:len(first["messages"])] == first["messages"]
    assert "reply is not JSON" in second["messages"][-1]["content"]
    meta = outputs(env)[1]
    assert all(w["status"] == "ok_after_retry" and w["attempt_used"] == 2 for w in meta["windows"])
    assert meta["totals"]["ok_after_retry"] == 4 and manifest_entry(env)["ok_after_retry"] == 4


def test_empty_after_retry_is_flagged(env, fake_extract):
    fake_extract.respond = lambda i, a, m: ("bad", metrics()) if a == 1 else (reply(record(i, concepts=[])), metrics())
    run(env)
    meta = outputs(env)[1]
    assert all(w["status"] == "ok_after_retry" and w["empty_after_retry"] for w in meta["windows"])
    assert meta["totals"]["empty_after_retry"] == 4


def test_failed_windows_give_a_warning_and_the_job_succeeds(env, fake_extract):
    fake_extract.respond = lambda i, a, m: ("bad", metrics()) if i in (1, 3) else (reply(record(i)), metrics())
    job = run(env)
    assert job.status == "succeeded"
    assert manifest_entry(env)["warnings"] == [{"code": "EXTRACT_WINDOWS_FAILED", "failed": 2, "windows": 4}]
    assert stage_row(job).message == "Concepts found in 2 of 4 parts, 2 failed"


def test_every_window_failed_fails_the_stage(env, fake_extract):
    fake_extract.respond = lambda i, a, m: ("bad", metrics())
    job = run(env)
    assert job.status == "failed" and "EXTRACT_ALL_WINDOWS_FAILED" in job.error
    assert env[2].stage_output_dir(WS, "extract") is None


def test_a_failed_window_stays_failed_for_its_key(env, fake_extract):
    fake_extract.respond = lambda i, a, m: ("bad", metrics()) if i == 2 else (reply(record(i)), metrics())
    run(env)
    fake_extract.respond = None
    calls = len(fake_extract.chats)
    job = run(env)
    assert [s.status for s in job.stages] == ["cached", "cached", "cached"]
    assert len(fake_extract.chats) == calls and outputs(env)[1]["windows"][2]["status"] == "failed"


def test_zero_windows_succeeds_with_an_empty_document_and_no_call(env, fake_extract):
    job = run(env, {"texts": []})
    assert job.status == "succeeded", job.error
    doc, meta = outputs(env)
    assert doc["windows"] == [] and meta["totals"] == {
        "windows": 0, "ok": 0, "ok_after_retry": 0, "failed": 0, "empty_after_retry": 0, "dropped_relations": 0,
        "calls": 0, "reused_from_store": 0}
    assert fake_extract.order == [] and manifest_entry(env)["warnings"] == []
    assert extraction_summary(env[1], env[2], env[0], WS)["state"] == "done"


# -- start checks (decision 1 and 7) -------------------------------------------------------------------------------


def test_a_different_digest_fails_with_model_mismatch(env, fake_extract):
    fake_extract.served_digest = "f" * 64
    job = run(env)
    assert job.status == "failed" and "EXTRACT_MODEL_MISMATCH" in job.error
    assert fake_extract.chats == [] and fake_extract.unloaded[-1] == "gemma4:e4b"


def test_another_ollama_version_fails_unless_allowed(env, fake_extract):
    fake_extract.served_version = "0.40.15"
    job = run(env)
    assert job.status == "failed" and "EXTRACT_OLLAMA_VERSION" in job.error and fake_extract.chats == []
    allowed = make_env({"extract": {"stage": {"allow_other_ollama_version": True}}})
    job = run(env, settings=allowed)
    assert job.status == "succeeded", job.error
    meta = outputs(env)[1]
    assert meta["allow_other_ollama_version_used"] is True and meta["ollama_version_served"] == "0.40.15"
    assert meta["fingerprint"]["frozen_ollama_version"] == "0.40.2"  # the key keeps the frozen version


def test_self_test_failure_stops_before_any_window(env, fake_extract):
    fake_extract.refuse_probe = False
    job = run(env)
    assert job.status == "failed" and "EXTRACT_SELF_TEST_FAILED" in job.error and fake_extract.chats == []


def test_low_vram_and_no_gpu(env, fake_extract, fake_asr):
    from insightex.asr.gpu import GpuQueryError

    gpu = fake_asr[1]
    gpu.free_mib = 100
    job = run(env)
    assert job.status == "failed" and "INSUFFICIENT_VRAM" in job.error and fake_extract.probes == 0

    def broken(device_index=0):
        raise GpuQueryError("nvidia-smi not found")

    extract_stage_gpu = extract_stage.gpu_vram
    extract_stage.gpu_vram = broken
    try:
        job = run(env)
    finally:
        extract_stage.gpu_vram = extract_stage_gpu
    assert job.status == "failed" and "GPU_NOT_AVAILABLE" in job.error


# -- Ollama failures through the real client (fake HTTP server) ----------------------------------------------------


@pytest.fixture
def http(monkeypatch):
    fake = FakeOllamaHTTP().install(monkeypatch)
    monkeypatch.setattr(extract_stage, "make_client",
                        lambda s: OllamaModelClient(s, keep_alive=s.extract.stage.keep_alive))
    return fake


def test_the_real_client_runs_the_stage(env, http):
    http.resident = ["qwen3.5:latest"]
    job = run(env)
    assert job.status == "succeeded", job.error
    assert len(http.chat_bodies) == 4 and all(b["keep_alive"] == 0 and b["truncate"] is False for b in http.chat_bodies)
    assert "qwen3.5:latest" in http.unloads and http.unloads[-1] == "gemma4:e4b"


def test_repeated_http_error_names_the_window_and_status_not_the_body(env, http):
    http.chat_error = lambda body: (httpx.Response(500, json={"error": "SECRET BODY"})
                                    if '"window_index": 2' in body["messages"][-1]["content"] else None)
    job = run(env)
    assert job.status == "failed" and "EXTRACT_OLLAMA_ERROR" in job.error
    row = stage_row(job)
    assert "HTTP 500" in job.error and "window 2" in job.error and "window 2" in row.error
    assert "SECRET BODY" not in job.error and "SECRET BODY" not in row.error


def test_connection_failure_and_timeout_have_distinct_messages(env, http):
    def refuse(body):
        raise httpx.ConnectError("connection refused")

    http.chat_error = refuse
    job = run(env)
    assert "EXTRACT_OLLAMA_UNREACHABLE" in job.error and "could not reach Ollama" in job.error

    def slow(body):
        raise httpx.ReadTimeout("timed out")

    http.chat_error = slow
    job = run(env)
    assert "EXTRACT_OLLAMA_UNREACHABLE" in job.error
    assert "did not answer within ollama.request_timeout_s seconds" in job.error


def test_model_missing_at_the_start_check_and_mid_run(env, http, monkeypatch):
    http.models = {}
    job = run(env)
    assert job.status == "failed" and "EXTRACT_MODEL_MISSING" in job.error and "gemma4:e4b" in job.error
    assert http.chat_bodies == []

    http.models = {"gemma4:e4b": FROZEN_DIGEST}
    from insightex.llm import ollama_client

    def vanish(body):  # the model is removed after the start check: the next chat's model check fails
        if '"window_index": 1' in body["messages"][-1]["content"]:
            http.models = {}
            monkeypatch.setattr(ollama_client, "_checked_models", set())

    http.chat_error = vanish
    job = run(env)
    assert job.status == "failed" and "EXTRACT_MODEL_MISSING" in job.error and "window 2" in job.error


# -- resume (decision 5) -------------------------------------------------------------------------------------------


def test_resume_after_a_stop_partway_through_makes_no_repeated_calls(env, fake_extract):
    def respond(i, attempt, messages):
        if i == 2 and not getattr(respond, "stopped", False):
            respond.stopped = True
            raise WorkerStopping()
        return reply(record(i)), metrics()

    fake_extract.respond = respond
    job = run(env)
    assert job.status == "queued"
    store_dir = env[2].path(WS) / ".resume"
    assert sorted(p.name for p in next(store_dir.iterdir()).iterdir()) == ["w0.json", "w1.json"]
    job = resume(env)
    assert job.status == "succeeded", job.error
    assert [c["window_index"] for c in fake_extract.chats] == [0, 1, 2, 2, 3]  # window 2 again (it never ended)
    meta = outputs(env)[1]
    assert meta["totals"]["reused_from_store"] == 2 and [w["reused_from_store"] for w in meta["windows"]] == [
        True, True, False, False]
    assert not store_dir.exists()


def test_a_kill_during_a_store_write_leaves_no_entry_and_the_window_is_called_again(env, fake_extract, monkeypatch):
    real_put = extract_stage.ResumeStore.put

    def dying_put(self, window_index, entry):
        if window_index == 1:
            (self.directory / f"w1.json.{os.getpid()}.tmp").write_text('{"partial', encoding="utf-8")
            raise WorkerStopping()  # the process dies before the rename
        real_put(self, window_index, entry)

    monkeypatch.setattr(extract_stage.ResumeStore, "put", dying_put)
    assert run(env).status == "queued"
    directory = next((env[2].path(WS) / ".resume").iterdir())
    assert sorted(p.name for p in directory.iterdir()) == ["w0.json", f"w1.json.{os.getpid()}.tmp"]
    monkeypatch.setattr(extract_stage.ResumeStore, "put", real_put)
    assert resume(env).status == "succeeded"
    assert [c["window_index"] for c in fake_extract.chats] == [0, 1, 1, 2, 3]


def test_the_store_write_is_atomic(tmp_path, monkeypatch):
    store_ = extract_stage.ResumeStore(tmp_path / "r")
    store_.prepare()

    def boom(src, dst):
        raise OSError("disk gone")

    monkeypatch.setattr(extract_stage.os, "replace", boom)
    with pytest.raises(OSError):
        store_.put(0, {"x": 1})
    assert store_.get(0) is None
    monkeypatch.undo()
    assert store_.prepare() == 1 and list((tmp_path / "r").iterdir()) == []


def _stop_after_two(fake_extract):
    def respond(i, attempt, messages):
        if i == 2 and not getattr(respond, "stopped", False):
            respond.stopped = True
            raise WorkerStopping()
        return reply(record(i)), metrics()

    fake_extract.respond = respond


@pytest.mark.parametrize("field,value", [("served_version", "0.40.3"), ("served_digest", "a" * 64)])
def test_stored_replies_from_another_version_or_digest_are_not_reused(env, fake_extract, field, value):
    _stop_after_two(fake_extract)
    assert run(env).status == "queued"
    setattr(fake_extract, field, value)
    settings = make_env({"extract": {"stage": {"allow_other_ollama_version": True,
                                               "frozen_model_digest": value if field == "served_digest"
                                               else FROZEN_DIGEST}}})
    if field == "served_digest":  # a new frozen digest is a new key; reuse the old key's store by copying it
        old = next((env[2].path(WS) / ".resume").iterdir())
        upstream = env[2].read_manifest(WS)["stages"]["index"]["key"]
        new_key = stage_key("extract", "1", extract_stage.extract_fingerprint(settings), upstream)
        old.rename(old.with_name(f"extract-{new_key}"))
    job = resume(env, settings=settings)
    assert job.status == "succeeded", job.error
    assert [c["window_index"] for c in fake_extract.chats] == [0, 1, 2, 0, 1, 2, 3]
    assert outputs(env)[1]["totals"]["reused_from_store"] == 0


def test_a_stored_failed_window_is_called_again(env, fake_extract):
    def respond(i, attempt, messages):
        if i == 0:
            return "bad", metrics()
        if i == 2 and not getattr(respond, "stopped", False):
            respond.stopped = True
            raise WorkerStopping()
        return reply(record(i)), metrics()

    fake_extract.respond = respond
    assert run(env).status == "queued"
    fake_extract.respond = None
    assert resume(env).status == "succeeded"
    assert [(c["window_index"], c["attempt"]) for c in fake_extract.chats] == [
        (0, 1), (0, 2), (1, 1), (2, 1), (0, 3), (2, 2), (3, 1)]  # window 0 called again; window 1 reused
    assert outputs(env)[1]["windows"][0]["status"] == "ok"


def test_a_rerun_from_the_store_still_runs_every_start_check(env, fake_extract):
    def respond(i, attempt, messages):
        return reply(record(i)), metrics()

    fake_extract.respond = respond
    real_after = ExtractStage.after_stage
    ExtractStage.after_stage = lambda self, ctx, upstream: None  # keep the store
    try:
        run(env)
        d = env[2].stage_output_dir(WS, "extract")
        for p in d.iterdir():
            p.unlink()
        d.rmdir()  # the published output is gone; the store holds every window
        fake_extract.order.clear()
        lease = RecordingLease()
        job = run(env, lease=lease)
    finally:
        ExtractStage.after_stage = real_after
    assert job.status == "succeeded", job.error
    assert fake_extract.order == ["resident", "version", "digest", "self_test", "unload:gemma4:e4b"]
    assert lease.held == ["extract"] and outputs(env)[1]["totals"]["reused_from_store"] == 4


# -- the cache key (decision 1) ------------------------------------------------------------------------------------


IN_KEY = {
    "extract.stage.model": {"extract": {"stage": {"model": "other:tag"}}},
    "extract.stage.frozen_model_digest": {"extract": {"stage": {"frozen_model_digest": "0" * 64}}},
    "extract.prompt_sha256": {"extract": {"prompt_sha256": "1" * 64}},
    "extract.num_ctx": {"extract": {"num_ctx": 4096}},
    "extract.num_predict_per_window": {"extract": {"num_predict_per_window": 512}},
    "ollama.temperature": {"ollama": {"temperature": 0.5}},
    "ollama.seed": {"ollama": {"seed": 7}},
    "ollama.think": {"ollama": {"think": True}},
    "extract.stage.keep_alive": {"extract": {"stage": {"keep_alive": "10m"}}},
    "extract.truncate": {"extract": {"truncate": True}},
    "extract.retry_error_chars": {"extract": {"retry_error_chars": 100}},
    "extract.stage.frozen_ollama_version": {"extract": {"stage": {"frozen_ollama_version": "0.40.3"}}},
    "extract.self_test_num_ctx": {"extract": {"self_test_num_ctx": 1024}},
    "extract.self_test_probe_lines": {"extract": {"self_test_probe_lines": 200}},
    "extract.token_estimate_scale": {"extract": {"token_estimate_scale": {"gemma4:e4b": 0.9}}},
}
NOT_IN_KEY = {
    "extract.stage.min_free_vram_mib": {"extract": {"stage": {"min_free_vram_mib": 1}}},
    "extract.stage.allow_other_ollama_version": {"extract": {"stage": {"allow_other_ollama_version": True}}},
    "extract.stage.device_index": {"extract": {"stage": {"device_index": 1}}},
    "extract.stage.heartbeat_interval_s": {"extract": {"stage": {"heartbeat_interval_s": 5.0}}},
    "extract.vram_poll_interval_s": {"extract": {"vram_poll_interval_s": 1.0}},
    "ollama.request_timeout_s": {"ollama": {"request_timeout_s": 30}},
}


def _key(settings) -> str:
    return stage_key("extract", ExtractStage.version, extract_stage.extract_fingerprint(settings), "upstream")


@pytest.mark.parametrize("name", sorted(IN_KEY))
def test_each_fingerprint_field_changes_the_key(name):
    assert _key(make_env(IN_KEY[name])) != _key(make_env())


@pytest.mark.parametrize("name", sorted(NOT_IN_KEY))
def test_runtime_only_settings_do_not_change_the_key(name):
    assert _key(make_env(NOT_IN_KEY[name])) == _key(make_env())


def test_the_language_tier_is_not_in_the_key(env, fake_extract):
    ctx = KeyContext("-", {"language": "english"}, WS, env[0])
    assert ExtractStage().config_fingerprint(ctx) == ExtractStage().config_fingerprint(KeyContext("-", {}, WS, env[0]))


# -- the hold (decision 8, Amendment 1) ----------------------------------------------------------------------------


def test_hold_skips_extract_with_no_call_and_no_lease_and_records_it(env, fake_extract):
    lease = RecordingLease()
    job = run(env, {"hold_extract": True}, lease=lease)
    assert job.status == "succeeded", job.error
    row = stage_row(job)
    assert row.status == "skipped" and row.message == "extraction held"
    assert fake_extract.order == [] and lease.held == []
    assert env[2].stage_output_dir(WS, "extract") is None and not (env[2].path(WS) / "stages" / "extract").exists()
    h = env[2].read_manifest(WS)["extract_hold"]
    assert h["job_id"] == job.id and h["set_at"] and "released_at" not in h


def test_the_hold_is_sticky_and_a_held_workspace_is_current(env, fake_extract):
    first = run(env, {"hold_extract": True})
    second = run(env, {})
    assert stage_row(second).status == "skipped" and fake_extract.order == []
    assert env[2].read_manifest(WS)["extract_hold"]["job_id"] == first.id  # the first hold record is kept
    assert pipeline_is_current(KIND, {}, WS, env[0], env[2])


def test_a_first_hold_flag_on_an_unextracted_workspace_is_not_current(env, fake_extract):
    """A lecture whose other stages are cached but which was never extracted (and is not held) needs its job, or
    no hold would be recorded."""
    run(env, {"hold_extract": True})
    manifest = env[2].read_manifest(WS)
    del manifest["extract_hold"]
    env[2].write_manifest(WS, manifest)
    assert not pipeline_is_current(KIND, {"hold_extract": True}, WS, env[0], env[2])


def test_release_job_writes_released_at_and_a_readd_then_extracts(env, fake_extract):
    from insightex.extract import hold

    run(env, {"hold_extract": True})
    lease = RecordingLease()
    release = run(env, kind=hold.RELEASE_KIND, lease=lease)
    assert release.status == "succeeded" and release.stages == [] and lease.held == []
    h = env[2].read_manifest(WS)["extract_hold"]
    assert h["released_at"] and h["released_by_job_id"] == release.id
    assert fake_extract.order == []  # releasing does not extract
    assert not pipeline_is_current(KIND, {}, WS, env[0], env[2])
    job = run(env, {})
    assert [s.status for s in job.stages] == ["cached", "cached", "succeeded"]
    assert len(fake_extract.chats) == 4


def test_an_ingest_queued_before_the_release_still_skips(env, fake_extract):
    from insightex.extract import hold

    base, conn, workspaces = env
    run(env, {"hold_extract": True})
    ingest_id = store.enqueue(conn, KIND, {}, WS)
    release_id = store.enqueue(conn, hold.RELEASE_KIND, {}, WS)
    for _ in range(2):
        run_job(conn, store.claim_next(conn, os.getpid()), base, workspaces)
    assert stage_row(store.get_job(conn, ingest_id)).status == "skipped"
    assert store.get_job(conn, release_id).status == "succeeded" and fake_extract.order == []


# -- extraction.state (Amendment 1 change 1) -----------------------------------------------------------------------


def test_extraction_state_none_held_done_outdated_failed(env, fake_extract):
    base, conn, workspaces = env
    state = lambda s=base: extraction_summary(conn, workspaces, s, WS)
    run(env, {"hold_extract": True})
    assert state() == {"state": "held", "windows": None, "failed": None}
    manifest = workspaces.read_manifest(WS)
    manifest["extract_hold"]["released_at"] = "2026-11-21T00:00:00Z"
    workspaces.write_manifest(WS, manifest)
    assert state()["state"] == "none"
    fake_extract.respond = lambda i, a, m: ("bad", metrics()) if i == 3 else (reply(record(i)), metrics())
    run(env)
    assert state() == {"state": "done", "windows": 4, "failed": 1}
    changed = make_env({"extract": {"retry_error_chars": 100}})  # a new key: the published one is older
    assert state(changed)["state"] == "outdated"
    fake_extract.respond = lambda i, a, m: ("bad", metrics())
    job = run(env, settings=changed)
    assert job.status == "failed" and state(changed)["state"] == "failed"


# -- eviction (decision 8) -----------------------------------------------------------------------------------------


def _index_workspace(conn, ws_id, accessed, pinned=0, size=100):
    conn.execute("INSERT OR REPLACE INTO workspaces (id, source_kind, source_ref, created_at, last_accessed_at, "
                 "size_bytes, pinned) VALUES (?, 'youtube', 'u', 't', ?, ?, ?)", (ws_id, accessed, size, pinned))


def test_eviction_skips_held_and_unreadable_workspaces(env, caplog):
    from insightex.jobs import cache

    _, conn, workspaces = env
    held, broken, plain = "yt-aaaaaaaaaaa", "yt-bbbbbbbbbbb", "yt-ccccccccccc"
    for ws_id in (held, broken, plain):
        workspaces.path(ws_id).mkdir(parents=True)
    workspaces.write_manifest(held, {"stages": {}, "extract_hold": {"set_at": "t", "job_id": "j"}})
    (workspaces.path(broken) / "manifest.json").write_text("{not json", encoding="utf-8")
    workspaces.write_manifest(plain, {"stages": {}})
    for n, ws_id in enumerate((held, broken, plain)):
        _index_workspace(conn, ws_id, f"2026-01-0{n + 1}")
    with caplog.at_level(logging.WARNING):
        removed = cache.evict(conn, workspaces, max_bytes=0)
    assert removed == [plain]
    assert any(broken in r.message and "cannot be read" in r.message for r in caplog.records)
    manifest = workspaces.read_manifest(held)
    manifest["extract_hold"]["released_at"] = "t2"
    workspaces.write_manifest(held, manifest)
    assert cache.evict(conn, workspaces, max_bytes=0) == [held]


def test_a_pinned_workspace_stays_pinned_after_its_hold_is_released(env):
    from insightex.jobs import cache

    _, conn, workspaces = env
    ws_id = "yt-ddddddddddd"
    workspaces.path(ws_id).mkdir(parents=True)
    workspaces.write_manifest(ws_id, {"stages": {}, "extract_hold": {"set_at": "t", "job_id": "j",
                                                                       "released_at": "t2"}})
    _index_workspace(conn, ws_id, "2026-01-01", pinned=1)
    assert cache.evict(conn, workspaces, max_bytes=0) == []
    assert conn.execute("SELECT pinned FROM workspaces WHERE id = ?", (ws_id,)).fetchone()["pinned"] == 1
