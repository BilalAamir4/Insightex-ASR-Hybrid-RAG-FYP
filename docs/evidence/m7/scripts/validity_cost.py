"""Print an M7 run's validity and cost only (ADR-0048 Amendment 10, decision 7).

Reads run.json and prints a fixed list of count, cost and metric fields. It never reads extraction.json or
calls.jsonl, and never prints `content`, `errors`, `unused_content` or any record. Use it, and nothing else, to read
a run while its comparison is blinded.

    python3 docs/evidence/m7/scripts/validity_cost.py <run dir> [<run dir> ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOTALS = ("windows", "invalid_windows", "needed_retry_windows", "retried_windows", "valid_empty_after_retry_windows",
          "dropped_relations", "prompt_overflow_calls", "prompt_too_long_calls", "estimate_over_budget_calls",
          "calls", "cache_hits", "translation_calls", "translation_cache_hits", "translation_failed_windows",
          "translation_retried_windows")
CALL_METRICS = ("prompt_eval_count", "eval_count", "done_reason", "load_duration_s")


def main(dirs: list[str]) -> int:
    for d in dirs:
        r = json.loads((Path(d) / "run.json").read_text(encoding="utf-8"))
        c, v, opts = r["cost"], r["cost"]["vram"], r["options"]
        print(f"== {r['arm']['name']} ({r['comparison']}), harness {r['harness_version']}, created {r['created_at']}")
        print(f"  model digest {r['model_digest'][:12]}  prompt {r['prompt_sha256'][:12]}  context block "
              f"{(r.get('context_block_sha256') or '-')[:12]}  system message(s) "
              f"{[s[:12] for s in r['system_message_sha256']]}  fresh {r.get('fresh')}  "
              f"self-test refused {(r.get('truncate_self_test') or {}).get('refused')}")
        print(f"  num_ctx {opts['num_ctx']}  num_predict/window {opts['num_predict_per_window']}")
        print("  totals: " + ", ".join(f"{k} {r['totals'][k]}" for k in TOTALS if k in r["totals"]))
        tps = c.get("tokens_per_sec")
        ps = c.get("ollama_ps_at_largest_prompt") or {}
        print(f"  cost: measured {c['measured']}  wall {c['wall_s']:.1f} s  translation {c['translation_wall_s']:.1f} s  "
              f"tok/s {tps:.1f}" if tps else "", end="")
        print(f"  largest prompt {c['max_prompt_eval_count']}  ollama ps {ps.get('processor')} ctx {ps.get('context_length')}")
        print(f"  vram: baseline {v['baseline_mib']}  peak {v['peak_mib']}  above baseline {v['peak_above_baseline_mib']}"
              f"  phases {v.get('phases')}")
        n = opts["num_ctx"]
        for call in r["calls"]:
            m = call.get("metrics") or {}
            where = call.get("targets") or call.get("window_index")
            margin = (n - m["prompt_eval_count"] - opts["num_predict_per_window"] * len(call.get("targets") or [1])
                      if call["kind"] == "extract" and m.get("prompt_eval_count") else None)
            print(f"  call {call['kind']} {where} attempt {call['attempt']} cache {call['cache_hit']}  "
                  + "  ".join(f"{k} {m.get(k)}" for k in CALL_METRICS)
                  + f"  margin {margin}  wall {call['wall_s']:.1f}  ps {(call.get('ps') or {}).get('processor')}"
                  + ("  ERROR" if call.get("error") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
