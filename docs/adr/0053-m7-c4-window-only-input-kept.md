# ADR-0053: M7 comparison C4: window-only input kept (previous-window context rejected on validity)

Status: Proposed
Date decided: not decided (drafted 2026-11-09, for Bilal's review)
Date recorded: 2026-11-09
Module: M7

Applies ADR-0048 (section 7; Amendments 2 and 10), ADR-0049 (harness call rules) and ADRs 0050 to 0052 (Gemma 4 E4B, original-language input, single-window calls).

## Context

C4 (ADR-0048 Amendment 2) compares window-only input with the previous grid window supplied as read-only context, on the Day 4 dev lecture (`sha256-de27cb67c2acbedebd0c2c7416932b8a`, 20 gold windows).

- **Arms:** both use Gemma 4 E4B (`gemma4:e4b`, digest `dc35e8d9c606…`), original-language input and one window per call.
  - **Arm A (kept on a tie):** the window only, `C4-window`.
  - **Arm B:** the window plus its previous grid window, `C4-previous`. Every target has a previous window. Windows 1, 4 and 6 have the reserved windows 0, 3 and 5 as context.
- **Prompts:**
  - **Arm A:** the frozen extraction prompt version 2 (`c7e061fc…4648`), system message `f2d8742f…`.
  - **Arm B:** the same prompt plus the frozen context block `config/prompts/m7_context_block_v1.txt` (`3132e2f9…912e`, tag `m7-c4-context-block-frozen`), system message `57536dad…d68e`. For context calls only, the block overrides the prompt's unnamed-concept sentence, mirroring the labelling guide (Amendment 10, decision 4).
  - **Shared settings:** `num_ctx` 8192, `num_predict` 1024, temperature 0, seed 42, think false, `keep_alive` 0, `truncate` false; both arms passed the self-test.
- **Checks before the run:**
  - **Budget:** the worst case (target 21 with window 20, as a retry) is 2,760 + 1,024 = 3,784 of 8,192, a margin of 4,408, at 100% GPU, 4,765 MiB above baseline (`C4/context_check.md`).
  - **Gold overlap:** the block shares no 3-, 4- or 5-word sequence with the gold windows.
- **Arm A is the C1 Gemma run, reused** under the identity rule (Amendment 10, decision 2; `C4/arm_a_reuse_check.md`).
- **Arm B ran on 2026-11-09** with `--fresh`, so its cost is measured.
- **Blinding:** results were read only through `docs/evidence/m7/scripts/validity_cost.py` until the decisions were frozen. The cause of window 6's invalidity was identified by matching its errors against the validator's messages, printing only the name of the rule.
- **Adjudication (for the informational scores):**
  - **The sheet:** blind and pooled from both arms (`C4-gold_v2_1-20261109T143053Z.json`, seed 802688807, sha256 `b7beb892…6e67`), committed before it was opened.
  - **The items:** 3 entries, 1 of them in windows 1, 4 or 6; all 3 decided as no-match.
  - **Frozen before any C4 score:** `adjudications_v2_1.json` (sha256 `72522b11…d199`, 36 decisions), tag `m7-c4-adjudications-v2.1-frozen`.

## Decision

**Window-only input is kept. C4 is decided by the validity rule (ADR-0048 section 7), not by scores.**

- **Arm B is rejected:** it fails the validity rule. Window 6 is invalid after its one retry. Both attempts broke the validator rule "head and tail are the same concept": a relation from a concept to itself, possibly under two of its names. Section 7 drops only dangling relations before validation, so this makes the window invalid.
- **Arm A is valid on all 20 windows.**
- **Only one arm failed,** so section 7's "both arms fail" clause (fix the validation, re-freeze, re-run both) does not apply.
- **Nothing is changed after seeing the result:** not the context block, not the validation, and nothing is re-run. Changing either now would be tuning on C4 output.

The final M7 configuration for the held-out lecture is therefore:
- Gemma 4 E4B (ADR-0050);
- the original-language transcript (ADR-0051);
- one window per call (ADR-0052);
- no previous-window context (this ADR);
- the frozen extraction prompt version 2 (`c7e061fc…4648`) alone, without the context block.

**Informational scores** (they decide nothing; arm B is already rejected). Against gold v2.1, with adjudication:

| | Window only (arm A) | With previous window (arm B) |
|---|---|---|
| Per-window wins / tied | 4 / 16 | 0 / 16 |
| Net wins for arm B | −4 | |
| Micro concept F1 | 0.320 | 0.259 |

Arm A's wins are windows 1, 6, 7 and 16. Window 6 counts for arm A because arm B has no valid record there. Arm B would not have been adopted even if it had been valid on window 6: without window 6 its net wins are still −3, and its micro F1 is lower.

## Alternatives considered

- **Score-based decision.** Not used: section 7 rejects an invalid arm regardless of its score. The informational scores point the same way.
- **Drop a self-relation like a dangling relation, then re-validate.** Rejected for C4: it would change a gate rule after seeing C4's output. It is recorded as a Session 3 question (see Consequences).
- **Change the context block and re-run C4.** Rejected under the freeze rule (Amendment 10, decision 3).
- **Skip scoring arm B.** Bilal chose to score it for information, so that the effect of context on the other 19 windows is on record for later decisions.

## Consequences

**Limitations to record with this decision:**

1. **Single annotator.** The gold is one annotator's labels (Bilal; ADR-0048 Amendment 1).
2. **Gold v2 is not blind to qwen3.5's prompt-iteration output** (Amendment 5), and gold v2.1 has one concept (window 16) added after seeing C1 output (Amendment 7). Window 16 is one of arm A's informational wins.
3. **One gold version only** (Amendment 10).
4. **Decided by one window's validity.** C4 rests on a single invalid window (6), and on one rule that a production stage might handle differently (see Session 3 below). It says that this configuration of context failed the gate on Day 4, not that context cannot help.
5. **Windows 1, 4 and 6 have reserved-window context** whose English glosses are the frozen prompt's worked examples (Amendment 10, Consequences).
   - **Informational dependence:** without windows 1, 4 and 6 the wins are arm A 2 (windows 7 and 16), arm B 0, tied 15, so arm B's net is −2. Even if all three had gone to arm B, its net would be +1, under 3.
   - **The validity decision does depend on this group:** the one invalid window (6) is in it, with reserved window 5 as context. Whether the gloss-plus-original combination contributed to the self-relation is not known and was not tested.
6. **The context block was not reply-tested before the freeze** (Amendment 10, decision 5, by Bilal's choice). Its first model outputs were the C4 run.
7. **The prompt was tuned on qwen3.5 without context** (ADR-0048 Consequences). The block is one fixed addition with no tuning, which may tilt C4 towards arm A.
8. **Arm A's cost is not re-run** (18 Oct 2026). Arm B was measured on 9 Nov 2026 with a higher desktop baseline (2,707 against 1,520 MiB), so VRAM is compared above baseline.
9. **Small set.** 20 windows from one lecture, 16 of them tied. F1 is low for both arms.
10. **No inter-annotator figure for gold v2 or v2.1** (Amendment 5, decision 5).
11. **Relations and importance are not evaluated on Day 4.** Gold v2.1 has none. Arm B flagged at least one window as important, so its importance precision is 0; arm A flagged none. This is informational only.
12. **Carry-over** (Amendment 10, decision 8; `C4/c4_informational.json`). This counts model concepts that string-match a gold concept of the previous window but none of the target window, over the 17 targets whose previous window has gold.
    - **Result:** arm B 1 and arm A 1, the same concept in the same window (window 15, "batch learning"). On this measure, context added no carry-over beyond what window-only extraction already shows.
    - **What the measure misses:** concepts taken from a previous window that are not in that window's gold. Arm B predicted 29 concepts against arm A's 25, with fewer matches. Its extra false positives are not split into carry-over and others.

**Note for Session 3 (production extraction):**
- **Self-relations.** Production should consider dropping a relation whose head equals its tail, as dangling relations are dropped, instead of failing the window. This is a separate decision with its own evidence: it changes the validity handling and would apply to every configuration, not only context.
- **Context.** A context-aware production stage is not ruled out. It would also be a separate decision with its own evidence, ideally on the held-out lecture's labelling or a new dev set, not on Day 4 again.

**Other consequences:**

- **Adjudication changed no score.** All 3 new decisions were no-match.
- **The context block stays frozen** in `config/default.yaml` for the record. It is not used by the final configuration.
- **M7's comparisons are complete.** Next: the held-out Hindi lecture (still to be found; ADR-0048 section 2), which is run once with the final configuration, and Session 3.

## Evidence

- **Runs:**
  - arm A: `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C4/C4-window/`, copied from `C1/C1-gemma4-e4b/`, with `reused_from.json`;
  - arm B: `C4/C4-previous/` (commit `9b461a4`).
- **Checks:** `C4/arm_a_reuse_check.md`, `C4/context_check.md` (with the measurement `docs/measurements/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/gemma4_e4b_20261109T142239Z.json`) and `C4/overlap_m7_context_block_v1.txt`.
- **Comparison report:** `C4/compare_C4_gold_v2_1.json`.
- **Informational figures:** `C4/c4_informational.json`, from `C4/scripts/c4_informational.py`.
- **Gold and decisions:** `gold_v2_1.json` `53248bbb…7d2c`; `adjudications_v2_1.json` `72522b11…d199` (tag `m7-c4-adjudications-v2.1-frozen`).

**Validity:**

| | Window only | With previous window |
|---|---|---|
| Valid windows | 20 of 20 | **19 of 20** (window 6 invalid: head and tail the same concept, both attempts) |
| Needed the retry / recovered by it | 0 / 0 | 2 / 1 (window 14 recovered) |
| Valid but empty after the retry | 0 | 0 |
| Dropped dangling relations | 1 | 3 |
| Calls refused as too long / over the real budget | 0 / 0 | 0 / 0 |

**Informational scores** (micro concept, gold v2.1; adjudicated, which here equals string rule only; arm B has no record for window 6):

| | Window only | With previous window |
|---|---|---|
| Matched / predicted / gold | 8 / 25 / 25 | 7 / 29 / 25 |
| Precision | 0.320 | 0.241 |
| Recall | 0.320 | 0.280 |
| F1 | 0.320 | 0.259 |

**Cost** (measured, no cache hits):

| | Window only (18 Oct 2026, C1 run) | With previous window (9 Nov 2026) |
|---|---|---|
| Calls | 20 | 22 (2 retries) |
| Wall time | 181.1 s | 206.8 s |
| VRAM above baseline | 4,828 MiB | 4,775 MiB |
| VRAM peak, whole GPU (baseline) | 6,348 MiB (1,520) | 7,482 MiB (2,707) |
| Largest prompt | 1,927 tokens | 2,349 tokens (margin 4,819) |
| Tokens per second | 136.7 | 127.8 |
| `ollama ps` at the largest prompt | 100% GPU, `num_ctx` 8192 | 100% GPU, `num_ctx` 8192 |

Residency: arm B's VRAM above baseline is within 53 MiB of arm A's, and its reloads took 6.8–7.1 s. Its slightly lower decode speed fits its longer prompts. Nothing indicates that layers left the GPU.

## Gate / revisit when

- **Acceptance.** This ADR is Proposed and awaits Bilal's review.
- **Session 3.** Revisit the self-relation handling and, separately, context-aware extraction, each with its own evidence.
- **The held-out lecture.** It runs once with the final configuration above, and does not reopen C4 by itself (ADR-0048).
