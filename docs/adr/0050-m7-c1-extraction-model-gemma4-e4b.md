# ADR-0050: M7 comparison C1: Gemma 4 E4B kept as the extraction model (tie under the noise rule)

Status: Accepted
Date decided: 2026-10-25 (accepted by Bilal after review; drafted 2026-10-22)
Date recorded: 2026-10-22
Module: M7

Applies ADR-0048 (gate rules, sections 4, 6 and 7; Amendments 5 to 7) and ADR-0049 (harness call rules). It settles the "LLM choice (qwen3.5 vs Gemma 4 E4B, M7)" open decision, for concept extraction only.

## Context

C1 compares the two candidate extraction models on the Day 4 dev lecture (`sha256-de27cb67c2acbedebd0c2c7416932b8a`, 20 gold windows).

- **Arms:** arm A is Gemma 4 E4B (`gemma4:e4b`, digest `dc35e8d9c606…`), the model with the smaller measured VRAM peak, which a tie keeps. Arm B is qwen3.5 (`qwen3.5:latest`, digest `44a38603922e…`).
- **Settings:**
  - single-window calls, original-language transcript, no previous-window context;
  - frozen prompt version 2 (`c7e061fce838d935c7335b01746fbec8c708f2d1f3845720c8e5728ac7154648`), harness version 7;
  - `num_ctx` 8192, `num_predict` 1024 per window, temperature 0, seed 42, think false;
  - `keep_alive` 0 (reload per call), `truncate` false, and the run-start self-test passed on both models.
- **Runs:** both arms ran on 18 Oct 2026 and were measured, with no cached replies.
- **Gold:** gold v1 was replaced before any C1 score was computed. Bilal relabelled Day 4 as gold v2 (Amendments 5 and 6). Gold v2.1 is gold v2 plus one concept (window 16, "Hardware Limitation") that was added after seeing model output during adjudication (Amendment 7). C1 is scored under both v2 and v2.1, and is decided only if both give the same decision.
- **Adjudication:**
  - The blind sheet against gold v2 had 23 items, pooled from both arms with no arm shown (`C1-gold_v2-20261022T140229Z.json`, seed 1976949482). It was committed before any decision.
  - Bilal decided all 23 (`adjudications_v2.json`, tag `m7-c1-adjudications-v2-frozen`).
  - For gold v2.1, 22 decisions were carried over. The window 16 item matches the added concept by the string rule, and the gold v2.1 sheet had 0 items (tag `m7-day4-gold-v2.1-frozen`).

## Decision

**Gemma 4 E4B is kept as the M7 extraction model.** Under the ADR-0048 section 7 noise rule, C1 is a tie on both gold versions, so arm A is kept:

| | Gold v2 | Gold v2.1 |
|---|---|---|
| Per-window wins: Gemma / qwen3.5 / tied | 2 / 2 / 16 | 2 / 2 / 16 |
| Net wins for qwen3.5 (adoption needs 3 or more) | 0 | 0 |
| Decision | tie, keep arm A (Gemma) | tie, keep arm A (Gemma) |

Both arms are valid on every window. qwen3.5's micro concept F1 is higher on both gold versions (0.304 vs 0.286 on v2, 0.340 vs 0.320 on v2.1). The rule adopts arm B only with net wins of 3 or more and a micro F1 that is not lower, so the F1 difference alone does not adopt it.

Later comparisons use this winner: C2 and C3 take Gemma, and C3 uses Gemma's k (5, ADR-0049). Under ADR-0048's prompt freeze, the frozen prompt is re-checked on Gemma: the validity rule (passed, below), plus a read-through of its output. Gemma gets no tuning of its own.

## Alternatives considered

- **Adopt qwen3.5 on its higher micro F1.** Rejected by the gate rule. With 20 windows one window is 5 points, so section 7 requires net wins of 3 or more, and here they are 0. qwen3.5 also needs about 1.3 GB more VRAM at its peak (about 7.6 GB of the 8 GB card, versus 6.3 GB), and it is slower in tokens per second.
- **Score against gold v1.** Rejected in Amendment 5: gold v1 breaks the guide's explanation rule and uses several names for one concept.
- **Score against gold v2.1 only.** Rejected in Amendment 7: gold v2.1 has one concept added after seeing model output, so the decision must hold on gold v2 too.

## Consequences

**Limitations to record with this decision:**

1. **Single annotator.** The gold is one annotator's labels (Bilal; ADR-0048 Amendment 1).
2. **Gold v2 is not blind to qwen3.5's prompt-iteration output** (Amendment 5). The prompt-iteration reports Bilal approved showed qwen3.5's extra and missed concepts by window. No Gemma output was shown.
3. **One concept added after seeing model output** (Amendment 7): gold v2.1, window 16, "Hardware Limitation". The decision is the same with and without it.
4. **The prompt was tuned on qwen3.5 only** (ADR-0048 Consequences). This, and limitation 2, tilt C1 towards qwen3.5. The tie still went to Gemma.
5. **No inter-annotator figure for gold v2.** The v1 figure (0.240) was measured on labels gold v2 replaces, so no human ceiling is placed next to the model F1 (Amendment 5, decision 5).
6. **Relations are not evaluated on Day 4.** Gold v2 has no relations (`docs/labelling/m7_day4_gold_v2.md`), so Day 4 relation scores are not computed and C1 says nothing about relation extraction. Relations are evaluated on the held-out lecture. Each arm predicted 5 relations; they are not scored.
7. **Small set.** 20 windows from one lecture, and 16 of them tied. The F1 values are low for both models (about 0.29 to 0.34), and the held-out lecture is the check of the final configuration.

**Other consequences:**

- **Adjudication changed no score.** One of the 23 decisions was a match, but its gold concept was already matched by the string rule, and section 4 uses an adjudicated match only when that gold concept is still unmatched. So the adjudicated and string-rule-only figures are equal for both arms on both gold versions.
- **No importance signal.** No window in either gold version is important, and neither arm flagged one, so importance P/R is undefined on Day 4.
- **What changes in the code.** `config/m7_arms.yaml`: the null `model` fields of the C2 to C4 arms are set to `gemma4:e4b`, after this ADR is accepted.

## Evidence

- **Runs:** `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C1/C1-gemma4-e4b/` and `C1-qwen3.5/` (`run.json`, `extraction.json`, `calls.jsonl`; commit `67b4686`).
- **Comparison reports** (`label_concepts.py compare --gold v2|v2.1`): `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C1/compare_C1_gold_v2.json` and `compare_C1_gold_v2_1.json`.
- **Gold:** `gold_v2.json` `19837236…55be` (tag `m7-day4-gold-v2-frozen`) and `gold_v2_1.json` `53248bbb…7d2c` (tag `m7-day4-gold-v2.1-frozen`).
- **Decisions:** `adjudications_v2.json` `7caa4a72…f0e6` (tag `m7-c1-adjudications-v2-frozen`) and `adjudications_v2_1.json`.

**Scores** (micro concept; adjudicated, which here equals string rule only):

| | Gemma, gold v2 | qwen3.5, gold v2 | Gemma, gold v2.1 | qwen3.5, gold v2.1 |
|---|---|---|---|---|
| Matched / predicted / gold | 7 / 25 / 24 | 7 / 22 / 24 | 8 / 25 / 25 | 8 / 22 / 25 |
| Precision | 0.280 | 0.318 | 0.320 | 0.364 |
| Recall | 0.292 | 0.292 | 0.320 | 0.320 |
| F1, adjudicated (primary) | 0.286 | 0.304 | 0.320 | 0.340 |
| F1, string rule only | 0.286 | 0.304 | 0.320 | 0.340 |

**Validity:**

| | Gemma | qwen3.5 |
|---|---|---|
| Valid windows | 20 of 20 | 20 of 20 |
| Needed the retry | 0 | 0 |
| Valid but empty after the retry | 0 | 0 |
| Dropped relations | 1 | 0 |

**Cost** (18 Oct 2026, measured, 20 calls each):

| | Gemma 4 E4B | qwen3.5 |
|---|---|---|
| Wall time | 181.1 s | 159.1 s |
| VRAM peak (whole GPU) | 6,348 MiB | 7,633 MiB |
| VRAM above baseline | 4,828 MiB | 6,092 MiB |
| Largest prompt | 1,927 tokens | 1,970 tokens |
| Tokens per second | 136.7 | 56.7 |

## Gate / revisit when

- **Accepted.** Bilal reviewed and accepted this ADR on 2026-10-25, with no changes.
- **The Gemma re-check.** Revisit if the read-through of Gemma's output under the frozen prompt shows a systematic problem the scores do not.
- **The held-out lecture.** Revisit if the held-out run of the final configuration shows extraction far below the Day 4 figures. That run is reported once and does not reopen C1 by itself (ADR-0048).
- **VRAM.** Revisit if Gemma's VRAM use or residency changes in a new Ollama version (ADR-0049's residency check).
