# C2 arm A reuse check (ADR-0048 Amendment 8, decision 2), 9 Nov 2026

**Result: arm A reuses the C1 Gemma run.** Everything that affects original-language extraction is identical. The C1 files are copied byte for byte into `C2-original/`, with `reused_from.json`. Arm A's cost is the C1 measurement of 18 Oct 2026 (not re-run).

- Script: `scripts/arm_a_reuse_check.py` (no generation call; Ollama gave only its version and the digest). Full output: `arm_a_reuse_check.json`.
- C1 run: `../C1/C1-gemma4-e4b/` (created 2026-10-18T18:00:07Z, harness 7). The code it ran is commit `bd6e9db` (2026-10-18T17:38Z), the last commit touching `extract/` or `llm/` before the run. The run files were committed in `67b4686`.
- Now: harness 8, the C2 translation stage. The bump by itself is not a difference (Amendment 8).

| Item | C1 | Now | Same |
|---|---|---|---|
| Ollama version | 0.40.2 (Session 2b; not in run.json) | 0.40.2 | yes |
| Model digest | `dc35e8d9c606…0c9c` | same | yes |
| Extraction prompt sha256 | `c7e061fc…4648` | same | yes |
| System message sha256 | `f2d8742f…a35f` | same | yes |
| Options (`num_ctx` 8192, `num_predict` 1024, temperature 0, seed 42, think false, `keep_alive` 0, `truncate` false, scale 0.761) | as listed | same | yes |
| `retry_error_chars`, self-test (`num_ctx` 2048, probe) | 1500; 2048, 10,505 chars | same | yes |
| Arm (model, input, batch_k, context) | gemma4:e4b, original, 1, none | same | yes |
| Target windows (text sha256 checked against `sample.json`) | 20 | same 20 | yes |
| Extraction requests rebuilt with current code, keyed with harness version 7 | 20 keys in `calls.jsonl` | 20 of 20 equal | yes |
| C1 replies re-parsed and validated with current code | `extraction.json` | equal | yes |

A key is the sha256 of the model, digest, messages, JSON Schema `format` and options. 20 equal keys mean byte-identical requests.

**Code on the extraction path** (`bd6e9db` against the working tree): 28 of 32 items are identical in source.
- **Whole files, identical:** `extraction_schema.py`, `extraction.schema.json`, `ollama_client.py` and the frozen prompt file.
- **Functions, identical:** `parse_reply`, `drop_dangling`, `extraction_messages`, `system_message`, `extraction_format`, `_options`, `prompt_overflow`, `truncate_self_test`, among others.
- **Four differ in source only,** from the C2 refactor:
  - `split_prompt` is new, shared with the translation prompt, and `split_extraction_prompt` now calls it;
  - `retry_messages` takes an optional `what` argument;
  - `load_prompts` now also checks the translation prompt's retry section, for english arms only.
- **Behaviour, identical:** the C1-era `prompts.py` (loaded from git) and the current one give equal results for `split_extraction_prompt`, `retry_messages` and `extraction_messages` on the frozen prompt. C1 Gemma needed no retry (0 of 20), so the retry path was not used in the run.
