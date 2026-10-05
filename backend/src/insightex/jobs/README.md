# insightex.jobs

**Purpose:** Job queue, worker, gpu_lease (one model in VRAM at a time) and stage runner.

**Model used:** none (orchestrates GPU stages)

**Feature numbers:** not assigned

**Status:** skeleton only. No code yet; this README is the contract for what belongs here.

**Ingest jobs:** `ingest_jobs.py` holds the in-memory job manager for URL ingestion (one worker thread, polled by the web UI) and the startup recovery of interrupted manifests. It is specific to ingestion. The GPU staging queue (`gpu_lease`, stage runner) is still to come.
