# G5 evidence (ADR-0046), run 2026-10-11 on the Day 4 lecture, grid 30 dense index `56d5cbf47e45`

Pre-registered rules: `docs/adr/0046-roman-urdu-question-rewrite.md`; prompt `config/prompts/query_rewrite_v1.txt` (sha256 `edac0394...2744e`). Provisional until M9.

- `g5_rewrites.md` / `g5_rewrites.json`: all 47 rewrites with the original, timing, raw model output and usability checks (for human review).
- `g5_A_original.json` (original only), `g5_B_fused.json` (original + rewrite, RRF k=60): `insightex search`-shaped runs for `score.py`. `g5_compare_roman.txt`, `g5_compare_english.txt`: the net counts. `g5_summary.json`, `g5_run.log`: latency and failure counts.
- Harness: `tools/eval_retrieval/g5_rewrite.py`. Searches go through the production API (CPU fp32, all windows ranked, no de-duplication); the rewrite call is made by the harness directly against Ollama with the pre-registered settings (think false, temperature 0, seed 42, num_ctx 8192, num_predict 64, keep_alive 10m, the ADR's JSON schema, no timeout). It does not go through `chat_json`: the standalone tool cannot import backend code, and `chat_json` builds its `format` from a pydantic model, so the request body differs from the ADR's literal schema only in that. M6 must send the ADR's schema.
- The model was loaded and warmed with a question outside the gold set (first call 18.9 s including a 17.0 s model load, not counted); 47 timed calls followed. The Ollama model was unloaded afterwards.

## M6 session A (backend for the ask box, ADR-0047), 2026-10-14

- **Index rebuilt for `first_segment_start`** (windows schema 2; index config id `56d5cbf47e45` -> `2bdfeed04854`; only the `index` stage ran, fetch, normalise and asr were cached). `rebuild_check.json`: against the committed evidence, the window ids, start/end times, ranks and scores of all 47 questions are identical, apart from the new field (and the config id): GPU fp16 `insightex search` equals `m5/g0_search_gpu.json`, `m5/idx_grid30.json` and `m5/g1_A_gpu_fp16.json`; API CPU fp32 search equals `m5/g4_api_cpu_fp32.json` and `g5_A_original.json` (top 10).
- **Replay of the G5 rewrites through production fusion** (`pytest -m replay backend/tests/unit/test_ask_flow.py`): for all 47 recorded rewrites, the production ranking's first 10 window ids equal `g5_B_fused.json` and the scores agree to 1e-12. Production fusion equals the G5 harness RRF (k=60, ties by smaller window id) on 200 random ranking pairs.
- **Request test** (`backend/tests/unit/test_rewrite.py`): the serialised production rewrite body is byte-identical to the body the G5 harness builds now and to a golden captured from `tools/eval_retrieval/g5_rewrite.py` as committed with the G5 run (`backend/tests/golden/rewrite_request_g5.json`, 5 questions including Urdu script and quotes); the bytes `post_chat` puts on the wire equal the golden; the warm-up request has the same model, keep_alive and options. The 47 recorded G5 replies are judged by production `parse_response` exactly as the harness judged them.
- **Live check against Ollama and the API on Day 4** (not an automated test; `tools/m6_verify` is session B):
  - Ollama unloaded: `ask` answers in 89 ms with 3 citations, `fallback_reason: llm_not_loaded`.
  - `warm-up` (202) loaded the model in 18.5 s with `context_length` 8192; the production rewrite body sent afterwards had `load_duration` 3.8 ms, so no reload.
  - Warm: three questions (Roman Urdu, English, Roman Urdu) answered in 0.52 to 0.62 s, rewrite used, 3 citations each; rewrite call 390 to 506 ms.
  - Another process holding the exclusive GPU lease (which also unloads the model): `ask` answers with `gpu_busy`, and `warm-up` is skipped with `gpu_busy`; after release `ask` falls back with `llm_not_loaded`.
  - Privacy: after these runs `api.log` holds only the JSON count lines (5 `ask`, 1 `warm_up`); none of the question words appear in it.

## M6 session B (ask box, citations, verification), 2026-10-14

- `m6_verify_20261014T173206Z.json` / `.log`: `tools/m6_verify` 13/13 on Day 4 in an isolated data directory (ingest 98 s). Highlights: the five checklist questions with the model warm each have a covering citation (A01 rank 1, A14 rank 2, A16 rank 3, A26 rank 3, A19r rank 2); all 47 questions through `/ask` give Recall@3 0.8511 (English 0.8696, Roman 0.8333) with no fallbacks and the same hit/miss as the gated G5 run; rewrite calls (52) median 556 ms, p95 764 ms, max 998 ms; fallbacks `llm_not_loaded`, `gpu_busy` (also skipping the warm-up) and `timeout` (1 ms limit) all return citations without an error; the API logs contain 59 count lines and no question or rewrite text.
- `manual_checklist.md`: the browser checks. **Not yet done** (needs you): the page was type-checked and its logic unit-tested (Deno, 26 tests) but not driven in a browser here.

Index config id `56d5cbf47e45` (windows format 1) became `2bdfeed04854` (format 2, same ranks and scores) on 2026-10-14; see `rebuild_check.json`. The `g5_*` files above name the old id.
