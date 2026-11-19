# M7 held-out lecture: inter-annotator agreement (ADR-0048 Amendment 11)

Computed 19 Nov 2026 with `label_concepts.py agreement --lecture yt-5vqk6HnITko --a bilal --b fatima`, string rule only (no adjudications), on the 10 shared windows (2, 5, 10, 14, 19, 26, 31, 36, 38, 43). A = Bilal's frozen `bilal_pre_review.json` (sha256 `e5eaaf77fd2034eeddd4d9c670c8b9bbd24a0d7a4082e981217b4b581d012dcb`, tag `m7-heldout-labels-frozen`), B = `fatima.json` (sha256 `7a249162a2c06970ca5f20f4f4ff05ab9efa5b4557101ba02584afe181cf5d2d`). Full per-window output: `tools/label_concepts/labels/yt-5vqk6HnITko/agreement_bilal_fatima.json` (sha256 `93827f86132a8f4a3303195c0626e4a282d458723971542166710eed4608eeb2`). Computed before any review or correction, and before any model read the lecture.

| Figure | Value |
|---|---|
| **Concept F1, string rule (the human ceiling)** | **0.190** (matched 2; Bilal 12, Fatima 9; P 0.222, R 0.167) |
| Relation agreement | not meaningful: neither labeller recorded a relation on the shared windows (the tool prints F1 1.000 for two empty sets; it is reported here as n/a) |
| Importance flag | same flag in 9 of 10 windows (0.900); Bilal flagged 1 window (14), Fatima none, so recall of Bilal's flag is 0.000 |

Per window, concept F1 is 1.000 on windows 2 (both empty), 5 and 14, and 0.000 on the other 7. Window 2 has no concepts from either labeller and counts as agreement in the micro figure only through its zero counts.

The ceiling is compared only with the model's string-rule-only concept F1, on all 40 windows and on the same 10 (Amendment 11). The review of Bilal's shared windows (corrections judged by the guide, logged with `log-correction`, shared windows only) comes next; the figure above is not recomputed after it.
