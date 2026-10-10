"""Show the most frequent reference words with their L1/L2 keys and the L2 collision rate.

usage: refwords.py manual_roman.txt [N]
"""
import collections
import sys
from pathlib import Path

import textnorm as tn

l1 = tn.l1_tokens(Path(sys.argv[1]).read_text(encoding="utf-8"))
n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
for w, c in collections.Counter(l1).most_common(n):
    print(f"{w:12s} x{c:<4d} L2={tn.l2_token(w)}")
r, col, tot = tn.collision_rate(l1)
print(f"collision rate: {col}/{tot} distinct reference words = {r:.1%}")
print("\nlargest collision groups (key: word xcount):")
cnt = collections.Counter(l1)
groups: dict[str, list[str]] = {}
for w in cnt:
    groups.setdefault(tn.l2_token(w), []).append(w)
big = sorted((g for g in groups.items() if len(g[1]) > 1), key=lambda kv: (-len(kv[1]), kv[0]))
for k, ws in big[:15]:
    print(f"{k:8s} {len(ws):3d} words, {sum(cnt[w] for w in ws)} tokens: " + " ".join(f"{w}x{cnt[w]}" for w in sorted(ws, key=lambda w: -cnt[w])[:12]))
