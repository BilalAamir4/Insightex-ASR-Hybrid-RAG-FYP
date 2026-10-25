# Insightex M7 handoff 3 (25 Oct 2026): after C1, before C2

For a fresh session. Read this first, then `CLAUDE.md`, ADR-0048 (with Amendments 1 to 7), ADR-0049 (with Amendments 1 and 2) and ADR-0050. Trust the files over this summary when they differ.

## 1. Where M7 stands

**Lecture.** Day 4 (`sha256-de27cb67c2acbedebd0c2c7416932b8a`), the dev lecture: 20 gold windows; windows 0, 3 and 5 are reserved as guide examples.

**Gold:**

| Version | File (in `tools/label_concepts/labels/<lecture>/`) | sha256 | Tag | Status |
|---|---|---|---|---|
| v1 | `gold.json` | `7fcec636…a4ff` | `m7-day4-gold-frozen` | Kept, not used for scoring. It breaks the explanation rule and the canonical names (Amendment 5). |
| v2 | `gold_v2.json` (+ `relabel_v2.json`, the change log) | `19837236e0e56e2368381541ad53d2c11fdc88cde8f224f3d7d439243fa055be` | `m7-day4-gold-v2-frozen` | Relabelling pass by Bilal (Amendments 5 and 6): 24 concepts, 7 names, no relations. Evidence: `docs/labelling/m7_day4_gold_v2.md`. |
| v2.1 | `gold_v2_1.json` (+ `gold_v2_1_changes.json`) | `53248bbb4187c84737dc1fd48867d96eec5ef39c55fd887a2fbc0b6310ea7d2c` | `m7-day4-gold-v2.1-frozen` | v2 plus window 16 "Hardware Limitation", added after seeing model output (Amendment 7). |

**Adjudication decisions** (append-only, keyed by window and normalised model label; reused by every later run against the same gold version):
- `adjudications_v2.json`: 23 decisions from sheet `C1-gold_v2-20261022T140229Z.json`; tag `m7-c1-adjudications-v2-frozen`.
- `adjudications_v2_1.json`: 22 decisions carried over from v2, without window 16 (its item string-matches the new concept). The v2.1 sheet had 0 items.

**Prompt and harness:**
- **Prompt:** frozen at version 2, `config/prompts/m7_extraction_v2.txt`, sha256 `c7e061fce838d935c7335b01746fbec8c708f2d1f3845720c8e5728ac7154648` (Session 2b, 18 Oct 2026).
- **Step 4a check:** re-scored against gold v2, it still wins over versions 1, 3 and 4 under fixed rule 8. Evidence: `docs/labelling/m7_day4_gold_v2_prompt_rescore.md`.
- **No Gemma tuning.** The Gemma read-through found patterns but did not change the prompt (`docs/evidence/m7/c1_gemma_readthrough.md`).

**Harness** (`insightex extract-eval run|measure`, `backend/src/insightex/extract/`; `HARNESS_VERSION` 7). Settings are in `config/default.yaml` under `extract:`:
- **Context and output caps:**
  - `num_ctx` 8192;
  - `num_predict` 1024 × k per call (`num_predict_per_window`);
  - translation cap `translate_num_predict` 1024.
- **Sampling:** temperature 0, seed 42, think false.
- **Reload and truncation:**
  - `keep_alive` 0 (reload per call; Gemma's output depended on session state);
  - `truncate` false (Ollama refuses an over-long prompt with HTTP 400);
  - a post-call overflow check (`prompt_eval_count` + `num_predict` > `num_ctx` means invalid);
  - a run-start self-test (a probe at `num_ctx` 2048 must be refused, or the run aborts before any real call).
- **Estimate gate:** a warning only, never refuses (scales: qwen3.5 0.84, Gemma 0.761).
- **Retry:** once, in the same unit, with the frozen `<<<RETRY>>>` template and the errors (capped at 1,500 characters).
- **Schema caps:** at most 10 concepts and 10 relations per window (ADR-0049 Amendment 1).

**C1 is decided: ADR-0050, Accepted 25 Oct 2026, Gemma 4 E4B** (`gemma4:e4b`, digest `dc35e8d9c606…`).
- It was a tie on both gold v2 and v2.1: net wins 0 (2 / 2 / 16 tied), so arm A, the smaller VRAM peak, is kept.
- qwen3.5's micro F1 was higher on both: 0.304 vs 0.286 on v2, and 0.340 vs 0.320 on v2.1.
- **Gemma's k = 5** for C3 (qwen3.5 would be 4; ADR-0049 and `session2b_prompt_iteration.md`).
- **Gemma's C1 cost:**
  - wall time 181.1 s for 20 calls;
  - VRAM peak 6,348 MiB (4,828 above baseline);
  - largest prompt 1,927 tokens;
  - 136.7 tokens/s.
- **Run folders:** `docs/evidence/m7/<lecture>/C1/` (both arms), with `compare_C1_gold_v2.json` and `compare_C1_gold_v2_1.json`.

**Blinding:** C1 is no longer blinded. Every later comparison follows the same pattern: no scores, outputs or per-window results are shown until that comparison's adjudication decisions are frozen.

## 2. Limitations recorded so far

1. **Single annotator.** The gold is Bilal's labels (ADR-0048 Amendment 1).
2. **Gold v2 is not blind to qwen3.5's prompt-iteration output** (Amendment 5). The iteration reports showed qwen3.5's extra and missed concepts by window; no Gemma output was shown.
3. **One concept was added after seeing model output** (Amendment 7, gold v2.1). C1 had the same decision with and without it.
4. **The prompt was tuned on qwen3.5 only** (ADR-0048 Consequences), which tilts the comparisons towards qwen3.5.
5. **No inter-annotator figure for gold v2.** The v1 figure (0.240) was measured on labels v2 replaces. The question is still open (Amendment 5, decision 5); see section 5.
6. **No relations in Day 4 gold v2.** Day 4 relation scores are not computed; relations are evaluated on the held-out lecture.
7. **Small set.** 20 windows from one lecture, 16 of them tied in C1, and low F1 for both models (0.29 to 0.34).
8. **The Gemma read-through findings** (`c1_gemma_readthrough.md`):
   - generic "model" in 4 windows;
   - example-setting concepts in windows 8 and 10;
   - passing mentions with invented `contrasts_with` (14, 22);
   - an alias split off in window 6;
   - a broader "batch learning" than the gold;
   - no aliases at all;
   - empty windows 13 and 21;
   - all 5 predicted relations wrong.
   No prompt change was made.

## 3. What C2 needs before it runs

**C2 (ADR-0048 section 8):** original transcript (arm A, kept on a tie) against a per-window English translation (arm B, ADR-0041). Both arms use Gemma, single window, no context. The arms are already in `config/m7_arms.yaml` as `C2-original` and `C2-english`. A tie keeps original-language input.

1. **Set the C2 arms' model.** Change `model: null` to `"gemma4:e4b"` for `C2-original` and `C2-english` in `config/m7_arms.yaml`. ADR-0050 says this follows its acceptance, and it hasn't been done yet. The C3 and C4 arms stay null until their earlier comparisons are decided.
2. **Write and freeze the translation prompt** (ADR-0048 section 8, "C2 translator").
   - **One fixed prompt:** e.g. `config/prompts/m7_translate_v1.txt`, used as the system message. The user message is `{"text": <window text>}` (`prompts.translation_messages`), and the reply format is `{"english": "<non-empty string>"}` (`TRANSLATION_FORMAT`).
   - **Content rules:**
     - a faithful English translation of the code-switched Urdu/English window;
     - English technical terms kept as said;
     - no summarising and no added content.
   - **No gold-window text** in the prompt, the same rule as for the extraction prompt (invented or reserved-window examples only). Check it by script for shared word sequences with the 20 gold windows, as in Session 2b.
   - **Freeze it** before C2 runs: set `extract.translate_prompt_file` and `extract.translate_prompt_sha256` in `config/default.yaml`. The harness refuses an unpinned or mismatched hash.
   - **Who approves:** Bilal approves the prompt before it runs.
   - **Display rule:** translations are internal and never shown to users (ADR-0041). Showing them to Bilal for evaluation is a separate question to settle if it's wanted.
3. **The translation cache stage. Check this gap first.**
   - **What ADR-0048 requires:** translations cached as their own stage, one per window, keyed by the window text's sha256, the model and the translation prompt's hash, so that extraction reruns reuse them.
   - **What exists now:** `translate_windows` caches through the generic `ReplyCache` (kind `translate`). Its key is the whole request plus `HARNESS_VERSION` and the attempt number (`harness.py`, `ReplyCache.key`). So a harness version bump throws away every cached translation.
   - **What to do:** decide and record whether to build a dedicated translation cache with exactly the ADR's key (window text sha256, model digest, prompt sha256), or to amend the ADR. The ADR text points to building it.
   - **Translation retry:** one retry on a blank or unparsable reply. A window whose translation fails twice is invalid for arm B (fail closed; tested in `test_english_arm_translates_targets_and_context_and_fails_closed`).
   - **Open question:** whether a translation also needs a language check, i.e. that it is actually English. The current check is only "non-empty".
4. **Tests,** on synthetic input only:
   - the cache key, with a hit on the same window text, model and prompt, and a miss when any of them changes;
   - reuse across extraction reruns, and across a harness version bump if the dedicated stage is built;
   - fail-closed on a blank translation;
   - the refusal of an unpinned translation prompt;
   - that the translation calls go through the same call rules: `truncate` false, the post-call check, reload per call, and the self-test before any call.
5. **Cost to record.**
   - Arm B's cost includes the translation calls: `cost.translation_wall_s` plus the extraction wall time, and the run's VRAM peak covers both phases.
   - Report cost only from a run with `cost.measured: true` (no cache hits).
   - **Arm A** has the same configuration as the C1 Gemma run. Either re-run it fresh (its cached replies would make `cost.measured` false unless the cache is bypassed), or reuse the C1 run folder for arm A. Bilal decides and it gets recorded.
6. **Adjudication flow,** as for C1:
   - run both arms;
   - report validity, wall time and VRAM only;
   - `adjudication-sheet --comparison C2` pooling both arms (unmatched concepts that already have a decision are left out, so C1 decisions are reused);
   - commit and push the sheet before Bilal opens it;
   - Bilal decides in the terminal (`adjudicate`);
   - freeze, tag and push the decisions;
   - only then run `compare --comparison C2` and show scores.
   - **Which gold:** decide before C2 runs whether C2 is scored against v2.1 only, or against both v2 and v2.1 with the same agreement rule as C1. Neither ADR-0048 nor Amendment 7 settles this for C2.

## 4. After C2

- **C3:** single window against batches of k = 5 (Gemma), on the C1 and C2 winners. The `C3-*` arms in `m7_arms.yaml` are filled in after C2 is decided. A tie keeps single-window calls.
- **C4:** window only against the previous window as read-only context (ADR-0048 Amendment 2), on the C1 to C3 winners.
  - Needs: a frozen context-block file (`extract.context_block_file`/`_sha256`).
  - The context is in C2's chosen language.
  - Watch for carry-over from the previous window, which the agreement review saw in a human annotator.
- **Held-out Hindi lecture: not found yet.** ADR-0048's requirements:
  - Hindi (Whisper `ur`), another speaker, at least 20 minutes;
  - 40 sampled windows labelled under the frozen guide before any model reads it;
  - used once, for the final configuration only.
  - Before it is sampled, an amendment decides whether a second annotator labels its shared windows (Amendment 3).
  - Relation extraction is evaluated there.
- **Session 3:** the production extraction stage, canonicalisation and the NetworkX graph. Gemma read-through finding 1 suggests a stop list for generic labels such as "model".

## 5. Open items

- **Untracked file:** the void v1 C1 sheet, `tools/label_concepts/labels/<lecture>/adjudication_sheets/C1-20261018T180252Z.json`. It was never opened, is not used, is kept untracked, and is not deleted. Bilal decides whether to delete it.
- **Inter-annotator figure for gold v2** (Amendment 5, decision 5), still open. The recommendation given was:
  - Fatima rechecks her 10 shared windows under the same explanation rule, without seeing Bilal's labels.
  - Any new figure is reported as not blind on Bilal's side, since he saw her labels in the review.
  - The clean ceiling comes from two blind annotators on the held-out lecture, if a second annotator is used there.
- **The Ollama logon task.** `Insightex Ollama` has only a one-time trigger (8 Oct 2026) and no logon trigger, so Ollama does not start at logon, although CLAUDE.md and ENVIRONMENT.md say it does. Adding an "At log on" trigger is Bilal's call; nothing was changed.
- **The guide's wording check.** The guide notes that "learning incrementally" was not checked against the textbook (window 5 worked example). This is minor and does not affect the gold.
- **Scratch files:** the provisional C1 score files from before adjudication sit in an old session's scratchpad. They are not part of the evidence and can be ignored.
