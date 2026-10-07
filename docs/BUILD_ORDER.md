# Insightex build order

Adopted October 2026. It replaces the module 1–21 list in the earlier `Insightex_Build_Order.md`.

**Principle.** Build a walking skeleton first: video in, cited answer out, citation seeks the video. Then thicken the system in order of risk. Shared engines come before the features that use them.

**Rule.** Every module has pending decisions, listed at the bottom of this file. Settle a module's decisions before building it, and record each one as an ADR in `docs/adr/`.

## Status (update at every module exit)

| Module | State |
|---|---|
| M0 | Not done: environment open items still need closing |
| M0b | Partial: git repo exists on GitHub, tag `import-baseline` pushed; config system, ADRs and textbook choice still to do |
| M1 | Partial: one-worker background jobs exist from link ingestion; GPU lease, resume-after-kill and generic stage runner still to do |
| M2 | Partial: normalisation path (video.mp4 + 16 kHz mono audio.wav) exists for link ingestion; local file upload still to do |
| M3 | **Done (6 Oct 2026)**; the eval-lecture fetch (4–6 lectures) still has to be run |
| M6 | Partial: FastAPI API, static HTML ingest/library/player page and `seekTo(seconds)` exist; ask box and citations still to do |
| All others | Not started |

## Phase 0: Foundation (week of 5 Oct)

- **M0: Close the environment's open items.** Done 7 Oct 2026 (`docs/ENVIRONMENT.md`). This covers the post-restart check, the Ollama call contract (model `qwen3.5:latest`, `think`, `num_ctx`, `format`, `keep_alive`), and a rewrite of `ENV_AUDIT_REPORT.md` as a single current-state document.
  Exit: one verification script passes from a cold boot.
- **M0b: Repo scaffold, config system, one ADR per decision, textbook chosen.**
  Exit: `docs/adr/` holds one ADR for every decision.

## Phase 1: Walking skeleton (to ~15 Nov)

- **M1: Core.** Workspace + manifest, SQLite job queue, GPU lease, single worker, CLI.
  Exit: a dummy two-stage job runs, resumes after being killed, and holds the lease.
- **M2: Ingest (upload).** ffprobe validation, then ffmpeg normalisation to the proxy video and 16 kHz audio.
  Exit: the Day 4 lecture normalises, and odd codecs are rejected cleanly.
- **M3: Ingest (URL).** Done. Design and open items are in `docs/features/README.md`.
- **M4: ASR stage + WER gate** in `tools/eval_wer`.
  Exit: the checkpoint and language decision is recorded as an ADR, with numbers.
- **M5: Windows + embedding (dense and sparse) + FAISS.**
  - Prerequisite for the sparse-weight work: `FlagEmbedding` is **not installed** and is not in `requirements.lock.txt`. Installing it needs the user's approval and a lockfile update (then re-run `scripts/verify_env.sh`). `tools/bench_models/loadtimes/verify_6b_loadtimes.py` fails at its bge-m3 step for the same reason.
  Exit: Test A reproduces through production code, and the CPU-query gate passes.
- **M6: Minimal API and UI.** Upload or link, progress, player, ask box, top-3 citations that seek the video.
  Exit: paste link → wait → ask → click → the video jumps to the right moment.

## Phase 2: Knowledge layer (to ~20 Dec)

- **M7: LLM extraction** with JSON Schema output: concepts, relations, importance (for F4) and `is_recap` (for F20).
  Exit: precision/recall against hand-labelled concepts on 2 lectures, and the LLM choice decided.
- **M8: Concept canonicalisation + graph build.**
  Exit: duplicate-node rate measured on 2 lectures, and the graph JSON passes schema checks.
- **M9: Router + fusion, reranker gate, retrieval eval harness** (Test A on more lectures, plus Test C).
  Exit: the router beats vector-only on graph-shaped queries, or the router is simplified.
- **M10: Book ingest** (PyMuPDF with page labels) + timestamp↔page fusion → F1, F2.
  Exit: Test B within ±2 pages on at least 20 queries.
- **M11: Grounded answer service** with citation validation, plus a frame grabbed at the cited timestamp → F6 Baseline.
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
  Exit: one results table per proposal metric.
- **M18: User study** with students and teachers (SUS + task success).
  Exit: ethics and consent completed before recruiting.
- **M19: Hardening** (error states, Tailscale demo path, nginx only if range requests misbehave).
  Exit: a clean demo on a fresh boot.
- **M20: Thesis and defense material.**
  - **Before making the repo final: remove lecture-derived text** (decided 6 Oct 2026: it stays until then). Keep `queries.csv` and `per_query_results.csv`, which are the project's own evaluation work.
    - Current tree: `docs/reports/embedding_bakeoff/results_seq1024/windows_W30.csv`, `windows_W60.csv` and `windows_W90.csv` (the full transcript); one transcript line in `docs/reports/PRE_MIGRATION_AUDIT.md` (the one in `ENV_AUDIT_REPORT.md` went with that file on 2026-10-07; it remains in git history); check the Urdu strings in `tools/bench_models/asr/verify_6a_whisper.py`.
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
  - Gate: concept extraction on 10 labelled windows, qwen3.5 vs Gemma 4 E4B. If the two are within noise, use the smaller model for interactive Q&A; using the larger one only for offline extraction is a valid split.
  - Optional lever: KV-cache quantisation.
- **M1: Job queue.**
  - A SQLite jobs table, one worker holding the GPU lease, and SSE progress: about 150 lines, no Celery.
  - On worker start, requeue or fail any stale "running" jobs.
- **M1: Session rule.**
  - Cache the processed workspace per video, keyed by content hash or YouTube ID, and include the pipeline version in the key.
  - "Nothing stored between sessions" becomes a UI/product rule: one video per session, no cross-session or cross-student data, no user history. Phrase it this way at the defense (M20).
- **M4: Whisper language setting.**
  - Earlier notes conflict. One says auto-detect beat forced `ur` because forcing dropped lines; another says forcing `ur` was needed because auto produced Devanagari.
  - Decide in the WER gate: medium and large-v3 × forced `ur` / auto-detect (4 configs, with large-v3-turbo as a 5th if time allows).
  - Confirm `task=transcribe`, not translate. Count dropped segments explicitly. Enable `word_timestamps=True`.
- **M5: Query-time VRAM conflict.**
  - BGE-M3 (1,141.7 MB measured bake-off peak, `Embedding_Report.md`; `MODELS.md` and `docs/ENVIRONMENT.md` carry 3,089 MiB, not re-run; re-measure in M5) and qwen3.5 (about 7.4 GB peak, `docs/ENVIRONMENT.md`) can't share 8 GB.
  - Encode documents on the GPU at ingest. Encode queries on the CPU in the API process (fp32, ~2.3 GB RAM), and run the reranker on the CPU too.
  - Gate: rerun Test A with CPU queries; Recall@3 must not change.
- **M5 / M9: Sparse weights.**
  - Use FlagEmbedding `BGEM3FlagModel` (dense + sparse in one pass) and fuse the two rankings with Reciprocal Rank Fusion.
  - If sparse adds nothing, drop the tie-break argument from the report.
- **M5: Window edges.**
  - Keep the 30 s target but snap edges to Whisper segment boundaries. Test 50% overlap (15 s stride) and adopt it only if Recall@3 improves.
  - Score hits by time overlap with the gold span, and dedupe overlapping hits.
- **M8: Concept identity across scripts.**
  - Canonicalisation is its own module. Each node has a canonical English label plus an alias list.
  - Find merge candidates by embedding similarity, then confirm them with the LLM.
- **M10: Page numbering.**
  - Store both the PDF page index and the printed page label (PyMuPDF `page.get_label()`, which may be empty if the PDF defines no labels).
  - Without this, the ±2-page criterion breaks silently.
- **Visual gate / V1–V3: Effort.**
  - Use a fixed time box: one owner, about 1 day a week, and a hard gate that decides continue vs freeze.
  - Scene detection + PP-OCR are cheap; PaddleOCR-VL is the time sink.