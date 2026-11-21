"""The `extract` stage: windows.json -> extraction.json + extract.json (ADR-0054, Amendment 1).

Fifth stage of `ingest_link` and `ingest_file`, after `index`. It runs the frozen M7 final configuration unchanged:
Gemma 4 E4B, the original-language text of each 30 s grid window, one window per call, no context, the frozen
extraction prompt v2, and the ADR-0049 call rules (reload per call, truncate false, run-start self-test, post-call
overflow check, one retry in the same unit). Requests are built by `insightex.extract.calls`, the same code the
harness uses, so the stage sends exactly the requests that were evaluated.

The runner holds the exclusive GPU lease (step 1). In the stage (decision 1, start checks): unload every resident
model (2); read the Ollama version and the served digest and check them against the frozen values (3); the VRAM
pre-flight (4); the truncation self-test (5); the window calls (6); in `finally`, unload the model (7). Steps 2 to 5
also run when every reply comes from the resume store, because reuse depends on step 3.

A window still invalid after its retry is `failed`: left out of `extraction.json`, recorded in `extract.json`; the
job still succeeds unless every window failed (decision 4). Ollama being unreachable, an HTTP error, a missing or
different model, another Ollama version, the self-test or the VRAM pre-flight fail the stage instead.

Resume (decision 5): each window's attempts are stored in `<workspace>/.resume/extract-<stage key>/` as soon as the
window ends, written to a temporary file and renamed. A rerun reuses a stored window only if it ended valid and was
made by the Ollama version and model digest served now. The store is deleted once the stage is published.

The extraction hold (decision 8): with `hold_extract` in the payload, or an unreleased hold in the manifest, the
runner skips the stage (no call, no lease, nothing published) and the hold is recorded in the manifest.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from insightex.asr import transcript as tr
from insightex.asr.gpu import GpuQueryError, Vram, query_vram
from insightex.core.config import Settings
from insightex.extract import hold
from insightex.extract.calls import (
    CallPlan,
    ModelClient,
    OllamaModelClient,
    SelfTestFailed,
    WindowOutcome,
    WindowText,
    extraction_num_predict,
    load_windows_json,
    parse_reply,
    prompt_overflow,
    run_self_test,
)
from insightex.extract.extraction_schema import SCHEMA_VERSION, check_document
from insightex.extract.prompts import (
    FORMAT_VERSION,
    USER_FORMAT_VERSION,
    FrozenText,
    extraction_format,
    extraction_messages,
    load_frozen,
    retry_messages,
    sha256_text,
    split_extraction_prompt,
)
from insightex.extract.vram import VramSampler
from insightex.index import store as index_store
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.jobs import store as job_store
from insightex.jobs.gpu_lease import gpu_memory_used_mib
from insightex.jobs.stages import KeyContext, Stage, StageContext, stage_key
from insightex.jobs.workspace import Workspaces
from insightex.llm.ollama_client import (
    ModelMissingError,
    OllamaError,
    OutputTruncated,
    PromptTooLong,
)

log = logging.getLogger(__name__)

EXTRACTION_JSON, EXTRACT_JSON = "extraction.json", "extract.json"
RESUME_DIR = ".resume"
RETRIES = 1  # ADR-0048 section 7 / ADR-0049 decision 4: one retry in the same unit; a rule, not a tunable
WARNING_CODE = "EXTRACT_WINDOWS_FAILED"
HOLD_REASON = "extraction held"  # the skipped stage's message (ADR-0054 decision 8)


class ExtractStageError(IngestError):
    """An extract-stage failure: `code` and a user-facing `message`; `details` goes to the stage error and the log."""

    def __init__(self, code: ErrorCode | str, message: str | None = None, details: str = "") -> None:
        super().__init__(code, message)
        self.details = details


# -- names tests replace -------------------------------------------------------------------------------------------


def make_client(settings: Settings) -> ModelClient:
    """The production client: the harness's ADR-0002 client with the stage's keep_alive. Tests replace this name."""
    return OllamaModelClient(settings, keep_alive=settings.extract.stage.keep_alive)


def gpu_vram(device_index: int) -> Vram:
    """Free/used VRAM for the pre-flight. Tests replace this name."""
    return query_vram(device_index)


def vram_used() -> int | None:
    """nvidia-smi memory.used for the VRAM peak. Tests replace this name."""
    return gpu_memory_used_mib()


# -- fingerprint ---------------------------------------------------------------------------------------------------


def extract_fingerprint(settings: Settings) -> dict[str, Any]:
    """The stage key's config part (ADR-0054 decision 1). Not in it: min_free_vram_mib, allow_other_ollama_version,
    device_index, heartbeat_interval_s, vram_poll_interval_s, the call timeout and the language tier."""
    x, st, o = settings.extract, settings.extract.stage, settings.ollama
    return {
        "model": st.model, "frozen_model_digest": st.frozen_model_digest, "prompt_sha256": x.prompt_sha256,
        "format_version": FORMAT_VERSION, "user_format_version": USER_FORMAT_VERSION, "schema_version": SCHEMA_VERSION,
        "num_ctx": x.num_ctx, "num_predict_per_window": x.num_predict_per_window, "temperature": o.temperature,
        "seed": o.seed, "think": o.think, "keep_alive": st.keep_alive, "truncate": x.truncate,
        "retry_error_chars": x.retry_error_chars, "frozen_ollama_version": st.frozen_ollama_version,
        "self_test_num_ctx": x.self_test_num_ctx, "self_test_probe_lines": x.self_test_probe_lines,
        "token_estimate_scale": x.estimate_scale(st.model),
    }


def config_id(fingerprint: dict[str, Any]) -> str:
    canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


# -- Ollama errors -------------------------------------------------------------------------------------------------


def infra_error(exc: BaseException, settings: Settings, window_index: int | None) -> ExtractStageError:
    """Map an Ollama failure to its code (ADR-0054 decision 4, Amendment 1). Timeout and connection failure are told
    apart by the underlying httpx exception; an HTTP error names its status, never the response body."""
    where = f" (window {window_index})" if window_index is not None else ""
    model = settings.extract.stage.model
    if isinstance(exc, ModelMissingError):
        return ExtractStageError(ErrorCode.EXTRACT_MODEL_MISSING,
                                 f"The concept extraction model {model} (extract.stage.model) is not in Ollama{where}, "
                                 "so concepts were not extracted.", details=f"{type(exc).__name__}{where}")
    cause = exc if isinstance(exc, httpx.HTTPError) else exc.__cause__
    if isinstance(cause, httpx.TimeoutException):
        return ExtractStageError(ErrorCode.EXTRACT_OLLAMA_UNREACHABLE,
                                 f"Ollama did not answer within ollama.request_timeout_s seconds "
                                 f"({settings.ollama.request_timeout_s:g}){where}. Retry the job.",
                                 details=f"timeout{where}")
    if isinstance(cause, httpx.HTTPStatusError):
        status = cause.response.status_code
        return ExtractStageError(ErrorCode.EXTRACT_OLLAMA_ERROR,
                                 f"Ollama returned HTTP {status}{where} during concept extraction. Retry the job; if "
                                 "it fails again, check the worker log.",
                                 details=f"HTTP {status}{where}")
    if isinstance(cause, httpx.TransportError):
        return ExtractStageError(ErrorCode.EXTRACT_OLLAMA_UNREACHABLE,
                                 f"Concept extraction could not reach Ollama{where}. Start Ollama, then retry the job.",
                                 details=f"{type(cause).__name__}{where}")
    return ExtractStageError(ErrorCode.EXTRACT_OLLAMA_ERROR,
                             f"Ollama returned an error{where} during concept extraction (no HTTP status). Retry the "
                             "job; if it fails again, check the worker log.",
                             details=f"{type(exc).__name__}{where}")


def _ollama(settings: Settings, window_index: int | None, fn, *args):
    try:
        return fn(*args)
    except (OutputTruncated, PromptTooLong):
        raise
    except (OllamaError, httpx.HTTPError) as exc:
        raise infra_error(exc, settings, window_index) from exc


# -- resume store --------------------------------------------------------------------------------------------------


class ResumeStore:
    """One file per window, `w<index>.json`, written to a temporary file and renamed (ADR-0054 decision 5)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def prepare(self) -> int:
        """Create the folder and delete leftover temporary files (never read). Returns how many were deleted."""
        self.directory.mkdir(parents=True, exist_ok=True)
        removed = 0
        for p in self.directory.glob("*.tmp"):
            p.unlink(missing_ok=True)
            removed += 1
        return removed

    def path(self, window_index: int) -> Path:
        return self.directory / f"w{window_index}.json"

    def get(self, window_index: int) -> dict[str, Any] | None:
        try:
            return json.loads(self.path(window_index).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, window_index: int, entry: dict[str, Any]) -> None:
        target = self.path(window_index)
        tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)


def resume_root(workspace_dir: Path) -> Path:
    return workspace_dir / RESUME_DIR


def resume_dir(workspace_dir: Path, stage_key: str) -> Path:
    return resume_root(workspace_dir) / f"extract-{stage_key}"


# -- one window ----------------------------------------------------------------------------------------------------


class _Run:
    """State of one stage run: the client, the prompt, the progress reporter and the call log."""

    def __init__(self, ctx: StageContext, client: ModelClient, prompt: FrozenText, windows: list[WindowText]) -> None:
        self.ctx, self.client, self.prompt = ctx, client, prompt
        self.settings = ctx.settings
        self.model = ctx.settings.extract.stage.model
        self.grid = {w.window_index: w for w in windows}
        self.n = len(windows)
        self.done = 0
        self.failed = 0
        self.calls: list[dict[str, Any]] = []

    def message(self) -> str:
        base = f"Finding concepts: window {min(self.done + 1, self.n)} of {self.n}"
        return base + (f", {self.failed} failed" if self.failed else "")

    def call(self, window_index: int, messages: list[dict], fmt: dict, num_predict: int) -> dict[str, Any]:
        """One model call, run in a thread while the stage reports progress every heartbeat (so cancel and shutdown
        are noticed). Truncation and a refused over-long prompt are attempt results; other Ollama errors raise."""
        hb = self.settings.extract.stage.heartbeat_interval_s
        t0 = time.monotonic()
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="extract-call")
        try:
            fut = pool.submit(self.client.chat, self.model, messages, fmt, self.settings.extract.num_ctx, num_predict)
            while True:
                try:
                    content, metrics = fut.result(timeout=hb)
                    error, category = None, None
                    break
                except concurrent.futures.TimeoutError:
                    self.ctx.progress(self.done / self.n, self.message())
                except OutputTruncated as e:
                    content, metrics = None, {"eval_count": e.eval_count, "done_reason": "length"}
                    error, category = str(e), "truncated"
                    break
                except PromptTooLong as e:
                    content, error, category = None, str(e), "prompt_too_long"
                    metrics = {"prompt_too_long": {"prompt_tokens": e.prompt_tokens, "num_ctx": e.num_ctx}}
                    break
                except (OllamaError, httpx.HTTPError) as exc:
                    raise infra_error(exc, self.settings, window_index) from exc
        finally:
            pool.shutdown(wait=False)
        return {"content": content, "error": error, "category": category, "metrics": metrics,
                "wall_s": round(time.monotonic() - t0, 3)}

    def evaluate(self, window_index: int, attempt: dict[str, Any], num_predict: int) -> WindowOutcome:
        """The post-call overflow check, then parsing and validation; re-applied to stored attempts too."""
        content, error, category = attempt["content"], attempt["error"], attempt["category"]
        overflow = prompt_overflow(attempt["metrics"], num_predict, self.settings.extract.num_ctx) if content else None
        if overflow is not None:
            content, error, category = None, overflow, "prompt_overflow"
        outcome = parse_reply(content, error, CallPlan((window_index,), ()), self.ctx.workspace_id, self.grid,
                              drop_self=True)[window_index]
        if not outcome.valid and outcome.category is None:
            outcome.category = category
        return outcome

    def run_window(self, w: WindowText) -> dict[str, Any]:
        """Both attempts of one window (one retry in the same unit with the errors in the frozen template)."""
        messages = extraction_messages(self.prompt, None, [(w.window_index, w.text)], [])
        fmt = extraction_format([w.window_index])
        num_predict = extraction_num_predict(self.settings, 1)
        attempts: list[dict[str, Any]] = []
        sent = messages
        for n in range(1, RETRIES + 2):
            attempt = {"attempt": n, **self.call(w.window_index, sent, fmt, num_predict)}
            attempts.append(attempt)
            self.calls.append({"window_index": w.window_index, "attempt": n, "metrics": attempt["metrics"],
                               "wall_s": attempt["wall_s"]})
            outcome = self.evaluate(w.window_index, attempt, num_predict)
            if outcome.valid:
                break
            sent = retry_messages(messages, self.prompt, outcome.errors, self.settings.extract.retry_error_chars)
        return {"attempts": attempts, "num_predict": num_predict}

    def outcome_of(self, w: WindowText, attempts: list[dict[str, Any]], num_predict: int) -> dict[str, Any]:
        """Status, record and errors of a window from its attempts (fresh or stored)."""
        cap = self.settings.extract.retry_error_chars
        errors, last = [], None
        for a in attempts:
            last = self.evaluate(w.window_index, a, num_predict)
            errors.append([e[:cap] for e in last.errors])
            if last.valid:
                status = "ok" if a["attempt"] == 1 else "ok_after_retry"
                return {"status": status, "record": last.record, "dropped_relations": last.dropped_relations,
                        "dropped_self_relations": last.dropped_self_relations, "attempt_used": a["attempt"], "errors": errors,
                        "empty_after_retry": status == "ok_after_retry" and not last.record.get("concepts")}
        assert last is not None
        return {"status": "failed", "record": None, "dropped_relations": 0, "dropped_self_relations": 0,
                "attempt_used": None, "errors": errors,
                "error_category": last.category, "empty_after_retry": False}


# -- the stage -----------------------------------------------------------------------------------------------------


def _empty_totals() -> dict[str, int]:
    return {"windows": 0, "ok": 0, "ok_after_retry": 0, "failed": 0, "empty_after_retry": 0, "dropped_relations": 0,
            "dropped_self_relations": 0, "calls": 0, "reused_from_store": 0}


class ExtractStage(Stage):
    name = "extract"
    version = "2"  # 2: self-pointing relations are dropped and counted, not a window error (ADR-0055)
    needs_gpu = True
    outputs = (EXTRACTION_JSON, EXTRACT_JSON)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return extract_fingerprint(ctx.settings)

    def skip_reason(self, ctx: KeyContext, workspaces: Workspaces) -> str | None:
        if ctx.payload.get("hold_extract") is True:
            return HOLD_REASON
        return HOLD_REASON if hold.active_hold(workspaces.read_manifest(ctx.workspace_id)) else None

    def skip_counts_as_current(self, ctx: KeyContext, workspaces: Workspaces) -> bool:
        """Only a hold already in the manifest makes a re-add a no-op: a first `--hold-extract` on a lecture that
        was never extracted must still create its job, or no hold would be recorded."""
        return hold.active_hold(workspaces.read_manifest(ctx.workspace_id)) is not None

    def on_skipped(self, ctx: KeyContext, workspaces: Workspaces) -> None:
        hold.record_hold(workspaces, ctx.workspace_id, ctx.job_id)

    def run(self, ctx: StageContext) -> None:
        s = ctx.settings
        x, st = s.extract, s.extract.stage
        assert ctx.stage_key is not None and ctx.workspace_dir is not None, "the runner sets the key and workspace"
        windows = load_windows_json(ctx.upstream["index"] / index_store.WINDOWS_JSON)
        transcript = json.loads((ctx.upstream["asr"] / tr.TRANSCRIPT_JSON).read_text(encoding="utf-8"))
        lang = transcript.get("language") or {}
        language = {"id": lang.get("id"), "tier_at_processing": lang.get("tier_at_processing")}
        prompt = load_frozen(x.prompt_file, x.prompt_sha256, "extraction prompt")  # refuses any other hash
        split_extraction_prompt(prompt)
        fingerprint = extract_fingerprint(s)
        meta: dict[str, Any] = {
            "stage_version": self.version, "fingerprint": fingerprint, "config_id": config_id(fingerprint),
            "model": {"tag": st.model, "digest_served": None}, "ollama_version_served": None,
            "allow_other_ollama_version_used": False, "self_test": None, "language": language,
            "prompt_sha256": prompt.sha256, "windows": [], "totals": _empty_totals(),
            "cost": {"wall_s": 0.0, "tokens_per_sec": None, "vram": None, "max_prompt_eval_count": None},
        }
        if not windows:  # decision 4: no model call at all, empty document, totals 0, no warning
            self._write(ctx, [], meta)
            ctx.progress(1.0, "No parts to search for concepts")
            return

        client = make_client(s)
        store = ResumeStore(resume_dir(ctx.workspace_dir, ctx.stage_key))
        if store.prepare():
            log.info("extract: deleted leftover temporary files in the resume store")
        run = _Run(ctx, client, prompt, windows)
        sampler = VramSampler(x.vram_poll_interval_s, read=vram_used)
        t0 = time.monotonic()
        results: list[dict[str, Any]] = []
        ctx.progress(0.0, run.message())
        try:
            for m in _ollama(s, None, client.resident):  # step 2: a clean GPU for the model
                _ollama(s, None, client.unload, m["name"])
            version = _ollama(s, None, client.version)  # step 3 (decision 7)
            digest = _ollama(s, None, client.digest, st.model)
            meta["ollama_version_served"], meta["model"]["digest_served"] = version, digest
            if digest != st.frozen_model_digest:
                raise ExtractStageError(
                    ErrorCode.EXTRACT_MODEL_MISMATCH,
                    f"Ollama serves {st.model} with digest {digest}, not the evaluated {st.frozen_model_digest}, so "
                    "concepts were not extracted. Bilal must decide before it is used.",
                    details=f"served {digest}, frozen {st.frozen_model_digest}")
            if version != st.frozen_ollama_version:
                if not st.allow_other_ollama_version:
                    raise ExtractStageError(
                        ErrorCode.EXTRACT_OLLAMA_VERSION,
                        f"Ollama is version {version}, not the evaluated {st.frozen_ollama_version}, so concepts were "
                        "not extracted. Bilal must decide before another version is used "
                        "(extract.stage.allow_other_ollama_version).",
                        details=f"served {version}, frozen {st.frozen_ollama_version}")
                meta["allow_other_ollama_version_used"] = True
                log.warning("extract: running on Ollama %s, not the frozen %s (allow_other_ollama_version)", version,
                            st.frozen_ollama_version)
            self._preflight(s)  # step 4
            sampler.start()
            sampler.phase("self_test")  # step 5
            try:
                meta["self_test"] = _ollama(s, None, run_self_test, client, s, st.model)
            except SelfTestFailed as e:
                raise ExtractStageError(ErrorCode.EXTRACT_SELF_TEST_FAILED, details=str(e)) from e
            sampler.phase("extraction")
            for w in windows:  # step 6
                ctx.progress(run.done / run.n, run.message())
                text_sha = sha256_text(w.text)
                stored = store.get(w.window_index)
                reused = (stored is not None and stored.get("status") in ("ok", "ok_after_retry")
                          and stored.get("ollama_version") == version and stored.get("model_digest") == digest
                          and stored.get("text_sha256") == text_sha)
                if reused:
                    attempts, num_predict = stored["attempts"], stored["num_predict"]
                    outcome = run.outcome_of(w, attempts, num_predict)
                    reused = outcome["status"] != "failed"  # validation is re-applied; a stored window must pass it
                if not reused:
                    fresh = run.run_window(w)
                    attempts, num_predict = fresh["attempts"], fresh["num_predict"]
                    outcome = run.outcome_of(w, attempts, num_predict)
                    store.put(w.window_index, {"window_index": w.window_index, "text_sha256": text_sha,
                                               "ollama_version": version, "model_digest": digest,
                                               "status": outcome["status"], "num_predict": num_predict,
                                               "attempts": attempts})
                results.append({"window": w, "reused": reused, **outcome})
                run.done += 1
                run.failed += outcome["status"] == "failed"
        finally:
            sampler.stop()
            try:  # step 7 (the runner releases the lease)
                client.unload(st.model)
            except Exception as e:  # noqa: BLE001 - the stage's own error matters more; log and keep it
                log.warning("extract: unload of %s failed: %s", st.model, e)

        if results and all(r["status"] == "failed" for r in results):
            raise ExtractStageError(ErrorCode.EXTRACT_ALL_WINDOWS_FAILED,
                                    details=f"all {len(results)} windows failed; categories "
                                            f"{sorted({r['error_category'] for r in results})}")
        meta["windows"] = [self._status_entry(r) for r in results]
        t = meta["totals"]
        t.update(windows=len(results), calls=len(run.calls),
                 reused_from_store=sum(r["reused"] for r in results),
                 dropped_relations=sum(r["dropped_relations"] for r in results),
                 dropped_self_relations=sum(r["dropped_self_relations"] for r in results),
                 empty_after_retry=sum(r["empty_after_retry"] for r in results))
        for r in results:
            t[r["status"]] += 1
        evals = [(c["metrics"].get("eval_count") or 0, c["metrics"].get("eval_duration_s") or 0.0) for c in run.calls]
        decode_s = sum(d for _, d in evals)
        prompts = [c["metrics"].get("prompt_eval_count") for c in run.calls if c["metrics"].get("prompt_eval_count")]
        meta["cost"] = {"wall_s": round(time.monotonic() - t0, 3),
                        "tokens_per_sec": round(sum(n for n, _ in evals) / decode_s, 1) if decode_s else None,
                        "vram": sampler.report(), "max_prompt_eval_count": max(prompts) if prompts else None}
        self._write(ctx, [r["record"] for r in results if r["record"] is not None], meta)
        ctx.progress(1.0, f"Concepts found in {t['ok'] + t['ok_after_retry']} of {t['windows']} parts"
                          + (f", {t['failed']} failed" if t["failed"] else ""))
        log.info("extract done: %d windows, %d ok, %d after retry, %d failed, %d reused, %d calls", t["windows"],
                 t["ok"], t["ok_after_retry"], t["failed"], t["reused_from_store"], t["calls"])

    def _preflight(self, settings: Settings) -> None:
        st = settings.extract.stage
        try:
            vram = gpu_vram(st.device_index)
        except GpuQueryError as exc:
            raise ExtractStageError(
                ErrorCode.GPU_NOT_AVAILABLE,
                "The graphics card couldn't be checked, so concepts can't be extracted. Make sure the NVIDIA driver "
                "works (nvidia-smi), then retry the job.", details=str(exc)) from exc
        if vram.free_mib < st.min_free_vram_mib:
            raise ExtractStageError(
                ErrorCode.INSUFFICIENT_VRAM,
                f"The graphics card has {vram.free_mib} MiB of free memory, but finding concepts needs "
                f"{st.min_free_vram_mib} MiB. Close other programs that use the graphics card, then retry the job.",
                details=f"free {vram.free_mib} MiB, used {vram.used_mib} MiB, required {st.min_free_vram_mib} MiB")
        log.info("extract pre-flight: %d MiB free (need %d)", vram.free_mib, st.min_free_vram_mib)

    @staticmethod
    def _status_entry(r: dict[str, Any]) -> dict[str, Any]:
        entry = {"window_index": r["window"].window_index, "status": r["status"], "attempt_used": r["attempt_used"],
                 "attempts": len(r["errors"]), "dropped_relations": r["dropped_relations"],
                 "dropped_self_relations": r["dropped_self_relations"],
                 "reused_from_store": r["reused"]}
        if r["empty_after_retry"]:
            entry["empty_after_retry"] = True
        if r["status"] == "failed":
            entry.update(error_category=r["error_category"], errors=r["errors"])
        return entry

    def _write(self, ctx: StageContext, records: list[dict[str, Any]], meta: dict[str, Any]) -> None:
        doc = {"schema_version": SCHEMA_VERSION, "lecture_id": ctx.workspace_id,
               "producer": {"kind": "model", "name": f"extract stage v{self.version} ({ctx.settings.extract.stage.model})"},
               "windows": records}
        problems = check_document(doc)
        if problems:  # every record was validated on its own; a document error is a bug
            raise RuntimeError("extraction document is invalid: " + "; ".join(problems[:5]))
        (ctx.staging_dir / EXTRACTION_JSON).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                                                       encoding="utf-8")
        (ctx.staging_dir / EXTRACT_JSON).write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n",
                                                    encoding="utf-8")

    def manifest_extra(self, stage_dir: Path) -> dict[str, Any]:
        meta = json.loads((stage_dir / EXTRACT_JSON).read_text(encoding="utf-8"))
        t = meta["totals"]
        warnings = ([{"code": WARNING_CODE, "failed": t["failed"], "windows": t["windows"]}] if t["failed"] else [])
        return {"windows": t["windows"], "failed": t["failed"], "ok_after_retry": t["ok_after_retry"],
                "dropped_relations": t["dropped_relations"],
                "dropped_self_relations": t["dropped_self_relations"], "config_id": meta["config_id"], "warnings": warnings}

    def after_stage(self, ctx: KeyContext, upstream: dict[str, Path]) -> None:
        """Delete the resume store once the stage is published (or found cached): every key's folder."""
        workspace_dir = upstream[self.name].parents[2]
        shutil.rmtree(resume_root(workspace_dir), ignore_errors=True)


# -- the lecture's extraction summary (API) ------------------------------------------------------------------------


def current_key(manifest: dict[str, Any], settings: Settings) -> str | None:
    """The extract key a job would use now: today's fingerprint chained on the lecture's current `index` key."""
    index_entry = (manifest.get("stages") or {}).get("index") or {}
    if not index_entry.get("key"):
        return None
    return stage_key(ExtractStage.name, ExtractStage.version, extract_fingerprint(settings), index_entry["key"])


def extraction_summary(conn, workspaces: Workspaces, settings: Settings, lecture_id: str) -> dict[str, Any]:
    """`{state, windows, failed}` for the lecture (ADR-0054 decision 8, Amendment 1), states checked in order:
    `held` (an unreleased hold), `done` (published at the current key), `failed` (the latest finished job with an
    `extract` stage failed there), `outdated` (published only at an older key), `none`. Counts come from the published entry
    (null without one)."""
    manifest = workspaces.read_manifest(lecture_id)
    entry = (manifest.get("stages") or {}).get(ExtractStage.name) or {}
    published = bool(entry.get("key")) and workspaces.stage_is_complete(lecture_id, ExtractStage.name, entry["key"],
                                                                        list(ExtractStage.outputs))
    counts = {"windows": entry.get("windows"), "failed": entry.get("failed")} if published else \
        {"windows": None, "failed": None}
    if hold.active_hold(manifest) is not None:
        state = "held"
    elif published and entry["key"] == current_key(manifest, settings):
        state = "done"
    else:
        job = job_store.latest_finished_job_with_stage(conn, lecture_id, ExtractStage.name)
        stage_row = next((r for r in job.stages if r.name == ExtractStage.name), None) if job else None
        if job is not None and job.status == "failed" and stage_row is not None and stage_row.status == "failed":
            state = "failed"
        elif published:
            state = "outdated"
        else:
            state = "none"
    return {"state": state, **counts}


def extraction_warnings(workspaces: Workspaces, lecture_id: str) -> list[dict]:
    """The published extraction's warnings (EXTRACT_WINDOWS_FAILED with counts) for the lecture document."""
    if workspaces.stage_output_dir(lecture_id, ExtractStage.name) is None:
        return []
    warnings = (workspaces.read_manifest(lecture_id)["stages"].get(ExtractStage.name) or {}).get("warnings")
    return warnings if isinstance(warnings, list) else []
