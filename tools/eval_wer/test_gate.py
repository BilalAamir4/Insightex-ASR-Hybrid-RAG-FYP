"""Synthetic checks for gate_metrics / textnorm. Run: python test_gate.py"""
import numpy as np

import gate_metrics as g
import textnorm as tn


def dp_lev(a, b):
    p = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        c = [i]
        for j, y in enumerate(b, 1):
            c.append(min(p[j] + 1, c[-1] + 1, p[j - 1] + (x != y)))
        p = c
    return p[-1]


rng = np.random.default_rng(0)
for _ in range(300):
    a = "".join(rng.choice(list("abcd"), rng.integers(0, 40)))
    b = "".join(rng.choice(list("abcd"), rng.integers(0, 40)))
    assert g.lev(a, b) == dp_lev(a, b), (a, b)

ref = "the cat sat on the mat today".split()
s = g.score(ref, "the bat sat the mat today".split(), [False] * 7)
assert (s["S"], s["D"], s["I"]) == (1, 1, 0), s
s = g.score(ref, "the cat sat on the mat today extra words here".split(), [False] * 7)
assert (s["S"], s["D"], s["I"], s["trimmed"]) == (0, 0, 0, 3), s  # cut tail is free
s = g.score(ref, "the cat extra sat on the mat today".split(), [False] * 7)
assert s["I"] == 1 and s["D"] == 0, s
# wildcard absorbs any number of hypothesis words and counts no errors
w = [False, False, True, False, False]
s = g.score("a b X c d".split(), "a b p q r c d".split(), w)
assert (s["S"], s["D"], s["I"], s["N"]) == (0, 0, 0, 4), s
s = g.score("a b X c d".split(), "a b c d".split(), w)
assert (s["S"], s["D"], s["I"]) == (0, 0, 0), s
# long deletion run is reported
ref2 = [f"w{i}" for i in range(30)]
hyp2 = ref2[:10] + ref2[22:]
s = g.score(ref2, hyp2, [False] * 30)
r = g.deletion_runs(s, [(i, i + 1.0) for i in range(len(hyp2))])
assert len(r) == 1 and r[0]["words"] == 12, r
# normalisation
assert tn.l1_tokens("Theek hai, Okay?") == ["thek", "hai", "okay"]
assert [tn.l2_token(x) for x in ("hai", "hye", "ho", "hu", "kya", "kia", "ke", "ki", "ka")] == \
    ["hE", "hE", "hO", "hO", "kA", "kA", "kE", "kI", "kA"]
# energy VAD: silence / tone / silence
sr = 16000
x = np.concatenate([np.random.default_rng(1).normal(0, 1e-4, sr * 2),
                    0.3 * np.sin(2 * np.pi * 220 * np.arange(sr * 2) / sr) * (1 + 0.1 * np.random.default_rng(2).normal(size=sr * 2)),
                    np.random.default_rng(3).normal(0, 1e-4, sr * 2)]).astype("float32")
mask, _ = g.energy_vad(x)
rr = g.runs(mask)
assert len(rr) == 1 and abs(rr[0][0] / 100 - 2) < 0.1 and abs(rr[0][1] / 100 - 4) < 0.1, rr
d = g.dropped_speech(mask, [{"start": 2.0, "end": 3.0}])
assert abs(d["uncovered_s"] - 1.0) < 0.1 and abs(d["longest_gap_s"] - 1.0) < 0.1, d
print("all checks passed")
