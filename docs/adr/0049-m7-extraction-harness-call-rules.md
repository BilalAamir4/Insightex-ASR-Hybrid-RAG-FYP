# ADR-0049: M7 extraction harness call rules (output cap, budget gate, context, retry, C1 tie-break, reload per call)

Status: Accepted (2026-10-18, by Bilal after review)
Date decided: 2026-10-18
Date recorded: 2026-10-18
Module: M7

Records the decisions taken in M7 Session 2b (18 Oct 2026) on how the evaluation harness (`insightex extract-eval`, `backend/src/insightex/extract/`) calls the models. They apply ADR-0048 (gate rules, section 8 arms and fairness). For M7 evaluation calls only, they override four rules of ADR-0002 (Ollama call contract):
- its `keep_alive: "10m"` during a batch, replaced by reload per call (decision 6);
- its residency check, which cannot verify Gemma (decision 6);
- its "retry with a larger `num_predict`" for truncated output, replaced by a retry with the same `num_predict` (decision 4);
- its budget-rule estimate, now calibrated per model (decision 2).

The rest of ADR-0002 applies unchanged, and so does all of it for every other caller (M6 ask and rewrite, the future production extraction stage). ADR-0048 is not amended: its "every window valid after one retry", the C3 k rule and the C1 tie-break are unchanged in substance. All measurements behind these decisions used synthetic input only (no lecture text): `docs/evidence/m7/session2b_vram_numctx.md`.

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
   - **Truncation:** a truncated reply (`done_reason: length`) is an invalid attempt and is retried in the same way, with the **same `num_predict`**. ADR-0002 says truncated output is handled by retrying with a larger `num_predict`; for M7 evaluation calls that rule is overridden. A larger cap on retry would give a window that truncated more output allowance than every other window in every arm, against ADR-0048 decision 8. A window that truncates twice is invalid.
   - **Records:** `run.json` records per window `needed_retry` and `attempt_used`.
   - **Budget:** the retry call is the largest prompt a run can send, so `extract-eval measure` measures each case as its retry call with errors at the cap.
5. **C1 tie-break kept as written.** C1 arm A remains "the model with the smaller VRAM peak at the worst-case prompt" (ADR-0048 section 8).
   - **Reason:** VRAM is the constrained resource on this machine, and system RAM is not. Gemma's per-layer embeddings in RAM are a design feature of the model and the runner, not a spill.
   - **Evidence (Ollama debug log, `num_ctx` 8192):** all layers are on the GPU for both models (Gemma 43/43, qwen3.5 34/34). Only input embedding tables are held in pinned system RAM: Gemma 2,730.00 MiB (`per_layer_token_embd` 2,205.00 + `token_embd` 525.00), qwen3.5 545.63 MiB. That host-weight difference (2,184 MiB) is larger than the whole measured VRAM-peak gap (1,406 MiB: qwen3.5 7,585 against Gemma 6,179, synthetic input).
   - **Re-measured under the evaluated configuration (decision 6, reload per call):** at C1's worst-case prompt (k = 1, largest synthetic window) the peaks are qwen3.5 7,732 MiB and Gemma 6,198 MiB. The gap is 1,534 MiB, still smaller than the 2,184 MiB host-weight difference.
   - **Result:** Gemma is arm A.
6. **Reload per call; speculative decoding left at Gemma's default.** Every harness call, for both models and retries included, is sent with `extract.keep_alive: 0`, so each call starts from a freshly loaded model. This includes C2 translation calls, which use the same client (confirmed in review).
   - **Overrides ADR-0002's `keep_alive`:** for M7 evaluation calls, ADR-0002's `keep_alive: "10m"` during a batch is overridden. ADR-0002 chose "10m" to avoid a reload per call. That cost is accepted here for reproducibility: about 6 s per Gemma call and 3.5 s per qwen3.5 call, counted in each arm's wall time.
   - **Reason:** Gemma's output depended on session state. A request repeated within one loaded session could return a different reply, with its MTP draft model on and also with it off. A request after a fresh load was reproducible.
   - **Verified on synthetic input:** under reload per call, the 1-window and 3-window cases, each sent three times in a row through the harness's own client, gave byte-identical outputs for both models.
   - **Speculative decoding:** it stays at Gemma's default (draft on), because it is reproducible under reload. Turning it off did not remove the session-state effect.
   - **Recorded:** `keep_alive` is in each call's cache key and in `run.json`, and `ollama ps` is read during the call.
   - **Production:** whether production uses speculative decoding or reloads is a Session 3 decision.
   - **GPU residency in evaluation runs.** ADR-0002's residency check (`ollama ps` 100% GPU, `size_vram / size`) cannot verify Gemma. On the llamacpp runner, `ollama ps` reports Gemma at about 250 MiB, so its "100%" is computed over a figure that leaves out most of the model. Residency is therefore verified as follows:
     - **Gemma, once per model digest and Ollama version:** an Ollama debug-log load must show all layers offloaded (43/43, `CUDA0 model buffer` 3,018.87 MiB, with only the input embedding tables, 2,730.00 MiB, in pinned host memory). In addition, a measured VRAM peak serves as the reference: 6,198 MiB at C1's worst-case prompt.
     - **qwen3.5:** `ollama ps` still works (5,368 MiB, `size_vram / size` = 100%), and the debug log agrees (34/34).
     - **Per run, the harness performs no residency check that can fail a run.** It records `ollama ps` for every call (read during the call, `PsWatch`) and the run's VRAM peak (nvidia-smi, `cost.vram` in `run.json`). For Gemma, the recorded `ollama ps` figure is not evidence of residency. The C1 report compares each run's recorded VRAM peak with the reference: a Gemma run whose peak falls well below the reference would mean layers left the GPU. That comparison is made when reporting, not by the harness.

## Alternatives considered

- **Output cap 1024 + 512 × (k − 1).** Cheaper in context, but a batched window would get half the single-window allowance. Rejected for fairness.
- **Keep the uncalibrated estimate.** With the frozen prompt it would refuse k values that the real budget allows. Also considered: replacing the estimate with a real-count pre-check. Rejected because it would need an extra tokenisation call per request. Calibration plus the measure-tool check is enough.
- **A larger `num_ctx` for Gemma.** That would give the two C1 arms different context limits and k arithmetic. Rejected for comparability.
- **Retry the identical request (old rule).** Shown to be a replay at temperature 0 for qwen3.5. Rejected.
- **Turn Gemma's draft model off instead of reloading.** Tested: a same-session repeat still changed the output with the draft off. Rejected.
- **Keep the model loaded and rely on the reply cache or a fixed call order.** That would make reruns reproducible only by replaying stored replies. Any change to the order or the set of windows could change outputs, so arms would not be comparable call by call. Rejected for reload per call, which costs about 6 s per Gemma call and 3.5 s per qwen3.5 call.
- **Retry failed windows singly.** It would give batched windows arm A's attempt as a second chance, but C3 would then partly measure single-window extraction. Rejected for "same unit".
- **Count pinned host weights, or total resident memory, in the C1 tie-break.** It would remove Gemma's placement advantage, but it would measure a resource that is not constrained here, and it would need an ADR-0048 amendment. Rejected.

## Consequences

- `config/default.yaml` `extract:` gains `num_predict_per_window` (replacing `num_predict`), `token_estimate_scale`, `keep_alive` and `retry_error_chars`. `HARNESS_VERSION` is 4 and `MEASURE_VERSION` 3. The harness version is in every reply-cache key, so replies from earlier harness versions are not reused.
- The extraction prompt written in Session 2b must contain the `<<<RETRY>>>` section, or the harness refuses it. The k check after the freeze includes the retry message.
- C1's tie-break favours Gemma because of where it keeps its embeddings. The C1 report must say so, citing the evidence above.
- **Gemma's session-state dependence, resolved by decision 6.** On synthetic input, Gemma's outputs at temperature 0 depended on session state, with its draft model on and also off (`draft_num_predict: 0`):
  - draft on: a 3-window request repeated in the same session changed its output;
  - draft off: a 1-window request repeated in the same session changed to the draft-on reply;
  - after a fresh load: reproducible, and every pattern repeated exactly across two runs.

  A likely cause is prompt-cache reuse between calls in one session (**unverified**). qwen3.5 was byte-identical in every repeat. With reload per call, both models are byte-identical across repeats.
- **Cost of reload per call:** every call pays a model load: about 6 s for Gemma and 3.5 s for qwen3.5, from `E:\FYP\LLMs`. This counts in each arm's wall time; tokens/s is decode speed only.

## Evidence

- `docs/evidence/m7/session2b_vram_numctx.md`: `num_ctx` sweep, real token counts, output-record sizes, the think check, the debug-log offload table, the determinism tables and the k arithmetic.
- `docs/measurements/m7/synthetic/`: `fill_*`, `prompt_counts_*`, `output_tokens_*`, `gen_check_*`, `determinism_*` and `ollama_debug_*` files, plus the scripts.
- Code: commits `9c791aa` (decisions 1, 2, 3), `6aaebdc` (decision 4) and `fae14d9` (decision 6). Tests are in `backend/tests/unit/test_extract_harness.py`, including a C3 retry being one batch call, and `test_ollama_chat_raw.py`.

## Gate / revisit when

- **After the prompt freeze:** run `extract-eval measure --k 3 4 5` with the frozen prompt (its retry call). k is final only then. If `gate_refuses_real_fit` is flagged, lower that model's `token_estimate_scale`.
- **New models or a new Ollama version:** when a model's digest or the Ollama version changes, re-measure the calibration factors, `num_ctx` and the reference VRAM peak, and repeat the debug-log layer check for Gemma.
- **Production use (Session 3):** decide whether the production extraction stage reloads per call and keeps Gemma's draft model. Reload per call is an evaluation rule for reproducibility.

## Amendment 1 (2026-10-18): at most 10 concepts and 10 relations per window

Decided by Bilal on 2026-10-18, before version 1 of the extraction prompt ran. The text above is kept.

- **The cap:** extraction schema v1 caps the `concepts` list and the `relations` list of a window record at 10 items each. It is set as `"maxItems": 10` in `extraction.schema.json` (both byte-identical copies) and as `LIST_MAX = 10` in `extraction_schema.py`, whose validator reports an 11th item as an error.
- **The model's output:** the Ollama `format` the harness sends carries the same `maxItems`, so the model's constrained output can hold at most 10 of each (`FORMAT_VERSION` 2, which changes every request and so every reply-cache key).
- **Schema version:** it stays 1. The change only tightens the schema, and the existing label files still validate (Day 4 gold has at most 3 concepts per window).
- **Reason:** a hard bound on one record's size keeps the output-token budget of decision 1 meaningful, and stops a looping reply from growing a list without limit inside its `num_predict`.
- **Effect:** a window with more than 10 genuine concepts would be cut to 10. No Day 4 gold window comes near that.

