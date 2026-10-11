# G5 evidence (ADR-0046), run 2026-10-11 on the Day 4 lecture, grid 30 dense index `56d5cbf47e45`

Pre-registered rules: `docs/adr/0046-roman-urdu-question-rewrite.md`; prompt `config/prompts/query_rewrite_v1.txt` (sha256 `edac0394...2744e`). Provisional until M9.

- `g5_rewrites.md` / `g5_rewrites.json`: all 47 rewrites with the original, timing, raw model output and usability checks (for human review).
- `g5_A_original.json` (original only), `g5_B_fused.json` (original + rewrite, RRF k=60): `insightex search`-shaped runs for `score.py`. `g5_compare_roman.txt`, `g5_compare_english.txt`: the net counts. `g5_summary.json`, `g5_run.log`: latency and failure counts.
- Harness: `tools/eval_retrieval/g5_rewrite.py`. Searches go through the production API (CPU fp32, all windows ranked, no de-duplication); the rewrite call is made by the harness directly against Ollama with the pre-registered settings (think false, temperature 0, seed 42, num_ctx 8192, num_predict 64, keep_alive 10m, the ADR's JSON schema, no timeout). It does not go through `chat_json`: the standalone tool cannot import backend code, and `chat_json` builds its `format` from a pydantic model, so the request body differs from the ADR's literal schema only in that. M6 must send the ADR's schema.
- The model was loaded and warmed with a question outside the gold set (first call 18.9 s including a 17.0 s model load, not counted); 47 timed calls followed. The Ollama model was unloaded afterwards.
