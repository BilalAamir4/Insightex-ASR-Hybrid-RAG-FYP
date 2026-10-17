# ADR-0049: M7 extraction harness call rules (output cap, budget gate, context, retry, C1 tie-break)

Status: Proposed
Date decided: 2026-10-18 (decisions by Bilal in Session 2b; this record awaits his review)
Date recorded: 2026-10-18
Module: M7

Records the decisions taken in M7 Session 2b on how the evaluation harness (`insightex extract-eval`, `backend/src/insightex/extract/`) calls the models. They apply ADR-0048 (gate rules, section 8 arms and fairness) and refine ADR-0002 (Ollama call contract) for M7 extraction calls only. ADR-0048 is not amended: its "every window valid after one retry", the C3 k rule and the C1 tie-break are unchanged in substance. All measurements behind these decisions used synthetic input only (no lecture text): `docs/evidence/m7/session2b_vram_numctx.md`.

## Context

Before the extraction prompt is frozen and C1 runs, the harness needed rules that keep the arms comparable under ADR-0048 decision 8 (each arm differs only in the thing being compared), on an 8 GB GPU shared with the Windows desktop. Session 2b part 1 measured both C1 models (`qwen3.5:latest` digest `44a38603…a399f`, `gemma4:e4b` digest `dc35e8d9…0c9c`) on Ollama 0.40.2 and found five issues:

1. With one fixed `num_predict` (1024) per call, a batch of k windows would get 1024/k output tokens per window (205 at k = 5), so C3 could fail validity through truncation, for reasons unrelated to extraction quality.
2. The ADR-0002 budget rule uses a character-based estimate. It over-counts these prompts by 1.5–1.7× (real `prompt_eval_count` / estimate: qwen3.5 0.625–0.647 over 9 prompts, Gemma 0.543–0.602 over 18), so it would refuse batch sizes that the real counts allow.
3. qwen3.5 runs at 100% GPU only up to `num_ctx` 8192 (peak 7,585 MiB). Gemma runs up to 131072.
4. The harness retried an invalid call by re-sending the identical request. At temperature 0, qwen3.5 returned byte-identical replies to identical requests, so that retry was a replay that could not fix anything.
5. `ollama ps` under-reports Gemma's size (about 270 MiB), and Gemma keeps 2,730 MiB of weights in system RAM. This raised the question of whether the C1 tie-break ("smaller VRAM peak") still measures what it should.

## Decision

1. **Output cap per window.** An extraction call of k target windows has `num_predict` = k × `extract.num_predict_per_window` (1024). Every window has the same output allowance in every arm. If the frozen prompt is too long for k = 5 under this cap, k falls to 4 or 3 under the existing ADR-0048 rule. The prompt is not trimmed to keep k = 5.
2. **Calibrated budget gate.** In the M7 harness, the ADR-0002 budget rule multiplies the prompt estimate by a per-model factor, `extract.token_estimate_scale`: the highest measured real/estimate ratio plus 5%, rounded up. That is qwen3.5 0.68 and Gemma 0.64. Unlisted models keep 1.0, so other callers of `chat_raw` are unchanged.
   - The gate must never refuse a k that the real `prompt_eval_count` measurement allows. This is enforced by `extract-eval measure`, which sends every case without the gate and flags `gate_refuses_real_fit`.
   - If the post-freeze measurement flags the chosen k, that model's factor is lowered before C3.
3. **One context size.** `extract.num_ctx` = 8192 for both C1 models (qwen3.5's maximum at 100% GPU). Gemma's larger usable context is not used.
4. **Retry in the same unit, with the errors fed back.** If any window of a call is invalid, the call is retried once in the same unit as the first attempt (all arms):
   - **Same unit:** a single window stays single, a batch stays a batch with the same windows and `num_predict`, and the context stays the same.
   - **The retry message:** the first attempt's messages plus one user message, the retry template with that attempt's validation errors in place of `{errors}`, capped at `extract.retry_error_chars` (1,500 characters).
   - **Frozen with the prompt:** the template is part of the extraction prompt file, after a line that is exactly `<<<RETRY>>>`. It is therefore frozen and hashed with the prompt, and it must ask for valid JSON only.
   - **Records:** `run.json` records per window `needed_retry` and `attempt_used`.
   - **Budget:** the retry call is the largest prompt a run can send, so `extract-eval measure` measures each case as its retry call with errors at the cap.
5. **C1 tie-break kept as written.** C1 arm A remains "the model with the smaller VRAM peak at the worst-case prompt" (ADR-0048 section 8).
   - **Reason:** VRAM is the constrained resource on this machine, and system RAM is not. Gemma's per-layer embeddings in RAM are a design feature of the model and the runner, not a spill.
   - **Evidence (Ollama debug log, `num_ctx` 8192):** all layers are on the GPU for both models (Gemma 43/43, qwen3.5 34/34). Only input embedding tables are held in pinned system RAM: Gemma 2,730.00 MiB (`per_layer_token_embd` 2,205.00 + `token_embd` 525.00), qwen3.5 545.63 MiB. That host-weight difference (2,184 MiB) is larger than the whole measured VRAM-peak gap (1,406 MiB: qwen3.5 7,585 against Gemma 6,179, synthetic input).
   - **Result:** on these peaks Gemma is arm A.

## Alternatives considered

- **Output cap 1024 + 512 × (k − 1).** Cheaper in context, but a batched window would get half the single-window allowance. Rejected for fairness.
- **Keep the uncalibrated estimate.** With the frozen prompt it would refuse k values that the real budget allows. Also considered: replacing the estimate with a real-count pre-check. Rejected because it would need an extra tokenisation call per request. Calibration plus the measure-tool check is enough.
- **A larger `num_ctx` for Gemma.** That would give the two C1 arms different context limits and k arithmetic. Rejected for comparability.
- **Retry the identical request (old rule).** Shown to be a replay at temperature 0 for qwen3.5. Rejected.
- **Retry failed windows singly.** It would give batched windows arm A's attempt as a second chance, but C3 would then partly measure single-window extraction. Rejected for "same unit".
- **Count pinned host weights, or total resident memory, in the C1 tie-break.** It would remove Gemma's placement advantage, but it would measure a resource that is not constrained here, and it would need an ADR-0048 amendment. Rejected.

## Consequences

- `config/default.yaml` `extract:` gains `num_predict_per_window`, `token_estimate_scale` and `retry_error_chars` (replacing `num_predict`). `HARNESS_VERSION` is 3 and `MEASURE_VERSION` 3, and both are in the cache keys, so replies from earlier harness versions are not reused.
- The extraction prompt written in Session 2b must contain the `<<<RETRY>>>` section, or the harness refuses it. The k check after the freeze includes the retry message.
- C1's tie-break favours Gemma because of where it keeps its embeddings. The C1 report must say so, citing the evidence above.
- **Open, not decided here: Gemma's speculative decoding.** Ollama runs Gemma with an MTP draft model by default. On synthetic input, Gemma's outputs at temperature 0 depend on session state, with the draft on and also with it off (`draft_num_predict: 0`):
  - with the draft on, a 3-window request repeated in the same session changed its output;
  - with the draft off, a 1-window request repeated in the same session changed its output (to the draft-on reply);
  - a request after a fresh load is reproducible, and every pattern repeated exactly across two runs each.

  Turning the draft off therefore does not make Gemma reproducible, and it stays on, as shipped. A likely cause is prompt-cache reuse between calls in one session (**unverified**). If so, a Gemma run's outputs may depend on call order: within a run, calls share the system prompt prefix. qwen3.5 was byte-identical in every repeat. The reproducibility of Gemma runs, and whether to use the draft in production (Session 3), are open before C1.

## Evidence

- `docs/evidence/m7/session2b_vram_numctx.md`: `num_ctx` sweep, real token counts, output-record sizes, the think check, the debug-log offload table, the determinism tables and the k arithmetic.
- `docs/measurements/m7/synthetic/`: `fill_*`, `prompt_counts_*`, `output_tokens_*`, `gen_check_*`, `determinism_*` and `ollama_debug_*` files, plus the scripts.
- Code: commits `9c791aa` (decisions 1, 2, 3) and `6aaebdc` (decision 4). Tests are in `backend/tests/unit/test_extract_harness.py`, including a C3 retry being one batch call, and `test_ollama_chat_raw.py`.

## Gate / revisit when

- **After the prompt freeze:** run `extract-eval measure --k 3 4 5` with the frozen prompt (its retry call). k is final only then. If `gate_refuses_real_fit` is flagged, lower that model's `token_estimate_scale`.
- **New models or a new Ollama version:** re-measure the calibration factors and `num_ctx` when a model's digest or the Ollama version changes.
- **Before C1:** decide how Gemma's session-state dependence is handled (see Consequences).
