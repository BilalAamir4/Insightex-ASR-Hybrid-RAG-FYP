"""Generation check with the harness's exact request (think as configured, extraction format), on synthetic windows.

For k = 1, 3, 4, 5 it sends the placeholder prompt plus the k largest synthetic windows through chat_raw (which sends
`think` from the config and raises if a reply carries thinking text), then records prompt_eval_count, eval_count,
done_reason and tokens/s, and re-counts the returned content's tokens (prompt_eval_count of the content alone minus
a baseline). eval_count well above the content's own tokens would mean hidden reasoning tokens. A prompt-only call
(no windows) gives the placeholder prompt's real cost so window tokens can be separated from it. The model's replies
are about synthetic text and are not extraction results; they are not kept.

  gen_check.py <model> <synthetic windows.json> <placeholder prompt> <out.json>
"""

import json
import sys
from pathlib import Path

from insightex.core.config import load_settings
from insightex.extract.harness import load_windows_json
from insightex.extract.prompts import FrozenText, extraction_format, extraction_messages, sha256_text
from insightex.jobs.gpu_lease import FileGpuLease
from insightex.llm import ollama_client as oc

NUM_CTX = 8192
NUM_PREDICT = 4096  # generous so the check itself is not truncated; the k arithmetic uses the measured counts


def main(model: str, windows_path: str, prompt_path: str, out: str) -> None:
    settings = load_settings()
    text = Path(prompt_path).read_text(encoding="utf-8")
    prompt = FrozenText(path=Path(prompt_path), sha256=sha256_text(text), text=text)
    windows = load_windows_json(Path(windows_path))
    grid = {w.window_index: w for w in windows}
    order = [w.window_index for w in sorted(windows, key=lambda w: -oc.estimate_prompt_tokens([{"content": w.text}]))]
    lease = FileGpuLease(settings)

    def call(messages, fmt, num_predict):
        content, m = oc.chat_raw(messages, fmt, NUM_CTX, ollama=settings.ollama, num_predict=num_predict, model=model)
        return content, m

    def tokens_of(content: str, base: int) -> int:
        _, m = call([{"role": "user", "content": content}], {"type": "boolean"}, 16)
        return m.prompt_eval_count - base

    result = {"model": model, "model_digest": oc.model_digest(model, settings.ollama),
              "think_sent": settings.ollama.think, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT,
              "prompt_sha256": prompt.sha256, "prompt_placeholder": True, "cases": []}
    with lease.exclusive(f"m7-gen-check:{model}", settings.extract.lease_timeout_s):
        try:
            _, m = call([{"role": "user", "content": "x"}], {"type": "boolean"}, 16)
            base = m.prompt_eval_count
            result["baseline_prompt_eval_count"] = base
            empty = extraction_messages(prompt, None, [], [])
            _, m = call(empty, {"type": "boolean"}, 16)
            result["prompt_only_prompt_eval_count"] = m.prompt_eval_count
            for k in (1, 3, 4, 5):
                targets = sorted(order[:k])
                messages = extraction_messages(prompt, None, [(t, grid[t].text) for t in targets], [])
                case = {"k": k, "targets": targets, "estimated_prompt_tokens": oc.estimate_prompt_tokens(messages)}
                try:
                    content, m = call(messages, extraction_format(targets), NUM_PREDICT)
                    case.update(prompt_eval_count=m.prompt_eval_count, eval_count=m.eval_count,
                                done_reason=m.done_reason, tokens_per_sec=round(m.tokens_per_sec, 1),
                                thinking_returned=False, content_chars=len(content),
                                content_tokens=tokens_of(content, base))
                    try:
                        case["records_returned"] = len(json.loads(content)["windows"])
                    except (ValueError, KeyError, TypeError):
                        case["records_returned"] = None
                except oc.OutputTruncated as e:
                    case.update(truncated=True, eval_count=e.eval_count)
                except oc.OllamaError as e:
                    case.update(error=str(e))
                result["cases"].append(case)
                print(json.dumps(case))
        finally:
            oc.unload(settings.ollama, model, poll_interval_s=settings.gpu.ollama_poll_interval_s,
                      timeout_s=settings.ollama.unload_wait_s)
    Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}))


if __name__ == "__main__":
    main(*sys.argv[1:5])
