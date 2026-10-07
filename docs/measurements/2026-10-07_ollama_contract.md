# Ollama contract probe (2026-10-07)

Model `qwen3.5:latest`, `think: false`, `temperature: 0`, `seed: 42`, `num_predict: 600`, `keep_alive: 10m`, JSON Schema `format`. Tool: `tools/ollama_contract_probe.py`. GPU: RTX 3070, 8192 MiB. Memory read from host `nvidia-smi` (whole GPU, polled every 0.2 s in a background thread) around each call.

Prompt: system prompt + 5 consecutive 30 s windows of the Day 4 transcript (from 60 s; 536 words, the 5 densest consecutive windows in the first 10 min) + 2 placeholder ML textbook chunks (350 and 383 words; placeholder text, not the chosen textbook).

| num_ctx | baseline MiB | peak MiB | model share MiB (peak - baseline) | free at peak MiB | PROCESSOR (`ollama ps`) | prompt_eval_count | truncated? | out tokens | tok/s | JSON valid | after unload MiB (within 200 of baseline?) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4096 | 971 | 7394 | 6423 | 798 | 100% GPU | 1760 | no | 269 | 64.9 | True | 967 (yes) |
| 8192 | 967 | 7397 | 6430 | 795 | 100% GPU | 1760 | no | 269 | 63.1 | True | 900 (yes) |

## Details

### num_ctx 4096

- `ollama ps`: `100% GPU`; model size 5490081790 B, of which in VRAM 5490081790 B; context_length 4096.
- done_reason `stop`, thinking text present: False, load 3.59 s, wall 8.8 s, VRAM samples 37.
- Sanity of output: {"n_concepts": 6, "quotes_found_verbatim": 4, "importance_in_1_5": true, "labels": ["Batch Learning (Offline Learning)", "Online Learning", "Incremental Training", "Production Environment vs Development Environment", "Learning Rate", "Out-of-Core Learning"]}; notes: none.

### num_ctx 8192

- `ollama ps`: `100% GPU`; model size 5628493822 B, of which in VRAM 5628493822 B; context_length 8192.
- done_reason `stop`, thinking text present: False, load 3.6 s, wall 8.9 s, VRAM samples 38.
- Sanity of output: {"n_concepts": 6, "quotes_found_verbatim": 4, "importance_in_1_5": true, "labels": ["Batch Learning (Offline Learning)", "Online Learning", "Incremental Training", "Production Environment vs Development Environment", "Learning Rate", "Out-of-Core Learning"]}; notes: none.

## Reading the numbers

- Largest prompt_eval_count seen: 1760. Truncation is flagged when a run saw fewer prompt tokens than the largest run, or when the count is within 2% of num_ctx.
- Baseline includes whatever the Windows desktop holds at that moment; the model's own share is peak minus that baseline.
- The earlier figures in `ENV_AUDIT_REPORT.md` (7,566 MiB peak, 626 MiB headroom) were not re-run here and are not confirmed by this file.

## Limits of this run

- The assembled prompt was only 1,760 tokens (the two placeholder chunks are 350 and 383 words, not 400). It is well under 4096, so prompt truncation at `num_ctx` 4096 was **not exercised**; "truncated? no" only means both runs saw the same 1,760 tokens. A prompt close to 4096 tokens has not been tested.
- Peak VRAM was within 3 MiB for both `num_ctx` values (7,394 vs 7,397 MiB), so on this run `num_ctx` 8192 cost no extra GPU memory over 4096. `ollama ps` reports the model at 5.49 GB (4096) and 5.63 GB (8192), both fully on GPU.
- Single run per setting, no repeats. Baseline here was about 970 MiB (Windows desktop only), after the Windows apps that held about 3.2 GB earlier were closed.

## Padded-prompt runs (near-limit context)

Prompt: system prompt + all 20 consecutive 30 s windows of the first 10 min of the Day 4 transcript + the 2 placeholder chunks above + additional textbook-style passages, added until `prompt_eval_count` reached the target (last passage trimmed at a sentence end). The extra passages are LLM-generated placeholder text (qwen3.5, 25 topics, cached at `$INSIGHTEX_DATA/eval/probe_textbook_chunks.json`), not filler repetition and not the chosen textbook. `num_predict` 600, otherwise the same call as above. Each measured run starts from a freshly loaded model (the calibration calls were unloaded first); calibration used `num_predict: 1` with a unique nonce so the prefix cache could not understate the count.

| num_ctx | target tokens | prompt_eval_count (measured run) | intact? | baseline MiB | peak MiB | model share MiB | free at peak MiB | PROCESSOR | out tokens | tok/s | done_reason | JSON valid | after unload MiB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8192 | 7000 | 6884 (calibrated 6889) | yes | 852 | 7421 | 6569 | 771 | 100% GPU | 600 | 63.7 | length | False | 861 (yes) |
| 16384 | 14000 | 13735 (calibrated 13740) | yes | 861 | 7296 | 6435 | 896 | 16%/84% CPU/GPU | 600 | 44.4 | length | False | 861 (yes) |

- num_ctx 8192: `ollama ps` model size 5628493822 B, in VRAM 5628493822 B, context_length 8192; load 3.57 s, wall 16.4 s; extra passages 7; sanity null; notes ["invalid JSON/schema: JSONDecodeError('Unterminated string starting at: line 1 column 2693 (char 2692)')"].
- num_ctx 16384: `ollama ps` model size 6554365456 B, in VRAM 5498543798 B, context_length 16384; load 5.08 s, wall 25.9 s; extra passages 21; sanity null; notes ["invalid JSON/schema: JSONDecodeError('Unterminated string starting at: line 1 column 3012 (char 3011)')"].

Single run per setting. "intact" means the measured run's prompt_eval_count matches the calibrated count (within 16 tokens) and is below num_ctx, i.e. nothing was cut.
## Reading the padded runs

- **Prompts were intact.** Measured `prompt_eval_count` was 6,884 (target 7,000) and 13,735 (target 14,000), each within 5 tokens of its calibration count and below `num_ctx`, so nothing was truncated.
- **8192 / ~6.9k tokens fits at 100% GPU** (peak 7,421 MiB, 771 MiB free, 63.7 tok/s).
- **16384 / ~13.7k tokens does not fit at 100% GPU.** `ollama ps` shows 16%/84% CPU/GPU; 5.50 of 6.55 GB is in VRAM. Peak reads lower (7,296 MiB) only because part of the model is on CPU. Generation drops to 44.4 tok/s. This is the case where the Windows-side `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` trial would apply; nothing was changed on Windows.
- **JSON invalid in both runs because of the output cap, not the model failing.** Both stopped with `done_reason: length` at `num_predict: 600`, cutting a string mid-way. With the 6.9k prompt in the earlier (lost) calibration-run the same call produced 474 tokens and valid JSON, so output length varies with the exact prompt. A 600-token cap is too tight for a long prompt that invites 10+ concepts; either cap the number of concepts in the prompt or raise `num_predict`. Not re-run.
- The first 8192 attempt (6,903-token prompt, 6 extra passages) was only in a console log because the 16384 fit failed afterwards; the table above is from the complete re-run with a fixed fitting loop.
