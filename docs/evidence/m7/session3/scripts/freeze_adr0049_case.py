"""Freeze the ADR-0049 synthetic counterexample as its exact request bodies (ADR-0056 decision 4).

ADR-0049's determinism run (`docs/measurements/m7/synthetic/scripts/determinism.py`, results in
`determinism_gemma4_e4b.json`) sent, per case, the body below to /api/chat. It was built with the code at commit
adad53c, before ADR-0049 Amendment 1 (cf00174) added `maxItems: 10` to the `format`. This script rebuilds those bodies
with that commit's own request builders, so the frozen file is the request ADR-0049 sent, minus `keep_alive` (which
the ADR-0056 session sets). Synthetic text only (day4_shape.json, placeholder prompt); no lecture text.

    git worktree add --detach <dir> adad53c
    python3 -I docs/evidence/m7/session3/scripts/freeze_adr0049_case.py <dir>/backend/src
    git worktree remove <dir>

Options are taken from the result file (num_ctx, temperature, seed, think, model) and determinism.py
(num_predict = 1024 x k); the body's key order is determinism.py's.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SYN = REPO / "docs" / "measurements" / "m7" / "synthetic"
OUT = REPO / "docs" / "evidence" / "m7" / "session3" / "keepalive" / "adr0049_case.json"
NUM_PREDICT_PER_WINDOW = 1024  # determinism.py: s.extract.num_predict_per_window at adad53c
CASES = ([18], [18, 20, 21])


def main(old_src: str) -> None:
    sys.path.insert(0, old_src)
    import insightex
    from insightex.extract.harness import load_windows_json
    from insightex.extract.prompts import (
        FrozenText,
        extraction_format,
        extraction_messages,
        sha256_text,
    )
    assert Path(insightex.__file__).resolve().is_relative_to(Path(old_src).resolve()), "not the adad53c code"

    result = json.loads((SYN / "determinism_gemma4_e4b.json").read_text(encoding="utf-8"))
    prompt_path = SYN / "placeholder_prompt.txt"
    text = prompt_path.read_text(encoding="utf-8")
    prompt = FrozenText(path=prompt_path, sha256=sha256_text(text), text=text)
    assert prompt.sha256 == result["prompt_sha256"], "placeholder prompt is not the one ADR-0049 used"
    grid = {w.window_index: w for w in load_windows_json(SYN / "day4_shape.json")}

    cases = []
    for targets, measured in zip(CASES, result["cases"], strict=True):
        assert measured["targets"] == targets
        assert measured["replay_1"]["sha256"] == measured["reloaded"]["sha256"], "fresh-load hash not unique"
        body = {
            "model": result["model"],
            "messages": extraction_messages(prompt, None, [(t, grid[t].text) for t in targets], []),
            "stream": False,
            "think": result["think"],
            "format": extraction_format(list(targets)),
            "options": {"num_ctx": result["num_ctx"], "temperature": result["temperature"], "seed": result["seed"],
                        "num_predict": NUM_PREDICT_PER_WINDOW * len(targets)},
        }
        cases.append({"name": f"k{len(targets)}", "targets": targets, "body": body,
                      "reference_sha256": measured["reloaded"]["sha256"],
                      "adr0049_same_session_replay_2_sha256": measured["replay_2"]["sha256"]})
    doc = {"what": "ADR-0049 synthetic counterexample, exact /api/chat bodies minus keep_alive (ADR-0056 decision 4)",
           "built_with_commit": "adad53c", "source_result": "docs/measurements/m7/synthetic/determinism_gemma4_e4b.json",
           "model_digest": result["model_digest"], "prompt_sha256": result["prompt_sha256"], "cases": cases}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"written {OUT.relative_to(REPO)} sha256 {hashlib.sha256(OUT.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main(sys.argv[1])
