# Insightex build order

Adopted October 2026. It replaces the module 1–21 list in the earlier `Insightex_Build_Order.md`.

**Principle.** Build a walking skeleton first: video in, cited answer out, citation seeks the video. Then thicken the system in order of risk. Shared engines come before the features that use them.

**Rule.** Every module has pending decisions, listed at the bottom of this file. Settle a module's decisions before building it, and record each one as an ADR in `docs/adr/`.

## Status (update at every module exit)

| Module | State |
|---|---|
| M0 | **Done (7 Oct 2026)**: `scripts/verify_env.sh` passes 12/12 after a full restart (`docs/ENVIRONMENT.md`) |
| M0b | **Done (8 Oct 2026)**: repo scaffold, typed config, ADR-0001 to ADR-0032 (`docs/adr/`), textbook chosen (ADR-0029) |
| M1 | **Done (9 Oct 2026)**: SQLite job queue, single worker with crash recovery and resume, GPU lease, workspaces with chained stage keys and cache eviction, and link ingestion on the runner with job progress over HTTP/SSE (ADR-0033 to ADR-0035). Evidence: `docs/evidence/m1/`. |
| M2 | **Done (10 Oct 2026)**: shared normalise engine and CLI file ingest (ADR-0036), HTTP upload endpoint and upload form (ADR-0037), A/V sync invariant that holds even in players that ignore MP4 edit lists (ADR-0038), `NORMALISER_VERSION` 4. `tools/m2_verify` 13/13 on the Day 4 lecture; by-hand browser checklist passed (`docs/evidence/m2/`). |
| M3 | **Done (6 Oct 2026)**; the eval-lecture fetch (4–6 lectures) still has to be run (it now goes through normaliser v4). It also supplies the language gates of ADR-0040: 3 lectures from different speakers per language, a 5-minute excerpt from the middle of each. Urdu and English stay untested until those gates pass. |
| M4 | **Done (10 Oct 2026)**: session 1, the WER gate chose large-v3 (ADR-0039); session 2, the production `asr` stage with the lecture language chosen per lecture from a two-tier list, English as the system output language, and the stage design (ADR-0040 to ADR-0042). `tools/m4_verify` 12/12, with check 4 an exact match to the gate (351 segments, 0 differing; the workspace `audio.wav` is byte-identical to the gate input). Manual checklist passed. Evidence: `docs/evidence/m4/`, `tools/eval_wer/results/m4/`. |
| M5 | **Done (11 Oct 2026)**: windows, BGE-M3 dense vectors on the GPU at ingest, a FAISS index per lecture (`index` stage, ADR-0044), question search on the CPU in the API process (`POST /api/lectures/{id}/search`), and the Test A scorer. Gates under ADR-0043 on the Day 4 lecture: G0 production equals the legacy encoder (identical rankings), G3s/G3 grid stride 30 kept, G2 dense only kept, G1 CPU fp32 queries equal GPU fp16 (min cosine 0.9999986, no hit changed). Final configuration (ADR-0045): Recall@3 0.8085 over 47 questions, 0.8696 for English questions. **Open: G4 says a Roman Urdu fix is needed** (Roman twins 3 net losses over 23 pairs); decided in ADR-0046 (LLM rewrite of every question, fused search; gate G5), built in M6. Provisional until M9. Evidence: `docs/evidence/m5/`. |
| M6 | **Done (15 Oct 2026)**: FastAPI API (ingest by link or upload, jobs with SSE progress, library, media), static HTML ingest/upload/library/player page and `seekTo(seconds)` exist; search endpoint exists (M5); session A (14 Oct 2026, ADR-0047): `POST /api/lectures/{id}/ask` (rewrite + RRF + citations), `/warm-up`, `searchable` on the lecture document, `first_segment_start` in `windows.json`, byte-identical rewrite request test, replay of the G5 rewrites; session B (14 Oct 2026): ask box and up to three citations on the player page, `index` progress label, warm-up on open and re-warm after `llm_not_loaded` (at most every 30 s), `tools/m6_verify` 13/13; manual browser checklist signed 15 Oct 2026 (`docs/evidence/m6/manual_check_report.md`; not done: audio at cited moments not listened to, old-lecture disabled box not tried) |
| M7 | **In progress.** Session 1 (15 Oct 2026): extraction schema v1 (`insightex/extract/extraction.schema.json` + validator, tool copy), labelling guide `docs/labelling/m7_concepts.md`, labelling tool `tools/label_concepts/` (sample, serve, validate, agreement, merge), gate rules ADR-0048 (**Accepted** 15 Oct 2026). Day 4 sample manifest committed (census of 20 windows). Browser check of the labelling page passed 15 Oct 2026 (Bilal: Play window stops at the window end, mixed Urdu/English order and Urdu rendering correct, autosave and relation dropdowns work). No extraction stage and no Ollama calls yet. Next: human labelling of Day 4 (20 windows), then Session 2 (arms C1 to C3). |
| All others | Not started |

## Phase 0: Foundation (week of 5 Oct)

- **M0: Close the environment's open items.** Done 7 Oct 2026 (`docs/ENVIRONMENT.md`). This covers the post-restart check, the Ollama call contract (model `qwen3.5:latest`, `think`, `num_ctx`, `format`, `keep_alive`), and a rewrite of `ENV_AUDIT_REPORT.md` as a single current-state document.
  Exit: one verification script passes from a cold boot.
- **M0b: Repo scaffold, config system, one ADR per decision, textbook chosen.**
  Exit: `docs/adr/` holds one ADR for every decision.

## Phase 1: Walking skeleton (to ~15 Nov)

- **M1: Core.** Workspace + manifest, SQLite job queue, GPU lease, single worker, CLI.
  Exit: a dummy two-stage job runs, resumes after being killed, and holds the lease.
- **M2: Ingest (upload).** ffprobe validation, then ffmpeg normalisation to `video.mp4` (H.264/AAC) and a 16 kHz mono `audio.wav` derived from it (ADR-0036), in sync within one frame even when a player ignores edit lists (ADR-0038).
  Exit: the Day 4 lecture normalises, and odd codecs are rejected cleanly.
- **M3: Ingest (URL).** Done. Design and open items are in `docs/features/README.md`.
- **M4: ASR stage + WER gate** in `tools/eval_wer`. Done (10 Oct 2026).
  - **Session 1 (10 Oct 2026):** the WER gate chose the checkpoint, large-v3 (ADR-0039; large-v3-turbo not evaluated). Evidence: `tools/eval_wer/results/m4/`.
  - **Session 2 (10 Oct 2026):** the production `asr` stage (ADR-0042) runs after `normalise` in both ingest pipelines. The language is **chosen per lecture** from a two-tier list (ADR-0040, `config/languages.yaml`): Hindi (Whisper code `ur`, the gate's winning config) is the only tested entry; every other faster-whisper language is untested and marked in the UI. No auto-detect and no default. Everything users read is English; transcripts are internal (ADR-0041). Day 4: 351 segments, RTF 0.113, peak 4,523 MiB above baseline, identical to the gate. Evidence: `docs/evidence/m4/`.
  - Re-ingest the eval lectures through normaliser v4 before measuring: older `audio.wav` files predate the start-offset padding, so their timings may be shifted. Carried-over WER numbers on old audio count as not re-run.
  - A language moves to tested only through the WER gate in ADR-0040 (3 lectures from 3 speakers, 5-minute excerpts); this needs the eval-lecture fetch (M3).
  Exit: the checkpoint and language decisions are recorded as ADRs, with numbers; `tools/m4_verify` passes.
- **M5: Windows + embedding (dense and sparse) + FAISS.**
  - Prerequisite for the sparse-weight work: `FlagEmbedding` is **not installed** and is not in `requirements.lock.txt`. Installing it needs the user's approval and a lockfile update (then re-run `scripts/verify_env.sh`). `tools/bench_models/loadtimes/verify_6b_loadtimes.py` fails at its bge-m3 step for the same reason.
  - Open question from ADR-0041, measured here and not decided yet: rerun Test A with **English questions** over native-script transcripts. Cross-language search is a gate: if English questions fail to retrieve the right windows, per-window English translation becomes a candidate stage (its own ADR).
  Done 11 Oct 2026 (ADR-0043 to ADR-0045). Exit met: Test A reproduces through production code (gate G0: identical rankings and scores to the legacy bake-off encoder on the same windows), and the CPU-query gate passes (G1). `FlagEmbedding` stays out of the project environment: the sparse head is verified against it in a throwaway venv. The ADR-0041 question is answered for M5: English questions retrieve native-script windows (Recall@3 0.8696 on 23 questions); per-window translation is not needed for retrieval.
- **M6: Minimal API and UI.** Upload or link, progress, player, ask box, top-3 citations that seek the video.
  - A citation seeks to the start of the first transcript segment inside the retrieved window, not the window's grid start (ADR-0044).
  - Roman Urdu questions (ADR-0046): rewrite every question into English with the LLM (temperature 0, question only, terms kept, one line), search the original and the rewrite fused with RRF k=60; original only if the LLM is not loaded. Reuse this module's LLM client. Gate G5 passed on 11 Oct 2026 (ADR-0046 Accepted, provisional until M9; evidence `docs/evidence/m6/`). Requirements: a 2 s timeout (`retrieval.rewrite_timeout_s`), original-only fallback, and a test that the production rewrite request body is byte-identical to the G5 harness request (model, options, schema, prompt sha256).
  Exit: paste link → wait → ask → click → the video jumps to the right moment.

## Phase 2: Knowledge layer (to ~20 Dec)

- **M7: LLM extraction** with JSON Schema output: concepts, relations, importance (for F4) and `is_recap` (for F20).
  - Open question from ADR-0041: LLM input. Decide between the original-language transcript and a per-window English translation, from measured extraction quality.
  - Rules: ADR-0048 (Accepted 15 Oct 2026): extraction schema v1, data split (Day 4 dev, a held-out Hindi lecture of 20+ minutes by another speaker, used once), gold set (dev: census of 20 Day 4 windows, windows 0, 3 and 5 reserved as guide examples; held-out: 40 sampled; 10 shared each), matching with blind pooled frozen adjudication, human ceiling compared with string-rule-only model F1, prompt frozen (qwen3.5-tuned) before C1, net >= 3 adoption rule, every window valid after one retry (dangling relations dropped and counted; if both arms fail, fix and re-run both), comparisons C1 model, C2 input language, C3 window batching.
  - **ADR-0048 Amendment 1 (17 Oct 2026): single labeller.** Fatima will not label; Bilal labels every gold window (Day 4: all 20; held-out: all 40). The human ceiling is replaced by an intra-rater check: at least 2 days after finishing, Bilal re-labels the 10 shared windows blind as `bilal_repeat`, and `bilal` vs `bilal_repeat` agreement (string rule only) is reported as single-annotator consistency, never as an inter-annotator ceiling. The consensus step is replaced by Bilal revising his own labels after the one guide update; gold = his revised labels. The Day 4 manifest was reassigned, not re-sampled (same windows, seed and shared flags; recorded under `amendments` in `sample.json`). The tool keeps `fatima` and `consensus` working for a later second labeller.
  - **Session 1 (15 Oct 2026):** the schema and validator (`backend/src/insightex/extract/`, copied byte-identically to `tools/label_concepts/`), the labelling guide `docs/labelling/m7_concepts.md`, the labelling tool `tools/label_concepts/` and ADR-0048. No extraction, no Ollama calls, no labels. Browser check of the labelling page passed 15 Oct 2026 (Play window stops at the end; Urdu rendering and mixed-script order correct; autosave and relation dropdowns work). Day 4 sample manifest committed (`tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/sample.json`).
  - Next: Bilal labels Day 4 (all 20 windows, validate, commit; at least 2 days later the blind `bilal_repeat` of the 10 shared windows; consistency figure; review; one guide update; revise; merge); Session 2 runs C1 to C3 on Day 4; Session 3 builds the production extraction stage.
  Exit: precision/recall against hand-labelled concepts on 2 lectures, and the LLM choice decided.
- **M8: Concept canonicalisation + graph build.**
  Exit: duplicate-node rate measured on 2 lectures, and the graph JSON passes schema checks.
- **M9: Router + fusion, reranker gate, retrieval eval harness** (Test A on more lectures, plus Test C).
  Exit: the router beats vector-only on graph-shaped queries, or the router is simplified.
- **M10: Book ingest** (PyMuPDF with page labels) + timestamp↔page fusion → F1, F2.
  Exit: Test B within ±2 pages on at least 20 queries.
- **M11: Grounded answer service** with citation validation, plus a frame grabbed at the cited timestamp → F6 Baseline.
  - Open question from ADR-0041: citation text shown to users next to an English answer (original-language excerpt, English translation, or timestamp only). Also, an answer that cites a lecture processed with an untested language shows the same "Untested language" badge (ADR-0040).
  Exit: no answer cites a window outside its retrieved set.
- **Visual gate (end of December).** Run scene detection + PP-OCR on 30 frames. If the output is usable on most slide frames, continue the Optional track; otherwise freeze the visual pipeline as a documented limitation. Run the PaddleOCR-VL bake-off only if the gate passes and Phase 3 is on schedule.

## Phase 3: Features (Jan to mid-March)

- **M12:** F3 dyslexia toggle, F5 graph↔timestamp navigation, F9 concept-map viewer.
- **M13:** F7/F14 quiz, notes and flashcards (one generation service with a role parameter).
- **M14:** F12 importance-flag review tool (it also produces the F4 precision/recall labels).
- **M15:** F8 prep mode, F10 prerequisite gap check.
- **M16:** F11 textbook coverage gap report, F15 highlight reel.
- **V1–V3:** the Optional visual track, run in parallel in a separate worker env. Covers scene detection, the PP-OCR baseline, the visual form of F6, F13 if built, and PaddleOCR-VL only if the gate let it in.

## Phase 4: Evaluation, hardening, demo (mid-March to May)

- **M17: Full evaluation run** (WER, retrieval A/B/C, extraction P/R, F4 flag P/R, answer faithfulness, latency, VRAM).
  - Lectures processed with an untested language are excluded from the evaluation numbers (ADR-0040).
  Exit: one results table per proposal metric.
- **M18: User study** with students and teachers (SUS + task success).
  Exit: ethics and consent completed before recruiting.
- **M19: Hardening** (error states, Tailscale demo path, nginx only if range requests misbehave).
  Exit: a clean demo on a fresh boot.
- **M20: Thesis and defense material.**
  - **Before making the repo final: remove lecture-derived text** (decided 6 Oct 2026: it stays until then). Keep `queries.csv` and `per_query_results.csv`, which are the project's own evaluation work.
    - Current tree: `docs/reports/embedding_bakeoff/results_seq1024/windows_W30.csv`, `windows_W60.csv` and `windows_W90.csv` (the full transcript); the worked examples in `docs/labelling/m7_concepts.md` (glosses and one Urdu-script quote of Day 4 windows 0, 3, 5) and the aliases in `tools/label_concepts/labels/*/` (lecture surface forms); one transcript line in `docs/reports/PRE_MIGRATION_AUDIT.md` (the one in `ENV_AUDIT_REPORT.md` went with that file on 2026-10-07; it remains in git history); check the Urdu strings in `tools/bench_models/asr/verify_6a_whisper.py`.
    - History (tree of tag `import-baseline`, under `_legacy_import/`): `embedding/data/day04_batch_vs_online/whisper_urdu.srt`; the `windows_W*.csv` files and result files under `embedding/tools/eval_embeddings/` (`results/` and `results_seq1024/`); `tools/env_audit/results/followup/T2.txt` and `T2_process_a.txt`; `tools/env_audit/results/followup2/F2.txt`, `F3.txt`, `F6.txt` and `F3_segments.json`; the transcript line in `STRUCTURE_AUDIT.md` and the Urdu-script line in `tools/env_audit/ENV_AUDIT_REPORT.md`.
    - Method: take a backup bundle first (`git bundle create`), run `git filter-repo`, force-push `main`, and re-point and re-push the `import-baseline` tag.
- **Stretch order:** F17 → F18 → F19 → F16, only if Milestones 1–9 finish early.

## Pending decisions by module

These come from the October 2026 review. Settle each one when its module starts.

- **M0b: Textbook.**
  - The candidates are Géron (best fit for the batch vs online learning dev lecture, but copyrighted for a public demo) and ISL or D2L (free to use).
  - Check that the chosen book actually covers the dev lecture's topic.
  - This decision blocks F1, F2, F11 and Test B.
- **M0 / M7 / M11: qwen3.5 VRAM headroom.**
  - The 2 Oct audit recorded a 7,566 MiB peak with 626 MiB free; re-measured 2026-10-07 at 7.4 to 7.7 GB peak with 510 to 818 MiB free (`docs/ENVIRONMENT.md`, `docs/adr/0002-ollama-call-contract.md`). The KV cache grows with context, and Urdu script is token-expensive. The risk is a silent CPU offload or a truncated prompt.
  - Always set `num_ctx` explicitly. Measure VRAM, tok/s and `ollama ps` at the worst-case prompt (3–5 Urdu windows + 2 textbook chunks).
  - Gate: concept extraction on 10 labelled windows, qwen3.5 vs Gemma 4 E4B. If the two are within noise, use the smaller model for interactive Q&A; using the larger one only for offline extraction is a valid split. (Replaced by ADR-0048 comparison C1 on the 20 Day 4 gold windows with the net >= 3 rule.)
  - Optional lever: KV-cache quantisation.
- **M1: Job queue.** Settled (ADR-0033, ADR-0035); kept for the record.
  - A SQLite jobs table, one worker holding the GPU lease, and SSE progress: about 150 lines, no Celery.
  - On worker start, requeue or fail any stale "running" jobs.
- **M1: Session rule.** Settled (ADR-0034); kept for the record.
  - Cache the processed workspace per video, keyed by content hash or YouTube ID, and include the pipeline version in the key.
  - "Nothing stored between sessions" becomes a UI/product rule: one video per session, no cross-session or cross-student data, no user history. Phrase it this way at the defense (M20).
- **M2: Upload ingestion and normalisation.** Settled (ADR-0036 to ADR-0038); kept for the record.
  - One engine for link and file sources; per-stream copy-or-transcode on CPU (libx264, no GPU lease); transcodes capped at 1080 lines.
  - Raw streamed upload body (no multipart), SHA-256 dedupe, one upload at a time, no CORS middleware.
  - `audio.wav` derived from `video.mp4` with start padding; sync within one frame even when a player ignores edit lists (libx264 `bframes=0`; copied video re-encoded when its ignored-edit-list skew exceeds the bound). Cost: about 3–19% larger transcodes, and more files transcoded instead of copied.
  - Closed, unprefixed error codes. Uploaded originals deleted unless `ingest.file.keep_original`; link sources kept (ADR-0035).
- **M4: Whisper language setting.** Settled by ADR-0039 (checkpoint: large-v3) and ADR-0040 (per-lecture language mapping: Hindi -> `ur` tested, all other languages untested); the notes below are the history.
  - Earlier notes conflict. One says auto-detect beat forced `ur` because forcing dropped lines; another says forcing `ur` was needed because auto produced Devanagari.
  - Decide in the WER gate: medium and large-v3 × forced `ur` / auto-detect (4 configs, with large-v3-turbo as a 5th if time allows).
  - Confirm `task=transcribe`, not translate. Count dropped segments explicitly. Enable `word_timestamps=True`.
- **M5: Query-time VRAM conflict.**
  - BGE-M3 (1,141.7 MB measured bake-off peak, `Embedding_Report.md`; `MODELS.md` and `docs/ENVIRONMENT.md` carry 3,089 MiB, not re-run; re-measure in M5) and qwen3.5 (about 7.4 GB peak, `docs/ENVIRONMENT.md`) can't share 8 GB.
  - Encode documents on the GPU at ingest. Encode queries on the CPU in the API process (fp32, ~2.3 GB RAM), and run the reranker on the CPU too.
  - Gate: rerun Test A with CPU queries; Recall@3 must not change. **Done (G1):** passed; bge-m3 peak VRAM re-measured at 1,142.4 MiB allocated (1,365 to 1,383 MiB above the nvidia-smi baseline); the API process holds 2.3 GiB after startup (peak 2.41 GiB). The GPU lease unloading Ollama was exercised for the first time on 11 Oct 2026 (it worked: `docs/evidence/m5/README.md`).
- **M9: Right window at rank 4 (known weakness, separate from ADR-0046).** A03, A12 and A23 and their Roman twins have the right window at rank 4 (just outside the top 3) in the M5 baseline. The planned CPU reranker is the candidate fix; gate it with the ADR-0043 net-count rule.
- **M5 / M9: Sparse weights.**
  - Use FlagEmbedding `BGEM3FlagModel` (dense + sparse in one pass) and fuse the two rankings with Reciprocal Rank Fusion.
  - If sparse adds nothing, drop the tie-break argument from the report. **Done (G2):** sparse added nothing (net -1); dense only; the sparse head was implemented in `tools/` and verified against `BGEM3FlagModel` instead of installing the package.
- **M5: Window edges.**
  - Keep the 30 s target but snap edges to Whisper segment boundaries. Test 50% overlap (15 s stride) and adopt it only if Recall@3 improves.
  - Score hits by time overlap with the gold span, and dedupe overlapping hits. **Done (G3s, G3):** snapping and the 15 s stride both tied the fixed grid, so the grid with stride 30 s stays; hits count at 50% of a gold span and any overlap is de-duplicated (ADR-0043).
- **M8: Concept identity across scripts.**
  - Canonicalisation is its own module. Each node has a canonical English label plus an alias list.
  - Find merge candidates by embedding similarity, then confirm them with the LLM.
- **M10: Page numbering.**
  - Store both the PDF page index and the printed page label (PyMuPDF `page.get_label()`, which may be empty if the PDF defines no labels).
  - Without this, the ±2-page criterion breaks silently.
- **M19: Storage cleanup and quota.** Open (noted in ADR-0036).
  - Workspaces are bounded by `cache.max_bytes` (least-recently-used unpinned workspaces are evicted after each successful job). ADR-0036 still lists storage cleanup as open: check its wording for exactly what remains (for example, kept link sources inside pinned workspaces, or anything stored outside workspaces).
  - Settle what is genuinely unbounded, if anything, before the demo period, and test it on a fresh boot as part of M19's exit.
- **Visual gate / V1–V3: Effort.**
  - Use a fixed time box: one owner, about 1 day a week, and a hard gate that decides continue vs freeze.
  - Scene detection + PP-OCR are cheap; PaddleOCR-VL is the time sink.