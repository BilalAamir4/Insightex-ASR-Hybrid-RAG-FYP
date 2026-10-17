"""Reload-per-call determinism check (ADR-0049) on synthetic input, through the harness's own client.

Each case (k = 1: window 18; k = 3: windows 18, 20, 21) is sent three times in a row with
`insightex.extract.harness.OllamaModelClient`, which sends `extract.keep_alive` (0: the model unloads after every
call), the calibrated budget gate, think false, temperature 0 and the config seed, at num_ctx 8192 with
num_predict = num_predict_per_window x k. Gemma keeps its default speculative decoding (draft on). Records each
reply's content sha256, done_reason, eval_count and load_duration_s (a fresh load each call shows a load time every
time). Replies are about gibberish and are not kept.

  reload_determinism.py <model> <synthetic windows.json> <placeholder prompt with retry section> <out.json>
"""

import hashlib
import json
import sys
from pathlib import Path

from insightex.core.config import load_settings
from insightex.extract.harness import OllamaModelClient, load_windows_json
from insightex.extract.prompts import draft_text, extraction_format, extraction_messages
from insightex.jobs.gpu_lease import FileGpuLease
from insightex.llm import ollama_client as oc

NUM_CTX = 8192
REPEATS = 3


def main(model: str, windows_path: str, prompt_path: str, out: str) -> None:
    s = load_settings()
    prompt = draft_text(Path(prompt_path))
    grid = {w.window_index: w for w in load_windows_json(Path(windows_path))}
    client = OllamaModelClient(s)
    result = {"model": model, "model_digest": oc.model_digest(model, s.ollama), "keep_alive": s.extract.keep_alive,
              "num_ctx": NUM_CTX, "prompt_sha256": prompt.sha256, "prompt_placeholder": True, "cases": []}
    with FileGpuLease(s).exclusive(f"m7-reload-determinism:{model}", s.extract.lease_timeout_s):
        try:
            for m in client.resident():
                client.unload(m["name"])
            for targets in ([18], [18, 20, 21]):
                messages = extraction_messages(prompt, None, [(t, grid[t].text) for t in targets], [])
                runs = []
                for _ in range(REPEATS):
                    content, m = client.chat(model, messages, extraction_format(targets), NUM_CTX,
                                             s.extract.num_predict_per_window * len(targets))
                    runs.append({"sha256": hashlib.sha256(content.encode()).hexdigest(), "chars": len(content),
                                 "done_reason": m["done_reason"], "eval_count": m["eval_count"],
                                 "prompt_eval_count": m["prompt_eval_count"],
                                 "load_duration_s": round(m["load_duration_s"], 2)})
                case = {"targets": targets, "runs": runs, "all_identical": len({r["sha256"] for r in runs}) == 1}
                result["cases"].append(case)
                print(json.dumps(case))
        finally:
            client.unload(model)
    Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:5])
