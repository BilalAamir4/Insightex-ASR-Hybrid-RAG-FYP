"""Worst-case prompt VRAM and num_ctx measurement for M7 (ADR-0048 section 8, Amendment 2; ADR-0002 budget rule).

For each requested batch size k, with or without previous-window context, the worst-case request is built with the
harness's own request builder (prompts.py), so the measured prompt is the one a run would send:

- k = 1, no context: the window with the largest estimated token count;
- k = 1, context: the window whose text plus its previous window's text is largest;
- k > 1: an upper bound, not a plan the harness would make: the k largest windows (by window tokens, or by window plus
  previous-window tokens with context), each carrying its own previous window as context.

Every case is measured as its retry call, the largest prompt a run can send for it: the first attempt's messages plus
the frozen retry template with validation errors filled to `extract.retry_error_chars` (Session 2b decision 3).

Each case runs once per requested num_ctx with num_predict = `num_predict_per_window` x k (the harness's output cap,
Session 2b decision 1): every resident model is unloaded, the VRAM baseline is sampled, one real call is made
(`chat_raw`; the output may be truncated, which is recorded and does not stop the measurement), and `ollama ps` is
read while the model is still loaded, then the model is unloaded. A case passes at a num_ctx when the real
prompt_eval_count + num_predict fits in num_ctx (the budget rule with real tokens) and `ollama ps` shows 100% GPU.

The calibrated budget rule (`extract.token_estimate_scale`) is not applied here: every case is sent (unless
num_predict alone fills num_ctx), so the report can compare it with the real counts. `gate_refuses_real_fit` marks a
case the real counts allow but a run's calibrated estimate would refuse: the scale must then be lowered, because the
gate may never refuse a k that the real measurement allows (Session 2b decision 2). `gate_allows_real_overflow`
marks the opposite (the gate is too loose; Ollama would truncate the prompt silently).

The report records the prompt's sha256 and whether it is the frozen prompt or a draft. The window texts are not
printed or written; only indices and token counts.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from insightex.core.config import Settings
from insightex.extract.harness import ModelClient, PsWatch, WindowText
from insightex.extract.prompts import (
    FrozenText,
    extraction_format,
    extraction_messages,
    retry_messages,
    sha256_text,
)
from insightex.extract.vram import VramSampler
from insightex.llm.ollama_client import OutputTruncated, estimate_prompt_tokens, scaled_estimate

MEASURE_VERSION = 3  # 3: the retry call (errors filled to the cap) is the measured prompt; 2: per-window num_predict


def window_tokens(text: str) -> int:
    return estimate_prompt_tokens([{"content": text}])


@dataclass(frozen=True)
class Case:
    k: int
    context: bool
    targets: tuple[int, ...]
    context_pairs: tuple[tuple[int, int], ...]
    note: str


def worst_case(windows: list[WindowText], k: int, context: bool) -> Case:
    if k < 1 or k > len(windows):
        raise ValueError(f"k={k} needs between 1 and {len(windows)} windows")
    grid = {w.window_index: w for w in windows}
    own = {i: window_tokens(w.text) for i, w in grid.items()}

    def weight(i: int) -> int:
        return own[i] + (own.get(i - 1, 0) if context else 0)

    chosen = sorted(sorted(grid, key=lambda i: (-weight(i), i))[:k])
    pairs = tuple((i - 1, i) for i in chosen if context and (i - 1) in grid)
    if k == 1:
        note = "largest window" + (" with its previous window" if context else "")
    else:
        note = (f"upper bound: the {k} largest windows" + (", each with its own previous window as context"
                                                           if context else ""))
    return Case(k, context, tuple(chosen), pairs, note)


def filler_errors(targets: tuple[int, ...], max_chars: int) -> list[str]:
    """Synthetic validation errors at least `max_chars` long, so the retry message is at its cap."""
    out: list[str] = []
    while sum(len(e) + 3 for e in out) <= max_chars:
        t = targets[len(out) % len(targets)]
        out.append(f"window {t}: relation head is not a concept label of the window; the cue must be empty unless "
                   f"the window is marked important (error {len(out) + 1})")
    return out


def case_messages(case: Case, grid: dict[int, WindowText], prompt: FrozenText, context_block: FrozenText | None,
                  retry_error_chars: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    messages = extraction_messages(prompt, context_block, [(t, grid[t].text) for t in case.targets],
                                   [(c, p, grid[c].text) for c, p in case.context_pairs])
    messages = retry_messages(messages, prompt, filler_errors(case.targets, retry_error_chars), retry_error_chars)
    return messages, extraction_format(list(case.targets))


def measure_case(client: ModelClient, model: str, messages: list[dict], fmt: dict, num_ctx: int, num_predict: int,
                 sampler: VramSampler, estimate_scale: float = 1.0, ps_interval_s: float = 0.2) -> dict[str, Any]:
    estimated = estimate_prompt_tokens(messages)
    gate_estimate = scaled_estimate(messages, estimate_scale)
    gate_allows = gate_estimate + num_predict <= num_ctx
    out: dict[str, Any] = {"num_ctx": num_ctx, "num_predict": num_predict, "estimated_prompt_tokens": estimated,
                           "token_estimate_scale": estimate_scale, "gate_estimated_prompt_tokens": gate_estimate,
                           "gate_allows": gate_allows}
    if num_predict >= num_ctx:
        return {**out, "sent": False, "passes": False, "gate_refuses_real_fit": False,
                "gate_allows_real_overflow": False, "reason": "num_predict alone fills num_ctx"}
    for m in client.resident():
        client.unload(m["name"])
    sampler.start()
    truncated, metrics = False, {}
    try:
        with PsWatch(client, model, ps_interval_s) as watch:  # read during the call: keep_alive 0 unloads after it
            try:
                _, metrics = client.chat(model, messages, fmt, num_ctx, num_predict)
            except OutputTruncated as e:
                truncated, metrics = True, {"eval_count": e.eval_count}
        ps = watch.seen
    finally:
        sampler.stop()
        client.unload(model)
    prompt_n = metrics.get("prompt_eval_count")
    fits = prompt_n is not None and prompt_n + num_predict <= num_ctx
    full_gpu = ps is not None and ps["gpu_pct"] == 100.0
    return {
        **out, "sent": True, "truncated": truncated,
        "prompt_eval_count": prompt_n,
        "estimate_over_real": (estimated / prompt_n) if prompt_n else None,
        "eval_count": metrics.get("eval_count"),
        "tokens_per_sec": metrics.get("tokens_per_sec"),
        "load_duration_s": metrics.get("load_duration_s"),
        "prompt_near_ctx_limit": prompt_n is not None and prompt_n >= int(num_ctx * 0.98),
        "ollama_ps": ps,
        "vram": sampler.report(),
        "fits_real_budget": fits,
        "gate_refuses_real_fit": fits and not gate_allows,
        "gate_allows_real_overflow": gate_allows and prompt_n is not None and not fits,
        "full_gpu": full_gpu,
        "passes": fits and full_gpu,
        "reason": None if fits and full_gpu else ("real prompt tokens + num_predict > num_ctx" if not fits
                                                  else "ollama ps does not show 100% GPU"),
    }


def run_measurement(settings: Settings, client: ModelClient, lease: Callable[[str], Any],
                    sampler_factory: Callable[[], VramSampler], *, lecture_id: str, model: str,
                    windows: list[WindowText], prompt: FrozenText, prompt_frozen: bool,
                    context_block: FrozenText | None, ks: list[int], contexts: list[bool], num_ctxs: list[int],
                    num_predict_per_window: int) -> dict[str, Any]:
    grid = {w.window_index: w for w in windows}
    if any(contexts) and context_block is None:
        raise ValueError("context cases need the context block (--context-block-file or the frozen one)")
    digest = client.digest(model)
    cases = []
    with lease(f"m7-measure:{model}"):
        for k in ks:
            for with_context in contexts:
                case = worst_case(windows, k, with_context)
                messages, fmt = case_messages(case, grid, prompt, context_block, settings.extract.retry_error_chars)
                runs = [measure_case(client, model, messages, fmt, n, num_predict_per_window * k, sampler_factory(),
                                     settings.extract.estimate_scale(model), settings.extract.vram_poll_interval_s)
                        for n in num_ctxs]
                cases.append({"k": k, "context": with_context, "targets": list(case.targets),
                              "context_windows": [list(p) for p in case.context_pairs], "note": case.note,
                              "window_tokens_estimated": {t: window_tokens(grid[t].text) for t in case.targets},
                              "system_message_sha256": sha256_text(messages[0]["content"]),
                              "runs": runs})
    summary = {str(n): {"passing": [{"k": c["k"], "context": c["context"]} for c in cases
                                    for r in c["runs"] if r["num_ctx"] == n and r["passes"]],
                        "gate_refuses_real_fit": [{"k": c["k"], "context": c["context"]} for c in cases
                                                  for r in c["runs"] if r["num_ctx"] == n
                                                  and r["gate_refuses_real_fit"]]} for n in num_ctxs}
    return {
        "measure_version": MEASURE_VERSION,
        "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lecture_id": lecture_id, "windows_in_lecture": len(windows),
        "model": model, "model_digest": digest,
        "prompt": {"path": str(prompt.path), "sha256": prompt.sha256, "frozen": prompt_frozen},
        "context_block_sha256": context_block.sha256 if context_block else None,
        "ollama_options": {"temperature": settings.ollama.temperature, "seed": settings.ollama.seed,
                           "think": settings.ollama.think, "keep_alive": settings.extract.keep_alive},
        "num_predict_per_window": num_predict_per_window,
        "measured_prompt": "the retry call: first attempt + retry template with errors at retry_error_chars",
        "retry_error_chars": settings.extract.retry_error_chars,
        "token_estimate_scale": settings.extract.estimate_scale(model),
        "rule": "passes = real prompt_eval_count + num_predict <= num_ctx and ollama ps 100% GPU (ADR-0048 s8, "
                "Amendment 2; ADR-0002 budget rule); num_predict = num_predict_per_window x k",
        "cases": cases,
        "summary_by_num_ctx": summary,
    }
