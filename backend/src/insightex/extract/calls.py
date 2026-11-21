"""Request building and reply handling shared by the M7 harness and the production `extract` stage (ADR-0054).

One builder for both callers, so the stage sends exactly the requests the harness evaluated (ADR-0054 decision 1):
the call options, the output cap, the run-start truncation self-test, the post-call overflow check, and the parsing
of a reply into schema v1 window records (dangling relations dropped and counted). Messages and `format` come from
`insightex.extract.prompts`. Nothing here writes files, keeps a cache or decides what an invalid window means; the
harness rejects the arm (ADR-0048 section 7) and the stage records a failed window (ADR-0054 decision 4).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from insightex.core.config import Settings
from insightex.extract.extraction_schema import check_window_record
from insightex.llm import ollama_client
from insightex.llm.ollama_client import OutputTruncated, PromptTooLong

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


@dataclass(frozen=True)
class CallPlan:
    targets: tuple[int, ...]
    context: tuple[tuple[int, int], ...]  # (context window index, the target it precedes)


# -- model access --------------------------------------------------------------------------------------------------


class ModelClient(Protocol):
    def digest(self, model: str) -> str: ...

    def version(self) -> str: ...  # Ollama server version (/api/version)

    def chat(self, model: str, messages: list[dict], format_schema: dict, num_ctx: int,
             num_predict: int) -> tuple[str, dict[str, Any]]: ...  # raises OutputTruncated, PromptTooLong, PromptBudgetError

    def resident(self) -> list[dict[str, Any]]: ...

    def unload(self, model: str) -> bool: ...


class OllamaModelClient:
    """The ADR-0002 contract: chat_raw (budget rule, think false, length is an error) and unload with polling.

    `keep_alive` is sent with every call: the harness's `extract.keep_alive` by default, the stage's
    `extract.stage.keep_alive` for the production stage (ADR-0054 decision 2)."""

    def __init__(self, settings: Settings, estimate_gate: bool = True, keep_alive: int | str | None = None) -> None:
        """`estimate_gate=False` (the measure tool only) sends every prompt so its real prompt_eval_count can be
        compared with what the calibrated budget rule would have allowed; runs always keep the gate."""
        self.settings = settings
        self.estimate_gate = estimate_gate
        self.keep_alive = settings.extract.keep_alive if keep_alive is None else keep_alive

    def digest(self, model: str) -> str:
        return ollama_client.model_digest(model, self.settings.ollama)

    def version(self) -> str:
        return ollama_client.server_version(self.settings.ollama)

    def chat(self, model: str, messages: list[dict], format_schema: dict, num_ctx: int,
             num_predict: int) -> tuple[str, dict[str, Any]]:
        scale = self.settings.extract.estimate_scale(model) if self.estimate_gate else 0.0
        content, m = ollama_client.chat_raw(messages, format_schema, num_ctx, ollama=self.settings.ollama,
                                            num_predict=num_predict, model=model, estimate_scale=scale,
                                            keep_alive=self.keep_alive,
                                            truncate=self.settings.extract.truncate, budget_rule="warn")
        return content, asdict(m)

    def resident(self) -> list[dict[str, Any]]:
        return ollama_client.loaded_models(self.settings.ollama)

    def unload(self, model: str) -> bool:
        return ollama_client.unload(self.settings.ollama, model, poll_interval_s=self.settings.gpu.ollama_poll_interval_s,
                                    timeout_s=self.settings.ollama.unload_wait_s)


# -- call settings -------------------------------------------------------------------------------------------------


def extraction_num_predict(settings: Settings, n_targets: int) -> int:
    """Output cap of one extraction call: the same allowance per target window in every arm (Session 2b decision 1)."""
    return settings.extract.num_predict_per_window * n_targets


def call_options(settings: Settings, num_predict: int, keep_alive: int | str) -> dict[str, Any]:
    """The options that decide a reply (recorded in cache keys and run records)."""
    o = settings.ollama
    return {"num_ctx": settings.extract.num_ctx, "num_predict": num_predict, "temperature": o.temperature,
            "seed": o.seed, "think": o.think, "keep_alive": keep_alive, "truncate": settings.extract.truncate}


# -- run-start self-test (ADR-0049 Amendment 2) --------------------------------------------------------------------


SELF_TEST_FORMAT: dict[str, Any] = {"type": "boolean"}
SELF_TEST_LINE = "Line {i}: the weather report for this town says it is mild and dry, with a light wind."


class SelfTestFailed(Exception):
    """Ollama answered the over-long probe instead of refusing it, so it would silently cut over-long prompts."""


def run_self_test(client: ModelClient, settings: Settings, model: str) -> dict[str, Any]:
    """One small synthetic prompt longer than its num_ctx, sent with the run's settings (truncate false). Ollama must
    refuse it; returns the result record, or raises SelfTestFailed if it answered."""
    x = settings.extract
    text = "\n".join(SELF_TEST_LINE.format(i=i) for i in range(1, x.self_test_probe_lines + 1))
    result: dict[str, Any] = {"model": model, "num_ctx": x.self_test_num_ctx, "truncate": x.truncate,
                              "probe_chars": len(text)}
    try:
        _, metrics = client.chat(model, [{"role": "user", "content": text}], SELF_TEST_FORMAT, x.self_test_num_ctx, 1)
    except PromptTooLong as e:
        return {**result, "refused": True, "prompt_tokens": e.prompt_tokens, "reported_num_ctx": e.num_ctx}
    except OutputTruncated:  # answered, and the one-token reply hit num_predict: not refused either
        metrics = {"prompt_eval_count": None}
    raise SelfTestFailed(f"run-start self-test failed: Ollama answered a {len(text)}-character prompt at num_ctx "
                         f"{x.self_test_num_ctx} with truncate={x.truncate} instead of refusing it (prompt_eval_count "
                         f"{metrics.get('prompt_eval_count')}); it would silently cut over-long prompts, so no real call "
                         "is made (ADR-0049 Amendment 2)")


# -- reply handling ------------------------------------------------------------------------------------------------


def prompt_overflow(metrics: dict[str, Any] | None, num_predict: int, num_ctx: int) -> str | None:
    """The post-call budget check (ADR-0049 Amendment 2): a reply whose real prompt_eval_count plus num_predict
    exceeds num_ctx is invalid, like a truncated one (the prompt may have been cut silently). None when it fits."""
    prompt_n = (metrics or {}).get("prompt_eval_count")
    if prompt_n is None or prompt_n + num_predict <= num_ctx:
        return None
    return (f"prompt overflow: prompt_eval_count {prompt_n} + num_predict {num_predict} = {prompt_n + num_predict} "
            f"> num_ctx {num_ctx}; the reply is not used")


@dataclass
class WindowOutcome:
    record: dict[str, Any] | None
    errors: list[str]
    dropped_relations: int = 0
    dropped_self_relations: int = 0  # production stage only (ADR-0055); always 0 in the harness
    # why a reply gave no valid record (ADR-0054 decision 4): not_json, missing_record or schema_invalid; None when
    # the record is valid or the attempt had no reply (the caller knows why: truncated, prompt_too_long, ...)
    category: str | None = None

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


def drop_self_relations(item: dict[str, Any]) -> int:
    """Remove relations whose head equals their tail, exact string comparison as in `check_labels` (ADR-0055). In
    place. Run after `drop_dangling`, so each removed relation's ends are concept labels of the window and a
    self-pointing relation on a non-label was already counted as dangling."""
    relations = item.get("relations")
    if not isinstance(relations, list):
        return 0
    kept = [r for r in relations if not (isinstance(r, dict) and isinstance(r.get("head"), str)
                                         and r.get("head") == r.get("tail"))]
    item["relations"] = kept
    return len(relations) - len(kept)


def parse_reply(content: str | None, error: str | None, plan: CallPlan, lecture_id: str,
                grid: dict[int, WindowText], drop_self: bool = False) -> dict[int, WindowOutcome]:
    """Window records from one reply. `drop_self` (the production stage only, ADR-0055) also drops self-pointing
    relations after the dangling ones; the harness keeps the M7 rule (a self-relation is a window error)."""
    if content is None:
        return {t: WindowOutcome(None, [error or "no reply"]) for t in plan.targets}
    try:
        obj = json.loads(content)
    except ValueError as e:
        return {t: WindowOutcome(None, [f"reply is not JSON: {e}"], category="not_json") for t in plan.targets}
    items = obj.get("windows") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        return {t: WindowOutcome(None, ["reply has no `windows` list"], category="missing_record") for t in plan.targets}
    by_index: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("window_index"), int):
            by_index.setdefault(item["window_index"], []).append(item)
    out = {}
    for t in plan.targets:
        found = by_index.get(t, [])
        if len(found) != 1:
            out[t] = WindowOutcome(None, [f"reply has {len(found)} records for window {t}"], category="missing_record")
            continue
        item = {k: v for k, v in found[0].items() if k != "window_index"}
        dropped = drop_dangling(item)
        dropped_self = drop_self_relations(item) if drop_self else 0
        w = grid[t]
        rec = {"window": {"lecture_id": lecture_id, "window_index": t, "start_s": w.start_s, "end_s": w.end_s}, **item}
        errors = check_window_record(rec, f"window {t}")
        out[t] = WindowOutcome(rec, errors, dropped, dropped_self, category="schema_invalid" if errors else None)
    return out
