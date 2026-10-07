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
