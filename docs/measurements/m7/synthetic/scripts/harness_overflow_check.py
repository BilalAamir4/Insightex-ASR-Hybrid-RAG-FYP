"""Cases A and B of the overflow test, through the harness itself (ADR-0049 Amendment 2; synthetic input only).

`insightex.extract.harness.run_arm` with the real `OllamaModelClient` (calibrated gate, `truncate` false, keep_alive
0, the post-call check, the same-unit retry) on one synthetic window per case, single-window arm, num_ctx 8192,
num_predict 1024:
  case A: the window's prompt is about 1,000 tokens longer than num_ctx -> Ollama must refuse it (PromptTooLong);
  case B: the prompt fits num_ctx but prompt + num_predict does not -> the post-call check must reject the reply;
  case A, gate off: case A with the estimate gate switched off, standing for a prompt that tokenises densely enough
  to pass the calibrated gate -> Ollama must refuse it (truncate false) and the window must be invalid.
The window text is numbered English filler (no lecture text). Its size comes from Ollama's own count: a first,
deliberately over-long request is refused with the exact prompt length, which fixes the tokens per filler line and
the fixed part (system prompt, JSON wrapper). The reply cache is a fresh directory, so no earlier reply is reused.

  harness_overflow_check.py <model> <prompt file with retry section> <cache dir> <out.json>
"""

import json
import sys
from pathlib import Path

from insightex.core.config import load_settings
from insightex.extract import harness as h
from insightex.extract.arms import Arm
from insightex.extract.cli import lease_factory
from insightex.extract.prompts import draft_text, extraction_format, extraction_messages
from insightex.extract.vram import VramSampler
from insightex.llm.ollama_client import PromptTooLong

LINE = "Line {i}: the weather report for this town says it is mild and dry, with a light wind."


def window(lines: int) -> h.WindowText:
    return h.WindowText(0, 0.0, 30.0, "\n".join(LINE.format(i=i) for i in range(1, lines + 1)))


def main(model: str, prompt_path: str, cache_dir: str, out: str) -> None:
    settings = load_settings({"extract": {"cache_dir": cache_dir}})
    x = settings.extract
    prompt = draft_text(Path(prompt_path))
    prompts = h.Prompts(prompt, None, None)
    client = h.OllamaModelClient(settings, estimate_gate=False)  # sizing only: get Ollama's exact counts

    def real_length(lines: int) -> int:
        messages = extraction_messages(prompt, None, [(0, window(lines).text)], [])
        try:
            client.chat(model, messages, extraction_format([0]), x.num_ctx, 1)
        except PromptTooLong as e:
            return e.prompt_tokens
        raise RuntimeError("expected a refusal while sizing")

    a, b = real_length(400), real_length(500)
    per_line = (b - a) / 100
    fixed = a - 400 * per_line
    lines_a = round((x.num_ctx + 1000 - fixed) / per_line)
    cases = {"case_a": (lines_a, True), "case_b": (round((x.num_ctx - 500 - fixed) / per_line), True),
             "case_a_gate_off": (lines_a, False)}
    result = {"model": model, "prompt_sha256": prompt.sha256, "num_ctx": x.num_ctx,
              "num_predict_per_window": x.num_predict_per_window, "truncate": x.truncate, "keep_alive": x.keep_alive,
              "estimate_scale": x.estimate_scale(model), "sizing": {"tokens_per_line": per_line, "fixed": fixed}}
    arm = Arm(name="overflow-" + model.replace(":", "_"), comparison="C1", model=model, input="original", batch_k=1, context="none")
    for name, (lines, gate) in cases.items():
        ctx = h.RunContext(settings=settings, client=h.OllamaModelClient(settings, estimate_gate=gate),
                           cache=h.ReplyCache(Path(cache_dir)),
                           lease=lease_factory(settings), sampler=VramSampler(x.vram_poll_interval_s))
        try:
            _, run = h.run_arm(ctx, arm, prompts, "synthetic-overflow", [window(lines)], [0])
        except Exception as e:  # noqa: BLE001 - a gate refusal (PromptBudgetError) is a result here, not a crash
            result[name] = {"lines": lines, "raised": f"{type(e).__name__}: {e}"}
            print(name, json.dumps(result[name]))
            continue
        w = run["windows"][0]
        calls = [{"attempt": c["attempt"], "error": c["error"], "metrics": {k: c["metrics"].get(k) for k in
                  ("prompt_eval_count", "eval_count", "done_reason", "prompt_too_long")},
                  "prompt_overflow": c.get("prompt_overflow")} for c in ctx.calls_log]
        result[name] = {"lines": lines, "valid": w["valid"], "needed_retry": w["needed_retry"],
                        "errors": w["errors"], "totals": run["totals"], "calls": calls}
        print(name, json.dumps({k: result[name][k] for k in ("lines", "valid", "errors")}))
    Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:5])
