"""Real token counts (Ollama prompt_eval_count) of synthetic extraction output records, per model.

Each record is sent as the whole user message, with a one-token boolean reply format; its token count is
prompt_eval_count minus that of a minimal baseline message, so the chat template cancels out. The records use the
harness's output shape and generic words from synth.py, not lecture or gold text. Runs under the exclusive GPU lease
and unloads the model at the end.

  count_output.py <model> <out.json>
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from synth import ENGLISH, URDU, make_text  # noqa: E402

from insightex.core.config import load_settings  # noqa: E402
from insightex.jobs.gpu_lease import FileGpuLease  # noqa: E402
from insightex.llm import ollama_client as oc  # noqa: E402

rng = random.Random(11)


def label(chars: int) -> str:
    words = []
    while len(" ".join(words)) < chars:
        words.append(rng.choice(ENGLISH).title())
    return " ".join(words)


def alias(chars: int) -> str:
    words = []
    while len(" ".join(words)) < chars:
        words.append(rng.choice(URDU))
    return " ".join(words)


def record(index: int, concepts: int, aliases_each: int, relations: int, cue_chars: int | None) -> dict:
    cs = [{"label": label(18), "aliases": [alias(22) for _ in range(aliases_each)]} for _ in range(concepts)]
    rels = [{"head": cs[i % concepts]["label"], "type": "part_of", "tail": cs[(i + 1) % concepts]["label"]}
            for i in range(relations)]
    cue = make_text(int(cue_chars * 0.35), cue_chars - int(cue_chars * 0.35), rng) if cue_chars else None
    return {"window_index": index, "concepts": cs, "relations": rels, "important": cue is not None, "cue": cue,
            "is_recap": False}


# densities: gold mean (1.35 concepts), gold maximum (3 concepts, 1 alias, 1 relation), and a headroom record
# (8 concepts with one alias each, 6 relations, important with a cue at CUE_MAX 300 chars)
RECORDS = {
    "gold_mean": record(18, 2, 0, 0, None),
    "gold_max": record(18, 3, 1, 1, 120),
    "headroom": record(18, 8, 1, 6, 300),
}


def count(settings, model: str, content: str) -> int:
    _, m = oc.chat_raw([{"role": "user", "content": content}], {"type": "boolean"}, 4096, ollama=settings.ollama,
                       num_predict=16, model=model)
    return m.prompt_eval_count


def main(model: str, out: str) -> None:
    settings = load_settings()
    lease = FileGpuLease(settings)
    result = {"model": model, "model_digest": oc.model_digest(model, settings.ollama), "records": {}}
    with lease.exclusive(f"m7-count-output:{model}", settings.extract.lease_timeout_s):
        try:
            base = count(settings, model, "x")
            result["baseline_prompt_eval_count"] = base
            for name, rec in RECORDS.items():
                one = json.dumps({"windows": [rec]}, ensure_ascii=False)
                n = count(settings, model, one) - base
                result["records"][name] = {"chars": len(one), "tokens": n, "concepts": len(rec["concepts"]),
                                           "relations": len(rec["relations"]), "cue_chars": len(rec["cue"] or "")}
                # a record inside a k-window reply costs its own JSON plus a comma; measure k = 5 of them
                five = json.dumps({"windows": [{**rec, "window_index": 18 + j} for j in range(5)]},
                                  ensure_ascii=False)
                result["records"][name]["tokens_k5"] = count(settings, model, five) - base
        finally:
            oc.unload(settings.ollama, model, poll_interval_s=settings.gpu.ollama_poll_interval_s,
                      timeout_s=settings.ollama.unload_wait_s)
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
