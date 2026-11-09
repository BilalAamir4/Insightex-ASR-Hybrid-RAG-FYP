"""Check that Ollama still matches the frozen M7 final configuration before the held-out run (handoff 4, step 6).

Reads /api/version and /api/tags only (no model call, no lecture data). Exit 0 when the version is 0.40.2 and
gemma4:e4b has the frozen digest; exit 1 otherwise, with STOP: do not run the held-out lecture, tell Bilal.

    python3 docs/evidence/m7/scripts/check_ollama_frozen.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

FROZEN_VERSION = "0.40.2"  # Ollama version of every C1-C4 run (handoff 4, final configuration)
FROZEN_MODEL = "gemma4:e4b"
FROZEN_DIGEST = "dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c"


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=10) as r:
        return json.load(r)


def main() -> int:
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        version = get(base, "/api/version").get("version")
        models = {m["name"]: m.get("digest") for m in get(base, "/api/tags").get("models", [])}
    except OSError as e:
        print(f"STOP: Ollama not reachable at {base} ({e})")
        return 1
    problems = []
    if version != FROZEN_VERSION:
        problems.append(f"Ollama version is {version}, frozen {FROZEN_VERSION}")
    digest = models.get(FROZEN_MODEL)
    if digest != FROZEN_DIGEST:
        problems.append(f"{FROZEN_MODEL} digest is {digest}, frozen {FROZEN_DIGEST}")
    if problems:
        for p in problems:
            print(f"STOP: {p}")
        print("Do not run the held-out lecture; tell Bilal.")
        return 1
    print(f"OK: Ollama {version}, {FROZEN_MODEL} digest {digest[:12]} match the frozen final configuration")
    return 0


if __name__ == "__main__":
    sys.exit(main())
