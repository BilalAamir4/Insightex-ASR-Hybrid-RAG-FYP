# insightex.jobs

**Purpose:** Job queue, worker, stage runner and workspaces (ADR-0033, ADR-0034).

**Model used:** none (orchestrates GPU stages)

**Feature numbers:** not assigned

**Status:** M1 session 1 done: SQLite job store, workspace manifest, chained stage keys, stage runner with resume, single worker, CLI and a dummy two-stage pipeline. Still to come: GPU lease (a no-op `NullGpuLease` stands in), source identity, cache eviction, progress API, ingestion on the runner.

| File | Role |
|---|---|
| `db.py` | connections (WAL, one per thread), UTC timestamps, `migrate()` |
| `store.py` | jobs and job_stages: enqueue, claim, update, cancel, retry, crash recovery |
| `workspace.py` | workspace layout, atomic manifest, staging cleanup |
| `stages.py` | `Stage`, `StageContext`, `stage_key`, `GpuLease`, pipeline registry (`register_pipeline`) |
| `runner.py` | runs one job: cache check, lease, staging, publish, cancel |
| `worker.py` | singleton worker process (flock on `run_dir/worker.lock`) |
| `dummy.py` | the `dummy` job kind used by tests and the manual check |
| `cli.py` | `insightex db`, `worker`, `jobs ...`; output formats in `docs/contracts/jobs-cli.md` |

**Ingest jobs:** `ingest_jobs.py` still holds the in-memory job manager for URL ingestion (one worker thread, polled by the web UI). It moves onto the runner in M1 session 3.
