# ADR-0052: M7 comparison C3: single-window extraction calls kept (tie under the noise rule)

Status: Accepted
Date decided: 2026-11-09 (accepted by Bilal after review; drafted 2026-11-09)
Date recorded: 2026-11-09
Module: M7

Applies ADR-0048 (gate rules, sections 4, 6, 7 and 8; Amendments 8 and 9), ADR-0049 (harness call rules), ADR-0050 (Gemma 4 E4B) and ADR-0051 (original-language input).

## Context

C3 compares the unit of extraction on the Day 4 dev lecture (`sha256-de27cb67c2acbedebd0c2c7416932b8a`, 20 gold windows).

- **Arms:** both use Gemma 4 E4B (`gemma4:e4b`, digest `dc35e8d9c606…`), original-language input and no context.
  - **Arm A (kept on a tie):** one window per call, `C3-single`.
  - **Arm B:** batches of k = 5 windows per call, `C3-batch`. That makes 4 calls: (1, 2, 4, 6, 7), (8–12), (13–17) and (18–22).
- **Shared settings:**
  - the frozen extraction prompt version 2 (`c7e061fc…4648`), unchanged for batches (Amendment 9, decision 3); both arms have system message sha256 `f2d8742f…`;
  - `num_ctx` 8192 and 1,024 output tokens per target window (5,120 per batch call), temperature 0, seed 42, think false;
  - `keep_alive` 0, `truncate` false, and a run-start self-test that both arms passed.
- **k = 5** was confirmed on 9 Nov 2026 before the run (`C3/k_check.md`). The worst-case retry call (the five longest windows of the lecture, errors at the 1,500-character cap) is 2,932 + 5,120 = 8,052 of 8,192 tokens, a margin of 140, at 100% GPU. That margin is at least the 100 tokens below which Bilal would have chosen between 5 and 4.
- **Arm A is the C1 Gemma run, reused** under the identity rule (Amendment 9, decision 2; `C3/arm_a_reuse_check.md`). It was copied byte for byte into `C3/C3-single/`.
- **Arm B ran on 2026-11-09** with `--fresh`, so no cached reply was used and its cost is measured.
- **Gold and adjudication:** gold v2.1 only (Amendment 9, decision 1).
  - **The sheet:** blind and pooled from both arms, with no arm shown (`C3-gold_v2_1-20261109T140556Z.json`, seed 1845759876, sha256 `830811e4…4bf9`). It was committed before it was opened.
  - **The items:** 10 entries; Bilal decided all 10 as no-match.
  - **Frozen before any C3 score:** `adjudications_v2_1.json` (sha256 `790cee89…7634`, 33 decisions), tag `m7-c3-adjudications-v2.1-frozen`.
- **Blinding exposure** (`C3/blinding_exposure.md`). During the arm B run, part of a shell command's output showed raw arm B output for windows 19–22 on Bilal's screen, before any decision or score. One of the 10 sheet entries is in those windows.

## Decision

**Single-window extraction calls are kept.** Under the ADR-0048 section 7 noise rule, C3 is a tie, so arm A is kept:

| | Gold v2.1 |
|---|---|
| Per-window wins: single / batch / tied | 2 / 1 / 17 |
| Net wins for batches (adoption needs 3 or more) | −1 |
| Micro concept F1: single / batch | 0.320 / 0.296 |
| Decision | tie, keep arm A (single-window calls) |

Both arms are valid on every window. Batches also have the lower micro F1, so they would not be adopted even with enough net wins. The decided windows are:
- window 6 and window 16, won by single-window calls (per-window F1 0.67 against 0.50, and 0.80 against 0.50);
- window 19, won by batches (0.00 against 0.50).

**The decision does not depend on windows 19–22,** where the exposure happened:
- Without those four windows, the net wins for batches are −2.
- Even if all four were batch wins, the net would be +2, still under 3.
- Windows 20, 21 and 22 are tied, and window 19 is a batch win. So the exposure could not have moved the decision towards the arm kept.

C4 (previous-window context) runs on single-window calls. In `config/m7_arms.yaml`, the `batch_k` of `C4-window` and `C4-previous` is set to 1 (done at acceptance).

## Alternatives considered

- **Adopt batches of 5.** Rejected by the gate rule. Net wins are −1, not 3 or more, and the micro F1 is lower: batches predicted 29 concepts against 25 for the same 8 matches. Batches are 3.5× faster in wall time (51.2 s against 181.1 s, mainly 4 model loads instead of 20 under reload per call), at the same VRAM above baseline. That cost advantage does not adopt them under section 7.
- **k = 4.** Not needed. k = 5 passed the section 8 checks with a margin of at least the threshold Bilal set.
- **A batch-specific prompt.** Not made. The frozen prompt already describes batches, and a new prompt would be a new freeze requiring C1 and C2 to be re-run (section 2; Amendment 9, decision 3).
- **Rebuild the sheet after the exposure.** Not done. Section 4 needs a decision for every unmatched concept, and the decision does not depend on the exposed windows.

## Consequences

**Limitations to record with this decision:**

1. **Single annotator.** The gold is one annotator's labels (Bilal; ADR-0048 Amendment 1).
2. **Gold v2 is not blind to qwen3.5's prompt-iteration output** (Amendment 5), and gold v2.1 has one concept (window 16) added after seeing C1 output (Amendment 7). Arm A is that C1 run, and window 16 is one of arm A's wins.
3. **One gold version only** (Amendment 9).
4. **Blinding exposure for windows 19–22** (`C3/blinding_exposure.md`). Arm B's raw output for those windows was on Bilal's screen during the run, as he reported. The one sheet entry in those windows was therefore not blind. The decision is the same under any outcome in those windows (see Decision).
5. **The prompt was tuned on qwen3.5 with single-window calls** (ADR-0048 Consequences; Session 2b), with batch use only measured for length. This may tilt C3 towards arm A.
6. **Arm A's cost is not re-run.** It is the 18 Oct 2026 measurement. Arm B was measured on 9 Nov 2026 with a higher desktop baseline (2,334 against 1,520 MiB), so VRAM is compared above baseline.
7. **Small set.** 20 windows from one lecture, 17 of them tied. F1 is low for both arms (0.30 to 0.32). The held-out lecture is the check of the final configuration.
8. **No inter-annotator figure for gold v2 or v2.1** (Amendment 5, decision 5).
9. **Relations and importance are not evaluated on Day 4.** Gold v2.1 has no relations and no important windows. Relation P is 0 for both arms, and relation recall and importance P/R are undefined. Batches dropped 4 dangling relations against 1 for single windows; this is reported, not scored.
10. **Thin worst-case margin at k = 5** (140 tokens). The real batch calls had 598–709 tokens of room. On the held-out lecture, the ADR-0049 Amendment 2 gate check would apply, but C3 does not adopt batches, so it is not needed.

**Other consequences:**

- **Adjudication changed no score.** All 10 new decisions were no-match, and the adjudicated and string-rule-only figures are equal for both arms.
- **The M7 configuration for C4 and the held-out run:** Gemma 4 E4B, original-language input, one window per call. C4 decides previous-window context.
- **Production (Session 3)** may still batch for speed. That would be a separate decision with its own evidence, because C3 measured only that batching does not improve quality on Day 4.
  - Most of batching's speed-up came from fewer model reloads under `keep_alive` 0 (4 loads instead of 20, about 6–7 s each). So Session 3 should first consider keeping the model loaded between single-window calls, as a separate decision with its own evidence (ADR-0049's reproducibility finding applies).

## Evidence

- **Runs:**
  - arm A: `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C3/C3-single/`, copied from `C1/C1-gemma4-e4b/`, with `reused_from.json`;
  - arm B: `C3/C3-batch/` (commit `49fcbd7`).
- **Arm A reuse check:** `C3/arm_a_reuse_check.md` and `.json`, with `C3/scripts/arm_a_reuse_check.py`.
- **k check:** `C3/k_check.md`, with the measurement `docs/measurements/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/gemma4_e4b_20261109T135953Z.json`.
- **Blinding exposure:** `C3/blinding_exposure.md`.
- **Comparison report:** `C3/compare_C3_gold_v2_1.json` (`label_concepts.py compare --gold v2.1 --comparison C3`).
- **Gold and decisions:** `gold_v2_1.json` `53248bbb…7d2c` (tag `m7-day4-gold-v2.1-frozen`); `adjudications_v2_1.json` `790cee89…7634` (tag `m7-c3-adjudications-v2.1-frozen`).

**Scores** (micro concept, gold v2.1; adjudicated, which here equals string rule only):

| | Single (arm A) | Batch k = 5 (arm B) |
|---|---|---|
| Matched / predicted / gold | 8 / 25 / 25 | 8 / 29 / 25 |
| Precision | 0.320 | 0.276 |
| Recall | 0.320 | 0.320 |
| F1, adjudicated (primary) | 0.320 | 0.296 |
| F1, string rule only | 0.320 | 0.296 |

**Validity:**

| | Single | Batch |
|---|---|---|
| Valid windows | 20 of 20 | 20 of 20 |
| Needed the retry | 0 | 0 |
| Valid but empty after the retry | 0 | 0 |
| Dropped relations | 1 | 4 |
| Calls refused as too long / over the real budget | 0 / 0 | 0 / 0 |

**Cost** (measured, no cache hits):

| | Single (18 Oct 2026, C1 run) | Batch k = 5 (9 Nov 2026) |
|---|---|---|
| Calls | 20 | 4 |
| Wall time | 181.1 s | 51.2 s |
| VRAM above baseline | 4,828 MiB | 4,829 MiB |
| VRAM peak, whole GPU (baseline) | 6,348 MiB (1,520) | 7,163 MiB (2,334) |
| Largest prompt | 1,927 tokens | 2,474 tokens (smallest margin 598) |
| Tokens per second | 136.7 | 156.5 |
| `ollama ps` at the largest prompt | 100% GPU, `num_ctx` 8192 | 100% GPU, `num_ctx` 8192 |

Residency: arm B's VRAM above baseline equals arm A's, its decode speed is higher, and its model loads took 6.6–7.4 s, the usual Gemma reload. Nothing indicates that layers left the GPU.

## Gate / revisit when

- **Accepted.** Bilal reviewed and accepted this ADR on 2026-11-09, adding the production note on model reloads.
- **The held-out lecture.** Revisit if the held-out run shows single-window extraction far below the Day 4 figures. That run is reported once and does not reopen C3 by itself (ADR-0048).
- **Production speed.** If Session 3 needs batching for throughput, that is a new decision with its own evidence.
