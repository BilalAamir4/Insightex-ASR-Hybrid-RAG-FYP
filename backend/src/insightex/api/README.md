# insightex.api

**Purpose:** HTTP API layer (FastAPI). `app.py` builds the app and serves `frontend/` as static files; routers live in `routers/`. The API enqueues and reads jobs; it never runs stages, takes the exclusive GPU lease or starts the worker.

**Model used:** none

**Feature numbers:** not assigned

**Status:** link ingestion (`routers/ingest.py`), jobs with Server-Sent Events progress (`routers/jobs.py`), the lecture library, media and delete (`routers/lectures.py`). Endpoints and response shapes: `docs/contracts/api.md`.

Start both processes: `bash scripts/dev_run.sh`. The API alone: `bash scripts/run_in_env.sh python -m insightex.api` (host and port from `api:` in config/default.yaml; loopback only); jobs then run only while `insightex worker` is running.
