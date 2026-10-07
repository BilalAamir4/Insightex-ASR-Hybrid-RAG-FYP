# ADR 0001: Ollama call contract (qwen3.5:latest)

Status: decided for M0 on 2026-10-07. The model choice itself is still open until M7 (qwen3.5 vs Gemma 4 E4B); this ADR fixes how any call to Ollama is made. Final model calls stay with the user.

(An earlier ADR file, `0001-bge-m3.md`, records the embedding decision. Both carry number 0001; renumber one when convenient.)

## Context

- The GPU is an RTX 3070 with 8,192 MiB, shared with the Windows desktop. Ollama runs on Windows, bound to `127.0.0.1:11434`, reached from WSL at `http://localhost:11434`.
- The earlier audit recorded a 7,566 MiB peak and 626 MiB of headroom at `num_ctx` 8192 on a short prompt. It never tested a long prompt or a larger context, and it used `num_predict` 600.
- Three failures drove this contract: a call with the wrong model name (`qwen3:latest`) returned a 404; a 600-token output cap silently cut JSON in the middle of a string on longer prompts; and Ollama will quietly truncate an over-long prompt or offload layers to CPU if the context is too big.
- Idle VRAM is not constant. After closing Windows apps it ranged from 600 to 1,273 MiB (right after boot); with them open the GPU showed about 3.2 GB used, roughly 2.3 GB more.

## Decision

Every LLM call goes through `backend/src/insightex/llm/ollama_client.py` (`chat_json`, `unload`) with this contract.

| Field / rule | Value | Reason |
|---|---|---|
| Model name | exactly `qwen3.5:latest`, checked against `/api/tags` before the first call | A near-miss name gives a 404; fail with a clear error and the list of installed models instead. |
| Endpoint | `POST {OLLAMA_BASE_URL}/api/chat`, `stream: false` | One complete reply to validate; no partial JSON. |
| `think` | `false` | Verified: the model returned no `thinking` field and no `<think>` text. The client raises if thinking text appears anyway. |
| `format` | JSON Schema generated from a pydantic model class | The engine constrains the output shape; the reply is then validated with the same model (`model_validate_json`). |
| `options.num_ctx` | **required, no default in the client**; project default 8192 | A forgotten value would silently inherit Ollama's VRAM-based default (4096 here). 8192 was measured at 100% GPU with a 6,884-token prompt. |
| `options.num_predict` | explicit field, default 1024, overridable per call | 600 cut valid JSON in half on long prompts. 1024 gave `done_reason: stop` with 786 output tokens. |
| Budget rule | estimated prompt tokens + `num_predict` must be <= `num_ctx`, else `PromptBudgetError` before anything is sent | Prevents silent prompt truncation. Estimate: 3.5 chars/token for Latin text, 1.5 chars/token for Arabic-script (Urdu) text, 8 tokens per message. Deliberately conservative, not calibrated. |
| Truncated output | `done_reason == "length"` raises `OutputTruncated` (carries `eval_count` and `num_predict`); the content is never parsed | A cut-off JSON string can look nearly valid; treating it as an error is the only safe option. |
| `options.temperature`, `seed` | 0 and 42 | Reproducible runs. (The earlier audit used 0.1; its reproducibility test had one chunk with mean Jaccard 0.47 at 0.1.) |
| `keep_alive` | `"10m"` during a batch | Removes the ~8.7 s reload per call seen in the earlier audit. |
| Unload | `unload()`: `POST /api/generate` with `keep_alive: 0`, then poll `/api/ps` until the model is gone; call it in a `finally` block | The GPU belongs to one stage at a time (VRAM contract). Verified: VRAM returned to within 5 MiB of baseline after every unload. |
| Logging | after each call, log estimated prompt tokens next to the real `prompt_eval_count` | Lets the estimate ratios be calibrated later. |
| Metrics returned | `prompt_eval_count`, `eval_count`, `eval_duration`, tokens/sec, load and total duration, `done_reason` | `prompt_near_ctx_limit` (>= 98% of `num_ctx`) flags a possible truncated prompt. |
| Residency check | `ollama ps` PROCESSOR must read 100% GPU; the self-test checks `size_vram / size` from `/api/ps` | A partial CPU split costs speed (below). |

## Measured numbers

All on 2026-10-07, RTX 3070, `qwen3.5:latest`, `think: false`, `temperature` 0, `seed` 42, from `docs/measurements/2026-10-07_ollama_contract.md` (probe: `tools/ollama_contract_probe.py`). Peak is the host `nvidia-smi` maximum during the call (0.2 s polling); model share = peak minus baseline; free = 8,192 minus peak. Baseline includes the Windows desktop.

| # | num_ctx | prompt_eval_count | num_predict | baseline | peak | model share | free | PROCESSOR | out tokens | tok/s | done_reason | JSON valid |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4096 | 1,760 | 600 | 971 | 7,394 | 6,423 | 798 | 100% GPU | 269 | 64.9 | stop | yes |
| 2 | 8192 | 1,760 | 600 | 967 | 7,397 | 6,430 | 795 | 100% GPU | 269 | 63.1 | stop | yes |
| 3 | 8192 | 6,884 | 600 | 852 | 7,421 | 6,569 | 771 | 100% GPU | 600 | 63.7 | **length** | **no (cut off)** |
| 4 | 16384 | 13,735 | 600 | 861 | 7,296 | 6,435 | 896 | **16%/84% CPU/GPU** | 600 | 44.4 | **length** | **no (cut off)** |
| 5 | 8192 | 6,905 | 1024 | 879 | 7,374 | 6,495 | 818 | 100% GPU | 786 | 61.6 | stop | yes |
| 5b | 8192 | 6,903 | 600 | 862 | 7,424 | 6,562 | 768 | 100% GPU | 474 | 59.7 | stop | yes |

- Run 5b was recorded only in a console log (its report write was lost when the 16384 fit failed); the numbers are from that log, with an earlier prompt variant (6 extra passages instead of 7, no concept cap).
- In every run the prompt was intact: measured `prompt_eval_count` was within 5 tokens of a calibration count made with a prefix-cache-defeating nonce, and below `num_ctx`. Runs 1 and 2 use only ~1,760 tokens, so truncation near 4096 was not exercised.
- `ollama ps` model size: 5.49 GB (ctx 4096), 5.63 GB (ctx 8192), 6.55 GB with 5.50 GB in VRAM (ctx 16384).
- Peak VRAM was within 3 MiB for ctx 4096 vs 8192 (rows 1 and 2), so the larger context cost no extra GPU memory at that prompt size. The lower peak in row 4 only reflects layers moved to CPU.
- Free VRAM at peak across all 100%-GPU runs: 768 to 818 MiB.
- Output of run 5: 16 concepts against a requested "at most 15"; 11 of 16 `evidence_quote` values appeared verbatim in the input.

## Consequences

- Default context is 8192; a prompt of about 7,000 tokens plus 1,024 output tokens fits at 100% GPU with about 800 MiB free on an otherwise idle desktop.
- Callers must size their prompts. Anything that would exceed `num_ctx - num_predict` fails loudly; the caller splits the input (fewer windows or passages per call) instead of raising the context.
- Truncated output is an error to handle (retry with a larger `num_predict` or less requested output), never a result to parse.
- Operational constraint: **Windows GPU-heavy apps must be closed during work.** They held about 2.3 GB of VRAM at one point (about 3.2 GB used with no model loaded, against about 0.9 GB clean). With that load the 7.4 GB peak does not fit. `tools/verify_env.py` reports the idle baseline and fails the unload check if VRAM does not return to within 200 MiB of it.
- Windows must start Ollama before the pipeline (Task Scheduler runs `E:\FYP\start_ollama.ps1` at logon; see `docs/ENVIRONMENT.md`).
- Single-user, single-GPU: one CUDA stage at a time stays in force; Ollama is a separate process and must be unloaded before Whisper or bge-m3 runs.

## Alternatives considered

| Alternative | Outcome |
|---|---|
| `num_ctx` 16384 | **Rejected.** One run (prompt 13,735 tokens, old 600-token cap): `ollama ps` showed 16%/84% CPU/GPU, 5.50 of 6.55 GB in VRAM, 44.4 tok/s (about 30% slower than at 8192). A 14k-token call is also rarely needed if inputs are chunked. |
| KV-cache `q8_0` + flash attention (`OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_FLASH_ATTENTION=1`, set on Windows) | **Not tested; left as an option** for longer context. It would need a Windows-side change, which was not made. Its effect on speed, VRAM and extraction quality is unknown. |
| Gemma 4 E4B as the LLM | **Not measured.** It stays the M7 fallback/alternative (qwen3.5 vs Gemma 4 E4B is an open decision). This contract is model-agnostic apart from the exact name string; a change of model re-runs the probe. |
| Default `num_predict` 600 (earlier audit value) | Rejected: cut valid JSON in runs 3 and 4. |
| Parse truncated JSON by repairing it | Rejected: a repaired object can silently lose concepts or end a quote early. |
| Leave `num_ctx` to Ollama's default | Rejected: the default depends on free VRAM (4096 here) and changes silently. |
| Plain `format: "json"` instead of a JSON Schema | Rejected: the earlier audit saw no validity difference (10/10 both), but the schema also enforces the fields and `additionalProperties: false` in the engine. |

## Open items for M7

1. **Prompt-level caps are advisory.** The model returned 16 concepts against "at most 15". Enforce limits in the schema (`max_length` on the list in the pydantic model, which becomes `maxItems` in the JSON Schema), not only in the prompt text.
2. **Quote grounding.** Only 11 of 16 evidence quotes appeared verbatim in the input. Extraction needs a quote-grounding check that drops or flags concepts whose quote is not in the source window.
3. **Calibrate the token estimate.** Use the logged `prompt_eval_count` values to tune the 3.5 (Latin) and 1.5 (Arabic-script) chars/token ratios; neither was measured, and no Urdu-script prompt was run through the probe.

Evidence limits: the 8192 result rests on single runs (two long-prompt runs at 8192, one of which finished valid; the 6,884-token run was cut by the old cap), and the 16384 rejection rests on one run made with the old 600-token cap (its JSON failure is the cap, but the 16/84 CPU/GPU split and 44.4 tok/s do not depend on it). No run was repeated, and extraction quality was not evaluated here.

## Evidence

`docs/measurements/2026-10-07_ollama_contract.md`; `tools/ollama_contract_probe.py`; `backend/src/insightex/llm/ollama_client.py`; `tools/verify_env.py` (12/12 after the full restart, report in `$INSIGHTEX_DATA/env_reports/`).
