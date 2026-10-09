# insightex.jobs

**Purpose:** Job queue, worker, stage runner and workspaces (ADR-0033, ADR-0034).

**Model used:** none (orchestrates GPU stages)

**Feature numbers:** not assigned

**Status:** M1 done. SQLite job store, workspace manifest, chained stage keys, stage runner with resume, single worker, GPU lease, source identity, cache index and eviction, and link ingestion on the runner (`insightex.ingest.pipeline`, ADR-0035).

| File | Role |
|---|---|
| `db.py` | connections (WAL, one per thread), UTC timestamps, `migrate()` |
| `store.py` | jobs and job_stages: enqueue, claim, update, cancel, retry, crash recovery |
| `workspace.py` | workspace layout, atomic manifest, staging cleanup |
| `stages.py` | `Stage`, `StageContext`, `stage_key`, `GpuLease`, pipeline registry (`register_pipeline`) |
| `runner.py` | runs one job: cache check, lease, staging, publish, cancel |
| `worker.py` | singleton worker process (flock on `run_dir/worker.lock`) |
| `rebind.py` | moves a job from `pending-<job id>` to its content-addressed workspace between stages (crash-safe order in the module docstring) |
| `cache.py` | workspace index: register, touch, pin, delete, eviction, orphan `pending-*` sweep |
| `gpu_lease.py` | the flock GPU lease |
| `dummy.py` | the `dummy` job kind used by tests and the manual check |
| `cli.py` | `insightex db`, `worker`, `jobs ...`; output formats in `docs/contracts/jobs-cli.md` |

**Ingest jobs:** the `ingest_link` pipeline lives in `insightex/ingest/pipeline.py`; the old in-memory job manager is gone.
