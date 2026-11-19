# M7 extraction report: concept extraction with a local LLM

**Status: DRAFT for Bilal's review (19 Nov 2026).** Not yet approved; M7 is not closed.

M7's exit criterion (`docs/BUILD_ORDER.md`): precision and recall of LLM concept extraction on the dev lecture (Day 4) and on one held-out lecture, plus a model choice. There is no pass bar; the numbers feed M17. Rules: ADR-0048 (schema, gold set, gate rules, Amendments 1–11) and ADR-0049 (harness call rules, Amendments 1–2).

## 1. Summary

| | Day 4 (dev, gold v2.1) | Held-out (`yt-5vqk6HnITko`, gold v1) |
|---|---|---|
| Windows scored | 20 | 40 (of 48) |
| Gold concepts / model concepts | 25 / 25 | 34 / 103 |
| **Concept P / R / F1, adjudicated (primary)** | **0.320 / 0.320 / 0.320** | **0.136 / 0.412 / 0.204** |
| Concept P / R / F1, string rule only | 0.320 / 0.320 / 0.320 | 0.107 / 0.324 / 0.161 |
| Relations | n/a (gold has none; the model predicted 5) | n/a (gold has none; the model predicted 24) |
| Importance P / R | n/a (gold has no important window; the model flagged none) | 0.111 / 1.000, on 1 gold important window (see 4.3) |
| Dropped relations | 1 | 1 |
| Validity | 20 of 20 valid, 0 retried | 40 of 40 valid, 0 retried |
| Wall time | 181.1 s (9.1 s per window) | 359.8 s (9.0 s per window) |
| VRAM above baseline | 4,828 MiB | 4,772 MiB |
| Human ceiling (string rule) | not available for gold v2.1 | 0.190 on the 10 shared windows; the model there: 0.085 |

The held-out figures are reported once. No prompt, model or setting was changed after any held-out score was seen, so they are not contaminated.

## 2. Final configuration

Chosen on Day 4 through comparisons C1–C4 and used unchanged on the held-out lecture.

| Setting | Value |
|---|---|
| Model | `gemma4:e4b`, digest `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`, Ollama 0.40.2 |
| Input | the original-language (Hindi/English code-switched) transcript of each 30 s grid window (ADR-0045) |
| Unit | one window per call |
| Context | none |
| Prompt | frozen extraction prompt v2, `config/prompts/m7_extraction_v2.txt`, sha256 `c7e061fce838…7154648`; system message `f2d8742f5155…` |
| Call settings | `num_ctx` 8192; `num_predict` 1024 per window; temperature 0, seed 42, `think` false; `keep_alive` 0 (model reloaded every call); `truncate` false; post-call overflow check; run-start truncation self-test; one retry in the same unit with the frozen retry template |
| Output | extraction schema v1 (concepts with aliases, relations, `important` + cue, `is_recap`), at most 10 concepts and 10 relations per window |
| Harness | `insightex extract-eval`, harness version 8 |

### The C1–C4 decisions (Day 4)

| Comparison | ADR | Kept | How decided |
|---|---|---|---|
| C1 model | ADR-0050 (25 Oct 2026) | Gemma 4 E4B over qwen3.5 | tie (net wins 0 on gold v2 and v2.1); the smaller measured VRAM peak is kept on a tie |
| C2 input language | ADR-0051 (9 Nov 2026) | original transcript over Gemma's own English translation | tie (net −1); micro F1 0.320 vs 0.292 |
| C3 unit | ADR-0052 (9 Nov 2026) | single window over batches of k = 5 | tie (net −1); micro F1 0.320 vs 0.296 |
| C4 context | ADR-0053 (9 Nov 2026) | window only over previous-window context | validity: the context arm's window 6 was invalid (a relation with head = tail, on both attempts); its scores are informational only (net −4, F1 0.259) |

Every comparison was decided by ADR-0048 section 7 (per-window adjudicated concept F1; an alternative is adopted only with net wins ≥ 3 and a micro F1 not lower; a tie keeps the simpler or cheaper arm A). No comparison produced a winner on quality: each was a tie or a validity failure. The final configuration is therefore the simplest one tested, not one shown to be better.

## 3. Day 4 (dev lecture)

- **Lecture:** Day 4, batch vs online learning (CampusX), `sha256-de27cb67c2acbedebd0c2c7416932b8a`, census of 20 windows (windows 0, 3 and 5 reserved as worked examples in the guide).
- **Gold:** v2.1, sha256 `53248bbb…7d2c` (tag `m7-day4-gold-v2.1-frozen`): 25 concepts, no relations, no important windows. Adjudications `adjudications_v2_1.json`, 36 decisions (tag `m7-c4-adjudications-v2.1-frozen`).
- **Run:** the C1 Gemma run (`docs/evidence/m7/sha256-de27…/C1/C1-gemma4-e4b`, 18 Oct 2026), which is the final configuration. Re-scored on 19 Nov 2026 with all 36 v2.1 decisions: unchanged from the C1 figures (adjudicated equals string rule only, 8 of 25 matched both ways).
- **Cost:** 181.1 s for 20 windows, 136.7 tok/s, largest prompt 1,927 tokens at 100% GPU, VRAM peak 6,348 MiB, 4,828 above a 1,520 MiB baseline. Its `run.json` does not record the Ollama version (recorded only from 13 Nov 2026); 0.40.2 rests on the handoff and the update log (`docs/ENVIRONMENT.md` section 5).

## 4. Held-out lecture

### 4.1 Lecture, gold and process

- **Lecture:** "Performance Metrics, Accuracy, Precision, Recall and F-Beta Score" (Krish Naik Hindi, `5vqk6HnITko`, 23:35), Hindi with English terms, a different speaker from Day 4; Géron chapter 3. Selection record `docs/evidence/m7/heldout/selection.md`, written and committed before ingestion.
- **Ingest:** language `hindi` (Whisper `ur`); 1,148 segments, 48 non-empty windows (`docs/evidence/m7/heldout/ingest.md`).
- **Sample:** seed 20261115, 40 of 48 windows (near-census), 10 shared windows (2, 5, 10, 14, 19, 26, 31, 36, 38, 43); `sample.json` committed before any labelling.
- **Labels:** Bilal labelled all 40; Fatima labelled the 10 shared windows blind as a second annotator, never gold (ADR-0048 Amendment 11). Both files were frozen (tag `m7-heldout-labels-frozen`) before agreement. One guide clarification from Claude (claude.ai) during labelling, with no label suggested, is disclosed in `docs/evidence/m7/heldout/labelling.md`.
- **Agreement:** string-rule concept F1 0.190 on the 10 shared windows (`agreement.md`, tag `m7-heldout-agreement`).
- **Review:** one correction, on shared window 10, logged with its reason; no non-shared window changed.
- **Gold:** `gold.json` sha256 `8c92dd27…23f7` (tag `m7-heldout-gold-frozen`): 40 windows, 34 concepts (10 distinct labels), 0 relations, 1 important window, 6 windows with no concept. Frozen before any model read the lecture.
- **Run (once):** `check_ollama_frozen.py` OK before the k check and again before the run; k = 1 check passed (real retry prompt 2,373 + 1,024 ≤ 8,192 at 100% GPU, +4,753 MiB; `measure_k1.json`). Arm `C4-window` with `--fresh`, `run.json` records Ollama 0.40.2. Its `run.json` says comparison `C4` and arm `C4-window`; that arm is exactly the final configuration. Run directory `docs/evidence/m7/yt-5vqk6HnITko/heldout/final`.
- **Adjudication:** blind sheet of 92 model concepts the string rule left unmatched (seed 574108888, committed before it was opened); all 92 decided by Bilal, none skipped: 4 match, 88 no match (`adjudications.json` sha256 `94ab8735…9a5258`, tag `m7-heldout-adjudications-frozen`).

### 4.2 Scores

From `docs/evidence/m7/yt-5vqk6HnITko/heldout/score.json`.

| Measure | Adjudicated (primary) | String rule only |
|---|---|---|
| Concepts matched / model / gold | 14 / 103 / 34 | 11 / 103 / 34 |
| Precision | 0.136 | 0.107 |
| Recall | 0.412 | 0.324 |
| **F1** | **0.204** | 0.161 |

The 4 "match" decisions add 3 true positives: in window 40 the model concept judged a match maps to a gold concept the string rule had already matched, and matching is one-to-one.

**Against the human ceiling** (string rule only on both sides; the adjudicated F1 is never compared with it):

| On the 10 shared windows | Matched / predicted / reference | Concept F1 |
|---|---|---|
| Fatima vs Bilal's pre-review labels (the ceiling) | 2 / 9 / 12 | **0.190** |
| The model vs the gold | 2 / 38 / 9 | **0.085** |

The model's string-rule F1 over all 40 windows is 0.161. The two rows do not use exactly the same reference: the ceiling uses Bilal's pre-review labels (window 10 with 4 concepts), the model row uses the reviewed gold (window 10 with 1), as Amendment 11 fixes.

**Relations:** n/a. The gold has no relation on any of the 40 windows, so recall is undefined; the model predicted 24 relations (all therefore unmatched) and 1 more was dropped as invalid.

**Importance:** the gold has 1 important window (14); the model flagged 9 windows, including window 14: P 0.111, R 1.000, same flag in 32 of 40 windows (0.800). One gold window makes recall meaningless as an estimate.

**Validity and cost:** 40 of 40 windows valid, 0 retried, 0 empty after retry, 1 dropped relation, `done_reason` stop on every call. 359.8 s for 40 windows (137.8 tok/s), largest prompt 1,932 tokens at 100% GPU, smallest margin 5,236 tokens. VRAM peak 6,936 MiB, 4,772 above a 2,164 MiB baseline (self-test phase 4,631).

## 5. Cost per window

About 9 s per window on both lectures with an RTX 3070 (8 GB). Of this, 6.3–7.1 s per call is loading the model, because `keep_alive` 0 reloads it for every call (ADR-0049, for reproducibility). Generation itself is about 2–3 s. VRAM above baseline is about 4.8 GB on both lectures, leaving headroom only for the desktop on an 8 GB card. A 48-window lecture (24 minutes) takes about 7 minutes under these settings.

## 6. Reading the numbers

- **Over-extraction on the held-out lecture.** The model gave 103 concepts for 40 windows (2.6 per window); the gold has 34 (0.85 per window, 6 windows empty). Precision is the weakest figure on the held-out lecture (0.136), while recall (0.412) is above Day 4's 0.320.
- **The task itself is hard to agree on.** Two people labelling the same 10 windows under the same frozen guide reached string-rule F1 0.190 (Day 4 v1: 0.240). Many gold labels on this lecture are non-textbook descriptions (e.g. "Focus on precision or recall", 12 windows), which the string rule cannot match against a model's different wording.
- **The model is below the human ceiling** on the shared windows (0.085 vs 0.190), by string rule only; with 2 matches each, both figures rest on very few concepts.
- **Day 4 and held-out are not directly comparable:** different gold versions (v2.1 after a relabelling pass vs v1), different window counts, and a census vs a near-census sample.

## 7. Limitations

**Gold and annotation**
1. **Single annotator** on both lectures (ADR-0048 Amendments 1 and 11). The second annotator labelled only 10 shared windows per lecture and never contributed to gold.
2. **Low inter-annotator agreement:** 0.190 (held-out) and 0.240 (Day 4 v1). No figure exists for Day 4 gold v2 or v2.1 (Amendment 5, decision 5, still open).
3. **Day 4 gold v2 is not blind** to qwen3.5's prompt-iteration output (Amendment 5); **v2.1 adds one concept after seeing model output** (window 16; Amendment 7). Window 16 decided a window win in C2, C3 and C4.
4. **Held-out correction after seeing the second annotator's labels:** window 10 (4 concepts → Confusion Matrix), allowed by Amendment 11, logged with the labeller's reason; the ceiling uses the pre-review labels.
5. **Held-out guide clarification:** Bilal asked Claude (claude.ai) how the guide treats a topic-preview window; no labels were suggested (disclosed in `labelling.md`).
6. **Adjudication by the gold labeller** on both lectures (blind sheets, but one person). On the held-out sheet, 4 of 92 entries were judged matches.
7. **Relations are not evaluated on either lecture:** Day 4 gold has none (v1 had one); the held-out gold has none, against the selection record's expectation. All model relations (5 on Day 4, 24 held-out) are therefore unmatched by definition.
8. **Importance is barely evaluated:** no gold important window on Day 4 and one on the held-out lecture.

**Data**
9. **Two lectures, two speakers, one language (Hindi/English).** 20 + 40 windows. The held-out lecture is under the preferred 25 minutes (23:35), so its 40-window sample is a near-census of one lecture; it says little about sampling across lectures.
10. **Held-out ASR differs in shape from Day 4** (about 3× as many segments, median 1.02 s vs 1.94 s), with no repetition loop (`ingest.md`); ASR errors in the input were not measured for this lecture.

**Comparisons C1–C4**
11. **The prompt was tuned on qwen3.5 only,** with original-language, single-window, no-context input (ADR-0048 Consequences), which tilts C1 towards qwen3.5 and C2–C4 towards arm A.
12. **C2–C4 rest on one gold version (v2.1),** with no cross-version check (Amendments 8–10).
13. **Arm A of C2–C4 is the reused C1 Gemma run** (18 Oct 2026), not re-run; each reuse passed an identity check. Arm B runs had higher desktop baselines, so VRAM is compared above baseline.
14. **C2: known translation errors in arm B** (windows 0 and 5); gold-window translations were not inspected.
15. **C3: blinding exposure** of raw arm B output for windows 19–22 (1 sheet entry); the decision does not depend on them (`C3/blinding_exposure.md`).
16. **C3: thin worst-case margin at k = 5** (140 tokens); not relevant to the final configuration.
17. **C4 was decided by one window's validity** (window 6) under one rule (head = tail), which production might handle differently. Its context was a reserved window whose gloss is a prompt example; untested whether that contributed.
18. **C4 carry-over measure** only sees concepts in the previous window's gold (1 vs 1).
19. **Small sets and ties:** most Day 4 windows tied in every comparison (16, 19, 17, 16 of 20), and every quality comparison was a tie. The final configuration is the simplest tested, not a demonstrated best.

**Model and environment**
20. **Gemma read-through findings, with no prompt change** (`c1_gemma_readthrough.md`): generic "model" labels, example-setting concepts, passing mentions with invented `contrasts_with`, no aliases, empty windows, all 5 Day 4 relations wrong. The held-out output was not read through.
21. **Gemma's residency on the GPU** is checked by VRAM above baseline (about 4.8 GB), not by `ollama ps`, which under-reports its size (ADR-0049 decision 6).
22. **Ollama version:** the app auto-updated to 0.40.15 on 9 Nov 2026, after all C1–C4 runs; 0.40.2 was reinstalled on 13 Nov with auto-update off. Day 4 `run.json` files do not record the version; the held-out run does (0.40.2).
23. **Reload per call** (`keep_alive` 0) makes about 70% of the per-window time model loading; production speed will differ if the model is kept loaded (Session 3, needs its own determinism evidence).

## 8. Open items for Session 3 (production extraction stage)

Carried from handoff 4 section 3; each needs its own evidence and ADR: keep the model loaded between calls; drop self-pointing relations instead of failing the window; context-aware extraction only with new evidence; batching only after the first item; a stop list for generic labels; canonicalisation and the NetworkX graph; production writes v1 records through `insightex.extract.extraction_schema`. The held-out over-extraction (2.6 concepts per window against 0.85 in gold) is a further input for the stop list and canonicalisation.

## 9. Evidence

| What | Where |
|---|---|
| Rules | `docs/adr/0048-…`, `0049-…`, `0050-…` to `0053-…` |
| Day 4 runs, comparisons | `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C1` to `C4` |
| Held-out selection, ingest, labelling, agreement | `docs/evidence/m7/heldout/` |
| Held-out run, k check, scores | `docs/evidence/m7/yt-5vqk6HnITko/heldout/` (`final/`, `measure_k1.json`, `score.json`) |
| Gold, adjudications, sheets | `tools/label_concepts/labels/<lecture>/` |
| Tags | `m7-day4-gold-v2.1-frozen`, `m7-c4-adjudications-v2.1-frozen`, `m7-heldout-labels-frozen`, `m7-heldout-agreement`, `m7-heldout-gold-frozen`, `m7-heldout-adjudications-frozen` |
| Handoff | `docs/evidence/m7/Insightex_M7_handoff_4.md` |
