"""ADR-0055 evidence (c): compare the Day 4 extract stage v2 output with the v1 copy (all 23 windows) and with the C1
Gemma run (its 20 target windows). Counts, indices and equality only; no labels, relations or text.

Expected outcome (stated in ADR-0055 before the run): a window changes only if its v1 first attempt was rejected only
because of self-relations. Count (b) and the v1 extract.json (23 of 23 valid on attempt 1) predict no change at all.

    python3 docs/evidence/m7/session3/scripts/compare_day4_v2.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
LECTURE = "sha256-de27cb67c2acbedebd0c2c7416932b8a"
V1_DIR = REPO / "docs" / "evidence" / "m7" / "session3" / "day4_stage_v1"
C1 = REPO / "docs" / "evidence" / "m7" / LECTURE / "C1" / "C1-gemma4-e4b" / "extraction.json"
OUT = REPO / "docs" / "evidence" / "m7" / "session3" / "day4_stage_v2_compare.json"


def canon(r: dict) -> str:
    return json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def by_index(doc: dict) -> dict[int, dict]:
    return {r["window"]["window_index"]: r for r in doc["windows"]}


def compare(ours: dict[int, dict], ref: dict[int, dict]) -> dict:
    same = sorted(i for i in ref if i in ours and canon(ours[i]) == canon(ref[i]))
    return {"windows_compared": len(ref), "identical": len(same),
            "changed": sorted(i for i in ref if i in ours and i not in same),
            "missing_in_v2": sorted(i for i in ref if i not in ours)}


def main() -> int:
    data = Path(os.environ.get("INSIGHTEX_DATA", Path.home() / "insightex-data"))
    ws = data / "workspaces" / LECTURE
    entry = json.loads((ws / "manifest.json").read_text(encoding="utf-8"))["stages"]["extract"]
    v2_dir = ws / "stages" / "extract" / entry["key"]
    v2_doc = json.loads((v2_dir / "extraction.json").read_text(encoding="utf-8"))
    v2_meta = json.loads((v2_dir / "extract.json").read_text(encoding="utf-8"))
    v1_meta = json.loads((V1_DIR / "extract.json").read_text(encoding="utf-8"))
    v2 = by_index(v2_doc)
    vs_v1 = compare(v2, by_index(json.loads((V1_DIR / "extraction.json").read_text(encoding="utf-8"))))
    vs_c1 = compare(v2, by_index(json.loads(C1.read_text(encoding="utf-8"))))
    t = v2_meta["totals"]
    result = {
        "lecture_id": LECTURE,
        "v2": {"stage_key": entry["key"], "stage_version": v2_meta["stage_version"],
               "producer": v2_doc["producer"]["name"], "ollama_version_served": v2_meta["ollama_version_served"],
               "digest_served": v2_meta["model"]["digest_served"], "totals": t,
               "attempt_used": sorted({w["attempt_used"] for w in v2_meta["windows"]}, key=str),
               "extraction_json_sha256": hashlib.sha256((v2_dir / "extraction.json").read_bytes()).hexdigest(),
               "cost": {k: v2_meta["cost"][k] for k in ("wall_s", "tokens_per_sec", "max_prompt_eval_count")},
               "vram_peak_above_baseline_mib": (v2_meta["cost"].get("vram") or {}).get("peak_above_baseline_mib")},
        "v1": {"stage_key": V1_DIR.name, "stage_version": v1_meta["stage_version"], "totals": v1_meta["totals"]},
        "vs_v1_all_windows": vs_v1,
        "vs_c1_target_windows": vs_c1,
        "expectation_met": (not vs_v1["changed"] and not vs_v1["missing_in_v2"] and not vs_c1["changed"]
                            and not vs_c1["missing_in_v2"] and t["dropped_self_relations"] == 0),
    }
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("vs_v1_all_windows", "vs_c1_target_windows", "expectation_met")}))
    print(f"v2 key {entry['key']} version {v2_meta['stage_version']}; totals {t}")
    print(f"written: {OUT.relative_to(REPO)}")
    return 0 if result["expectation_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
