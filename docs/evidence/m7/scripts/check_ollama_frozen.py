"""Check that Ollama still matches the frozen M7 final configuration before the held-out run (handoff 4, step 6).

Reads /api/version and /api/tags only (no model call, no lecture data), and lists the Ollama app's staged-update
folder (a staged installer is installed at the next app start). Exit 0 when the version is 0.40.2, gemma4:e4b has the
frozen digest and no installer is staged; exit 1 otherwise, with STOP: do not run the held-out lecture, tell Bilal.

    python3 docs/evidence/m7/scripts/check_ollama_frozen.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

FROZEN_VERSION = "0.40.2"  # Ollama version of every C1-C4 run (handoff 4, final configuration)
FROZEN_MODEL = "gemma4:e4b"
FROZEN_DIGEST = "dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c"
# the Windows app stages downloaded installers here (WSL path; OLLAMA_UPDATES_DIR overrides; skipped if absent)
UPDATES_DIR = "/mnt/c/Users/Bilal Aamir/AppData/Local/Ollama/updates_v2"


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
    updates = Path(os.environ.get("OLLAMA_UPDATES_DIR", UPDATES_DIR))
    staged = sorted(str(f.relative_to(updates)) for f in updates.rglob("*") if f.is_file()) if updates.is_dir() else []
    if staged:
        problems.append(f"an installer is staged in {updates} ({', '.join(staged)}); the app installs it at its next "
                        "start: delete it and check that auto-update is off")
    if problems:
        for p in problems:
            print(f"STOP: {p}")
        print("Do not run the held-out lecture; tell Bilal.")
        return 1
    note = "no installer staged" if updates.is_dir() else f"{updates} not found, staged-update check skipped"
    print(f"OK: Ollama {version}, {FROZEN_MODEL} digest {digest[:12]} match the frozen final configuration; {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
