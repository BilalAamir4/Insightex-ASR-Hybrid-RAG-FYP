---
paths:
  - "backend/src/insightex/api/**"
  - "backend/src/insightex/jobs/**"
  - "frontend/**"
  - "backend/tests/api/**"
---
# API + UI (M6) — loaded only when touching API or frontend code

- FastAPI serves on `127.0.0.1:8000` (loopback only). The frontend is static HTML/JS; there is no build step.
- Background work goes through the single worker. Never run GPU work inside a request handler.
- `seekTo(seconds)` is the single player integration point. Citations (M11), graph navigation (F5) and the highlight reel (F15) must all call it rather than adding new seek logic.
- Product rule: one video per session. Keep no cross-session or cross-student data and no user history.
- The API never runs stages, never takes the exclusive GPU lease and never starts the worker. It enqueues jobs and reads the job database; `insightex worker` (or `scripts/dev_run.sh`) runs them.
- Endpoints and response shapes: `docs/contracts/api.md`. Field names are stable; add fields, do not rename. Job progress is `GET /api/jobs/{id}/events` (Server-Sent Events that poll the database); the UI falls back to polling `GET /api/jobs/{id}` every 2 s.
- The library is `/api/lectures*`, backed by workspaces whose `normalise` stage is complete. Media is resolved through the workspace manifest, with Range requests; access times are touched at most once per `api.touch_min_interval_s` per workspace.
- The ingest page also uploads files with `XMLHttpRequest` (progress, cancel, `beforeunload` guard). All error-code texts are in the one `ERROR_MESSAGES` object in `frontend/index.html`; add a new `ErrorCode` there too. The player shows the lecture's `warnings` as notices.
- Still to build: ask box and top-3 citations that seek the video.
