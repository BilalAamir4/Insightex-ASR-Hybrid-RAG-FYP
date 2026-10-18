"""M7 extraction evaluation harness (ADR-0048 sections 7 and 8, Amendment 2): run one arm over a lecture's target
windows and write the evidence the scorer in tools/label_concepts reads.

One run:

1. Checks: the arm has no unset fields; the extraction prompt (and, if the arm needs them, the context block and the
   translation prompt) are the frozen files with their pinned sha256; every target is a window of the grid.
2. Plan: the targets in window order, cut into calls of `batch_k` windows. With `context: previous`, each call gets
   the previous grid window (`window_index - 1`) of its first window, and of any later window whose predecessor is
   not the window before it in the call (Amendment 2). The first window of the lecture has no context.
3. Under the exclusive GPU lease (ADR-0033), after unloading every resident Ollama model so the VRAM baseline is
   clean: English input is translated first (one call per window, by the arm's model, cached per window); then one
   extraction call per planned call (ADR-0002 contract through `ollama_client.chat_raw`, JSON Schema `format`).
4. Per target window: relations whose head or tail is not a concept label of the window are dropped and counted;
   the result is a full schema v1 record, checked by `check_window_record`. If any window of a call is invalid, the
   call is retried once in the same unit (a single window stays single, a batch stays a batch, with the same
   context): the first attempt's messages plus the frozen retry template carrying that attempt's validation errors
   (prompts.retry_messages; Session 2b decision 3). Each still-invalid window takes its record from the retry if it is
   valid there ("every window valid after one retry"); run.json records per window whether it needed the retry. A
   truncated reply (done_reason length) is an invalid attempt. An identical re-send would be a replay: at
   temperature 0 qwen3.5 returned byte-identical replies (docs/evidence/m7/session2b_vram_numctx.md).
   The output cap of a call is `extract.num_predict_per_window` times its number of target windows, so every window
   has the same output allowance in every arm (ADR-0048 decision 8; Session 2b decision 1).
5. The model is unloaded in a `finally` block.

Cache. Every model reply is cached under `extract.cache_dir`, keyed by the sha256 of the full request (model tag and
digest, messages, `format`, options), the harness version and the attempt number, so any change that can change
output (prompt, context block, translation, window text, batch, model, num_ctx, num_predict, temperature, seed)
changes the key. Validation is re-applied to cached replies on every run.

Evidence, in the run directory (default `<extract.evidence_dir>/<lecture_id>/<comparison>/<arm>/`):
`extraction.json` (schema v1, producer.kind = model, valid windows only), `run.json` (per-window status, per-call
metrics and `ollama ps`, cost: wall time, tokens/s, VRAM peak) and `calls.jsonl` (every attempt's raw reply).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, Self

from insightex.core.config import Settings
from insightex.extract.arms import Arm
from insightex.extract.extraction_schema import SCHEMA_VERSION, check_document, check_window_record
from insightex.extract.prompts import (
    TRANSLATION_FORMAT,
    FrozenText,
    extraction_format,
    extraction_messages,
    load_frozen,
    retry_messages,
    sha256_text,
    split_extraction_prompt,
    translation_messages,
)
from insightex.extract.vram import VramSampler
from insightex.llm import ollama_client
from insightex.llm.ollama_client import OutputTruncated, PromptTooLong

log = logging.getLogger(__name__)

HARNESS_VERSION = 6  # 6: truncate false (Ollama refuses over-long prompts); 5: post-call overflow check; 4: keep_alive per call; 3: retry with errors; 2: num_predict/window. Bump when request building or reply handling changes in a way that changes output
RUN_VERSION = 1  # run.json layout (tools/label_concepts/scoring.py RUN_VERSION)
RETRIES = 1  # ADR-0048 section 7: "valid after one retry"; a gate rule, not a tunable


class HarnessError(Exception):
    pass


# -- inputs --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowText:
    window_index: int
    start_s: float
    end_s: float
    text: str


def load_windows_json(path: Path) -> list[WindowText]:
    """The index stage's windows.json (or a synthetic file of the same shape)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [WindowText(int(w["id"]), float(w["start"]), float(w["end"]), w["text"]) for w in doc["windows"]]


def load_targets(path: Path, grid: dict[int, WindowText]) -> list[int]:
    """Target windows: a JSON list of window indices, or a label_concepts sample.json (its rows' window_index; start,
    end and text sha256 are checked against the grid, so a changed transcript is refused)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc["windows"] if isinstance(doc, dict) else [{"window_index": i} for i in doc]
    out = []
    for r in rows:
        i = int(r["window_index"])
        w = grid.get(i)
        if w is None:
            raise HarnessError(f"target window {i} is not in the lecture's grid")
        if "start_s" in r and (float(r["start_s"]), float(r["end_s"])) != (w.start_s, w.end_s):
            raise HarnessError(f"target window {i}: start/end differ from the grid")
        if "text_sha256" in r and r["text_sha256"] != sha256_text(w.text):
            raise HarnessError(f"target window {i}: text differs from the one the sample was drawn on")
        out.append(i)
    if len(set(out)) != len(out):
        raise HarnessError("duplicate target windows")
    return sorted(out)


@dataclass(frozen=True)
class Prompts:
    extraction: FrozenText
    context_block: FrozenText | None
    translation: FrozenText | None


def load_prompts(settings: Settings, arm: Arm) -> Prompts:
    x = settings.extract
    extraction = load_frozen(x.prompt_file, x.prompt_sha256, "extraction prompt")
    split_extraction_prompt(extraction)  # the retry template is part of the freeze; refuse a prompt without it
    return Prompts(
        extraction=extraction,
        context_block=(load_frozen(x.context_block_file, x.context_block_sha256, "context block")
                       if arm.context == "previous" else None),
        translation=(load_frozen(x.translate_prompt_file, x.translate_prompt_sha256, "translation prompt")
                     if arm.input == "english" else None),
    )


# -- planning ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CallPlan:
    targets: tuple[int, ...]
    context: tuple[tuple[int, int], ...]  # (context window index, the target it precedes)


def plan_calls(targets: list[int], grid: dict[int, WindowText], batch_k: int, use_context: bool) -> list[CallPlan]:
    ordered = sorted(targets)
    plans = []
    for start in range(0, len(ordered), batch_k):
        chunk = ordered[start:start + batch_k]
        context = []
        if use_context:
            for p, t in enumerate(chunk):
                prev = t - 1
                if prev < 0 or prev not in grid or (p > 0 and chunk[p - 1] == prev):
                    continue
                context.append((prev, t))
        plans.append(CallPlan(tuple(chunk), tuple(context)))
    return plans


# -- model access --------------------------------------------------------------------------------------------------


class ModelClient(Protocol):
    def digest(self, model: str) -> str: ...

    def chat(self, model: str, messages: list[dict], format_schema: dict, num_ctx: int,
             num_predict: int) -> tuple[str, dict[str, Any]]: ...  # raises OutputTruncated, PromptTooLong, PromptBudgetError

    def resident(self) -> list[dict[str, Any]]: ...

    def unload(self, model: str) -> bool: ...


class OllamaModelClient:
    """The ADR-0002 contract: chat_raw (budget rule, think false, length is an error) and unload with polling."""

    def __init__(self, settings: Settings, estimate_gate: bool = True) -> None:
        """`estimate_gate=False` (the measure tool only) sends every prompt so its real prompt_eval_count can be
        compared with what the calibrated budget rule would have allowed; runs always keep the gate."""
        self.settings = settings
        self.estimate_gate = estimate_gate

    def digest(self, model: str) -> str:
        return ollama_client.model_digest(model, self.settings.ollama)

    def chat(self, model: str, messages: list[dict], format_schema: dict, num_ctx: int,
             num_predict: int) -> tuple[str, dict[str, Any]]:
        scale = self.settings.extract.estimate_scale(model) if self.estimate_gate else 0.0
        content, m = ollama_client.chat_raw(messages, format_schema, num_ctx, ollama=self.settings.ollama,
                                            num_predict=num_predict, model=model, estimate_scale=scale,
                                            keep_alive=self.settings.extract.keep_alive,
                                            truncate=self.settings.extract.truncate)
        return content, asdict(m)

    def resident(self) -> list[dict[str, Any]]:
        return ollama_client.loaded_models(self.settings.ollama)

    def unload(self, model: str) -> bool:
        return ollama_client.unload(self.settings.ollama, model, poll_interval_s=self.settings.gpu.ollama_poll_interval_s,
                                    timeout_s=self.settings.ollama.unload_wait_s)


def ps_entry(client: ModelClient, model: str) -> dict[str, Any] | None:
    """`ollama ps` for one model: size, size_vram and the GPU share (PROCESSOR column)."""
    for m in client.resident():
        if m.get("name") == model:
            size, vram = m.get("size", 0), m.get("size_vram", 0)
            pct = round(100 * vram / size, 1) if size else None
            return {"size": size, "size_vram": vram, "gpu_pct": pct,
                    "processor": f"{pct:g}% GPU" if pct is not None else None,
                    "context_length": m.get("context_length")}
    return None


class PsWatch:
    """Reads `ollama ps` for one model while a call runs. With `extract.keep_alive` 0 the model unloads as soon as
    the call returns, so a read afterwards finds nothing; this keeps the largest entry seen during the call (and one
    read after it, for a model that stays loaded)."""

    def __init__(self, client: ModelClient, model: str, interval_s: float) -> None:
        self.client, self.model, self.interval_s = client, model, interval_s
        self.seen: dict[str, Any] | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _read(self) -> None:
        try:
            entry = ps_entry(self.client, self.model)
        except Exception as e:  # noqa: BLE001 - a failed status read must not fail the call it observes
            log.debug("ollama ps read failed: %s", e)
            return
        if entry is not None and (self.seen is None or entry["size_vram"] >= self.seen["size_vram"]):
            self.seen = entry

    def _run(self) -> None:
        while not self._stop.is_set():
            self._read()
            self._stop.wait(self.interval_s)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()
        self._read()


# -- cache ---------------------------------------------------------------------------------------------------------


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ReplyCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def key(self, kind: str, request: dict[str, Any], attempt: int) -> str:
        return hashlib.sha256(canonical({"kind": kind, "harness_version": HARNESS_VERSION, "request": request,
                                         "attempt": attempt}).encode("utf-8")).hexdigest()

    def _path(self, kind: str, key: str) -> Path:
        return self.root / kind / key[:2] / f"{key}.json"

    def get(self, kind: str, key: str) -> dict[str, Any] | None:
        p = self._path(kind, key)
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def put(self, kind: str, key: str, entry: dict[str, Any]) -> None:
        p = self._path(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)


# -- reply handling ------------------------------------------------------------------------------------------------


@dataclass
class WindowOutcome:
    record: dict[str, Any] | None
    errors: list[str]
    dropped_relations: int = 0

    @property
    def valid(self) -> bool:
        return self.record is not None and not self.errors


def drop_dangling(item: dict[str, Any]) -> int:
    """Remove relations whose head or tail is not a concept label of the window (ADR-0048 section 7). In place."""
    concepts = item.get("concepts")
    relations = item.get("relations")
    if not isinstance(concepts, list) or not isinstance(relations, list):
        return 0
    labels = {c.get("label") for c in concepts if isinstance(c, dict)}
    kept = [r for r in relations if not isinstance(r, dict) or (r.get("head") in labels and r.get("tail") in labels)]
    item["relations"] = kept
    return len(relations) - len(kept)


def parse_reply(content: str | None, error: str | None, plan: CallPlan, lecture_id: str,
                grid: dict[int, WindowText]) -> dict[int, WindowOutcome]:
    if content is None:
        return {t: WindowOutcome(None, [error or "no reply"]) for t in plan.targets}
    try:
        obj = json.loads(content)
    except ValueError as e:
        return {t: WindowOutcome(None, [f"reply is not JSON: {e}"]) for t in plan.targets}
    items = obj.get("windows") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        return {t: WindowOutcome(None, ["reply has no `windows` list"]) for t in plan.targets}
    by_index: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("window_index"), int):
            by_index.setdefault(item["window_index"], []).append(item)
    out = {}
    for t in plan.targets:
        found = by_index.get(t, [])
        if len(found) != 1:
            out[t] = WindowOutcome(None, [f"reply has {len(found)} records for window {t}"])
            continue
        item = {k: v for k, v in found[0].items() if k != "window_index"}
        dropped = drop_dangling(item)
        w = grid[t]
        rec = {"window": {"lecture_id": lecture_id, "window_index": t, "start_s": w.start_s, "end_s": w.end_s}, **item}
        out[t] = WindowOutcome(rec, check_window_record(rec, f"window {t}"), dropped)
    return out


# -- the run -------------------------------------------------------------------------------------------------------


@dataclass
class RunContext:
    settings: Settings
    client: ModelClient
    cache: ReplyCache
    lease: Callable[[str], AbstractContextManager[Any]]
    sampler: VramSampler
    clock: Callable[[], float] = time.monotonic
    calls_log: list[dict[str, Any]] = field(default_factory=list)


def extraction_num_predict(settings: Settings, n_targets: int) -> int:
    """Output cap of one extraction call: the same allowance per target window in every arm (Session 2b decision 1)."""
    return settings.extract.num_predict_per_window * n_targets


def _options(settings: Settings, num_predict: int) -> dict[str, Any]:
    o = settings.ollama
    return {"num_ctx": settings.extract.num_ctx, "num_predict": num_predict, "temperature": o.temperature,
            "seed": o.seed, "think": o.think, "keep_alive": settings.extract.keep_alive,
            "truncate": settings.extract.truncate}


def prompt_overflow(metrics: dict[str, Any] | None, num_predict: int, num_ctx: int) -> str | None:
    """The post-call budget check (ADR-0049 Amendment 2): a reply whose real prompt_eval_count plus num_predict
    exceeds num_ctx is invalid, like a truncated one (the prompt may have been cut silently). None when it fits."""
    prompt_n = (metrics or {}).get("prompt_eval_count")
    if prompt_n is None or prompt_n + num_predict <= num_ctx:
        return None
    return (f"prompt overflow: prompt_eval_count {prompt_n} + num_predict {num_predict} = {prompt_n + num_predict} "
            f"> num_ctx {num_ctx}; the reply is not used")


def _cached_call(ctx: RunContext, kind: str, model: str, digest: str, messages: list[dict], fmt: dict,
                 num_predict: int, attempt: int, label: dict[str, Any]) -> dict[str, Any]:
    request = {"model": model, "model_digest": digest, "messages": messages, "format": fmt,
               "options": _options(ctx.settings, num_predict)}
    key = ctx.cache.key(kind, request, attempt)
    entry = ctx.cache.get(kind, key)
    hit = entry is not None
    if entry is None:
        t0 = ctx.clock()
        with PsWatch(ctx.client, model, ctx.settings.extract.vram_poll_interval_s) as watch:
            try:
                content, metrics = ctx.client.chat(model, messages, fmt, ctx.settings.extract.num_ctx, num_predict)
                error = None
            except OutputTruncated as e:
                content, metrics, error = None, {"eval_count": e.eval_count, "done_reason": "length"}, str(e)
            except PromptTooLong as e:  # Ollama refused it (truncate false): an invalid attempt, recorded with counts
                content, error = None, str(e)
                metrics = {"prompt_too_long": {"prompt_tokens": e.prompt_tokens, "num_ctx": e.num_ctx}}
        entry = {"key": key, "kind": kind, "attempt": attempt, "content": content, "error": error,
                 "metrics": metrics, "wall_s": ctx.clock() - t0, "ps": watch.seen,
                 "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        ctx.cache.put(kind, key, entry)
    # re-applied to cached replies too: a reply over the real budget is never parsed or scored
    overflow = prompt_overflow(entry["metrics"], num_predict, ctx.settings.extract.num_ctx)
    if overflow is not None:
        entry = {**entry, "content": None, "error": overflow, "unused_content": entry["content"],
                 "prompt_overflow": {"prompt_eval_count": entry["metrics"]["prompt_eval_count"],
                                     "num_predict": num_predict, "num_ctx": ctx.settings.extract.num_ctx}}
    ctx.calls_log.append({**label, "kind": kind, "attempt": attempt, "cache_hit": hit, "key": key,
                          "content": entry["content"], "error": entry["error"], "metrics": entry["metrics"],
                          "wall_s": entry["wall_s"], "ps": entry["ps"],
                          **({"prompt_overflow": entry["prompt_overflow"], "unused_content": entry["unused_content"]}
                             if overflow is not None else {})})
    return entry


def translate_windows(ctx: RunContext, arm: Arm, digest: str, prompt: FrozenText, indices: list[int],
                      grid: dict[int, WindowText]) -> dict[int, str | None]:
    """Per-window English (C2 arm B), made by the arm's model; one retry; None when both attempts fail."""
    out: dict[int, str | None] = {}
    for i in indices:
        messages = translation_messages(prompt, grid[i].text)
        out[i] = None
        for attempt in range(1, RETRIES + 2):
            entry = _cached_call(ctx, "translate", arm.model, digest, messages, TRANSLATION_FORMAT,
                                 ctx.settings.extract.translate_num_predict, attempt, {"window_index": i})
            try:
                english = json.loads(entry["content"])["english"] if entry["content"] is not None else None
            except (ValueError, KeyError, TypeError):
                english = None
            if isinstance(english, str) and english.strip():
                out[i] = english
                break
    return out


def run_arm(ctx: RunContext, arm: Arm, prompts: Prompts, lecture_id: str, windows: list[WindowText],
            targets: list[int]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one arm. Returns (extraction document, run record); nothing is written here."""
    arm.require_complete()
    assert arm.model is not None and arm.batch_k is not None
    grid = {w.window_index: w for w in windows}
    missing = [t for t in targets if t not in grid]
    if missing:
        raise HarnessError(f"target windows not in the grid: {missing}")
    plans = plan_calls(targets, grid, arm.batch_k, arm.context == "previous")
    needed = sorted({t for p in plans for t in p.targets} | {c for p in plans for c, _ in p.context})
    digest = ctx.client.digest(arm.model)
    outcomes: dict[int, WindowOutcome] = {}
    attempts_used: dict[int, int | None] = {}
    errors: dict[int, list[list[str]]] = {t: [] for t in targets}
    systems: set[str] = set()
    t_start = ctx.clock()
    translation_wall = 0.0
    with ctx.lease(f"m7-eval:{arm.name}"):
        for m in ctx.client.resident():  # clean VRAM baseline: the lease unloads only the configured model
            ctx.client.unload(m["name"])
        ctx.sampler.start()
        try:
            texts = {i: grid[i].text for i in needed}
            if arm.input == "english":
                assert prompts.translation is not None
                t0 = ctx.clock()
                english = translate_windows(ctx, arm, digest, prompts.translation, needed, grid)
                translation_wall = ctx.clock() - t0
                texts = english  # type: ignore[assignment]
            for plan in plans:
                lost = [i for i in (*plan.targets, *(c for c, _ in plan.context)) if texts.get(i) is None]
                if lost:
                    for t in plan.targets:
                        outcomes[t] = WindowOutcome(None, [f"no English translation for window(s) {lost}"])
                        errors[t].append(outcomes[t].errors)
                        attempts_used[t] = None
                    continue
                messages = extraction_messages(prompts.extraction, prompts.context_block,
                                               [(t, texts[t]) for t in plan.targets],
                                               [(c, p, texts[c]) for c, p in plan.context])
                systems.add(messages[0]["content"])
                fmt = extraction_format(list(plan.targets))
                pending = list(plan.targets)
                sent = messages
                for attempt in range(1, RETRIES + 2):
                    entry = _cached_call(ctx, "extract", arm.model, digest, sent, fmt,
                                         extraction_num_predict(ctx.settings, len(plan.targets)), attempt,
                                         {"targets": list(plan.targets), "context": [list(c) for c in plan.context]})
                    parsed = parse_reply(entry["content"], entry["error"], plan, lecture_id, grid)
                    for t in pending:
                        errors[t].append(parsed[t].errors)
                        if parsed[t].valid or t not in outcomes:
                            outcomes[t] = parsed[t]
                        if parsed[t].valid:
                            attempts_used[t] = attempt
                    pending = [t for t in pending if not outcomes[t].valid]
                    if not pending:
                        break
                    # retry in the same unit: the same targets and context, plus this attempt's validation errors
                    sent = retry_messages(messages, prompts.extraction, [e for t in pending for e in parsed[t].errors],
                                          ctx.settings.extract.retry_error_chars)
                for t in pending:
                    attempts_used[t] = None
        finally:
            ctx.sampler.stop()
            try:
                ctx.client.unload(arm.model)
            except Exception as e:  # noqa: BLE001 - the run's own error matters more; log and keep it
                log.warning("unload of %s failed: %s", arm.model, e)
    wall = ctx.clock() - t_start
    doc = {"schema_version": SCHEMA_VERSION, "lecture_id": lecture_id,
           "producer": {"kind": "model", "name": f"{arm.name} ({arm.model})"},
           "windows": [outcomes[t].record for t in sorted(targets) if outcomes[t].valid]}
    doc_errors = check_document(doc)
    if doc_errors:  # every record was validated on its own; a document error is a harness bug
        raise HarnessError("extraction document is invalid: " + "; ".join(doc_errors[:5]))
    run = _run_record(ctx, arm, prompts, lecture_id, targets, plans, digest, outcomes, attempts_used, errors,
                      sorted(systems), wall, translation_wall)
    return doc, run


def _run_record(ctx: RunContext, arm: Arm, prompts: Prompts, lecture_id: str, targets: list[int],
                plans: list[CallPlan], digest: str, outcomes: dict[int, WindowOutcome],
                attempts_used: dict[int, int | None], errors: dict[int, list[list[str]]], systems: list[str],
                wall: float, translation_wall: float) -> dict[str, Any]:
    calls = ctx.calls_log
    fresh = [c for c in calls if not c["cache_hit"]]
    extract_calls = [c for c in calls if c["kind"] == "extract"]
    evals = [(c["metrics"].get("eval_count", 0), c["metrics"].get("eval_duration_s", 0.0)) for c in fresh
             if c["metrics"]]
    eval_n, eval_s = sum(n for n, _ in evals), sum(s for _, s in evals)
    worst = max(extract_calls, key=lambda c: c["metrics"].get("prompt_eval_count", 0), default=None)
    # a window invalid on the first attempt has a second attempt's entry in `errors` (one list per attempt)
    windows = [{"window_index": t, "valid": outcomes[t].valid, "attempt_used": attempts_used.get(t),
                "needed_retry": len(errors[t]) > 1,
                # valid only through the retry, and the retry's record has no concepts: reported apart from
                # ordinary valid windows (ADR-0049 Amendment 2)
                "empty_after_retry": bool(outcomes[t].valid and attempts_used.get(t) == 2
                                          and not outcomes[t].record["concepts"]),
                "dropped_relations": outcomes[t].dropped_relations if outcomes[t].valid else 0,
                "errors": errors[t]} for t in sorted(targets)]
    return {
        "run_version": RUN_VERSION,
        "harness_version": HARNESS_VERSION,
        "lecture_id": lecture_id,
        "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "comparison": arm.comparison,
        "arm": arm.model_dump(),
        "model_digest": digest,
        "prompt_sha256": prompts.extraction.sha256,
        "context_block_sha256": prompts.context_block.sha256 if prompts.context_block else None,
        "translation_prompt_sha256": prompts.translation.sha256 if prompts.translation else None,
        "system_message_sha256": [sha256_text(s) for s in systems],  # with the context block: the arm B prompt hash
        "options": {**_options(ctx.settings, extraction_num_predict(ctx.settings, 1)),
                    "num_predict_per_window": ctx.settings.extract.num_predict_per_window,
                    "num_predict_rule": "num_predict_per_window x target windows in the call",
                    "token_estimate_scale": ctx.settings.extract.estimate_scale(arm.model)},
        "translate_num_predict": ctx.settings.extract.translate_num_predict if arm.input == "english" else None,
        "retries": RETRIES,
        "retry_rule": "once, in the same unit as the first attempt, with the frozen retry template and its errors",
        "retry_error_chars": ctx.settings.extract.retry_error_chars,
        "targets": sorted(targets),
        "plan": [{"targets": list(p.targets), "context": [list(c) for c in p.context]} for p in plans],
        "windows": windows,
        "totals": {
            "windows": len(targets),
            "invalid_windows": sum(1 for w in windows if not w["valid"]),
            "retried_windows": sum(1 for w in windows if w["attempt_used"] == 2),  # recovered by the retry
            "needed_retry_windows": sum(1 for w in windows if w["needed_retry"]),
            "valid_empty_after_retry_windows": sum(1 for w in windows if w["empty_after_retry"]),
            "prompt_overflow_calls": sum(1 for c in calls if c.get("prompt_overflow")),
            "prompt_too_long_calls": sum(1 for c in calls if (c.get("metrics") or {}).get("prompt_too_long")),
            "dropped_relations": sum(w["dropped_relations"] for w in windows),
            "calls": len(calls), "cache_hits": len(calls) - len(fresh),
        },
        "cost": {
            "measured": not (len(calls) - len(fresh)),  # a run served from the cache did not load the model
            "wall_s": wall,
            "translation_wall_s": translation_wall,
            "tokens_per_sec": eval_n / eval_s if eval_s else None,
            "max_prompt_eval_count": worst["metrics"].get("prompt_eval_count") if worst else None,
            "ollama_ps_at_largest_prompt": worst["ps"] if worst else None,
            "vram": ctx.sampler.report(),
        },
        "calls": [{k: c[k] for k in ("kind", "attempt", "cache_hit", "key", "error", "metrics", "wall_s", "ps")}
                  | {k: c[k] for k in ("targets", "context", "window_index") if k in c} for c in calls],
    }


def write_evidence(out_dir: Path, doc: dict[str, Any], run: dict[str, Any], calls: list[dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in (("extraction.json", doc), ("run.json", run)):
        (out_dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (out_dir / "calls.jsonl").open("w", encoding="utf-8") as f:
        for c in calls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def default_out_dir(settings: Settings, lecture_id: str, arm: Arm) -> Path:
    return settings.extract.evidence_dir / lecture_id / arm.comparison / arm.name
