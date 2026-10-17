"""Real prompt_eval_count of the harness's worst-case k-window extraction prompts on synthetic windows, per model.

Same messages as gen_check.py (placeholder prompt + the k largest synthetic windows), sent with a one-token boolean
reply format so no long generation runs; the `format` does not enter the prompt tokens (checked: k = 1 with the
extraction format gave the same count in gen_check.py). Also the prompt alone and each window's own JSON entry.

  prompt_counts.py <model> <synthetic windows.json> <placeholder prompt> <out.json>
"""

import json
import sys
from pathlib import Path

from insightex.core.config import load_settings
from insightex.extract.harness import load_windows_json
from insightex.extract.prompts import FrozenText, extraction_messages, sha256_text
from insightex.jobs.gpu_lease import FileGpuLease
from insightex.llm import ollama_client as oc


def main(model: str, windows_path: str, prompt_path: str, out: str) -> None:
    settings = load_settings()
    text = Path(prompt_path).read_text(encoding="utf-8")
    prompt = FrozenText(path=Path(prompt_path), sha256=sha256_text(text), text=text)
    windows = load_windows_json(Path(windows_path))
    grid = {w.window_index: w for w in windows}
    order = [w.window_index for w in sorted(windows, key=lambda w: -oc.estimate_prompt_tokens([{"content": w.text}]))]

    def n(messages) -> int:
        _, m = oc.chat_raw(messages, {"type": "boolean"}, 8192, ollama=settings.ollama, num_predict=16, model=model)
        return m.prompt_eval_count

    result = {"model": model, "model_digest": oc.model_digest(model, settings.ollama),
              "think_sent": settings.ollama.think, "prompt_sha256": prompt.sha256, "prompt_placeholder": True}
    with FileGpuLease(settings).exclusive(f"m7-prompt-counts:{model}", settings.extract.lease_timeout_s):
        try:
            result["prompt_only"] = n(extraction_messages(prompt, None, [], []))
            result["k"] = {}
            for k in (1, 2, 3, 4, 5):
                targets = sorted(order[:k])
                msgs = extraction_messages(prompt, None, [(t, grid[t].text) for t in targets], [])
                result["k"][k] = {"targets": targets, "prompt_eval_count": n(msgs),
                                  "estimated_prompt_tokens": oc.estimate_prompt_tokens(msgs)}
            # every window alone (k = 1), to rank windows by real tokens for this model
            result["per_window"] = {w.window_index: n(extraction_messages(prompt, None, [(w.window_index, w.text)],
                                                                          [])) - result["prompt_only"]
                                    for w in windows}
        finally:
            oc.unload(settings.ollama, model, poll_interval_s=settings.gpu.ollama_poll_interval_s,
                      timeout_s=settings.ollama.unload_wait_s)
    Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main(*sys.argv[1:5])
