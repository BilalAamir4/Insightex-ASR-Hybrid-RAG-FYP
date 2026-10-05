# insightex.api

**Purpose:** HTTP API layer (FastAPI). `app.py` builds the app and serves `frontend/` as static files; routers live in `routers/`.

**Model used:** none

**Feature numbers:** not assigned

**Status:** URL ingestion (`routers/ingest.py`) and the lecture library and media (`routers/lectures.py`).

Start: `bash scripts/run_in_env.sh python -m insightex.api` (host and port from `api:` in config/default.yaml; loopback only).
