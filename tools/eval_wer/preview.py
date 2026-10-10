"""Stop-point-1 preview: raw Whisper segments next to uroman output and L1/L2 forms.

usage: preview.py RAW.json [N]
"""
import json
import sys
from pathlib import Path

import textnorm as tn

d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
print(f"# {d['model']} language_setting={d['language_setting']} detected={d['detected_language']} p={d['language_probability']:.3f}")
step = max(1, len(d["segments"]) // n)
for s in d["segments"][::step][:n]:
    words = [w["word"].strip() for w in s["words"]] or s["text"].split()
    rom = " ".join(tn.romanise_word(w) for w in words)
    l1 = tn.l1_tokens(rom)
    print(f"[{s['start']:.1f}-{s['end']:.1f}]\n  raw : {s['text'].strip()}\n  rom : {rom}\n  L1  : {' '.join(l1)}\n  L2  : {' '.join(tn.l2_tokens(l1))}")
