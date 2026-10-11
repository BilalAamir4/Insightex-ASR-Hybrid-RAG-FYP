# ADR-0044: Index stage design (windows, BGE-M3 dense vectors, FAISS per lecture)

Status: Accepted
Date decided: 2026-10-11
Date recorded: 2026-10-11
Module: M5

## Context

ADR-0001 chose BAAI/bge-m3 on 30 s windows of native-script Whisper text, and ADR-0043 fixed the rules that decide the open M5 choices (window stride, sparse fusion, CPU queries, Roman Urdu). The pipeline needs a stage that turns `transcript.json` into a searchable per-lecture index inside the 8 GB GPU contract (ADR-0011), and a query path that never touches the GPU.

This ADR records the baseline built for gate G0. The choices ADR-0043 leaves to measurement (stride, sparse, CPU/GPU queries) are not decided here; each gets its own ADR if it changes this design.

## Decision

- **Stage.** `index` (version 1) runs after `asr` in `ingest_link` and `ingest_file`, as a GPU stage under the existing lease. Outputs: `windows.json`, `dense.faiss`, `index.json`.
- **Windows.** `insightex.windows.build`: fixed grid, window k covers [k x `index.stride_s`, k x `index.stride_s` + `index.window_s`); a segment belongs to the window its START falls in (the bake-off's rule); text is the member segments' text, NFC-normalised, stripped, joined by one space; empty windows are dropped; the last window's end is clipped to the audio duration. Defaults 30 s / 30 s (no overlap). Segment-boundary snapping exists behind `index.snap_to_segments` (default false: ADR-0043 gate G3s kept the grid).
- **Encoding.** SentenceTransformer BAAI/bge-m3 at the pinned snapshot `index.model_revision`, float16 on the GPU, `max_seq_length` 1024, batch 16, normalised vectors; the settings are the bake-off's. It runs in a child process (`python -m insightex.index.child`) with the ASR stage's process rules (PR_SET_PDEATHSIG, no inherited descriptors, SIGTERM then SIGKILL, timeout), so VRAM is returned when it exits. Pre-flight: at least `index.min_free_vram_mib` free or `INSUFFICIENT_VRAM`.
- **Index fingerprint.** `index_fingerprint(settings)` (model repo and revision, device, dtype, `max_seq_length`, batch size, window, stride, snapping, library versions, windows schema) is the stage's cache-key input, is written into `index.json` and the manifest entry with a 12-character `config_id`, and is printed by `insightex search`, so every search result names the index that produced it. Re-adding a lecture counts the index as current only if its stored fingerprint equals the current one.
- **Index.** FAISS `IndexFlatIP` over the unit vectors, one per lecture, row i = window id i. `index.json` records model, windows, truncated count, library versions, timings and peak VRAM.
- **Failure codes.** New: `ENCODE_CRASHED`, `ENCODE_TIMEOUT`, `NO_WINDOWS`; GPU and model-load failures reuse `INSUFFICIENT_VRAM`, `GPU_NOT_AVAILABLE`, `MODEL_LOAD_FAILED`, `GPU_OUT_OF_MEMORY`.
- **Cache key.** Chained from the `asr` key, plus stage name and version, model repo and revision, device, dtype, `max_seq_length`, batch size, window and stride, library versions and the windows schema version. A new transcript therefore rebuilds the index.
- **Query side.** `insightex.retrieval.search`: questions are encoded by the same code on the CPU in float32 (`retrieval.query_*`) in the calling process; exact search; optional de-duplication (a window overlapping a higher-ranked kept one by more than `retrieval.dedupe_min_overlap_s` seconds, default 0, is dropped; ADR-0043). `insightex search` is the CLI used by the evaluation scorer. `--device cuda` takes the exclusive GPU lease.
- **Resubmission.** An uploaded lecture counts as current only if it also has an `index` of the current stage version, so existing lectures get indexed when they are added again.
- **HTTP search:** `POST /api/lectures/{id}/search` (docs/contracts/api.md) encodes the question in the API process with the same `QueryEncoder` (CPU, float32, one question at a time, model loaded on the first question and kept) and returns window times and scores, never text.
- **Not built:** sparse vectors (gate G2 kept dense only, ADR-0043).

## Alternatives considered

- **Encode inside the worker process.** The CUDA context would keep VRAM until the worker ends.
- **FlagEmbedding for the baseline.** It is not installed and installing it moves the lockfile; the dense path is identical to the bake-off's, which G0 requires. It is considered at G2.
- **Search by loading vectors into NumPy.** FAISS is the decided index (ADR-0001) and keeps the later merge with the graph router simple.

## Consequences

- Every ingest adds a few seconds of GPU time (23 windows encode in about 0.1 s on Day 4; model load dominates).
- All stage-list assertions in the job tests grow from three to four stages.
- Changing the window or model settings rebuilds the index of each lecture on its next job.

- A citation seeks to the start of the first transcript segment inside the window (M6, M11), not to the window's grid start: the grid start can fall in a pause or mid-sentence. `windows.json` records `first_segment`; the transcript has its start time.

## Evidence

- Code: `backend/src/insightex/{windows,index,retrieval}/`, `config/default.yaml` (`index:`, `retrieval:`). Tests: `backend/tests/unit/test_windows_and_search.py`, `test_index_stage.py`.
- Gate G0 evidence: `docs/evidence/m5/`.

## Gate / revisit when

Revisit after G3 (window stride and segment snapping) and G2 (sparse vectors), and when the HTTP search endpoint is built.
