# HTTP API contract

Base: `http://127.0.0.1:8000`. JSON in and out. Errors are `{"error": {"code": "<CODE>", "message": "<text for a person>"}}` with a 4xx status (request-body validation errors that FastAPI raises itself keep its 422 shape). Field names below are stable; fields are only added.

The API enqueues and reads jobs; the worker (`insightex worker`) runs them. On startup the API runs the idempotent `db migrate`.

## Ingest

`POST /api/ingest/probe` `{"url": "..."}` returns metadata without downloading (and, for a YouTube link already in the library, answers from disk):

```json
{"canonical_id": "yt:a7YHpixqiUg", "workspace_id": "yt-a7YHpixqiUg", "source_type": "youtube",
 "normalized_url": "https://www.youtube.com/watch?v=a7YHpixqiUg", "title": "...", "uploader": "...",
 "duration_s": 1140.0, "thumbnail_url": "https://i.ytimg.com/...", "exists_locally": false}
```

`workspace_id` is `null` for links that are not YouTube (the id is the content hash, known after download).

`POST /api/ingest/link` `{"url": "...", "rights_confirmed": true}` returns **202**:

```json
{"job_id": "d6d9b09576704269871640c87b32b77d", "workspace_id": "yt-a7YHpixqiUg", "deduplicated": false}
```

- `workspace_id` of a non-YouTube link is `pending-<job_id>` until `fetch` finishes; the job document then carries the final `sha256-...` id.
- `deduplicated: true` means a queued or running job for the same workspace (YouTube) or the same normalised URL (other links) was returned.
- **400**: `RIGHTS_NOT_CONFIRMED` (anything but JSON `true`), `UNSUPPORTED_URL`, `PLAYLIST_NOT_SUPPORTED`. Nothing is enqueued.

`GET /api/ingest/limits` returns `{"max_upload_bytes": 4294967296}` (`ingest.url.max_download_bytes`).

`POST /api/ingest/upload` takes the file as the **raw request body** (not multipart). Request headers:

| Header | Meaning |
|---|---|
| `Content-Type: application/octet-stream` | |
| `Content-Length` | required |
| `X-Insightex-Filename` | percent-encoded original name; display text only |
| `X-Insightex-Rights-Confirmed: true` | must be exactly `true` |

Checks run before any body byte is read, in this order: rights missing or not `true` → **400** `RIGHTS_NOT_CONFIRMED`; no valid `Content-Length` → **411** `LENGTH_REQUIRED`; length 0 → **400** `EMPTY_FILE`; over the limit → **413** `TOO_LARGE`; another upload running → **409** `UPLOAD_BUSY`; free-space rule → **507** `INSUFFICIENT_DISK`. These responses carry `Connection: close`. While the body streams, more or fewer bytes than `Content-Length` or a dropped connection → the staged copy is deleted and the answer is **400** `UPLOAD_INTERRUPTED`.

On success: **202** `{"lecture_id": "sha256-<32 hex>", "job_id": "...", "deduplicated": false}`. If a job for the same bytes is already queued or running, that job's id is returned with `deduplicated: true` (202). If an up-to-date lecture already exists: **200** `{"lecture_id": "...", "job_id": null, "deduplicated": true}`. Follow the job with `/api/jobs/{job_id}/events`; a media rejection (`NO_VIDEO_STREAM`, `NO_AUDIO_STREAM`, `NOT_A_VIDEO`, `TOO_SHORT`, ...) appears as the failed `normalise` stage's error (`IngestRejected: <CODE>: <message>`). There is no CORS: other origins cannot call this endpoint from a browser (ADR-0037).

## Jobs

`GET /api/jobs/{job_id}` (404 `JOB_NOT_FOUND`), `GET /api/jobs?limit=20&status=queued|running|succeeded|failed|cancelled` (newest first, `limit` 1 to 200; 400 for an unknown status):

```json
{"id": "d6d9...", "kind": "ingest_link", "status": "running",
 "workspace_id": "yt-a7YHpixqiUg", "workspace_deleted": false,
 "created_at": "2026-10-09T08:15:02.123Z", "started_at": "2026-10-09T08:15:03.001Z", "finished_at": null,
 "error": null,
 "stages": [
   {"name": "fetch", "status": "succeeded", "progress": 1.0, "message": null, "error": null},
   {"name": "normalise", "status": "running", "progress": 0.31, "message": "Copying video", "error": null}
 ]}
```

Stage `status`: `pending | running | succeeded | cached | failed | cancelled`. A stage `error` holds `Type: message` and a trimmed traceback; show its first line. `workspace_deleted` is true for a finished job whose workspace directory is gone.

`GET /api/jobs/{job_id}/events` is Server-Sent Events (`Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`). The first event is sent at once; later ones only when the document changes:

```
event: status
data: {<the job document above, one line>}

: keepalive
```

A `: keepalive` comment is sent after `api.sse_keepalive_s` of silence. After the event with `succeeded`, `failed` or `cancelled` the server closes the stream. The database is polled every `api.sse_poll_interval_s`.

`POST /api/jobs/{job_id}/cancel` and `POST /api/jobs/{job_id}/retry` return the job document. **409** `INVALID_STATE` when the job is already final (cancel) or not failed/cancelled (retry); 404 for an unknown job. A running job stops at its next progress call, so the cancel response can still say `running`.

## Library

| Request | Response |
|---|---|
| `GET /api/lectures` | `{"lectures": [{"lecture_id", "title", "duration_s", "thumbnail_url", "created_at"}]}`, newest first; only workspaces whose `normalise` stage is complete |
| `GET /api/lectures/{id}` | the item above plus `video_url`, `external_timestamp_url_template` (`null` unless YouTube) and `warnings` (the `{code, detail}` list from `normalise.json`, for example `AUDIO_NEAR_SILENT`, `ROTATED`) |
| `GET/HEAD /api/lectures/{id}/video` | `video/mp4`, Range requests (`206`, `Content-Range`, `416`) |
| `GET/HEAD /api/lectures/{id}/thumbnail` | `image/jpeg` |
| `DELETE /api/lectures/{id}` | **204**; **409** `LECTURE_BUSY` while a queued or running job uses it; 404 `LECTURE_NOT_FOUND` |

`{id}` is a workspace id (`yt-<id>` or `sha256-<32 hex>`). The player page keeps `?lecture=<id>`.
