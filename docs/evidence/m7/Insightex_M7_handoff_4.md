# Insightex M7 handoff 4 (9 Nov 2026): after C1–C4, before the held-out lecture

For a fresh session. Read this first, then:
- `CLAUDE.md`;
- ADR-0048 with Amendments 1 to 10;
- ADR-0049 with Amendments 1 and 2;
- ADRs 0050 to 0053.

Trust the files over this summary when they differ. Handoff 3 (`Insightex_M7_handoff_3.md`) covers the state before C2.

## 1. Where M7 stands

**The Day 4 comparisons are complete.** Dev lecture: Day 4, `sha256-de27cb67c2acbedebd0c2c7416932b8a`, 20 gold windows; windows 0, 3 and 5 are reserved as guide examples.

| Comparison | ADR (Accepted) | Arm kept | How it was decided | Gold |
|---|---|---|---|---|
| C1 model | 0050 (25 Oct 2026) | Gemma 4 E4B over qwen3.5 | tie (net 0 on v2 and v2.1), smaller VRAM peak kept | v2 and v2.1 |
| C2 input language | 0051 (9 Nov 2026) | original transcript over Gemma's own English translation | tie (net −1), micro F1 0.320 vs 0.292 | v2.1 |
| C3 unit | 0052 (9 Nov 2026) | single window over batches of k = 5 | tie (net −1), micro F1 0.320 vs 0.296 | v2.1 |
| C4 context | 0053 (9 Nov 2026) | window only over previous window as context | **validity**: the context arm had window 6 invalid (a relation with head = tail, both attempts); scores informational only (net −4, F1 0.320 vs 0.259) | v2.1 |

**Final M7 configuration** (used once on the held-out lecture):

| Setting | Value |
|---|---|
| Model | `gemma4:e4b`, digest `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`, Ollama 0.40.2 |
| Input | the original-language transcript of each 30 s grid window (ADR-0045) |
| Unit | one window per call |
| Context | none |
| Prompt | frozen extraction prompt version 2, `config/prompts/m7_extraction_v2.txt`, sha256 `c7e061fce838d935c7335b01746fbec8c708f2d1f3845720c8e5728ac7154648`; system message sha256 `f2d8742f5155f1d1afef4ebc0324cfb0108a05de97185ff2167e4d30bac1a35f` |
| Call settings | `num_ctx` 8192; `num_predict` 1024 per window; temperature 0, seed 42, think false; `keep_alive` 0 (reload per call); `truncate` false; the post-call overflow check; the run-start self-test; the estimate gate as a warning only (Gemma scale 0.761); one retry in the same unit with the frozen `<<<RETRY>>>` template |
| Schema | extraction schema v1, at most 10 concepts and 10 relations per window |
| Arm | `C4-window` in `config/m7_arms.yaml` has exactly this configuration. So does `C1-gemma4-e4b`, `C2-original` and `C3-single`. |

**Harness:** version 8 (`backend/src/insightex/extract/`).
- **Translation stage:** `translation.py`, keyed by window text sha256, model digest and prompt sha256.
- **`run --fresh`:** reads no cache, so `cost.measured` is true.
- **`translate-check`:** translates non-gold windows only.
- **VRAM:** peaks per phase.
- **Frozen but unused by the final configuration:** the translation prompt `m7_translate_v2.txt` (`dfc9aa5c…49a8`) and the context block `m7_context_block_v1.txt` (`3132e2f9…912e`).

**Gold and decisions** (`tools/label_concepts/labels/<Day 4>/`):
- **Gold:** gold v2.1 `53248bbb…7d2c` (tag `m7-day4-gold-v2.1-frozen`).
- **Decisions:** `adjudications_v2_1.json`, 36 decisions, `72522b11…d199`, latest tag `m7-c4-adjudications-v2.1-frozen`.
- **Also kept:** gold v1 and v2 and their files; v1 is not used for scoring.

**Day 4 headline** (the final configuration, which is the C1 Gemma run), gold v2.1: micro concept P 0.320, R 0.320, F1 0.320, adjudicated, which equals string rule only. Cost: 181.1 s for 20 windows, 4,828 MiB above baseline.

**Evidence:**
- **Run folders:** `docs/evidence/m7/<Day 4>/C1` to `C4`. Each comparison folder has a reuse check, `reused_from.json` for arm A, the run folders, and `compare_*.json`.
- **C2:** `translation_prompt_freeze.md`.
- **C3:** `k_check.md` and `blinding_exposure.md`.
- **C4:** `context_check.md` and `c4_informational.json`.
- **Blinded reader:** `docs/evidence/m7/scripts/validity_cost.py` is the only way to read a run while it is blinded.

## 2. Limitations so far

1. **Single annotator.** The gold is Bilal's labels (ADR-0048 Amendment 1). A second annotator (Fatima) labelled only the 10 shared Day 4 windows of gold v1 (Amendment 3).
2. **No inter-annotator figure for gold v2 or v2.1.** The v1 figure (0.240) was measured on labels v2 replaced. This is still open (Amendment 5, decision 5).
3. **Gold v2 is not blind to qwen3.5's prompt-iteration output** (Amendment 5); the iteration reports showed qwen3.5's extra and missed concepts by window.
4. **Gold v2.1 has one concept added after seeing model output** (window 16, "Hardware Limitation"; Amendment 7). Window 16 decided a window win in C2, C3 and C4 (all for the window-only/original arm).
5. **The extraction prompt was tuned on qwen3.5 only,** with original-language, single-window input and no context (ADR-0048 Consequences). This tilts C1 towards qwen3.5 and C2–C4 towards their arm A.
6. **C2–C4 rest on one gold version (v2.1),** with no cross-version check (Amendments 8–10).
7. **Arm A of C2–C4 is the reused C1 Gemma run** (18 Oct 2026), not re-run. Each reuse passed an identity check. Arm B runs were measured on 9 Nov 2026 with higher desktop baselines, so VRAM is compared above baseline.
8. **C2: known translation errors in arm B.** On reserved windows, a count was added in window 0 ("three types") and the opening fragment of window 5 was mistranslated. Two prompt versions did not change Gemma's output at temperature 0 (`C2/translation_prompt_freeze.md`). Gold-window translations were not inspected.
9. **C3: blinding exposure.** Raw arm B output for windows 19–22 was on Bilal's screen during the run, as he reported; 1 sheet entry was in those windows. The decision does not depend on those windows (`C3/blinding_exposure.md`, ADR-0052).
10. **C3: thin worst-case margin at k = 5** (140 tokens). Not relevant to the final configuration (k = 1).
11. **C4: decided by one window's validity** (window 6) and by one rule (head = tail), which production might handle differently.
    - Window 6's context was reserved window 5, whose English gloss is a worked example in the prompt. Whether that contributed is untested.
    - Without windows 1, 4 and 6 the informational result is unchanged (net −2).
    - The context block was not reply-tested before its freeze (Bilal's choice).
12. **C4 carry-over** (string-matched to the previous window's gold): 1 vs 1, the same concept. The measure misses concepts not in the previous window's gold.
13. **Small set.** 20 windows from one lecture, with most windows tied in every comparison (16, 19, 17 and 16) and low F1 (0.26–0.34).
14. **Relations and importance are not evaluated on Day 4.** Gold v2.1 has no relations and no important windows; relations are evaluated on the held-out lecture.
15. **Gemma read-through findings, with no prompt change** (`c1_gemma_readthrough.md`):
    - generic "model" labels;
    - example-setting concepts;
    - passing mentions with invented `contrasts_with`;
    - no aliases;
    - empty windows 13 and 21;
    - all 5 predicted relations wrong.
16. **Residency of Gemma** is checked by VRAM above baseline (about 4.8 GB), not by `ollama ps` (ADR-0049 decision 6). Every run so far is consistent.

## 3. Open Session 3 notes (production extraction stage)

Each is a separate decision with its own evidence and its own ADR.

1. **Keep the model loaded between single-window calls** (ADR-0052). Most of batching's speed-up in C3 came from 4 model loads instead of 20 under `keep_alive` 0, about 6–7 s each. ADR-0049 chose reload per call for evaluation reproducibility, because Gemma's output depended on session state. Production needs its own determinism and quality evidence before keeping the model loaded.
2. **Self-pointing relations** (ADR-0053). Consider dropping a relation whose head equals its tail, as dangling relations are dropped, instead of failing the window. That changes validity handling for every configuration.
3. **Context-aware extraction** is not ruled out (ADR-0053), but needs new evidence, not Day 4 again.
4. **Batching for throughput** (ADR-0052): only with its own evidence, after point 1.
5. **A stop list for generic labels** such as "model" (Gemma read-through, finding 1).
6. **Canonicalisation and the NetworkX graph** (`docs/BUILD_ORDER.md`).
7. **Production writes v1 records** and imports `insightex.extract.extraction_schema` (ADR-0048 Consequences).

## 4. Open items

- **Ollama launcher (corrected 9 Nov 2026).** The earlier note here ("only a one-time trigger, no At log on trigger") was wrong: the task has one "At log on" trigger and ran at logon on 9 Nov (16:10, result 0), but its server had exited (task Ready), and the server running was the tray app's, which had staged an update to 0.40.15. Fix (Bilal's decision): the task is the only launcher (the Startup shortcut is removed and the tray app is not opened); the tray app's auto-update is off and its staged installer is deleted; `start_ollama.ps1` now logs to `E:\FYP\logs\ollama_serve.log` and exits with `ollama serve`'s exit code (re-copied to `E:\FYP`); `docs/evidence/m7/scripts/check_ollama_frozen.py` checks Ollama 0.40.2 and the `gemma4:e4b` digest (step 6). **Windows-side steps not yet confirmed** (at the last check on 9 Nov the tray app was still running, the shortcut was present, and the new script was not yet re-copied); confirm with the process check in `docs/ENVIRONMENT.md` section 5 before step 6. Why the task's server stopped is still unknown; the log should show it next time.
- **yt-dlp test crash.** In one full `pytest` run (9 Nov 2026), `test_ytdlp_download.py::test_byte_cap_enforced_by_hook_without_content_length` crashed the interpreter ("no Python frame"). It passed alone on the working tree and on clean HEAD. Cause not investigated.
- **The untracked void v1 sheet.** `tools/label_concepts/labels/<Day 4>/adjudication_sheets/C1-20261018T180252Z.json` was never opened or used, and is kept untracked and undeleted. Bilal decides whether to delete it.
- **Inter-annotator figure for gold v2** (Amendment 5, decision 5). The earlier recommendation: Fatima rechecks her 10 shared windows under the explanation rule without seeing Bilal's labels, and any new figure is reported as not blind on Bilal's side. The clean ceiling comes from the held-out lecture if a second annotator is used there (see step 3 below).
- **Guide wording.** "Learning incrementally" (window 5 worked example) was not checked against the textbook. Minor.

## 5. The held-out lecture, step by step

ADR-0048 sections 2 and 3, Amendments 1–3, and ADR-0049 Amendment 2 ("Gate / revisit"). **The held-out lecture is used once,** for the final configuration only, with no tuning after seeing it. A crash may be fixed and the run repeated. If any prompt, model or setting is changed after held-out scores have been seen, the held-out numbers are reported as contaminated.

**1. Choose the lecture.** It must be:
- **in Hindi**, the only tested language (Whisper code `ur`, ADR-0039/0040). The sampler refuses a lecture transcribed with an untested language;
- **by a different speaker** from Day 4;
- **at least 20 minutes long** (at least 40 non-empty windows on the 30 s grid).

It should also be on a machine learning topic, so the guide and the prompt apply, and preferably not covered by Day 4. Bilal chooses it, and the choice and its reasons are recorded before ingestion. No model output for it may be produced or seen before its gold is merged (section 3).

**2. Ingest it** with the language set to Hindi:
- link: `POST /api/ingest/...` or the UI;
- file: `insightex ingest-file <path> --confirm-rights --language <hindi id> --wait`.

Wait for `normalise`, `asr` and `index` to finish. Check:
- `windows.json` exists;
- the window count is at least 40;
- `transcript.json` is present.

Record the workspace id. The `asr` and `index` stages are not extraction, so they do not break the "no model output before gold" rule. Do not run `extract-eval` on it.

**3. Decide the second-annotator question, before sampling** (ADR-0048 Amendment 3, last point). Bilal decides in a new ADR-0048 amendment (11) whether a second annotator labels the held-out lecture's 10 shared windows. If yes, it also fixes:
- who it is;
- that they label blind under the frozen guide;
- that their labels never enter the gold;
- that agreement (string rule only, on the pre-review file) is the human ceiling, compared only with the model's string-rule-only F1 (section 6).

This should also settle the open inter-annotator question for the thesis. Commit the amendment before `sample` runs.

**4. Sample 40 windows:**

```
python label_concepts.py sample --lecture <id> --n 40 --shared 10 --seed <recorded> --labellers bilal
# only if Amendment 11 adds a second annotator: shared windows only, never gold
python label_concepts.py add-annotator ...   # as for Day 4 (Amendment 3)
```

- **Not `--labellers bilal fatima`** (corrected 9 Nov 2026): that alternates the 30 non-shared windows between the labellers, so the second annotator would label 15 gold windows, against Amendment 1 (gold = Bilal's labels). `add-annotator` adds them to the shared windows only.

- **How it samples:** stratified across the timeline, seed recorded, 10 shared windows.
- **What it checks:** that its grid matches the index stage's `windows.json`.
- **Commit `sample.json`** before any labelling.
- **Reserved windows:** none are needed. The guide is frozen and its worked examples come from Day 4.

**5. Bilal labels** the 40 windows (`serve --labeller bilal`, then `validate`):
- under the frozen guide (`docs/labelling/m7_concepts.md`), with no rule update (Amendment 2);
- before any model reads the lecture;
- relations are labelled (they are evaluated here).

Then:
- if there is a second annotator, they label the shared windows blind, and agreement is computed on the pre-review files, as in Amendment 3;
- `merge` to `gold.json`, then commit and tag it (e.g. `m7-heldout-gold-frozen`) before step 6.

**6. Run the final configuration once:**
- **The k check first** (ADR-0049 Amendment 2, "Gate / revisit"): `extract-eval measure --lecture <id> --model gemma4:e4b --k 1` with the frozen prompt. The worst-case retry call must fit (real prompt + 1,024 ≤ 8,192) at 100% GPU, with VRAM above baseline about 4.8 GB. Record it.
- **Then the run:**

  ```
  insightex extract-eval run --arm C4-window --lecture <id> --targets <sample.json> --fresh --out docs/evidence/m7/<id>/heldout/final
  ```

  `C4-window` is exactly the final configuration. A dedicated arm name (e.g. `final`, with a new comparison value) would need a code change, which is optional.
- **Before running:** `python3 docs/evidence/m7/scripts/check_ollama_frozen.py` must print OK (Ollama 0.40.2 and the frozen `gemma4:e4b` digest); **on STOP, do not run, and tell Bilal.** Also check `ollama ps`, the GPU lease and that nothing else is using the GPU. Run it again just before `run`, after the k check.
- **Run directory:** `--out` is required here, or the run goes to the C4 default `<evidence>/<id>/C4/C4-window`. `run.json` will still say comparison `C4` and arm `C4-window`; the held-out README records that this is the final configuration (checked by reading `cli.py`, 9 Nov 2026).
- **Report:** validity and cost only, through `validity_cost.py`.
- **If a window is invalid:** report it. There is no comparison here to reject, and no re-run with changes.

**7. Adjudication:**
- `adjudication-sheet --lecture <id> --gold v1 --comparison <label> --arm final=<run dir>`. The held-out lecture's gold is its own `gold.json` and `adjudications.json`, so `--gold v1` is the right selector there.
- The sheet builder accepts any comparison label (checked by reading `label_concepts.py`, 9 Nov 2026, not run): `--comparison heldout` writes `adjudication_sheets/heldout-<time>.json`. Only `compare` is restricted to C1–C4, and the held-out lecture does not use it.
- Commit and push the sheet before Bilal opens it. Bilal decides with `adjudicate`; then freeze and tag the decisions.

**8. The final report for M7's exit** (BUILD_ORDER: precision and recall on both lectures, plus an LLM choice; no pass bar, the numbers feed M17):
- **Scores:** `score --lecture <id> --gold v1 --arm final=<run dir>`. Report:
  - concept P/R/F1 (adjudicated primary, string rule only next to it);
  - relation P/R/F1 (now meaningful);
  - importance P/R;
  - dropped relations;
  - validity and cost;
  - the human ceiling, if step 3 added an annotator, next to the string-rule-only F1 only.
- **The report:** `docs/reports/M7_extraction_report.md`. It covers:
  - Day 4 (gold v2.1, the final configuration's figures);
  - the held-out figures, reported once;
  - C1–C4 with their ADRs;
  - every limitation in section 2;
  - the cost per window.
- **Close M7:** update CLAUDE.md's current state and `docs/BUILD_ORDER.md`, and record any decision in an ADR.
