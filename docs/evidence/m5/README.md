# M5 evidence (session A: gate G0)

Lecture: Day 4 upload, workspace `sha256-de27cb67c2acbedebd0c2c7416932b8a` (351 segments, 23 windows of 30 s). Provisional until Test A runs on more lectures (M9).

- `legacy_sanity/`: the restored legacy bake-off script (tag `import-baseline`, `_legacy_import/embedding/tools/eval_embeddings/embed_bakeoff.py`), run on its own SRT, queries and hit rule (bge-m3, W30, seq 1024, batch 16). Its per-query results and window file equal the recorded `docs/reports/embedding_bakeoff/results_seq1024/` rows exactly (28/28 queries: first-hit rank, hit@3, top-5 string).
- `g0_search_gpu.json`: `insightex search --device cuda --dtype float16 --k 10` for the 47 gold questions (production index and code).
- `g0_equivalence.json`: `tools/eval_retrieval/g0_compare.py` result. The legacy window builder reproduces the production windows; for all 47 queries the top-10 window order is identical and the largest |score difference| is 0.0 (tolerance 1e-4): PASS.
- `g0_scores.json`: the G0 baseline under the ADR-0043 hit rule, from `score.py score`.
- `lease_and_index_job.log`: the worker's lease and index lines for the job that built the index (Ollama model loaded before; see the session report).
