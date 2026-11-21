# ADR-0054: M7 Session 3: the production extraction stage, built on the frozen final configuration

Status: Accepted
Amended: 2026-11-21, Amendment 1 (build-time decisions: hold refusals, release as a job, Ollama error codes, no stage lease timeout, verify fixture, extraction states, plumbing keys); at the end. The decision text below is updated to match it.
Date decided: 2026-11-21
Date recorded: 2026-11-21
Module: M7 (Session 3)

Applies ADR-0048 (schema v1, its Consequences: production writes v1 records through `insightex.extract.extraction_schema`), ADR-0049 (harness call rules) and ADR-0050 to ADR-0053 (the final configuration). For the production stage only, it overrides ADR-0002's `keep_alive: "10m"` (decision 2). It also settles, as stage design, three questions from handoff 5 section 4: the scope of canonical names (open decision 4, scope only), invalid windows in production, and untested languages. Open decisions 1 (keep the model loaded) and 2 (self-pointing relations) get their own ADRs after this stage exists; 3 (stop list) and 5 (relations and importance) wait for a fresh lecture (decision 10).

## Context

M7 chose a configuration and measured it, but only through the evaluation harness (`insightex extract-eval`, harness version 8). No ingest job extracts anything, so later modules (M8 graph, F4 importance, F20 recaps) have no input. Session 3 adds the stage. The plan approved on 2026-11-21 builds it first with the frozen configuration unchanged (a walking skeleton), then changes one thing at a time, each with its own evidence.

Facts from the existing code that shape the design:
- **Stages publish all-or-nothing** (`jobs/stages.py`): outputs go to an empty staging directory, and a crash reruns the stage from the start. At about 9 s per window (report section 5), a 48-window lecture is about 7 minutes, so a crash near the end would repeat almost all of it.
- **Ollama is already its own process** (on Windows). The stage is an HTTP client and runs no CUDA itself. The GPU contract is met as the harness meets it: the exclusive lease, every resident model unloaded at the start, the model unloaded in `finally` (polling `/api/ps`).
- **The exclusive lease unloads only `ollama.model`** (qwen3.5, `jobs/gpu_lease.py`). Gemma is not that model, so the stage must unload whatever else is resident itself, as `run_arm` does.
- **Questions keep working during extraction.** The question rewrite takes a shared lease with `timeout_s` 0 (`retrieval/rewrite.py`); while the stage holds the exclusive lease it falls back to the original question only, and search runs on the CPU. `index` is published before `extract` starts, so the lecture is already searchable.
- **The transcript records the language tier** at processing time (`language.tier_at_processing`), and the API reads the current tier from `config/languages.yaml`.
- **ADR-0049 kept ADR-0002's `keep_alive: "10m"` for every non-evaluation caller**, the future production stage included. Using `keep_alive` 0 in production is therefore an override that must be recorded here.

## Decision

### 1. The stage

- **Name `extract`, version 1, `needs_gpu`.** It is the fifth stage of `ingest_link` and `ingest_file`, after `index`.
- **Input:** every window of the `index` stage's `windows.json` (fixed 30 s grid, ADR-0045), its native-script text unchanged (ADR-0051). Not only the M7 sample: all windows.
- **One window per call, no context** (ADR-0052, ADR-0053). No translation step (ADR-0051).
- **Model:** `gemma4:e4b` (ADR-0050), its tag in `extract.stage.model`.
- **Prompt:** the frozen extraction prompt v2 (`extract.prompt_file`, `extract.prompt_sha256` `c7e061fc…4648`); any other hash refuses the stage, as it refuses the harness.
- **Call rules: ADR-0049 unchanged.** `num_ctx` 8192; `num_predict` 1024; temperature 0, seed 42, `think` false; `truncate` false; the run-start truncation self-test (inside the lease, after the unloads, before any real call); the post-call overflow check; the estimate a warning only; one retry in the same unit with the frozen `<<<RETRY>>>` template; dangling relations dropped and counted; at most 10 concepts and 10 relations (the `format` the harness sends).
- **Same requests as the harness.** Request building and reply handling (call options, `extraction_messages`, `extraction_format`, `parse_reply`, `drop_dangling`, the self-test, the overflow check) move into one module that both the harness and the stage call. A test asserts that the stage's request body for a window is byte-identical to the request the harness builds today (harness 8) for the same window under the final configuration (arm `C4-window`, which is the C1 Gemma run; see Evidence) (model tag, messages, `format`, options, and `keep_alive`). The served digest is checked separately (decision 7); it is not part of the request body. `keep_alive` is part of the request body. The test holds today because `extract.stage.keep_alive` and the harness both send 0. The ADR for decision (a) must change this test to compare with `keep_alive` held equal. `HARNESS_VERSION` stays 8, because no harness request changes.
- **Shared and stage-only settings.** The stage reads the frozen keys it shares with the harness from `extract:` (prompt file and hash, `num_ctx`, `num_predict_per_window`, `truncate`, `retry_error_chars`, the self-test keys, `token_estimate_scale`). Settings that only the stage has go in a new `extract.stage:` block, each with a one-line comment and unit: `model`, `keep_alive`, `frozen_ollama_version`, `frozen_model_digest`, `allow_other_ollama_version`, `min_free_vram_mib`, `device_index` (0, the GPU the VRAM pre-flight reads), `heartbeat_interval_s` (1.0 s between progress heartbeats while a call runs). The VRAM peak sampling reuses the harness key `extract.vram_poll_interval_s`. There is no stage lease timeout (Amendment 1, decision 3). A later production change (ADR for decision (a)) then changes `extract.stage.keep_alive` without touching the harness.
- **Call timeout:** the stage uses the harness's per-call timeout through the same key, `ollama.request_timeout_s` (600 s; the harness's `chat_raw` calls pass no timeout of their own, so this default applies).
- **Fingerprint (stage key).** In the fingerprint:
  - `stage_version`;
  - the upstream key chain (the stage key chains the `index` key, as every stage key does);
  - `extract.stage.model` (tag);
  - `extract.stage.frozen_model_digest`;
  - `extract.prompt_sha256`;
  - the format version and the schema version;
  - `num_ctx`;
  - `num_predict_per_window`;
  - temperature;
  - seed;
  - `think`;
  - `extract.stage.keep_alive`;
  - `truncate`;
  - `retry_error_chars`;
  - `extract.stage.frozen_ollama_version`;
  - the self-test keys;
  - `token_estimate_scale`.

  Not in the fingerprint: `extract.stage.min_free_vram_mib`, `extract.stage.allow_other_ollama_version`, `extract.stage.device_index`, `extract.stage.heartbeat_interval_s`, `extract.vram_poll_interval_s`, the call timeout (`ollama.request_timeout_s`), and the language tier (decision 6).

  Changing `frozen_ollama_version` or `frozen_model_digest` in config changes the stage key, so every lecture is extracted again.
- **Order of the start checks.**
  1. Take the exclusive lease.
  2. Unload every resident model.
  3. Read `/api/version` and the served digest, and apply decision 7.
  4. The VRAM pre-flight.
  5. The truncation self-test.
  6. The window calls.
  7. In `finally`, unload the model and release the lease.

  Steps 1 to 5 run on every run of the stage, including a rerun where every reply comes from the resume store, because the reuse rule in decision 5 depends on step 3.
- **VRAM pre-flight:** after the unloads, free VRAM must be at least `extract.stage.min_free_vram_mib`, or the stage fails with `INSUFFICIENT_VRAM` (as `index` does). The run's VRAM peak and baseline are recorded. As in ADR-0049 decision 6, residency is not checked in a way that can fail the stage, because `ollama ps` cannot verify Gemma; the recorded VRAM above baseline is the reference (about 4.8 GB in M7).
- **Progress:** `ctx.progress` between calls and as a heartbeat while a call is running (so cancel and shutdown are noticed within a few seconds), with the message "Finding concepts: window i of n", plus ", k failed" once a window has failed.

### 2. Reload per call in production, for now (overrides ADR-0002's `keep_alive` for this stage)

`extract.stage.keep_alive` is 0: every call starts from a freshly loaded model, as in every M7 run. Reason: it is the only setting under which Gemma's output was shown to be reproducible (ADR-0049 decision 6), and the walking skeleton must equal the evaluated configuration. Cost: about 6.3–7.1 s of every ~9 s window (report section 5). Keeping the model loaded is decision (a), a separate ADR with its own determinism evidence on Day 4.

### 3. Outputs

In `stages/extract/<key>/`:

- **`extraction.json`**: a schema v1 document (`producer` `{kind: model, name: "extract stage v1 (gemma4:e4b)"}`), with the records of **valid windows only**, checked with `check_document` before publishing. The scorer in `tools/label_concepts` can read it like a harness `extraction.json`.
- **`extract.json`**: the stage's metadata:
  - `stage_version`, the fingerprint and its short `config_id`;
  - the model tag and the digest actually served, the Ollama version actually served, and whether `allow_other_ollama_version` was used;
  - the self-test result;
  - `language`: `{id, tier_at_processing}`, copied from the transcript (decision 6);
  - one status entry per window (decision 4);
  - totals: windows, `ok`, `ok_after_retry`, `failed`, `empty_after_retry`, dropped dangling relations, calls made, replies reused from the resume store;
  - cost: wall time, tokens per second (decode), VRAM baseline and peak, largest prompt.
- **Manifest extra:** `windows`, `failed`, `ok_after_retry`, `dropped_relations`, `config_id`, and `warnings` (decision 4).

Raw replies are not kept in the published stage directory (they are model output, internal; ADR-0041). They live only in the resume store (decision 5) until the stage is published.

### 4. Invalid windows in production

In evaluation an invalid window rejected the arm (ADR-0048 section 7). In production, one window that is still invalid after its retry must not fail the lecture.

- **Window statuses:** `ok` (valid on the first attempt), `ok_after_retry`, `failed`. A window valid only through the retry with no concepts also gets `empty_after_retry: true` (ADR-0049 Amendment 2's category).
- **A failed window is not written as an empty record.** An empty v1 record means "this window has no concept"; M8 and the scorer could not tell it from a failure. The failed window is left out of `extraction.json` and recorded in `extract.json`: `{window_index, status: failed, error_category, errors (capped at extract.retry_error_chars per attempt), attempts}`.
- **Error categories (closed list, model-output failures only):** `not_json`, `missing_record` (the reply has no single record for the window), `schema_invalid` (a validator rule), `truncated` (`done_reason` length), `prompt_too_long` (refused by Ollama under `truncate` false), `prompt_overflow` (the post-call check). When the two attempts fail differently, the category is the last attempt's; every attempt's errors are kept.
- **Infrastructure failures fail the stage,** because they are not about the window: Ollama unreachable or timing out, an HTTP error from Ollama, the model missing (`EXTRACT_MODEL_MISSING`, at the start check or mid-run), the self-test failing, the version or digest check (decision 7), the VRAM pre-flight, the lease. The job fails at this stage with a coded error and an English message. A retry of the job resumes (decision 5).
  - **Unreachable and timed out share one code,** `EXTRACT_OLLAMA_UNREACHABLE`, and the error message tells the two apart: "could not reach Ollama" vs "Ollama did not answer within ollama.request_timeout_s seconds". The stage tells them apart by the underlying httpx exception; the shared client (`chat_raw`) is not changed.
  - **The model missing** (`EXTRACT_MODEL_MISSING`): at the start check (decision 7) or mid-run (`ModelMissingError` from `chat_raw`). The message names `extract.stage.model`.
  - **An HTTP error from Ollama on one call** counts as an infrastructure failure (`EXTRACT_OLLAMA_ERROR`), except the `prompt_too_long` refusal, which is a window category, and connection failures and timeouts (`EXTRACT_OLLAMA_UNREACHABLE`). Its message names the window index and the HTTP status and never includes the response body. If such an error repeats on the same window, every retry of the job fails at that window and the lecture cannot finish extraction until the cause is found. This is accepted. The stage's error message names the window index so the cause can be found, and the failed job's error details record that window index.
- **The job succeeds** whenever at least one window is valid. If any window failed, the stage adds a warning (code `EXTRACT_WINDOWS_FAILED`) to its manifest entry, shown in both the lecture's and the job's `warnings` through the existing warnings path (`frontend/warnings.js`): "Concepts could not be found in k of n parts of this lecture." **The stage fails only if every window failed** (`EXTRACT_ALL_WINDOWS_FAILED`): that points to a system problem, not a window. Decided by Bilal on 2026-11-21; no percentage threshold, because M7 saw 0 invalid windows in 60 and any other number would be a guess.
- **A failed window stays failed** in the published stage for that key: a re-add finds the stage cached and does not call the model again. Under reload per call a new call would return the same reply anyway.
- **A lecture with zero windows:** if `windows.json` has no windows, the stage calls no model, publishes an `extraction.json` with no records and an `extract.json` with all totals 0, adds no warning, and succeeds. The lecture document shows extraction state `done`. `EXTRACT_ALL_WINDOWS_FAILED` requires at least one window.

### 5. Resume within the stage

- **The resume store:** each window's reply (both attempts, with metrics) is written as soon as it arrives, under the workspace in a folder named by the stage key, outside the staging directory. It is deleted after the stage is published, and an evicted workspace takes it with it.
- **A rerun of the stage** (crash, worker restart, job retry) reuses a stored reply instead of calling the model, then re-applies the post-call overflow check and validation. The key is the stage key, which chains every upstream key, so a stored reply is reused only for exactly the same window text and settings.
- **Atomic writes:** each stored reply is written to a temporary file in the same folder and then renamed into place, so a kill during a write leaves either no entry or a complete one. On rerun, a leftover temporary file is deleted and never read.
- **Served version and digest:** every stored reply records the Ollama version and the model digest that were actually served when it was made. A stored reply is reused only if both equal the values served in the current run. Otherwise it is ignored and the window is called again.
- **Only valid windows are reused:** a stored reply is reused only if its window ended valid (`ok` or `ok_after_retry`). A window that ended `failed` is called again on every rerun of the stage, so a rerun after a fixed system problem (for example after `EXTRACT_ALL_WINDOWS_FAILED`) does not repeat the old failures from the store.
- **Why this is sound now:** under reload per call, a repeated request returns a byte-identical reply (ADR-0049 decision 6), so a stored reply is what a new call would return. The ADR for decision (a) must re-check this if the model is kept loaded.
- `extract.json` records how many replies came from the store; the cost figures are those of the calls actually made.

### 6. Untested languages (ADR-0040)

- **The stage extracts every lecture,** whatever its language tier. Extraction output is internal (ADR-0041), and without it an untested-language lecture would have no concepts and later no graph.
- **The flag is carried:** `extract.json` records `language.id` and `language.tier_at_processing` from the transcript. The tier is not in the fingerprint, so promoting a language reprocesses nothing (as in `asr`, ADR-0042). Readers that show something to users take the current tier from config, as the API already does.
- **Evaluation:** untested lectures stay out of every extraction figure (ADR-0040). Extraction quality has been measured on Hindi only (two lectures), so "tested" for extraction means a tested ASR language plus M7's Hindi figures, nothing more.

### 7. Ollama version and model digest

- **At the start of the stage,** inside the lease, it reads `/api/version` and the served digest of `extract.stage.model`.
- **A digest different from `extract.stage.frozen_model_digest` (`dc35e8d9…0c9c`) always fails the stage** (`EXTRACT_MODEL_MISMATCH`): another model is not the evaluated configuration. A model that is not present at all fails it with `EXTRACT_MODEL_MISSING` (decision 4).
- **A version different from `extract.stage.frozen_ollama_version` (0.40.2) fails the stage by default** (`EXTRACT_OLLAMA_VERSION`). Reason: `truncate: false` is undocumented behaviour verified on 0.40.2 only (ADR-0049 Amendment 2), and the self-test checks only one way it could change.
- **`extract.stage.allow_other_ollama_version`** (default false) lets the stage run on another version and records the version served and the switch in `extract.json`. Turning it on needs its own ADR, because ADR-0049's revisit rule applies (re-measure the calibration, `num_ctx`, the VRAM reference and Gemma's layer check). The intended path after a deliberate upgrade is to update `frozen_ollama_version` in config, which changes the stage key. With `allow_other_ollama_version` on, the stage key still uses the configured `frozen_ollama_version`, `extract.json` records the served version, and the reuse rule of decision 5 stops replies from one version being reused on another.
- **The staged-installer check of `check_ollama_frozen.py` is not in the stage:** it uses a path specific to one Windows machine. `tools/m7_verify` runs that script first and stops on STOP.
- The failed job leaves the lecture searchable. Its message says what differs and that Bilal must decide.

### 8. Ingesting a lecture without extraction (an extraction hold)

So that a fresh lecture can be ingested and labelled later without the model reading it (gold before model output, ADR-0048 section 3):

- **How it is asked for:** `insightex ingest <url> --hold-extract` and `insightex ingest-file <path> --hold-extract` put `hold_extract: true` in the job payload. Not in the HTTP API or the UI: only a developer needs it.
- **Links whose lecture id is not known up front:** a non-YouTube link gets its lecture id (the content hash) only after download, so `insightex ingest <url> --hold-extract` refuses before creating any job, with the message: "A hold needs the lecture id before the job starts, and this link only gets one after download. Download the file and use: insightex ingest-file <path> --hold-extract". The exit code is non-zero. This is a CLI usage refusal with no error code.
- **No hold while a job is active:** `--hold-extract` refuses, and creates no job, when the workspace has any queued or running job. Error code `EXTRACT_HOLD_JOB_ACTIVE`, message: "A job for this lecture is already queued or running, so a hold could not stop it from extracting. Wait for it to finish, then ingest again with --hold-extract."
- **What the stage does:** it calls no model, takes no GPU lease and publishes no stage directory. The runner marks the job's stage `skipped` (shown as "Skipped (extraction held)" in the job list) and records in the workspace manifest an `extract_hold`: `{set_at, job_id}`. The job succeeds.
- **No hold after extraction:** `insightex ingest --hold-extract` and `insightex ingest-file --hold-extract` refuse, before any job is created, when the workspace already has a published `stages/extract/` directory under any key. Error code `EXTRACT_HOLD_AFTER_EXTRACTION`, message: "This lecture has already been through extraction, so a hold can no longer keep model output away from it before its gold is frozen. No job was created." The exit code is non-zero.
- **The hold is sticky:** while the manifest has an unreleased `extract_hold`, every later job on that workspace skips `extract` the same way, with or without the flag. A re-add from the UI therefore cannot extract a held lecture by accident.
- **Releasing it:** `insightex extract-hold release <lecture_id>` enqueues a job of a new kind, `extract_hold_release`, for that workspace; the CLI never writes the manifest (the worker-only rule in `jobs/workspace.py` stays, with no exception). The worker runs the job: it writes `released_at` into the hold record (the hold record is kept) with its usual atomic manifest write, takes no GPU lease, runs no stages, and succeeds. If the workspace has no unreleased hold, the CLI refuses before creating a job, with the message "This lecture has no active extraction hold." and a non-zero exit code. The release job does not trigger extraction. The next ingest job on the workspace (a re-add) then runs `extract` and finds every other stage cached. If an ingest job for the same workspace is queued ahead of the release job, it runs first and still skips `extract`, because the hold is still unreleased when it runs. `insightex extract-hold list` shows held workspaces.
- **The harness is unaffected:** `extract-eval run` reads `windows.json` directly. Running the evaluation on a held lecture after its gold is frozen is the intended path.
- **Re-add and `pipeline_is_current`:** a held workspace counts as current when every other stage is cached, so a re-add is a no-op while the hold stands.
- **Eviction:** jobs/cache.py:evict() skips any candidate workspace whose manifest has an extract_hold without released_at. If a candidate's manifest cannot be read, evict skips that workspace and logs a warning naming it, rather than risk evicting a held lecture. Releasing the hold makes the workspace evictable again; the pinned flag is never read or changed by the hold.
- **The lecture document** shows `extraction: {state}`, evaluated in this order:
  1. `held`: there is an unreleased hold;
  2. `done`: `extract` is published under the current stage key;
  3. `failed`: the workspace's latest finished job failed at `extract`;
  4. `outdated`: `extract` is published only under an older key;
  5. `none`: otherwise (for example a lecture ingested before this stage existed).

### 9. Canonical names (open decision 4, scope only)

The stage writes the model's labels and aliases exactly as the reply gives them, in schema v1. It does not merge, rename, map to textbook terms or filter. All of that is M8 (canonicalisation, ADR-0019; exit: duplicate-node rate on 2 lectures). Read-through findings such as surface-form labels ("performance matrix"), unclear tokens ("tp") and sentence-long aliases are inputs to M8, not stage rules.

### 10. What this ADR does not decide

- **(a) keeping the model loaded**: next ADR, after self-pointing relations; decision rule fixed before any run; Day 4 determinism evidence.
- **(b) self-pointing relations**: its own ADR, production only, tests and counts on Day 4 run files; the harness keeps the M7 rule.
- **(c) stop list, (e) relations and importance**: need a fresh Hindi lecture with gold, ingested with the extraction hold, rules registered before its one run. Relations and importance are stored as schema v1 requires until then; importance is decided with M14 (F12 produces the F4 labels), relations at the start of M8.
- **Context-aware extraction and batching:** unchanged (ADR-0052, ADR-0053); each would need its own evidence.

## Alternatives considered

- **A Python child process for the stage, like `asr` and `index`.** Not needed: the stage loads no CUDA library; the VRAM belongs to Ollama, which is released by the unload in `finally`. A child would add a process boundary and nothing else.
- **Reuse the harness's `run_arm` directly.** Rejected: it raises on a document error, treats an invalid window as an arm failure, writes evidence files and has a reply cache outside the workspace. The shared module keeps one request builder without importing evaluation behaviour into production.
- **Store a failed window as an empty record with a flag.** Rejected: schema v1 has no failure field (adding one is a schema change), and an empty record reads as "no concepts" to every consumer.
- **Fail the job above a share of failed windows.** Rejected by Bilal (2026-11-21): no evidence for any threshold.
- **Skip extraction for untested languages.** Rejected: those lectures would have no concepts and no graph, and the flag already keeps them out of evaluation.
- **Only warn on an Ollama version change.** Rejected: the overflow guard rests on undocumented behaviour of one version.
- **A global config switch to turn extraction off.** Rejected for the hold: easy to leave on or off by mistake, and not recorded per lecture. The per-ingest flag with a sticky manifest hold is recorded where the lecture is.
- **A non-sticky flag (payload only).** Rejected: a later re-add without the flag, for example from the UI, would extract a lecture whose gold is not yet frozen.
- **Keep the model loaded from the start.** Rejected for the skeleton: no evidence yet that Gemma is reproducible that way (ADR-0049); it is decision (a).

## Consequences

- **Speed:** about 9 s per window on the RTX 3070 until decision (a); a 48-window lecture adds about 7 minutes to ingest. During that time questions use the original wording only (no rewrite).
- **Code:** a shared request module used by the harness and the stage; the stage; `extract.stage:` config keys; error codes `EXTRACT_MODEL_MISMATCH`, `EXTRACT_MODEL_MISSING`, `EXTRACT_OLLAMA_VERSION`, `EXTRACT_SELF_TEST_FAILED`, `EXTRACT_ALL_WINDOWS_FAILED`, `EXTRACT_HOLD_AFTER_EXTRACTION`, `EXTRACT_HOLD_JOB_ACTIVE`, `EXTRACT_OLLAMA_UNREACHABLE` (Ollama unreachable or timed out), `EXTRACT_OLLAMA_ERROR` (another Ollama HTTP error) plus the existing `INSUFFICIENT_VRAM` and `GPU_NOT_AVAILABLE`; runner support for a skipped stage; jobs/cache.py: one more skip condition in evict(); the `--hold-extract` flag and `extract-hold` commands; the `extract_hold_release` job kind; the warning code `EXTRACT_WINDOWS_FAILED`; `docs/contracts/api.md` updated (the `skipped` stage status, the `extract_hold_release` job kind, the new error codes, the lecture document's `extraction` field and its states); the stage label "Find concepts" in the player page; an `extraction` summary (counts and state only) on the lecture document. No concepts are shown to users yet.
- **Lectures ingested before this stage** have no extraction (`state: none`); a re-add runs only `extract`.
- **Tests (step 2), fake client and synthetic input only:**
  - the byte-identical request against the request the harness builds today (harness 8) for the same window under the final configuration (arm `C4-window`, which is the C1 Gemma run; see Evidence) (model tag, messages, `format`, options, and `keep_alive`; the served digest is checked separately, decision 7, and is not part of the request body; the test holds because both send `keep_alive` 0, and the ADR for decision (a) must change it to compare with `keep_alive` held equal);
  - each error category, the infrastructure failures, all windows failed, and a job that succeeds with failed windows (and its warning);
  - resume after a kill partway through, with no repeated model calls;
  - a kill during a resume-store write leaves no partial entry, and the rerun calls that window again;
  - a stored reply with a different served Ollama version or digest is not reused;
  - a stored reply of a failed window is not reused; the window is called again;
  - a rerun where every reply comes from the store still runs start-check steps 1 to 5 and step 7;
  - zero windows: success, empty document, totals 0, no warning;
  - `--hold-extract` on a workspace with a published extract directory refuses with `EXTRACT_HOLD_AFTER_EXTRACTION` and creates no job;
  - A workspace with an unreleased hold is skipped by eviction; after release it can be evicted; a workspace whose manifest cannot be read is skipped and a warning is logged; a pinned workspace stays pinned after its hold is released;
  - a repeated Ollama HTTP error on one window fails the stage with that window's index in the error details;
  - the version and digest checks and the allow switch;
  - the untested-language flag;
  - the unloads at the start and in `finally`;
  - cache-key changes for each fingerprint field;
  - the hold: flag recorded, no model call and no lease, sticky across a later job without the flag, release then re-add runs `extract`, `pipeline_is_current` with a hold;
  - `--hold-extract` on a non-YouTube link refuses before creating any job;
  - `--hold-extract` with a queued or running job for the workspace refuses with `EXTRACT_HOLD_JOB_ACTIVE` and creates no job;
  - `EXTRACT_OLLAMA_ERROR` (window index and HTTP status in the message, no response body) and `EXTRACT_MODEL_MISSING` (at the start check and mid-run);
  - release via the job writes `released_at`; the CLI refuses when there is no hold; an ingest queued before the release still skips `extract`; release then re-add runs `extract`;
  - each `extraction.state`: `held`, `done`, `failed`, `outdated`, `none`.
- **`tools/m7_verify` (step 2):** standalone, over HTTP, after `check_ollama_frozen.py` prints OK; Day 4 only. Its checks include that the records for the 20 C1 target windows are byte-identical to `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C1/C1-gemma4-e4b/extraction.json`, which shows the stage equals the evaluated configuration (an equality check, not a quality figure), and a hold round trip on a 90 s cut of the Day 4 video (Amendment 1, decision 6). It prints counts and equality results only. The held-out lecture is not used. The C1 records are the reference because C4-window is the C1 run, and its requests were rebuilt identically with current code (see Evidence).
- **Manual check:** the stage label and the failed-window warning in the browser.

## Evidence

- The final configuration and its cost: `docs/reports/M7_extraction_report.md` sections 2 and 5; `docs/evidence/m7/Insightex_M7_handoff_5.md`.
- Reproducibility under reload per call: ADR-0049 decision 6 and `docs/evidence/m7/session2b_vram_numctx.md`.
- The overflow guards and their version dependence: ADR-0049 Amendment 2.
- C4-window is the C1 Gemma run reused under the identity rule (C4/C4-window/reused_from.json); its run.json, calls.jsonl and extraction.json are byte-identical to C1/C1-gemma4-e4b/. C4/arm_a_reuse_check.md (2026-11-09) rebuilt all 20 requests with harness 8 and matched C1's keys (harness 7, prompt c7e061fc…4648, digest dc35e8d9…0c9c, num_ctx 8192, num_predict 1024, temperature 0, seed 42, think false, keep_alive 0, truncate false, scale 0.761). run.json does not record the Ollama version (not recorded before 2026-11-13); 0.40.2 comes from Session 2b.
- Code read for this design (2026-11-21): `jobs/stages.py`, `jobs/runner.py`, `jobs/gpu_lease.py`, `index/stage.py`, `asr/stage.py`, `extract/harness.py`, `retrieval/rewrite.py`.

## Gate / revisit when

- **Acceptance:** Bilal reviews this draft; step 2 (the build) starts only after it is Accepted.
- **Step 2 exit:** tests pass, `tools/m7_verify` passes on Day 4 including the byte-identical check, the manual check is signed. The exit needs one `m7_verify` run in which the resume check actually ran and passed; a run that reports it "not run (already extracted)" does not count as passed for it. `m7_verify` never deletes stage outputs.
- **Decision (a):** if the model is kept loaded, decision 2 and the soundness argument of decision 5 are revisited in that ADR.
- **An Ollama or model change:** decision 7 and ADR-0049's revisit rule.
- **A fresh lecture:** decisions (c) and (e), with rules registered before its run.

## Amendment 1 (2026-11-21): build-time decisions

Decided by Bilal on 2026-11-21, after acceptance and before any step 2 code, on questions found while reading the code against this ADR. The decision text above is updated to match; where they differ, this amendment applies.

1. **`--hold-extract` on a link whose lecture id is not known up front.** A non-YouTube link starts in `pending-<job id>` and gets its lecture id (the content hash) only after download, so decision 8's refusal ("before any job is created") cannot run for it. `insightex ingest <url> --hold-extract` therefore refuses before creating any job, with: "A hold needs the lecture id before the job starts, and this link only gets one after download. Download the file and use: insightex ingest-file <path> --hold-extract". Exit code non-zero; no error code (a CLI usage refusal). YouTube links and files know the id up front.
2. **`--hold-extract` while a job for the same lecture is active.** Both enqueue paths de-duplicate onto an active job, which would extract if it has no hold. `--hold-extract` refuses, and creates no job, when the workspace has any queued or running job: `EXTRACT_HOLD_JOB_ACTIVE`, "A job for this lecture is already queued or running, so a hold could not stop it from extracting. Wait for it to finish, then ingest again with --hold-extract."
3. **No `extract.stage.lease_timeout_s`.** The runner takes the GPU lease for the stage, and the worker waits on it with no timeout by design (`FileGpuLease.hold`). The stage takes no lease of its own, so the key would control nothing. It is removed from decision 1. This ADR does not change lease behaviour.
4. **Ollama HTTP errors and a missing model.**
   - `EXTRACT_OLLAMA_ERROR`: an HTTP error from Ollama that is not a connection failure, a timeout or the `prompt_too_long` refusal. The message names the window index and the HTTP status and never includes the response body.
   - `EXTRACT_MODEL_MISSING`: the model is not present, at the start check (decision 7) or mid-run (`ModelMissingError` from `chat_raw`). The message names `extract.stage.model`. `EXTRACT_MODEL_MISMATCH` stays for a served digest that differs.
   - Both are infrastructure failures (decision 4).
5. **Releasing a hold is a job.** `insightex extract-hold release <lecture_id>` enqueues an `extract_hold_release` job; the worker writes `released_at` with its usual atomic manifest write, takes no GPU lease, runs no stages and succeeds. The CLI never writes the manifest; the worker-only rule in `jobs/workspace.py` stays with no exception. Without an unreleased hold the CLI refuses before creating a job ("This lecture has no active extraction hold.", non-zero exit). The release does not trigger extraction; a later re-add does. An ingest job queued ahead of the release runs first and still skips `extract`.
6. **The `m7_verify` hold round trip uses a 90 s cut of the Day 4 video.** A synthetic fixture cannot reach `extract`: a video with no speech fails at `asr` (`EMPTY_TRANSCRIPT`) or at `index` (`NO_WINDOWS`). For the same reason the zero-windows case of decision 4 cannot occur through the pipeline and is covered by unit tests only. `m7_verify` makes the cut itself with ffmpeg (stream copy if possible, otherwise re-encode) from a fixed start offset chosen from the Day 4 transcript so that all 90 s are speech, a named constant with a one-line comment. It prints the cut's sha256 and offset, ingests it with `ingest-file --hold-extract` (`extract` skipped), releases the hold, re-adds it (`extract` runs, every other stage cached), and removes the workspace through the existing lecture-removal path; a failed removal is a failed check, and it never deletes files directly. The model reading this cut is allowed because Day 4 is the dev lecture.
7. **Smaller choices.**
   - Config keys `extract.stage.device_index` (0) and `extract.stage.heartbeat_interval_s` (1.0 s); VRAM peak sampling reuses `extract.vram_poll_interval_s`. None is in the fingerprint.
   - Timeout and connection failure are told apart by the underlying httpx exception; the shared client is not changed.
   - Warning code `EXTRACT_WINDOWS_FAILED`, shown in both the lecture's and the job's `warnings`.
   - The `skipped` stage status is shown as "Skipped (extraction held)" in the job list; `docs/contracts/api.md` gains the status, the `extract_hold_release` job kind and the new error codes.
8. **`extraction.state`**, evaluated in order: `held` (unreleased hold), `done` (published under the current stage key), `failed` (the workspace's latest finished job failed at `extract`), `outdated` (published only under an older key), `none`. `outdated` is added to decision 8 and `api.md`; each state is tested.
9. **The `m7_verify` resume check** can only run while Day 4 has no extraction at the current key. A later run reports it "not run (already extracted)", which does not count as passed: the step 2 exit needs one run in which it ran and passed. `m7_verify` never deletes stage outputs.
