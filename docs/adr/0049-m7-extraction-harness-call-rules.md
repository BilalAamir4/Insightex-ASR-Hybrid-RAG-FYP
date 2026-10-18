# ADR-0049: M7 extraction harness call rules (output cap, budget gate, context, retry, C1 tie-break, reload per call)

Status: Accepted
Accepted: 2026-10-18, by Bilal after review. Amended: 2026-10-18, Amendment 1 (at most 10 concepts and 10 relations per window); Amendment 2 (budget gate recalibrated on the frozen prompt, `truncate: false` and a post-call overflow check, valid-but-empty-after-retry category) **Proposed**, awaiting review; both at the end
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

## Amendment 2 (2026-10-18, Proposed): budget gate recalibrated on the frozen prompt, post-call overflow check

Status of this amendment: **Proposed**, awaiting Bilal's review. The text above and Amendment 1 are kept; where they conflict with this amendment, this amendment applies.

**Context.** After the prompt freeze (version 2, sha256 `c7e061fc…4648`), `extract-eval measure --k 3 4 5` on the Day 4 lecture measured these real `prompt_eval_count` / estimate ratios, each case as its retry call:

| Model | k = 3 | k = 4 | k = 5 |
|---|---|---|---|
| qwen3.5 | 0.793 | 0.785 | 0.778 |
| Gemma | 0.761 | 0.746 | 0.734 |

That is well above the synthetic-input ratios behind decision 2's factors (0.68 and 0.64). For qwen3.5 at k = 5, the gate estimated 2,718 tokens and would have allowed a call whose real prompt (3,108) plus `num_predict` (5,120) is 8,228, over `num_ctx` 8,192. That is the silent-truncation case the ADR-0002 budget rule exists to prevent; the measure tool flagged it as `gate_allows_real_overflow`. Evidence: `docs/evidence/m7/session2b_prompt_iteration.md` ("Final k with the frozen prompt") and the two `measure` reports in `docs/measurements/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/`.

**Decision.**

1. **Recalibrate on the frozen prompt.** `extract.token_estimate_scale` becomes:
   - **qwen3.5: 0.84**, its highest frozen-prompt ratio (0.793) plus a margin, as in decision 2. The gate then allows k = 4 (⌈3,746 × 0.84⌉ + 4,096 = 7,243) and refuses k = 5 (3,357 + 5,120 = 8,477). That matches the real counts.
   - **Gemma: 0.761**, its highest measured ratio with **no margin**. Any factor above 0.768 would make the gate refuse k = 5 (3,996 × factor + 5,120 > 8,192), although the real prompt fits (2,932 + 5,120 = 8,052).

   The estimate is now **a first filter only**: it refuses calls that clearly cannot fit, before anything is sent. The "+5% margin" of decision 2 no longer holds for Gemma.
2. **Two guards against a prompt that does not fit, each tested (synthetic input; see "Tests" below):**
   - **Case A, a prompt longer than `num_ctx`:** every harness call sends `truncate: false` (`extract.truncate`; in each call's options, so in the reply-cache key and in `run.json`). With it, Ollama 0.40.2 refuses the request with HTTP 400 `exceed_context_size_error` and the exact counts ("request (9204 tokens) exceeds the available context size (8192 tokens)"), instead of silently keeping only the end of the prompt.
     - `chat_raw` raises `PromptTooLong` with both counts.
     - The harness treats it like truncated output: an invalid attempt, never parsed, recorded with `prompt_too_long` (`prompt_tokens`, `num_ctx`). The same-unit retry applies, and `run.json` totals count `prompt_too_long_calls`.
     - `extract-eval measure` records the refusal and uses its count as the real prompt length.
     - Other callers of `chat_raw` send no `truncate` field, as before.
   - **Case B, a prompt that fits `num_ctx` but leaves less than `num_predict`:** Ollama does not cut or refuse this prompt, even with `truncate: false`. The post-call check covers it: if the reply's real `prompt_eval_count` plus `num_predict` exceeds `num_ctx`, the reply is invalid.
     - Treated like truncated output: never parsed and never scored.
     - Recorded in `calls.jsonl` with both counts (`prompt_overflow`: `prompt_eval_count`, `num_predict`, `num_ctx`) and the unused reply; `run.json` totals count `prompt_overflow_calls`.
     - It applies to every harness call (extraction and translation, fresh or from the reply cache).
   - **The estimate (point 1)** stays as a first filter in front of both.
3. **"Valid but empty after retry" as its own category.** A window that is valid only through the retry, and whose retry record has no concepts, is reported per window, separately from ordinary valid windows:
   - `run.json`: `empty_after_retry` per window and `valid_empty_after_retry_windows` in the totals;
   - the scorer (`tools/label_concepts`, `score` and `compare`): `valid_empty_after_retry_windows` in the validity section, plus `valid_empty_after_retry_a` / `_b` in a comparison. The scorer derives it from the record and `attempt_used`, so earlier runs are covered.

   Reason: in prompt version 4, windows 15 and 20 counted as valid and recovered by the retry, but the retry returned an empty record, and the window's concept was lost.

**Test: how Ollama reports a prompt that does not fit (18 Oct 2026, synthetic input only, before acceptance).** `docs/measurements/m7/synthetic/scripts/overflow_probe.py`, results in `overflow_probe_qwen3.5.json` and `overflow_probe_gemma4_e4b.json`.
- **The prompt:** a synthetic document with a first code word at the very start and a last code word at the very end, around numbered English filler lines. The model was asked for both code words.
- **How it was sent:** directly to `/api/chat` with `chat_raw`'s body (think false, temperature 0, the config seed, `keep_alive` 0), because the harness gate would not have stopped these prompts (see below) but is not the subject of the test.
- **True lengths:** measured first at `num_ctx` 16384.

| Model | Case | true prompt tokens | `num_ctx` | `num_predict` | reported `prompt_eval_count` | `done_reason` | first / last code word | prompt cut? | post-call check |
|---|---|---|---|---|---|---|---|---|---|
| qwen3.5 | A: prompt about 1,000 over `num_ctx` | 9,204 | 8,192 | 64 | **4,098** | stop | **lost** ("the") / kept | **yes, silently, from the start** | **not caught** (4,098 + 64 ≤ 8,192) |
| Gemma | A | 9,201 | 8,192 | 64 | **4,099** | stop | **lost** ("light wind") / kept | **yes, silently, from the start** | **not caught** (4,099 + 64 ≤ 8,192) |
| qwen3.5 | B: prompt fits, prompt + `num_predict` does not | 7,704 | 8,192 | 1,024 | 7,704 | stop | kept / kept | no | **caught** (7,704 + 1,024 = 8,728) |
| Gemma | B | 7,701 | 8,192 | 1,024 | 7,701 | stop | kept / kept | no | **caught** (7,701 + 1,024 = 8,725) |

What the test shows:
- **A prompt longer than `num_ctx` is cut silently.** Ollama keeps only the end of a prompt that does not fit, about half of `num_ctx` (4,098 of 9,204 tokens here). It reports `prompt_eval_count` as the kept part only and returns `done_reason: stop`, with no error. The start of the prompt (here the first code word; in a real call, the system prompt with its instructions) is lost, and the reply looks normal.
- **The post-call check therefore does not catch case A**: the reported count plus `num_predict` fits. It does catch case B, where Ollama does not cut the prompt. In case B the reply was correct, because the generation was short, but the check rejects it by rule: the call did not have its full `num_predict` available.
- **The gate did not stop either case.** This filler tokenises at 0.996 real tokens per estimated token, far above the frozen prompt's 0.734–0.793. With the factors of decision 1 here, the gate passes a prompt longer than 8,192 real tokens (one window, `num_predict` 1,024) only when real / estimate exceeds 0.960 (qwen3.5) or 0.870 (Gemma). Day 4's frozen-prompt calls are well below that; text that tokenises like this filler is not.

**Chosen method (18 Oct 2026).** The post-call check alone does not catch case A, because Ollama reports only the kept part of a cut prompt. Of the options considered, the first worked: a request setting that refuses an over-long prompt. Counting calls and a tokenize endpoint were therefore not needed and not built.
- **Tested on both models (synthetic, case A, `num_ctx` 8192):** with `truncate: false` at the top level of the `/api/chat` body (alone, and together with `shift: false`), both returned HTTP 400 `exceed_context_size_error`, with `n_prompt_tokens` 9,204 (qwen3.5) and 9,201 (Gemma) and `n_ctx` 8,192.
- **No effect on calls that fit:** with `truncate: false`, an in-budget call (1,038 / 1,035 tokens) and the case B call (7,704 / 7,701 tokens) returned the same `prompt_eval_count`, `done_reason` and byte-identical reply as without it.
- **The setting is undocumented:** found by test, not in Ollama's documentation. If an Ollama upgrade changes it, case A is again silent. The overflow probe and the harness check below must be re-run on any Ollama version change.

**Tests through the harness (18 Oct 2026, synthetic input only).**
- **Setup:** `scripts/harness_overflow_check.py` runs `run_arm` with the real `OllamaModelClient` (calibrated gate, `truncate: false`, `keep_alive` 0, the post-call check, the same-unit retry) on one synthetic window per case, single-window arm, `num_ctx` 8192, `num_predict` 1024, prompt `placeholder_prompt_retry.txt`, and a fresh reply cache. The window sizes come from Ollama's own refusal counts.
- **Results:** `harness_overflow_check_qwen3.5.json` and `harness_overflow_check_gemma4_e4b.json`.

| Case | qwen3.5 | Gemma | Caught by |
|---|---|---|---|
| A (prompt about 1,000 over `num_ctx`) | refused before sending (estimate 8,322 + 1,024 > 8,192) | refused before sending (7,540 + 1,024 > 8,192) | the estimate (first filter) |
| A with the estimate gate switched off (a prompt dense enough to pass the gate) | window invalid: both attempts refused by Ollama, 9,189 and 9,245 tokens | window invalid: both attempts refused, 9,187 and 9,245 tokens | **`truncate: false`** |
| B (prompt fits, prompt + `num_predict` does not) | window invalid: attempt 1 stopped by Ollama at the context limit (`done_reason: length` after 503 tokens, handled as truncated output); the retry (7,749 + 1,024 = 8,773) rejected | window invalid: both attempts rejected (7,687 + 1,024; 7,761 + 1,024) | **the post-call check** (and Ollama's own length stop) |

**Both case A and case B are now caught.** Unit tests cover:
- `truncate` sent, and `PromptTooLong` parsed from Ollama's error body (`test_ollama_chat_raw.py`);
- every harness call sending `truncate: false`;
- a refused prompt being an invalid attempt recorded with both counts;
- `measure` recording a refused prompt with its real length (`test_extract_harness.py`).

**Not changed, noted for review:** when the estimate refuses a call (`PromptBudgetError`), `run_arm` stops the whole run instead of marking that window invalid. That is existing behaviour from Session 2a. For C1 to C4 it means one over-long window aborts the arm's run.

**Consequences.**
- `HARNESS_VERSION` is 6 (5: post-call check; 6: `truncate: false`), which changes every reply-cache key. The frozen prompt's runs are made under version 6.
- The two scales are now fitted to Day 4 and the frozen prompt. Gemma's has no margin, so a held-out window that tokenises more expensively than Day 4's could pass the gate and then fail the post-call check, which costs a retry. That is the intended behaviour of a first filter.
- Prompt-iteration reports and the C1 to C4 reports list "valid but empty after retry" windows apart from ordinary valid windows.

**Gate / revisit.** Before the held-out lecture runs, check the chosen k against its real windows: run `extract-eval measure --k <k>` on the held-out lecture with the frozen prompt, for the C1 winner. If its worst-case retry call does not fit (real `prompt_eval_count` + `num_predict` > `num_ctx`), or the gate refuses it, k is lowered for that lecture under the ADR-0048 rule. That decision is recorded before the held-out run.

