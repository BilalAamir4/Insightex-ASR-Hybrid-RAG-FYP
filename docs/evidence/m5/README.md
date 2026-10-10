# M5 evidence (session A: gate G0)

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
