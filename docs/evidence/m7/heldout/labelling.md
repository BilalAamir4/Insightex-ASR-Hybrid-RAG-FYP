# M7 held-out lecture: labelling record (handoff 4, step 5)

Lecture `yt-5vqk6HnITko`. Sample `sample.json` sha256 `807cb794c525b20ef2f48978e880d06dfb10b41ddeda7f26adfc4cfc2635bafb` (commit 68b63e7, committed before any labelling). Rules: ADR-0048 with Amendment 11.

## Who labelled what

| Labeller | Windows | File | sha256 at freeze |
|---|---|---|---|
| Bilal (gold labeller) | all 40 sampled windows | `bilal.json` | `e5eaaf77fd2034eeddd4d9c670c8b9bbd24a0d7a4082e981217b4b581d012dcb` |
| Fatima (second annotator, never gold) | the 10 shared windows 2, 5, 10, 14, 19, 26, 31, 36, 38, 43 | `fatima.json` | `7a249162a2c06970ca5f20f4f4ff05ab9efa5b4557101ba02584afe181cf5d2d` |

Both labelled separately in the labelling tool and did not discuss any window (Bilal, 15 Nov 2026). Fatima labelled her 10 windows in the labelling page, without seeing `bilal.json`. Both files passed `validate` (schema v1 validator; an important window must have a cue) before the freeze. Counts only: Bilal 37 concepts, 0 relations, 1 important window, 6 windows with no concept; Fatima 9 concepts, 0 relations, 0 important windows, 1 window with no concept.

**No relations.** Neither labeller recorded a relation, so the held-out relation scores have an empty gold and are not meaningful, as on Day 4 (one relation). The selection record expected relations on this lecture; that expectation was not met.

## Freeze

`bilal_pre_review.json` is a byte-identical copy of `bilal.json` at the freeze (all 40 windows, same sha256). It was committed and tagged with `fatima.json` (tag `m7-heldout-labels-frozen`) before `agreement` ran and before either labeller saw the other's labels. The whole file is frozen, not only the 10 shared windows: `validate` compares the current file with it, so a later change to any of the 30 non-shared windows is refused (Amendment 11 allows corrections on shared windows only). The inter-annotator figure uses the 10 shared windows of this copy.

## Disclosure: guide clarification during labelling

During labelling Bilal asked Claude (claude.ai, not this repository's sessions) how the guide treats one window in which the speaker only previews the topics of the video. Claude explained the guide's rule and pointed to the Day 4 window 0 worked example. It did not suggest any labels; the labels for that window are Bilal's decision. Recorded as guide clarification only. No model read the lecture's windows, and no model output for this lecture exists.

## Review and gold (19 Nov 2026)

After the agreement (`agreement.md`), Bilal reviewed his 10 shared windows. One correction, judged by the guide and logged with `log-correction` in `corrections_bilal.json` (sha256 `adcd4e0c43fcdee53bb773b449db6da8237f66ca0b56486d5af96164c0664ff7`); the entry's `amendment` field reads 3 because the tool knows only Amendments 3 and 4, and its reason names Amendment 11:

| Window | Before | After | Reason (Bilal) |
|---|---|---|---|
| 10 | True Positive, True Negative, False Positive, False Negative | Confusion Matrix | The main concept being explained from before that window was Confusion Matrix. |

The other 9 shared windows were kept. No non-shared window changed (`validate` compares with `bilal_pre_review.json`). The inter-annotator figure (0.190) is not recomputed.

`merge` wrote `gold.json` (single annotator, ADR-0048 Amendment 1 and 11: every window from the corrected `bilal.json`; Fatima's labels are never gold): sha256 `8c92dd27706ec4d7e19514f7d2653515ff0a683342df8d34deed03ff11fe23f7`, 40 windows, 34 concepts (10 distinct labels), 0 relations, 1 important window, 6 windows with no concept. Tag `m7-heldout-gold-frozen`. Corrected `bilal.json` sha256 `166a8638bd9697aeca86d0b260c35761b6770317f7f34664b58f34f224b9ea27`. Frozen before any model read the lecture.
