"""How does Ollama report prompt_eval_count for prompts that do not fit num_ctx? (ADR-0049 Amendment 2; synthetic.)

The prompt is a synthetic document: a first code word at the very start, numbered filler lines, a last code word at
the very end; the model is asked for both code words. If Ollama cuts the prompt from the start, the first code word
is lost; if it cuts the end, the last one is. Sent directly to /api/chat (the body chat_raw sends: think from the
config, temperature 0, the config seed, keep_alive 0, a JSON Schema format) because the harness gate would refuse
case A before sending. No lecture text.

  1. count: the true length of each prompt, at num_ctx 16384 (enough room; qwen3.5 may run partly on the CPU there,
     which only slows the call), num_predict 1;
  2. case A: a prompt about 1,000 tokens longer than num_ctx 8192, num_predict 64;
  3. case B: a prompt that fits 8192 alone (about 7,700 tokens) with num_predict 1024, so prompt + num_predict > 8192.

  overflow_probe.py <model> <out.json>
"""

import json
import sys
from pathlib import Path

import httpx

from insightex.core.config import load_settings
from insightex.extract.harness import prompt_overflow
from insightex.jobs.gpu_lease import FileGpuLease
from insightex.llm import ollama_client as oc

FIRST, LAST = "ORCHID", "GRANITE"
SYSTEM = ("You will be shown a long document. Reply with the code word given at the very beginning of the document "
          "and the code word given at the very end of it. If you cannot see one of them, reply \"NONE\" for it.")
FORMAT = {"type": "object", "additionalProperties": False, "required": ["first_code_word", "last_code_word"],
          "properties": {"first_code_word": {"type": "string"}, "last_code_word": {"type": "string"}}}
COUNT_CTX, CTX = 16384, 8192


def document(lines: int) -> str:
    body = "\n".join(f"Line {i}: the weather report for this town says it is mild and dry, with a light wind."
                     for i in range(1, lines + 1))
    return f"BEGIN. The first code word is {FIRST}.\n{body}\nEND. The last code word is {LAST}."


def main(model: str, out: str) -> None:
    s = load_settings()
    base = s.ollama.base_url.rstrip("/")

    def send(lines: int, num_ctx: int, num_predict: int) -> dict:
        body = {"model": model, "stream": False, "think": s.ollama.think, "format": FORMAT, "keep_alive": 0,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": document(lines)}],
                "options": {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": s.ollama.temperature,
                            "seed": s.ollama.seed}}
        r = httpx.post(f"{base}/api/chat", json=body, timeout=s.ollama.request_timeout_s)
        r.raise_for_status()
        d = r.json()
        content = d.get("message", {}).get("content", "")
        try:
            reply = json.loads(content)
        except ValueError:
            reply = None
        return {"lines": lines, "num_ctx": num_ctx, "num_predict": num_predict,
                "prompt_eval_count": d.get("prompt_eval_count"), "eval_count": d.get("eval_count"),
                "done_reason": d.get("done_reason"), "reply": reply if reply is not None else content[:200]}

    result = {"model": model, "model_digest": oc.model_digest(model, s.ollama), "think": s.ollama.think,
              "expected": {"first_code_word": FIRST, "last_code_word": LAST}}
    with FileGpuLease(s).exclusive(f"m7-overflow-probe:{model}", s.extract.lease_timeout_s):
        try:
            # tokens per filler line, from two true counts
            a, b = send(100, COUNT_CTX, 1), send(300, COUNT_CTX, 1)
            per_line = (b["prompt_eval_count"] - a["prompt_eval_count"]) / 200
            fixed = a["prompt_eval_count"] - 100 * per_line
            lines_a = round((CTX + 1000 - fixed) / per_line)
            lines_b = round((CTX - 500 - fixed) / per_line)
            count_a, count_b = send(lines_a, COUNT_CTX, 1), send(lines_b, COUNT_CTX, 1)
            result["calibration"] = {"tokens_per_line": per_line, "fixed_tokens": fixed}
            result["true_length"] = {"case_a": count_a["prompt_eval_count"], "case_b": count_b["prompt_eval_count"]}
            for name, lines, num_predict in (("case_a", lines_a, 64), ("case_b", lines_b, 1024)):
                r = send(lines, CTX, num_predict)
                rep = r["reply"] if isinstance(r["reply"], dict) else {}
                r["true_prompt_tokens"] = result["true_length"][name]
                r["prompt_was_cut"] = r["prompt_eval_count"] is not None and r["prompt_eval_count"] < r[
                    "true_prompt_tokens"]
                r["first_code_word_ok"] = rep.get("first_code_word", "").strip().upper() == FIRST
                r["last_code_word_ok"] = rep.get("last_code_word", "").strip().upper() == LAST
                r["post_call_check"] = prompt_overflow({"prompt_eval_count": r["prompt_eval_count"]}, num_predict, CTX)
                result[name] = r
                print(name, json.dumps(r))
        finally:
            oc.unload(s.ollama, model, poll_interval_s=s.gpu.ollama_poll_interval_s, timeout_s=s.ollama.unload_wait_s)
    Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("calibration", "true_length")}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
