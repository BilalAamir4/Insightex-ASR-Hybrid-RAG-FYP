# Fresh lecture `yt-YyXP7yCfOIU`: inter-annotator agreement (ADR-0048 Amendment 12)

Computed 27 Nov 2026 with `label_concepts.py agreement --lecture yt-YyXP7yCfOIU --a bilal --b fatima`, string rule only (no adjudications), on the 10 shared windows (3, 7, 9, 18, 19, 26, 30, 34, 40, 43). This is the same method used for Day 4 and the held-out lecture.

- A = Bilal's frozen `bilal_pre_review.json`: sha256 `84aec3fc04a6962bc004c73e5748fc844d6b0d58502d61015314bfb645936845`, commit `902edaf`, tag `m7-fresh-bilal-labels-frozen`.
- B = `fatima.json`: sha256 `d24ee89a1a0e851929f65a0865ed68df739f7cf6073371cf548d582c746fe48e`, commit `9f40623`, tag `m7-fresh-labels-frozen`.
- Sample manifest sha256: `1307741c2f97c64b4c8f89bfe2abeeb417e11aad2c5a7c5111a44be2c9c1e6fd`.
- Full per-window output: `tools/label_concepts/labels/yt-YyXP7yCfOIU/agreement_bilal_fatima.json`, sha256 `d0b681ee0a844c3a06ad8ba475c07168bdaee32abf4501abc404c70e39983c91`. It contains labels; do not open it before the review.

The figure was computed before any review or correction, and before any model read the lecture (the extraction hold is still set). This file records counts only.

## Figures

| Figure | Fresh `yt-YyXP7yCfOIU` | Held-out `yt-5vqk6HnITko` | Day 4 |
|---|---|---|---|
| **Concept F1, string rule (human ceiling)** | **0.400** | 0.190 | 0.240 |
| Concept P / R (B against A) | 0.500 / 0.333 | 0.222 / 0.167 | 0.273 / 0.214 |
| Matched / Bilal / Fatima | 2 / 6 / 4 | 2 / 12 / 9 | 3 / 14 / 11 |
| Relation agreement | n/a: no relation from either labeller on the shared windows | n/a (none) | 1 gold relation in the whole lecture (window 16) |
| Importance, same flag | 8 of 10 (0.800); Bilal flagged 1 window, Fatima 1, none in common | 9 of 10 (0.900) | not reported here |

The held-out and Day 4 columns are copied from `docs/evidence/m7/heldout/agreement.md` and `docs/labelling/m7_day4_agreement_review.md`; they were not re-run.

The counts are small: 6 and 4 concepts, 2 matched. One more or one fewer match moves F1 by about 0.2, so the 0.400 is not evidence that this lecture is easier to label than the other two.

## Per window (concept F1, string rule)

- **1.000:** windows 7 and 9, where both labellers gave one concept and they match. Also windows 26, 30 and 34, where both gave none; these count as agreement only through their zero counts.
- **0.000:** windows 3, 18, 19, 40 and 43.
- **Windows with any disagreement (concepts, relations or importance):** 5, namely 3, 18, 19, 40 and 43. The importance flag differs on 18 and 19, which are both also concept disagreements.

The tool prints relation F1 1.000 when both sets are empty. That is reported above as n/a.

## Relations across the three lectures (a fact, not a decision)

In the gold actually used, no human relation exists. Day 4 gold v2.1, the held-out gold, and this lecture's pre-review labels and Fatima's shared windows all have 0. The model predicted 5 relations on Day 4 (ADR-0050) and 24 on the held-out lecture (`docs/evidence/m7/heldout/readthrough.md`).

Day 4's v1 labels did have relations: Bilal had 6 before review, Fatima 1, and gold v1 1. They were dropped in the v2 relabel (Amendment 5) by decision, with relations to be evaluated on the held-out lecture instead. On the held-out lecture neither labeller recorded any.

Under decision 5, the relations and importance parts of (e) stay open on this lecture. No labels are changed to meet the minimums.

## Whole-lecture counts from `bilal_pre_review.json` (for Amendment 12, decision 5)

The pre-review gold labels have 22 concepts in 22 of the 48 windows, **0 relations** and **2 important windows**. Both counts are below decision 5's minimums (10 relations, 3 important windows). Unless the review changes them, the relations and importance parts of decision (e) stay open on this lecture. The review corrects shared windows only.

## Procedure notes

- **Order departure:** Fatima labelled her 10 windows before freeze A, at the same time as Bilal. The runbook (section 5) put her labelling after it. Sessions, as Bilal states them in `labelling.md`: Bilal from about 15:40 to 17:08, Fatima from about 16:30 to 17:20, on Bilal's machine. Bilal states that `bilal.json` was not edited after Fatima started.
- Both freezes (A, then B) were run on 27 Nov 2026, after both files were complete, with the runbook's commands and messages. `bilal.json` was last written at 17:08 and `fatima.json` at 17:20.
- Bilal reports that Fatima labelled on his machine without seeing `bilal.json`, and that they did not discuss any window.
- At the time of freezing, `labelling.md` had no entries. They were added on 27 Nov 2026, after both freezes and this agreement run, from Bilal's statements: self-containment YES; no guide-rule questions; Bilal did not read the no-speech or code-only indices. `labelling_fatima.md` was not created.

The ceiling is compared only with the model's string-rule-only concept F1 (Amendment 3). The next step is the review of Bilal's shared-window disagreements: corrections judged by the guide, logged with `log-correction`, shared windows only. The figure above is not recomputed after the review.
