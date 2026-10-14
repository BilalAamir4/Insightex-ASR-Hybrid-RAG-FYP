# M5 evidence (session A: gate G0)

## Summary of the M5 gates (Day 4 lecture, 47 gold questions; provisional until M9)

| Gate | Comparison | Result | Verdict |
|---|---|---|---|
| G0 | production encoder against the legacy bake-off encoder, same window texts | top-10 order identical for 47 queries, largest score difference 0.0 | pass; baseline Recall@3 0.8085 (all), 0.8750 (24-query set), 0.8696 (English), 0.7500 (Roman) |
| G3s | fixed grid (A) against segment-snapped windows (B), 24 queries | 0.8750 against 0.8333; wins 0, losses 1, net -1 | tie, grid stays |
| G3 | grid stride 30 s (A) against 15 s (B), 24 queries | 0.8750 both; wins 2, losses 2, net 0 | tie, stride 30 stays |
| G2 | dense (A) against dense + sparse RRF k=60 (B), 24 queries | 0.8750 against 0.8333; wins 0, losses 1, net -1 | tie, dense only |
| G1 | GPU fp16 questions (A) against API CPU fp32 questions (B), 47 queries | min cosine 0.9999986; 0 wins, 0 losses | pass |
| G4 | Roman twin against English partner, 23 pairs, final configuration | Roman wins 0, losses 3 (A25, A19r, A22r), net -3; English partners 0.8696, Roman twins 0.7391 | fix needed (its own decision; not proposed or built) |

`g4_api_cpu_fp32.json` is the 47-question run through the API on the final configuration; `g4_pairs.txt` is the per-pair table (`score.py pairs`).

## GPU lease unloading Ollama (first real exercise, 11 Oct 2026; closes the M4 open item)

Ollama had to be started first (`E:\FYP\start_ollama.ps1`; it was not running at session start). `qwen3.5:latest` was then loaded with `num_ctx` 8192: `/api/ps` listed it, GPU memory used 7,854 MiB, free 165 MiB. The worker took the exclusive lease for the `index` stage and logged "memory.used before: 7854 MiB"; the model was unloaded; the stage's pre-flight saw 6,720 MiB free; the encoder subprocess peaked at 1,142.4 MiB allocated; on release the log shows "memory.used after: 1314 MiB" and `/api/ps` was empty. See `lease_and_index_job.log`. It worked as designed.

## API startup (question encoder loaded and warmed)

`retrieval.preload_query_encoder: true` (default): measured 2026-10-11 on the API process: ready after 5.2 s (0.6 s without preload), idle memory 2,400,212 KiB (2.29 GiB), first question 81 ms, then median 50.2 ms and p95 58.6 ms over the 47 questions, peak 2,430,904 KiB. Preloading without the warm-up question left the weights partly unloaded (idle 1.14 GiB, first question 3.0 s), so the warm-up is part of the preload.

Lecture: Day 4 upload, workspace `sha256-de27cb67c2acbedebd0c2c7416932b8a` (351 segments, 23 windows of 30 s). Provisional until Test A runs on more lectures (M9).

- `legacy_sanity/`: the restored legacy bake-off script (tag `import-baseline`, `_legacy_import/embedding/tools/eval_embeddings/embed_bakeoff.py`), run on its own SRT, queries and hit rule (bge-m3, W30, seq 1024, batch 16). Its per-query results and window file equal the recorded `docs/reports/embedding_bakeoff/results_seq1024/` rows exactly (28/28 queries: first-hit rank, hit@3, top-5 string).
- `g0_search_gpu.json`: `insightex search --device cuda --dtype float16 --k 10` for the 47 gold questions (production index and code).
- `g0_equivalence.json`: `tools/eval_retrieval/g0_compare.py` result. The legacy window builder reproduces the production windows; for all 47 queries the top-10 window order is identical and the largest |score difference| is 0.0 (tolerance 1e-4): PASS.
- `g0_scores.json`: the G0 baseline under the ADR-0043 hit rule, from `score.py score`.
- `lease_and_index_job.log`: the worker's lease and index lines for the job that built the index (Ollama model loaded before; see the session report).

## Session B: gate G3 (window stride)

- `g3_A.json`, `g3_B.json`: `insightex search --device cuda --dtype float16 --k 10` for the 47 gold questions on the segment-snapped index built with stride 30 s (A, 23 windows) and stride 15 s (B, 45 windows). `g3_A_scores.json`, `g3_B_scores.json`: Test A scores under the ADR-0043 rules (de-duplication: any overlap above 0 s).
- Compare with: `python tools/eval_retrieval/score.py compare --a docs/evidence/m5/g3_A.json --b docs/evidence/m5/g3_B.json --subset g23`.

## Session B (re-gate): fingerprinted indexes

`idx_grid30.json`, `idx_snapped30.json`, `idx_grid15.json` were produced after the cache fix, from freshly rebuilt indexes; each file carries `index_config_id` and `index_fingerprint` (grid30 `56d5cbf47e45`, snapped30 `e772272e32b3`, grid15 `c0775ceb56f8`). `idx_grid30.json` reproduces `g0_search_gpu.json` exactly (same windows, ranks and scores) and `idx_snapped30.json` reproduces `g3_A.json`. `g3_A.json` / `g3_B.json` (snapped, stride 30 / 15) came from rebuilt indexes too: their `index.windows` shows snap true, 23 and 45 windows. `g0_search_gpu.json` predates the fingerprint; its `index.windows` has no snapping field (grid).

- G3s (grid vs snapped): `score.py compare --a idx_grid30.json --b idx_snapped30.json --subset g23` -> net -1, tie, grid stays.
- G3 (grid stride 30 vs 15): `score.py compare --a idx_grid30.json --b idx_grid15.json --subset g23` -> net 0, tie, stride 30 stays.

## Session B: gate G2 (sparse)

- `g2_verify.json`: `tools/eval_retrieval/g2_verify.py` run in a throwaway venv (FlagEmbedding 1.4.2; torch and transformers 5.18.0 shared read-only from the project environment, nothing installed into the project venv). 70 texts (23 windows + 47 questions), fp16 and fp32 on the GPU, batch size 1: same token set for all 70, largest sparse weight difference 0.0, minimum dense cosine 0.9999999. Our encoder at batch 16 against batch 1 (fp16 noise): largest weight difference 0.0044.
  - The reference only loads the real sparse head when its model directory holds both `sparse_linear.pt` and `colbert_linear.pt`; with a repo id, or either file missing, FlagEmbedding silently random-initialises both (first attempts produced empty or wrong lexical weights). The check used a scratch directory with symlinks to the snapshot, the real `sparse_linear.pt`, and a placeholder `colbert_linear.pt` (never used: `return_colbert_vecs=False`).
- `g2_A_dense_full.json` (all 23 windows ranked, dense, GPU fp16 queries; identical to `idx_grid30.json` on the top 10), `g2_B_rrf.json` (dense + sparse, RRF k=60), `g2_sparse_only.json` (informational), `g2_sparse_diag.json`, `g2_*_scores.json`.
- Compare with: `python tools/eval_retrieval/score.py compare --a docs/evidence/m5/g2_A_dense_full.json --b docs/evidence/m5/g2_B_rrf.json --subset g23`.
- `sparse_linear.pt` (3516 bytes, sha256 `45c93804...`) was downloaded into the master cache and copied to the runtime cache; `run_F7_check.py` lists it as a matching LFS blob.

## Day 4 re-add (full re-run of normalise and ASR) and the network canary tests

- Re-added `lecture_test.mp4` after the re-add-check change (normalise key gained four fields, so every later key changed). Before/after: `audio.wav` sha256 `658c124d...` and `video.mp4` sha256 `0d6569bc...` identical; ASR 351 segments, segment lists byte-for-byte identical (segments-only sha256 `b5aa6d95...` both times); `transcript.json` as a file differs (sha256 `9cf49adb...` before, `43bae7c9...` after) only in `audio.path` (new normalise key directory) and `stats` (wall time 83.7 s -> 79.9 s, peak VRAM 4673 -> 4491 MiB); index config id `56d5cbf47e45` before and after, 23 windows; a search with the rebuilt index equals `idx_grid30.json` exactly (ranks and scores to 6 decimals). The G0, G3s, G3 and G2 evidence therefore stands.
- `test_youtube_probe_and_ingest` and `test_drive_public_large_file_probe_and_ingest` (`pytest -m network`) failed identically at the parent of the re-add change (`5c6953a~1`) and at HEAD: `KeyError: 'video'` at `test_ingest_known_links.py:33` (`info["video"]["codec"]`). Cause: the tests were stale against our own normalise schema 2, not an external failure (`normalise.json` describes the source in `probe` and the checks in `verify`; it has had no `video` or `audio` output block since schema 2), and the YouTube test's `["cached", "cached"]` stage list predated the ASR and index stages. Fixed in the commit that follows: the tests now read the outputs' own streams with ffprobe and expect four cached stages. Both pass with `-m network` (2 passed, 182 s).


## Session B: gate G1 (CPU fp32 queries against GPU fp16 queries)

- A = `insightex search --device cuda --dtype float16` (all 47 questions in one call, batch 16: the path every gate used), `g1_A_gpu_fp16.json`, vectors `g1_A_vectors.npy`. B = the production API path: `POST /api/lectures/{id}/search`, CPU fp32, one question per request, `g1_B_api_cpu_fp32.json`; question vectors from the same encoder through `insightex search --device cpu --dtype float32 --one-by-one` (`g1_B_vectors.npy`, `g1_B_cli_cpu_fp32.json`; its hits equal the API's). Same grid-30 dense index `56d5cbf47e45`.
- `g1_vectors.json`: minimum cosine(A, B) 0.9999986 (median 0.9999993), none below 0.999. Hit/miss: 0 wins, 0 losses on all 47 queries; Recall@3 0.8085 and MRR 0.6583 on both sides. Top-10 order differs for A02 and A25 only (the known near-ties at ranks 6-9). Largest top-10 score difference 3.9e-4.
- Latency of the CPU path through HTTP (after two warm-up questions; 47 timed): median 51.7 ms, p95 59.7 ms, max 60.3 ms; the first request, which loads the model, took 4.8 s. API process memory: 113 MiB before the first question, 2.30 GiB after the model loaded, peak 2.41 GiB (VmHWM 2,525,764 KiB) at the end of the 47 questions.

## Index config ids (traceability)

Index config id `56d5cbf47e45` (windows format 1) became `2bdfeed04854` (windows format 2, which adds `first_segment_start` to `windows.json`) on 2026-10-14 for the Day 4 lecture: the same windows, ranks and scores (`docs/evidence/m6/rebuild_check.json`). Evidence files in this folder and in `docs/evidence/m6/g5_*` that name `56d5cbf47e45` were produced with format 1 and remain valid for format 2.
