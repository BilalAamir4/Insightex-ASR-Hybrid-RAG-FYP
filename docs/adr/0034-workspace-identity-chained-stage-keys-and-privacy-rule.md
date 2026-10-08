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

The helpers that compute these are built in the next session. This session accepts any id that matches `^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$`, because the id is a directory name.

**Chained stage keys.** Each stage has a key: the first 16 hex characters of the SHA-256 of the canonical JSON (sorted keys, compact separators, no ASCII escaping) of the stage name, the stage's code version, the stage's config fingerprint and the upstream stage's key. For the first stage the upstream key is the workspace id. Changing one stage's version or config changes its key and every downstream key, and no upstream key.

**Layout.** `<jobs.workspaces_dir>/<workspace_id>/manifest.json`, `stages/<stage>/<key>/` for completed outputs and `.staging/` for in-progress ones. The manifest records the key, completion time, duration and output paths of each completed stage and is written atomically. A stage is cached when the manifest holds its current key and every declared output exists. When a stage completes under a new key, the previous key's directory is deleted after the new manifest is durable; a failed delete is logged and does not fail the job.

**Privacy rule.** Lecture artifacts (transcript, windows, embeddings, graph) are derived only from the video, are identical for everyone and are cached. User data (questions, answers, notes, quiz attempts, anything tied to a person) is never persisted beyond the session.

**Two layouts for now.** Link ingestion still writes `lectures/<lecture_id>/` (ADR-0025). Workspaces under `workspaces/` are used by the new runner. The next sessions move ingestion onto the runner and remove `lectures/`.

## Alternatives considered

- One global pipeline version: any prompt tweak reruns ASR.
- No caching: reprocessing an hour of audio every session breaks the demo, the evaluation loop and the user study.
- The URL string as identity: many URL forms point at one video.
- Hash of the normalised media: FFmpeg output is not byte-stable across versions.
- Perceptual fingerprints: complexity and false positives for a problem this project does not have.

## Consequences

- Editing one stage's code or config reruns that stage and everything after it, and nothing before it. Each stage's author must bump `version` when its outputs change, or stale outputs stay cached.
- The manifest's current key for a stage can be stale after a pipeline change, until the stage reruns.
- Cached workspaces use disk. A size cap with least-recently-used eviction and a delete action per video follow in the next session; until then nothing evicts a workspace.
- The privacy rule limits what later modules may store: question and answer history, notes and quiz attempts stay in the browser session or process memory.
- This ADR supersedes the session-rule wording of ADR-0023. The defense phrasing of the rule is for the project owner to confirm.

## Evidence

- `backend/tests/unit/test_jobs_engine.py`: key sensitivity to each input, label change reruns both stages and removes the old key directories, a downstream-only change keeps the upstream stage cached, a retry shows finished stages as cached, a missing declared output moves nothing into `stages/`.
- `backend/src/insightex/jobs/workspace.py`, `backend/src/insightex/jobs/stages.py`.

## Gate / revisit when

Revisit when the source-identity helpers or the eviction policy show that the workspace id or key scheme does not fit (next session), or when a feature needs data tied to a person to persist.
