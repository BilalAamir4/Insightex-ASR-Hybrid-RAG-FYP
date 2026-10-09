# ADR-0034: Workspace identity, chained stage keys and privacy rule

Status: Accepted
Date decided: 2026-10-09
Date recorded: 2026-10-09
Module: M1

## Context

ADR-0023 said processed workspaces are cached per video, keyed by content hash or YouTube ID with one pipeline version. Processing an hour of lecture audio takes long enough that repeating it every session breaks the demo, the evaluation loop and the user study. A single pipeline version would rerun speech recognition after any prompt change. The product also promises that nothing about a person is kept between sessions.

## Decision

**Workspace identity.** A workspace is identified by its source:
- the YouTube video ID for YouTube links;
- the SHA-256 of the downloaded bytes for other links;
- the SHA-256 of the uploaded bytes for uploads.

The helpers that compute these are in `insightex.sources.identity`. Any id that matches `^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$` is accepted, because the id is a directory name.

**Chained stage keys.** Each stage has a key: the first 16 hex characters of the SHA-256 of the canonical JSON (sorted keys, compact separators, no ASCII escaping) of the stage name, the stage's code version, the stage's config fingerprint and the upstream stage's key. For the first stage the upstream key is the workspace id. Changing one stage's version or config changes its key and every downstream key, and no upstream key.

**Layout.** `<jobs.workspaces_dir>/<workspace_id>/manifest.json`, `stages/<stage>/<key>/` for completed outputs and `.staging/` for in-progress ones. The manifest records the key, completion time, duration and output paths of each completed stage and is written atomically. A stage is cached when the manifest holds its current key and every declared output exists. When a stage completes under a new key, the previous key's directory is deleted after the new manifest is durable; a failed delete is logged and does not fail the job.

**Privacy rule.** Lecture artifacts (transcript, windows, embeddings, graph) are derived only from the video, are identical for everyone and are cached. User data (questions, answers, notes, quiz attempts, anything tied to a person) is never persisted beyond the session.

**One layout.** The `lectures/<lecture_id>/` layout of ADR-0025 is retired: link ingestion runs on the stage runner and writes only to `workspaces/` (ADR-0035). Lectures ingested before that change are left on disk, are never read, and must be re-ingested.

### Source identity, cache index and eviction

- **Identity helpers:** `insightex.sources.identity` gives `youtube_video_id(url)`, `workspace_id_for_youtube` (`yt-<id>`), `workspace_id_for_bytes` (`sha256-<first 32 hex>`), `sha256_file` and `HashingWriter`, which hashes while a download or upload streams to disk. Every id passes `validate_workspace_id`.
- **Index:** the `workspaces` table (schema version 2) holds `id`, `source_kind` (`youtube`, `url`, `upload`, `dummy`), `source_ref`, `created_at`, `last_accessed_at`, `size_bytes` and `pinned`. Each pipeline declares its source through `register_pipeline(..., source_for=payload -> (source_kind, source_ref))`; the runner registers the workspace at job start. `created_at` is never overwritten.
- **Access times:** the runner touches the workspace when a job starts and when it ends; the API touches it when media is served.
- **After every successful job** the runner runs the stale-key sweep, the size refresh and eviction, in that order. A failure in any of them logs a warning and never changes the job's status.
- **Eviction:** when the sum of `size_bytes` exceeds `cache.max_bytes` (40 GiB), the least recently accessed workspaces are deleted until the sum is under the cap. Pinned workspaces, workspaces with a queued or running job, and the workspace whose job just finished are never evicted. If that workspace alone exceeds the cap, a warning says so. Directories with no row in the table are never evicted. Each eviction logs the id, size and last access time.
- **Pin:** `cache pin` marks a workspace so eval lectures are never evicted; `cache unpin` reverses it.
- **Delete:** `cache.delete(id)` raises `WorkspaceBusy` while a queued or running job references the workspace; otherwise it removes the directory and the row. Finished job rows stay; they hold no lecture content. Delete also works on directories with no row.
- **Stale keys:** `Workspaces.sweep_stale_keys` removes stage-key directories the manifest does not name. `insightex cache gc` runs it for every workspace without a queued or running job, then evicts.

## Alternatives considered

- One global pipeline version: any prompt tweak reruns ASR.
- No caching: reprocessing an hour of audio every session breaks the demo, the evaluation loop and the user study.
- The URL string as identity: many URL forms point at one video.
- Hash of the normalised media: FFmpeg output is not byte-stable across versions.
- Perceptual fingerprints: complexity and false positives for a problem this project does not have.

## Consequences

- Editing one stage's code or config reruns that stage and everything after it, and nothing before it. Each stage's author must bump `version` when its outputs change, or stale outputs stay cached.
- The manifest's current key for a stage can be stale after a pipeline change, until the stage reruns.
- Cached workspaces use disk. Workspaces are evicted least-recently-used above `cache.max_bytes`, and each can be deleted or pinned.
- The privacy rule limits what later modules may store: question and answer history, notes and quiz attempts stay in the browser session or process memory.
- This ADR supersedes the session-rule wording of ADR-0023. The defense phrasing of the rule is for the project owner to confirm.

## Evidence

- `backend/tests/unit/test_jobs_engine.py`: key sensitivity to each input, label change reruns both stages and removes the old key directories, a downstream-only change keeps the upstream stage cached, a retry shows finished stages as cached, a missing declared output moves nothing into `stages/`.
- `backend/src/insightex/jobs/workspace.py`, `backend/src/insightex/jobs/stages.py`.

## Gate / revisit when

Revisit when the source-identity helpers or the eviction policy show that the workspace id or key scheme does not fit, or when a feature needs data tied to a person to persist.
