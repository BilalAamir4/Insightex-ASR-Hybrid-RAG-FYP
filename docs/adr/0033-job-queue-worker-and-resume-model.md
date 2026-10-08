# ADR-0033: Job queue, worker and resume model

Status: Accepted
Date decided: 2026-10-09
Date recorded: 2026-10-09
Module: M1

## Context

ADR-0022 proposed a SQLite jobs table and one worker. Link ingestion today runs on a thread pool inside the API process with in-memory state (`backend/src/insightex/jobs/ingest_jobs.py`), so a restart loses every job. The pipeline must survive a killed worker mid-stage, share one 8 GB GPU with Ollama (ADR-0011), and keep the API process free for CPU query encoding (ADR-0015).

## Decision

- **Queue:** a SQLite database (`jobs.db_path`, WAL mode) with a `jobs` table and a `job_stages` table. Jobs are claimed with one `UPDATE ... RETURNING` inside `BEGIN IMMEDIATE`.
- **Worker:** exactly one worker process (`insightex worker`). It holds an exclusive `flock` on `<jobs.run_dir>/worker.lock`; a second worker exits with code 2. Because the worker is a singleton, any `running` row found at start-up belongs to a dead worker, so recovery needs no heartbeat.
- **Pipelines:** a job kind maps to a linear, ordered list of stages. A stage declares a name, a version, `needs_gpu`, a config fingerprint, its output file names and a `run` method.
- **Resume comes from idempotent stages with atomic outputs, not from the queue.** A stage writes into a staging directory, the runner verifies the declared outputs, then moves the directory into place and updates the manifest. A killed worker leaves only a staging directory, which the next worker deletes. A finished stage is skipped on the next run (ADR-0034).
- **Crash recovery:** at worker start every `running` job returns to `queued` while `attempts < jobs.max_attempts`, otherwise it becomes `failed`.
- **Exceptions are not retried automatically.** A stage that raises fails its job with the traceback stored on the stage row. The user runs retry, and finished stages return as cached.
- **Cancel and shutdown** are cooperative. `ctx.progress` raises when cancel is requested or the worker received SIGINT/SIGTERM. A stop returns the job to the queue without counting an attempt.
- **Progress** is written to `job_stages` (throttled by `jobs.progress_min_interval_s`) and read from the database. SSE with a polling fallback serves it from the API in a later session.
- **GPU lease:** an OS file lock in `jobs.run_dir`, held for the duration of one `needs_gpu` stage. The kernel releases a lock when its holder dies; a database row cannot do that. This session defines the `GpuLease` interface and a no-op implementation; the file lock and the Ollama unload on release follow in the next session.

## Alternatives considered

- FastAPI `BackgroundTasks` or in-process threads: no persistence, so resume-after-kill fails, and GPU work would run in the API process, which is reserved for CPU query encoding.
- Celery with Redis: needs a broker service, resume is still task-level so stage checkpoints are custom anyway, and with concurrency 1 most of its value is gone (ADR-0021).
- Huey, RQ or Dramatiq: replace only the claim loop. Stage resume, progress and GPU arbitration remain custom.
- Prefect or Dagster: need a server and database for one linear pipeline.
- Manifest files without a database: no atomic claim, and listing jobs means scanning directories.
- A heartbeat column to detect dead workers: unnecessary with a singleton worker.

## Consequences

- Jobs run strictly in order. A long job delays every job queued behind it.
- A `needs_gpu` stage blocks on the lease once the lease is implemented; until then it runs without arbitration.
- A stage that does not call `ctx.progress` every few seconds delays cancel and SIGTERM until it returns.
- Stage code must be idempotent and write only into its staging directory.
- A job that kills the worker `jobs.max_attempts` times is marked failed instead of looping.
- Link ingestion still uses its own in-memory thread pool until it moves onto this runner.
- The worker writes `worker.log` under `paths.data_dir/logs` and to stderr, with the job id and stage name on every line.

## Evidence

- `backend/tests/unit/test_jobs_engine.py`: single claim under two connections, crash recovery below and at the attempt limit, cancel of queued and running jobs, stop-and-requeue.
- `backend/tests/integration/test_worker_process.py`: `kill -9` during the GPU stage, restart, job succeeds with the CPU stage cached and `attempts == 2`; second worker exits with code 2.
- `docs/contracts/jobs-cli.md`: CLI and JSON output.

## Gate / revisit when

Revisit when jobs must run in parallel (a second GPU, or CPU-only stages that should not wait), or when the single worker's strict ordering makes the demo or the user study wait noticeably.
