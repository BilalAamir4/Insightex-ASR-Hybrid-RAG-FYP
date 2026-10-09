# ADR-0035: Link ingestion on the runner: chain root, provisional workspace and rebind

Status: Accepted
Date decided: 2026-10-09
Date recorded: 2026-10-09
Module: M1

## Context

Link ingestion (M3) ran on an in-process thread pool with in-memory job state and wrote `lectures/<lecture_id>/` (ADR-0025). ADR-0033 and ADR-0034 gave the project a SQLite job queue, a stage runner and content- or ID-addressed workspaces. A YouTube link has its workspace id (`yt-<id>`) before any download. Any other link only has one after the file is downloaded and hashed. ADR-0034 chains stage keys from the workspace id, so a provisional id would change every key on every run and nothing would ever be cached.

## Decision

- **Pipeline `ingest_link`**, payload `{"url"}`, two CPU stages: `fetch` (download; outputs `source`, `source.json`, optional `thumbnail.src`) and `normalise` (outputs `video.mp4`, `audio.wav`, `thumbnail.jpg`, `normalise.json`). The fetch output is kept; disk is bounded by `cache.max_bytes` and eviction.
- **Chain root.** A pipeline may register `chain_root(payload, workspace_id)`, the upstream key of its first stage. For `ingest_link` it is `yt-<id>` for YouTube and the normalised URL for every other link. This amends ADR-0034, where the first stage's upstream key is the workspace id (still the default).
- **Provisional workspace.** Non-YouTube jobs are enqueued as `pending-<job id>`. After `fetch` is published, the runner rebinds the job to `sha256-<first 32 hex of the content hash>` between stages (`ctx.rebind_workspace`, replayed from the stage's own output by `Stage.workspace_id_after` when the stage is cached). If that workspace already holds completed stages, the provisional workspace is merged into it and deleted; otherwise its directory is renamed. The directory move and the one transaction that updates `jobs.workspace_id` and the cache row are ordered so a crash leaves either the provisional or the final state (`backend/src/insightex/jobs/rebind.py`). The worker deletes unreferenced `pending-*` directories and rows at start.
- **De-duplication at enqueue.** A queued or running job for the same workspace id (YouTube) or the same normalised URL (other links) is returned instead of a new job.
- **Cache index.** `workspaces.source_kind` also allows `gdrive` (schema version 3).
- **Progress to the browser.** The worker is a separate process, so Server-Sent Events poll the database (`api.sse_poll_interval_s`) and send the full job document when it changes.
- **Retired.** `lectures/`, the v2 lecture manifest, the in-memory job manager and `keep_source` are removed; ADR-0025 is superseded.

## Alternatives considered

- Hash the file inside a single `ingest` stage: no separate cache for the download, so a changed FFmpeg setting would re-download.
- Key the chain on the provisional id and fix it up afterwards: a repeated direct link would never hit the cache.
- A WebSocket or a notification channel from the worker to the API: needs a second IPC path; the database already is the shared state.

## Consequences

- A repeated direct link downloads again (its bytes are unknown until hashed) but `normalise` is cached through the key chain. A repeated YouTube link is cached in both stages and finishes in about a second.
- A different URL serving identical bytes merges into the existing `sha256-` workspace and re-runs `normalise`, because its `fetch` key differs.
- Lectures in `lectures/` from before this change are not migrated and must be re-ingested.

## Evidence

`backend/tests/unit/test_rebind.py`, `backend/tests/unit/test_ingest_pipeline.py`, `backend/tests/api/test_job_events.py`; manual run recorded in `docs/evidence/m1/`.

## Gate / revisit when

Revisit when local upload (M2) needs the same rebind from a hash computed in the API, or when a source can identify its content without downloading.
