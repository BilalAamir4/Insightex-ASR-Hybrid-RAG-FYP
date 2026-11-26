# Insightex M7 handoff 6 (26 Nov 2026): M7 Session 3 closed, before M8

**DRAFT for Bilal's review.** For a fresh session. Read this first, then:
- `CLAUDE.md`;
- ADR-0054 (Amendments 1–3), ADR-0055 and ADR-0056 (with its Outcome);
- `docs/reports/M7_extraction_report.md` and handoff 5 (`Insightex_M7_handoff_5.md`) for the M7 results and the five Session 3 decisions as first posed.

Trust the files over this summary when they differ. It holds counts, hashes and settings only: no labels and no transcript text.

## 1. What Session 3 delivered

| Item | What | Commits |
|---|---|---|
| Production `extract` stage (step 2) | Fifth stage of `ingest_link` and `ingest_file`, after `index`. It runs on the frozen final configuration, under the GPU lease, and unloads the model in `finally`. Covers the resume store, invalid-window handling, untested-language rules, and the Ollama version and digest check (ADR-0054, Accepted 21 Nov 2026). | ADR: `0ffb1a6` draft, `c785b9d`, `21cdb54`, `64ad6e5` accepted, `4ea7f69` Amendment 1. Build: `e67626e`. Review follow-ups and Amendment 2: `13ad308` |
| Extraction hold | `--hold-extract` on `ingest` (YouTube) and `ingest-file`, `insightex extract-hold list\|release`, and `extraction.state` (`held`/`done`/`failed`/`outdated`/`none`), per ADR-0054 decision 8 and Amendments 1–2. The held-out lecture is held (job `89f4cfe2…`). | `e67626e`, `13ad308` |
| `tools/m7_verify` (step 2 exit) | 7 of 7 checks passed on Day 4, 21 Nov 2026 (`docs/evidence/m7/session3/m7_verify_20261121T145444Z.json`). The resume check really ran (killed with 3 windows stored, 3 reused, 20 calls after the restart). The 20 C1 target windows are byte-identical to the C1 Gemma run. The hold round trip used a 90 s cut of Day 4 (offset 390 s, sha256 `186eb65e…e9f7`). | `8633070` |
| Self-pointing relations dropped and counted (step 3) | Stage v2 drops a relation with head == tail (after the dangling drop) and counts it as `dropped_self_relations`, instead of failing the window (ADR-0055, Accepted 21 Nov 2026). Day 4 rerun at v2 (key `a92d9cabba3b68fe`): 23/23 records identical to v1 and 20/20 to C1, `dropped_self_relations` 0. | ADR: `cb7af48` draft, `dbfd2b7` accepted. v1 copy: `39de6f0`. Build: `4f9bf11`. Rerun: `354e8ae`. Outcome: `925ecad` |
| Recent jobs list | Home page list from `GET /api/jobs?limit=20`. Refreshes every 2 s while a job is active and every 10 s when idle, paused while the tab is hidden. CLI-started jobs appear in it (ADR-0054 Amendment 3). | ADR: `2e12113`. Build: `3cea6ec` |
| Both manual checks (22 Nov 2026) | Bilal saw "Skipped (extraction held)" on the held-out hold job `89f4cfe2…`. He saw "Find concepts: window i of n" live on job `0a1c3f5a…`, a CLI re-add of `yt-B7TQYJLfYZQ`. With these checks the step 2 exit is fully met. | `155aad7` (record corrected), `30f3278` |
| Keep-alive test (step 4, decision (a)) | ADR-0056 (Accepted 22 Nov 2026). Command `insightex extract-eval keepalive`, with the frozen ADR-0049 case `docs/evidence/m7/session3/keepalive/adr0049_case.json`. Session `20261126T144306Z`: not void, both references reproduced. Day 4: 23/23 identical in all 3 repeats. ADR-0049 case: k = 1 identical; k = 3 differed (raw and parsed) in all 3 repeats. **The rule fails, so reload per call stays.** | ADR: `be1c649` draft, `5e47f86` accepted. Command: `25717a1`. Evidence: `1705653`. Outcome recorded: `88edbb2` |

## 2. The production extract configuration (as it stands; unchanged from the M7 final configuration)

| Setting | Value |
|---|---|
| Model | `gemma4:e4b`, digest `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |
| Ollama | 0.40.2 (`extract.stage.frozen_ollama_version`; another version fails the stage unless `allow_other_ollama_version`, which needs its own ADR). App auto-update stays off; run `check_ollama_frozen.py` before any measured run |
| Prompt | `config/prompts/m7_extraction_v2.txt`, sha256 `c7e061fce838d935c7335b01746fbec8c708f2d1f3845720c8e5728ac7154648` |
| Input and unit | Original-language text of each 30 s grid window, one window per call, no context, no translation (ADR-0051 to ADR-0053) |
| Call settings | `num_ctx` 8192; `num_predict` 1024 per window; temperature 0; seed 42; `think` false; `truncate` false; **`keep_alive` 0 (reload per call)**; one retry in the same unit with the frozen `<<<RETRY>>>` template (`retry_error_chars` 1500); post-call overflow check; run-start truncation self-test (`num_ctx` 2048, 122 probe lines); estimate gate as a warning only (scale 0.761) |
| Output | Extraction schema v1 (`schema_version` 1, `format_version` 2, `user_format_version` 1). At most 10 concepts and 10 relations per window. Dangling relations, then self-pointing relations, are dropped and counted |
| Stage | `extract`, **version 2**, `needs_gpu`. `min_free_vram_mib` 5000 (pre-flight; not in the fingerprint) |
| Cost per window | **7.861 s mean** (client wall, max 8.208 s). Measured in the ADR-0056 run 0 on Day 4, 26 Nov 2026: 180.8 s for 23 windows. The model load is 6.30–6.78 s of each call. VRAM peak 4,814 MiB above a 1,763 MiB baseline. For comparison, a loaded model took 0.612–0.625 s per call (Day 4 repeats 2–3; information only, not adopted) |

## 3. Rules still in force

- **The held-out lecture `yt-5vqk6HnITko` is used up and stays held.** It was run once (19 Nov 2026) and its output has been read. Its `extract` stays skipped by the hold; do not release the hold or re-add it to extract. No change may be evaluated on it.
- **Any quality claim needs a fresh lecture with its own gold.** The lecture must be neither Day 4 nor the held-out one. Select and label it under ADR-0048's rules **before any model output for it is seen**. Never label or pre-fill gold yourself.
- **Day 4 (`sha256-de27cb67c2acbedebd0c2c7416932b8a`) is for development only.** It was used for every M7 decision and for Session 3's checks, so it is not independent evidence.
- **Keeping the model loaded is closed on this evidence.** It can come back only through a quality check on a fresh lecture under a new ADR (ADR-0056 decision 1), never by re-running the keep-alive test.
- Shell commands print counts, hashes and costs only, never raw model output.

## 4. Open decisions carried forward from handoff 5

Decisions (a) and (b) are closed: (a) by ADR-0056 (failed, reload per call kept) and (b) by ADR-0055 (self-relations dropped and counted). Each remaining decision gets its own ADR.

| Decision | What evidence it needs | Where it is decided |
|---|---|---|
| **(c) Stop list** for generic labels and confusion-matrix-cell-like terms | The patterns came from reading held-out output, so any filter (a fixed list, a prompt rule as a new frozen prompt version, or post-processing) is evaluated on a **fresh lecture only**. Also open: whether finer terms are wrong or only finer than the gold (report limitation 25) | Its own ADR, after the fresh lecture's gold is frozen |
| **(d) Canonical names** | The stage writes raw model labels plus aliases (v1 records; ADR-0054 decision 9). Merging, textbook names and ADR-0019 are owned by M8. Evidence: the M8 duplicate-node rate on 2 lectures | M8 |
| **(e) Keeping relations and importance** (and `is_recap`) | A **fresh lecture** whose gold has relations and important windows. Neither current gold has a relation, and importance rests on 1 gold window in 60. Options: drop, keep stored but unused, or keep with filters | Its own ADR. **Affects F4 (importance), F20 (`is_recap`) and the M8 graph (relations)** |

Also carried from handoffs 4 and 5, each needing its own evidence:
- **Context-aware extraction** is not ruled out, but needs new evidence (ADR-0053).
- **Batching for throughput** (ADR-0052) was to follow decision (a). With reload per call kept, a batch would put several windows in one loaded call. Whether that is reproducible is **unverified**: the ADR-0049 counterexample is itself a k = 3 batch.

## 5. Open items

- **The void v1 C1 sheet.** `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/adjudication_sheets/C1-20261018T180252Z.json` was never opened or used. Commit `957dd46` committed it unchanged as a record, with a one-line README. It must not be deleted or used. It is now tracked, no longer untracked as handoff 5 says (checked with `git ls-files`, 26 Nov 2026).
- **yt-dlp test crash.** In one full `pytest` run (9 Nov 2026), `test_ytdlp_download.py::test_byte_cap_enforced_by_hook_without_content_length` crashed the interpreter. Cause not investigated. It did not recur in the full suite on 26 Nov 2026 (1060 passed).
- **Inter-annotator figure for Day 4 gold v2/v2.1.** The only Day 4 figure (0.240) was measured on gold v1. A v2 figure would not be blind on Bilal's side; the held-out ceiling (0.190) is the clean figure.
- **`yt-B7TQYJLfYZQ` is a new run, not used for evaluation.** Job `0a1c3f5a…` re-ran normalise, asr and index (normaliser v4). Its transcript shows 5 segments (ids 6–10) on temperature fallback. Extraction key `4ae313af114e2305`, stage v2: 28/28 windows ok on attempt 1, 1 dangling relation dropped, 0 self-relations.
- **`IndexStageError` is missing from `_FAILED_CODE_RE`** in `ingest/file_jobs.py`. Pre-existing since M5 and not fixed (`docs/BUILD_ORDER.md`, Open items).
- **m7_verify prints a traceback** instead of a clear message when the API is not reachable. Small fix, not done.
- **The Day 4 v2 cost figures disagree.** ADR-0056's Context gives Day 4 at stage v2 as 179.6 s for 23 windows, but no committed file I found holds 179.6. `docs/evidence/m7/session3/day4_stage_v2_compare.json` records `wall_s` 209.877 and `vram_peak_above_baseline_mib` 6,169 for the v2 rerun, against about 4.8 GB in every other Gemma run (4,814 MiB in the keep-alive session). The cause is not investigated. Section 2's cost per window uses the keep-alive run 0, not these figures.
- **`docs/report-notes/`** (5 thesis-note files) is untracked. It is left as it is and is not part of Session 3.

## 6. What comes next

- **M8: concept canonicalisation and graph build** (`docs/BUILD_ORDER.md`). Exit: duplicate-node rate measured on 2 lectures, and the graph JSON passes schema checks. Check M8's pending decisions in `docs/BUILD_ORDER.md` before building. Decision (d) is settled inside M8.
- **A fresh lecture must be chosen** before (c) and (e) can be decided. It must not be Day 4, the held-out lecture or `yt-B7TQYJLfYZQ` (whose output has been produced). Ingest it with `--hold-extract` (a YouTube link or `ingest-file`) so no model output exists before its gold. Label it under ADR-0048's rules and freeze the gold, then release the hold.
