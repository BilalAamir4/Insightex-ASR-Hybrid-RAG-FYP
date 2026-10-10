"""Show the most frequent reference words with their L1/L2 keys and the L2 collision rate.

usage: refwords.py manual_roman.txt [N]
"""
import collections
import sys

import textnorm as tn

l1 = tn.l1_tokens(open(sys.argv[1], encoding="utf-8").read())
n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
for w, c in collections.Counter(l1).most_common(n):
    print(f"{w:12s} x{c:<4d} L2={tn.l2_token(w)}")
r, col, tot = tn.collision_rate(l1)
print(f"collision rate: {col}/{tot} distinct reference words = {r:.1%}")
