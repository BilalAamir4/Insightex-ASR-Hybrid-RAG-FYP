# ADR-0042: ASR stage design

Status: Proposed
Date decided: 2026-10-10
Date recorded: 2026-10-10
Module: M4

## Context

ADR-0039 chose the Whisper checkpoint (large-v3) from a gate run by a standalone tool; ADR-0040 made the language a per-lecture choice. The production pipeline needs a stage that turns a workspace's normalised `audio.wav` into a timestamped transcript on the M1 runner (ADR-0033, ADR-0034), within the 8 GB GPU contract (ADR-0011), and that reproduces the gate exactly for Hindi.

## Decision

Each decision with its reason:

- **Stage.** `asr` (version 1) runs after `normalise` in both `ingest_link` and `ingest_file`, as a GPU stage under the existing lease. *One path for every source, as for normalisation (ADR-0036).*
- **Model and options (4.4).** large-v3 (`Systran/faster-whisper-large-v3`, snapshot `edaa852e…` pinned in `asr.model_revision`), `task="transcribe"`, cuda, float16, beam 5, `vad_filter=True`, `word_timestamps=True`, temperature fallback on with `[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]`. Every other `transcribe()` option is set explicitly in `asr.transcribe` to the gate's value, taken from `tools/eval_wer/transcribe_one.py` and the stored `large-v3_ur/raw.json` metadata; options the gate never passed and `raw.json` does not record (`chunk_length`, `language_detection_*`, `log_progress`, constructor threads/workers) are pinned at the faster-whisper 1.2.1 defaults. The same options apply to every language; only `language` varies (the entry's `whisper_language`). *A library upgrade must not silently change behaviour, and Hindi must reproduce the accepted gate.*
- **Execution (4.5).** Whisper runs in a child process per job (`python -m insightex.asr.child`), started while the worker holds the GPU lease; the child loads the model, transcribes, streams NDJSON events and exits. It gets `PR_SET_PDEATHSIG` (a `kill -9` of the worker kills it too) and does not inherit the worker's descriptors (it never holds the lease's flock). Timeout `max(600 s, 1.0 × audio duration)`; on timeout, cancel or worker shutdown the child gets SIGTERM, then SIGKILL. *The process exit is the only reliable way to return all VRAM.*
- **GPU pre-flight (4.6).** After the lease is acquired, `nvidia-smi` must report at least `asr.min_free_vram_mib` (5500 MiB) free, else the stage fails at once with `INSUFFICIENT_VRAM`, naming free and needed MiB. *The gate peaked at 4638 MiB above baseline; failing fast beats an out-of-memory crash halfway through.*
- **Outputs (4.7).** `transcript.json` (schema 1, the single source of truth; contract `docs/contracts/transcript.schema.json`) and `transcript.vtt` (one cue per segment, a developer check only, never served). Times are seconds on the `audio.wav` timeline rounded to milliseconds; text is exactly what Whisper returned. Both are written atomically (temp file in the same directory, fsync, rename) inside the runner's staging directory, which is itself published by rename. *A killed stage can never leave a file that looks complete.*
- **Failures and warnings (4.8).** Fail on `INSUFFICIENT_VRAM`, `GPU_NOT_AVAILABLE` (nvidia-smi missing or failing), `MODEL_LOAD_FAILED`, `GPU_OUT_OF_MEMORY`, `TRANSCRIBE_CRASHED` (non-zero exit or no result), `TRANSCRIBE_TIMEOUT`, `MISSING_LANGUAGE` / `UNKNOWN_LANGUAGE` (raised while computing the cache key, so before the lease), and `EMPTY_TRANSCRIPT` (no segments or only whitespace for audio longer than 30 s). Warn but succeed on `TEMPERATURE_FALLBACK` (any segment with temperature > 0) and `HIGH_COMPRESSION_RATIO` (> 2.4); warnings go to `transcript.json` and to the manifest entry, and the job document shows them. *Codes are unprefixed members of the existing `ErrorCode` enum, as in M2; messages say what to do next.*
- **Resume (4.9).** Stage-level only: a killed ASR stage restarts from zero. *Partial checkpoints would add a resume path for a stage that takes minutes.*
- **Resume past a consumed input.** `normalise` deletes an uploaded original once it is published (ADR-0036), so after a crash in `asr` the `fetch` stage of an `ingest_file` job looked incomplete and its staged input was gone: the resumed job failed for good (found by the m4_verify kill test). The runner now counts a stage as cached when the manifest records it at the same key, a later hook removed some of its outputs, and the **next** stage is complete at its chained key. If the next stage must rerun, the stage reruns as before. *Before M4 nothing ran after `normalise`, so the gap could not show.* Evidence: the first `tools/m4_verify` run, `docs/evidence/m4/m4_verify_20261010T094021Z.json` (check 6 FAIL: killed at ASR 13%, restarted job failed at `fetch`); the rerun `m4_verify_20261010T094558Z.json` passes check 6 (job succeeded, attempts 2, `fetch` and `normalise` cached). Unit tests (`backend/tests/unit/test_jobs_engine.py`): the earlier stage counts as cached and is not run again when the next stage is complete at the matching chained key; when the next stage is not complete it does not count as cached and reruns, or fails with its own error if its input is gone, as before; the last stage is never vouched for. This changes only the runner's cache decision; ADR-0033 and ADR-0034 are otherwise unchanged.
- **Cache key (4.9).** Chained from the `normalise` key, plus stage name and version, language id and `whisper_language`, model name, repo and revision, device and compute type, the complete options, the compression-warning threshold, faster-whisper and ctranslate2 versions, and the transcript `schema_version`. The tier is not in it. A cache hit takes no lease and starts no child. *Any change to what produces the transcript invalidates it; promoting a language reprocesses nothing.*
- **One current transcript per lecture.** Resubmitting the same lecture with a different language runs ASR again under a new key; the new transcript replaces the old one (the superseded key's directory is removed) and the lecture shows the latest language. Resubmitting a file whose current transcript is in the same language is de-duplicated at submission (no job). *A lecture has one spoken language; keeping several transcripts would need a language choice in every later stage.*
- **Progress (4.9).** Through the existing job progress and SSE: last segment end / audio duration, updated only when both 2 s and 2 percentage points have passed since the last update (`asr.progress_min_interval_s`, `asr.progress_min_step`). Between updates the stage re-sends the unchanged value once a second, which keeps cancel and shutdown checks prompt without new events.
- **Statistics.** `wall_time_s` is transcription time without model load (as the gate's warm RTF), `rtf = wall_time_s / duration`, `peak_vram_mib` is the peak `nvidia-smi` memory.used during the child minus the reading taken before it started.

## Alternatives considered

- **Run Whisper inside the worker process.** CTranslate2 keeps its CUDA context until the process ends, so VRAM is not reliably returned before the next GPU stage.
- **Wait or retry when VRAM is short.** Hides contention and can stall the queue; the lease already unloads Ollama (ADR-0033), so remaining shortage is something else using the GPU and needs a person.
- **Store only VTT/SRT.** Loses per-segment confidence, temperature and word timings that M5 windowing and the evaluation need.
- **Keep transcripts for every language submitted.** See "one current transcript per lecture".

## Consequences

- Every ingest now uses the GPU for a few minutes per lecture (Day 4: see `docs/evidence/m4/`), and m2_verify needs a free GPU.
- M5 windowing reads `transcript.json` through `Workspaces.stage_output_dir(workspace_id, "asr")`.
- Changing any Whisper option, the model revision or the libraries re-transcribes every lecture on its next job.

### Limitations

- Measured on one Hindi lecture only (ADR-0039); other languages are untested (ADR-0040).
- Transcription can vary between runs when temperature fallback triggers on a segment (faster-whisper then samples at a higher temperature). Per-segment `temperature` is stored, and a `TEMPERATURE_FALLBACK` warning is raised, to make this visible. On Day 4 no segment fell back in the gate's runs 2 and 3.
- GPU sharing with Ollama: the GPU lease unloads Ollama on acquire (ADR-0033); the VRAM pre-flight is a final check for memory used by anything else and never waits, retries or unloads.

## Evidence

- Gate parameters: `tools/eval_wer/transcribe_one.py`, `tools/eval_wer/results/m4/large-v3_ur/raw.json`.
- Code: `backend/src/insightex/asr/` (`stage.py`, `child.py`, `transcriber.py`, `transcript.py`, `gpu.py`), `config/default.yaml` (`asr:`).
- Tests: `backend/tests/unit/test_asr_stage.py`, `test_asr_subprocess.py`, `test_asr_transcript.py`, `backend/tests/integration/test_asr_pipeline.py`, `test_asr_gpu.py` (`pytest -m gpu`).
- Verification: `tools/m4_verify` results in `docs/evidence/m4/`.

## Gate / revisit when

Accepted when all twelve `tools/m4_verify` checks pass (check 4 may WARN only with an explained audio difference), `tools/m1_verify` and `tools/m2_verify` still pass, and the human approves `docs/evidence/m4/manual_checklist.md`. Revisit when a second lecture is gated, when faster-whisper is upgraded, or when Q&A (M11) starts using the GPU while lectures are being ingested.
