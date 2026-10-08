# M1 session 3: manual end-to-end run (curl against `scripts/dev_run.sh`)

Run on 2026-10-09 (WSL clock 2026-10-08 21:27 to 21:29 UTC). Link: the YouTube canary in `backend/tests/integration/test_ingest_known_links.py` (`a7YHpixqiUg`, 19 min, 201 MB). Driven with curl; **the browser UI (EventSource rendering, player click-to-seek) was not exercised in this run** and still needs the manual check described in the session prompt.

1. `bash scripts/dev_run.sh`: worker started in the background, API on 127.0.0.1:8000.
2. `POST /api/ingest/link` returned `{"job_id": "d6d9b095...", "workspace_id": "yt-a7YHpixqiUg", "deduplicated": false}`. A `curl -N` on `/api/jobs/<id>/events` stayed open for the whole run (86 `status` events).
3. `fetch` progress 0.00 to 1.00 ("17.7 MB of 201.0 MB" ...) over about 55 s; then `normalise` "Copying video".
4. `kill -9` of the worker while `normalise` was at 0.89 ("Extracting audio for transcription"). The job document stayed `running` (`normalise` 0.89); the open event stream stayed open.
5. A new `insightex worker` was started. Its startup recovery requeued the job; the job document then showed `fetch` **cached**, `normalise` running from 0.31, and the job `succeeded` about 10 s later. The same event stream received the whole sequence and closed after the `succeeded` event.
6. `POST /api/ingest/link` again with a different spelling of the same link (`?si=x`): new job, `deduplicated: false` (the first job had finished); `queued` then `succeeded` with stages `[cached, cached]`; about 1.1 s end to end.
7. `GET /api/lectures` listed the lecture (title from `source.json`, duration 1139.984). `GET /api/lectures/yt-a7YHpixqiUg/video` with `Range: bytes=0-99` returned `206 Partial Content`, `content-length: 100`.
8. `DELETE /api/lectures/yt-a7YHpixqiUg` returned 204; `workspaces/` was empty; the library was empty; a second DELETE returned 404; the old job document reported `workspace_deleted: true`.
9. `scripts/dev_run.sh` stop: SIGTERM to the script stopped the API and the worker it had started. With a worker already running, it printed "a worker is already running; using it" and left that worker alone.
