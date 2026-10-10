# ADR-0037: HTTP upload transport: raw streamed body, one upload at a time, no CORS

Status: Accepted
Date decided: 2026-10-09
Date recorded: 2026-10-09
Module: M2

## Context

M2 session 2 adds browser upload on top of the shared engine (ADR-0036). Lectures are up to 4 GB, the server runs on a student's machine with a GPU worker next to it, and the API listens on loopback only. The upload must not hold a lecture in memory, must not starve the Server-Sent Events that show job progress, and must not let a web page on another origin post files to the local server.

## Decision

- **Transport.** `POST /api/ingest/upload` takes the file as the raw request body (`Content-Type: application/octet-stream`), not multipart. The handler reads `request.stream()`; it uses neither `UploadFile` nor `python-multipart`. Chunks are gathered up to `ingest.file.copy_chunk_bytes` and written and hashed in a worker thread (`anyio.to_thread`), so the event loop stays free. The body is never held whole.
- **Staging.** Bytes go to `<staging_dir>/<uuid>.tmp`, are hashed as they arrive, and on a complete body are fsynced and renamed to `<uuid>.part`, the same protocol as the CLI copy (`ingest/staging.py`, `StagedUpload`). A job never sees a half-written copy and a leftover `.tmp` is swept like any stale staging file. The brief said to write to `.part` directly; the only difference is the temporary name.
- **One entry path.** After the body is complete the handler calls `ingest/file_jobs.enqueue_staged`, the function `enqueue_file` (the CLI) also ends in, with `via="http"`. `enqueue_file` was split in two for this; its behaviour is unchanged. The media is judged by the job, so a rejection reaches the page through the job status and SSE with its closed error code.
- **Checks before any body byte is read, in this order:** rights header is not `true` (400 `RIGHTS_NOT_CONFIRMED`); no valid `Content-Length` (411 `LENGTH_REQUIRED`); length 0 (400 `EMPTY_FILE`); over `ingest.url.max_download_bytes` (413 `TOO_LARGE`); another upload running (409 `UPLOAD_BUSY`); the ADR-0036 free-space rule fails (507 `INSUFFICIENT_DISK`). Refusals send `Connection: close` because the body is left unread.
- **While streaming.** More bytes than `Content-Length`, fewer bytes, a disconnect or any read error: the staged file is deleted and the answer is 400 `UPLOAD_INTERRUPTED` (logged at WARNING). There are no resumable uploads. A dropped connection starts over.
- **One active upload.** A process-wide non-blocking lock; a second upload gets 409. It is released in a `finally`, on every exit path. This matches the one-video-per-session rule and keeps the disk rule simple.
- **Result.** 202 `{lecture_id, job_id, deduplicated}`. If the same bytes already have a queued or running job, that job is returned with `deduplicated: true`. If an up-to-date lecture exists the answer is 200 with `job_id: null` and `deduplicated: true`; the duplicate copy is deleted.
- **No CORS.** No CORS middleware is installed. The custom `X-Insightex-*` headers force a browser preflight, which the server does not answer with `Access-Control-Allow-*`, so another origin cannot post files here.
- **Upload limit for the page.** `GET /api/ingest/limits` returns `{max_upload_bytes}` so the page can refuse an oversize file before sending it.

## Alternatives considered

- **Multipart with `UploadFile`.** Rejected: adds a dependency, spools to a temp file, and makes progress, the length check and the hash harder to control.
- **Chunked or resumable uploads (tus-style).** Rejected for now: a lecture upload over loopback or a LAN is short, and resumption needs server state that the one-video-per-session rule argues against.
- **CORS allow-list for the page's own origin.** Rejected: the page is served by the same server, so it needs none, and an allow-list is a way to get it wrong.
- **Several concurrent uploads.** Rejected: disk accounting would have to reserve space per upload, and the product has one video per session.

## Consequences

- Memory use during an upload is flat. Measured 2026-10-09 with a 1 GiB body: server resident memory moved from 75 MB to 88 MB (`curl -T`, one run, one machine).
- A browser that is still sending when a refusal arrives can see a network error instead of the status. The page therefore checks size and rights itself first; the server remains the authority.
- A server crash mid-upload leaves a `.tmp` file; the worker's staging sweep removes it after `ingest.file.staging_max_age_h`.

## Evidence

`docs/evidence/m2/` (`tools/m2_verify`, 13 checks including the Day 4 lecture, an interrupted raw-socket upload and the 413 timing). Tests: `backend/tests/api/test_upload_api.py`. The pass/fail record of the browser steps is `docs/evidence/m2/BROWSER_CHECKLIST.md`, filled in by hand.

## Gate / revisit when

Revisit if uploads must cross a network where drops are common (resumable upload), or if the product allows more than one video per session (concurrent uploads).
