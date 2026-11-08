"""Gold-overlap check of a translation prompt (handoff 3, section 3.2): no 3-, 4- or 5-word sequence of the prompt
may occur in any of the 20 gold windows' transcript text. Prints counts only, plus each shared sequence from the
prompt side (never gold text beyond that sequence).

    bash scripts/run_in_env.sh python docs/evidence/m7/<lecture>/C2/scripts/translate_prompt_overlap.py <prompt file>
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from insightex.core.config import load_settings, repo_root
from insightex.extract.cli import lecture_windows

LECTURE = "sha256-de27cb67c2acbedebd0c2c7416932b8a"


def words(text: str) -> list[str]:
    return [w for w in re.split(r"\W+", unicodedata.normalize("NFKC", text).casefold()) if w]


def grams(ws: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def main(prompt_path: str) -> int:
    settings = load_settings()
    sample = json.loads((repo_root() / "tools/label_concepts/labels" / LECTURE / "sample.json").read_text())
    gold = {int(r["window_index"]) for r in sample["windows"]}
    grid = {w.window_index: w for w in lecture_windows(settings, LECTURE, None)}
    prompt = words(Path(prompt_path).read_text(encoding="utf-8"))
    print(f"prompt: {len(prompt)} words; gold windows: {len(gold)}")
    total = 0
    for n in (5, 4, 3):
        pg = grams(prompt, n)
        hits = {}
        for i in sorted(gold):
            shared = pg & grams(words(grid[i].text), n)
            if shared:
                hits[i] = shared
        total += sum(len(s) for s in hits.values())
        print(f"{n}-word sequences shared: {sum(len(s) for s in hits.values())} in {len(hits)} window(s)")
        for i, shared in hits.items():
            for g in sorted(shared):
                print(f"   window {i}: \"{' '.join(g)}\" (prompt side)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
