# ADR-0051: M7 comparison C2: original-language input kept for extraction (tie under the noise rule)

Status: Proposed
Date decided: not decided (drafted 2026-11-09, for Bilal's review)
Date recorded: 2026-11-09
Module: M7

Applies ADR-0048 (gate rules, sections 4, 6 and 7; Amendment 8), ADR-0049 (harness call rules) and ADR-0050 (Gemma 4 E4B, the C1 winner).

## Context

C2 compares two ways of feeding the extraction model on the Day 4 dev lecture (`sha256-de27cb67c2acbedebd0c2c7416932b8a`, 20 gold windows).

- **Arms:** both use Gemma 4 E4B (`gemma4:e4b`, digest `dc35e8d9c606…`), single windows and no previous-window context.
  - **Arm A (kept on a tie):** the original code-switched transcript, `C2-original`.
  - **Arm B:** a per-window English translation made by Gemma, `C2-english` (ADR-0041).
- **Shared settings:**
  - extraction prompt version 2 (`c7e061fc…4648`);
  - `num_ctx` 8192, `num_predict` 1024 per window, temperature 0, seed 42, think false;
  - `keep_alive` 0, `truncate` false, and a run-start self-test that both arms passed.
- **Translation (arm B):**
  - **Prompt:** one frozen prompt, `config/prompts/m7_translate_v2.txt` (sha256 `dfc9aa5cd904…49a8`, tag `m7-c2-translate-prompt-frozen`), with its own frozen retry template.
  - **English check:** at most 10% of a reply's letters may be Arabic-script or Devanagari.
  - **Stage:** the translations are stored per window, keyed by the window text sha256, the model digest and the prompt sha256 (harness version 8).
  - **Approval:** the prompt was checked on the reserved windows 0, 3 and 5 only and approved before any C2 arm B run.
- **Arm A is the C1 Gemma run, reused** (Amendment 8, decision 2). Everything that affects original-language extraction is identical to C1. All 20 rebuilt requests have C1's cache keys, and C1's replies re-parse to C1's `extraction.json`. The run files were copied byte for byte into `C2/C2-original/`.
- **Arm B ran on 2026-11-09** with `--fresh`, so no cached reply was used and its cost is measured.
- **Gold:** v2.1 only (Amendment 8, decision 1).
- **Adjudication:**
  - **The sheet:** blind and pooled from both arms, with no arm shown (`C2-gold_v2_1-20261108T225357Z.json`, seed 2098278477, sha256 `9b78735f…dc90`). It was committed before it was opened.
  - **The item:** it had 1 entry; the 22 decisions carried for v2.1 were reused. Bilal decided it as no-match (window 18).
  - **Frozen before any C2 score:** `adjudications_v2_1.json` (sha256 `c8c5ac00…824e`, 23 decisions), tag `m7-c2-adjudications-v2.1-frozen`.

## Decision

**Original-language input is kept for M7 extraction.** Under the ADR-0048 section 7 noise rule, C2 is a tie, so arm A is kept:

| | Gold v2.1 |
|---|---|
| Per-window wins: original / English / tied | 1 / 0 / 19 |
| Net wins for English (adoption needs 3 or more) | −1 |
| Micro concept F1: original / English | 0.320 / 0.292 |
| Decision | tie, keep arm A (original-language input) |

Both arms are valid on every window. The English arm also has the lower micro F1, so it would not be adopted even with enough net wins. The one decided window is window 16 (per-window F1: original 0.80, English 0.50).

Later comparisons use this winner. C3 (single window against batches of k = 5) and C4 (previous-window context, with the context in the original language) run on Gemma with original-language input. The `input` fields of the C3 and C4 arms in `config/m7_arms.yaml` are set to `original` after this ADR is accepted.

## Alternatives considered

- **Adopt English input.** Rejected by the gate rule. Its net wins are −1, not 3 or more, and its micro F1 is lower. It also costs 1.85× the wall time (a translation call per window) and a higher VRAM peak.
- **Score against both gold v2 and v2.1, as in C1.** Rejected in Amendment 8, decision 1. The window 16 concept is part of the frozen gold, and C1's decision did not depend on it.
- **Re-run arm A.** Not needed: the reuse check showed every input to original-language extraction is identical to the C1 run (Amendment 8, decision 2).
- **A third translation prompt.** Not made. Two prompt versions gave nearly the same output at temperature 0 (see Consequences), and more tuning on three reserved windows would risk fitting them.

## Consequences

**Limitations to record with this decision:**

1. **Single annotator.** The gold is one annotator's labels (Bilal; ADR-0048 Amendment 1).
2. **Gold v2 is not blind to qwen3.5's prompt-iteration output** (Amendment 5), and gold v2.1 has one concept (window 16, "Hardware Limitation") added after seeing C1 output (Amendment 7). Arm A is that C1 run. The only window where the arms differ is window 16.
3. **One gold version only.** Unlike C1, there is no cross-version check (Amendment 8).
4. **Known translation errors in arm B** (`C2/translation_prompt_freeze.md`). On the reserved windows, Gemma added a count in window 0 ("three types"; the speaker gives none) and gave window 5's opening fragment the wrong meaning. Two prompt versions, v2 adding a rule against exactly these, did not change Gemma's output at temperature 0. Arm B therefore measures Gemma's own translation, errors included. Whether the gold windows' translations have similar errors was not checked; they are not shown (Amendment 8, decision 3).
5. **The extraction prompt was tuned on qwen3.5 with original-language input** (ADR-0048 Consequences). It was not written for English input, which may tilt C2 towards arm A.
6. **Arm A's cost is not re-run.** It is the 18 Oct 2026 measurement. Arm B was measured on 9 Nov 2026, with a VRAM baseline 53 MiB higher (the Windows desktop shares the GPU).
7. **Small set.** 20 windows from one lecture, 19 of them tied. F1 is low for both arms (0.29 to 0.32). The held-out lecture is the check of the final configuration.
8. **No inter-annotator figure for gold v2 or v2.1** (Amendment 5, decision 5), so no human ceiling is placed next to the model F1.
9. **Relations and importance are not evaluated on Day 4.** Gold v2.1 has no relations and no important windows. Relation P is 0 for both arms (relation recall is undefined), and importance P/R is undefined.

**Other consequences:**

- **Adjudication changed no score.** The new decision was a no-match, and the adjudicated and string-rule-only figures are equal for both arms.
- **The translation stage stays** in the harness for evaluation (harness version 8). The production extraction stage (Session 3) needs no translation step.
- **What changes in the code.** In `config/m7_arms.yaml`, the `input` fields of the C3 and C4 arms are set to `original`, after this ADR is accepted.

## Evidence

- **Runs:**
  - arm A: `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C2/C2-original/`, copied from `C1/C1-gemma4-e4b/`, with `reused_from.json`;
  - arm B: `C2/C2-english/` (`run.json`, `extraction.json`, `calls.jsonl`; commit `7476122`).
- **Arm A reuse check:** `C2/arm_a_reuse_check.md` and `.json`, with `C2/scripts/arm_a_reuse_check.py`.
- **Translation prompt freeze:** `C2/translation_prompt_freeze.md`, plus the test reports in `C2/translate_check/` (reserved windows 0, 3 and 5 only).
- **Comparison report:** `C2/compare_C2_gold_v2_1.json` (`label_concepts.py compare --gold v2.1 --comparison C2`).
- **Gold and decisions:** `gold_v2_1.json` `53248bbb…7d2c` (tag `m7-day4-gold-v2.1-frozen`); `adjudications_v2_1.json` `c8c5ac00…824e` (tag `m7-c2-adjudications-v2.1-frozen`).

**Scores** (micro concept, gold v2.1; adjudicated, which here equals string rule only):

| | Original (arm A) | English (arm B) |
|---|---|---|
| Matched / predicted / gold | 8 / 25 / 25 | 7 / 23 / 25 |
| Precision | 0.320 | 0.304 |
| Recall | 0.320 | 0.280 |
| F1, adjudicated (primary) | 0.320 | 0.292 |
| F1, string rule only | 0.320 | 0.292 |

**Validity:**

| | Original | English |
|---|---|---|
| Valid windows | 20 of 20 | 20 of 20 |
| Needed the retry | 0 | 0 |
| Valid but empty after the retry | 0 | 0 |
| Dropped relations | 1 | 1 |
| Translation failures / translation retries | n/a | 0 / 0 |

**Cost** (measured, no cache hits):

| | Original (18 Oct 2026, C1 run) | English (9 Nov 2026) |
|---|---|---|
| Wall time | 181.1 s (20 calls) | 335.7 s (40 calls: translation 162.4 s, extraction 165.1 s) |
| VRAM peak (whole GPU) | 6,348 MiB | 6,611 MiB (translation phase 6,611, extraction 6,588) |
| VRAM above baseline | 4,828 MiB | 5,038 MiB |
| Largest extraction prompt | 1,927 tokens | 1,919 tokens |
| Tokens per second | 136.7 | 142.1 |
| `ollama ps` at the largest prompt | 100% GPU, `num_ctx` 8192 | 100% GPU, `num_ctx` 8192 |

## Gate / revisit when

- **Acceptance.** This ADR is Proposed and awaits Bilal's review.
- **The held-out lecture.** Revisit if the held-out run shows original-language extraction far below the Day 4 figures. That run is reported once and does not reopen C2 by itself (ADR-0048).
- **The translation model.** Revisit if a later model or Ollama version changes Gemma's translation, since the known errors are part of arm B.
