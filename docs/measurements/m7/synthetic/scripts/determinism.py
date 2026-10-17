"""Determinism / replay check on synthetic input: are repeated identical requests byte-identical?

The request body is chat_raw's (/api/chat, think from the config, the extraction `format`, temperature, seed, num_ctx
8192, num_predict = num_predict_per_window x k), built from the placeholder prompt and the synthetic Day 4-shaped
windows (no lecture text). Sent directly with httpx only so that one extra option can be added: `draft_num_predict: 0`
turns Gemma's MTP draft model off (the runner then starts without any --spec-* flag; checked by hand).

Per case (k = 1: window 18; k = 3: windows 18, 20, 21):
  replay_1, replay_2  the same request twice in a row, model kept loaded (what the current harness retry does)
  reloaded            the same request after unloading the model
  draft_off           (Gemma only) the same request with draft_num_predict 0 (forces a reload)
Each reply's content sha256, done_reason and eval_count are recorded; the replies themselves are about gibberish and
are not kept.

  determinism.py <model> <synthetic windows.json> <placeholder prompt> <out.json>
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

from insightex.core.config import load_settings
from insightex.extract.harness import load_windows_json
from insightex.extract.prompts import FrozenText, extraction_format, extraction_messages, sha256_text
from insightex.jobs.gpu_lease import FileGpuLease
from insightex.llm import ollama_client as oc

NUM_CTX = 8192


def main(model: str, windows_path: str, prompt_path: str, out: str) -> None:
    s = load_settings()
    base = s.ollama.base_url.rstrip("/")
    text = Path(prompt_path).read_text(encoding="utf-8")
    prompt = FrozenText(path=Path(prompt_path), sha256=sha256_text(text), text=text)
    grid = {w.window_index: w for w in load_windows_json(Path(windows_path))}

    def send(targets, extra=None):
        messages = extraction_messages(prompt, None, [(t, grid[t].text) for t in targets], [])
        options = {"num_ctx": NUM_CTX, "temperature": s.ollama.temperature, "seed": s.ollama.seed,
                   "num_predict": s.extract.num_predict_per_window * len(targets), **(extra or {})}
        body = {"model": model, "messages": messages, "stream": False, "think": s.ollama.think,
                "format": extraction_format(list(targets)), "keep_alive": s.ollama.keep_alive, "options": options}
        r = httpx.post(f"{base}/api/chat", json=body, timeout=s.ollama.request_timeout_s)
        r.raise_for_status()
        d = r.json()
        content = d.get("message", {}).get("content", "")
        if d.get("message", {}).get("thinking"):
            raise RuntimeError("thinking text returned")
        return {"sha256": hashlib.sha256(content.encode()).hexdigest(), "chars": len(content),
                "done_reason": d.get("done_reason"), "eval_count": d.get("eval_count"),
                "prompt_eval_count": d.get("prompt_eval_count")}

    def unload():
        oc.unload(s.ollama, model, poll_interval_s=s.gpu.ollama_poll_interval_s, timeout_s=s.ollama.unload_wait_s)

    gemma = model.startswith("gemma")
    result = {"model": model, "model_digest": oc.model_digest(model, s.ollama), "num_ctx": NUM_CTX,
              "temperature": s.ollama.temperature, "seed": s.ollama.seed, "think": s.ollama.think,
              "prompt_sha256": prompt.sha256, "prompt_placeholder": True, "cases": []}
    with FileGpuLease(s).exclusive(f"m7-determinism:{model}", s.extract.lease_timeout_s):
        try:
            for targets in ([18], [18, 20, 21]):
                unload()
                case = {"targets": targets, "replay_1": send(targets), "replay_2": send(targets)}
                unload()
                time.sleep(1)
                case["reloaded"] = send(targets)
                if gemma:
                    case["draft_off"] = send(targets, {"draft_num_predict": 0})
                    unload()
                runs = [v for k, v in case.items() if k != "targets"]
                case["all_identical"] = len({r["sha256"] for r in runs}) == 1
                case["replay_identical"] = case["replay_1"]["sha256"] == case["replay_2"]["sha256"]
                result["cases"].append(case)
                print(json.dumps(case))
        finally:
            unload()
    Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:5])
