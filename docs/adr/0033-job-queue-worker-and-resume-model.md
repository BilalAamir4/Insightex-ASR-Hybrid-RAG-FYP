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
- **GPU lease:** an OS file lock in `jobs.run_dir`, held for the duration of one `needs_gpu` stage. The kernel releases a lock when its holder dies; a database row cannot do that. Semantics are in "GPU lease semantics" below.

### GPU lease semantics

- **Lock:** `fcntl.flock` on `gpu.lease_path` (default `<jobs.run_dir>/gpu.lock`). Every hold opens its own file descriptor, so holds conflict across processes and inside one process. A holder that dies, including by `kill -9`, loses the lock at once.
- **Exclusive** (`LOCK_EX`) is for worker stages that load models onto the GPU: Whisper, BGE-M3 document encoding, and the extraction stage if it runs in the worker. `GpuLease.hold(job_id, stage_name)` is an exclusive hold with purpose `<job_id>:<stage_name>` and no timeout. The runner takes it only for `needs_gpu` stages.
- **Shared** (`LOCK_SH`) is for interactive Q&A calls to Ollama from the API process. Several run together; none runs beside an exclusive hold. `FileGpuLease.shared(purpose, timeout_s)` raises `GpuBusy` after `timeout_s`; the API uses `gpu.qa_lease_timeout_s` to answer "GPU busy, try again" quickly.
- **Waiting:** the lock is retried non-blocking every `gpu.lock_retry_interval_s`. `timeout_s=None` waits forever. On timeout `GpuBusy` carries the exclusive holder's info. The worker passes `stop_event.is_set` as `should_stop`, so a SIGTERM while waiting raises `WorkerStopping` and the job returns to the queue without counting an attempt.
- **Ollama unload:** after an exclusive acquire, the lease sends `keep_alive: 0` for `ollama.model` and polls `/api/ps` every `gpu.ollama_poll_interval_s` for up to `gpu.ollama_unload_timeout_s`. If the model is still listed, the lease is released and `GpuUnavailable` fails the stage with a clear message instead of an out-of-memory error. If Ollama is unreachable, the lease logs a warning and continues. Unloading the model through the lease needs no confirmation; stopping the Ollama service does.
- **Holder info:** `<lease_path>.holder` holds `{pid, mode, purpose, acquired_at}` for the exclusive holder and is removed on release. It is diagnostic. `insightex gpu status` reports it only while the lock is held. Shared holds are logged only.
- **Memory log:** when `nvidia-smi` exists, `memory.used` is logged at info level before and after each exclusive hold. Its absence is never an error.
- **Config:** `gpu.lease_enabled` false makes the worker use no lease.
- **Known limits:** anything that talks to Ollama without taking the lease, such as the Ollama app used directly, bypasses it. A continuous stream of shared holders can starve an exclusive holder. Both are acceptable for a single-user system.

## Alternatives considered

- FastAPI `BackgroundTasks` or in-process threads: no persistence, so resume-after-kill fails, and GPU work would run in the API process, which is reserved for CPU query encoding.
- Celery with Redis: needs a broker service, resume is still task-level so stage checkpoints are custom anyway, and with concurrency 1 most of its value is gone (ADR-0021).
- Huey, RQ or Dramatiq: replace only the claim loop. Stage resume, progress and GPU arbitration remain custom.
- Prefect or Dagster: need a server and database for one linear pipeline.
- Manifest files without a database: no atomic claim, and listing jobs means scanning directories.
- A heartbeat column to detect dead workers: unnecessary with a singleton worker.

## Consequences

- Jobs run strictly in order. A long job delays every job queued behind it.
- A `needs_gpu` stage blocks until the lease is free. CPU stages never take it.
- A stage that does not call `ctx.progress` every few seconds delays cancel and SIGTERM until it returns.
- Stage code must be idempotent and write only into its staging directory.
- A job that kills the worker `jobs.max_attempts` times is marked failed instead of looping.
- Link ingestion still uses its own in-memory thread pool until it moves onto this runner.
- The worker writes `worker.log` under `paths.data_dir/logs` and to stderr, with the job id and stage name on every line.

## Evidence

- `backend/tests/unit/test_jobs_engine.py`: single claim under two connections, crash recovery below and at the attempt limit, cancel of queued and running jobs, stop-and-requeue.
- `backend/tests/integration/test_worker_process.py`: `kill -9` during the GPU stage, restart, job succeeds with the CPU stage cached and `attempts == 2`; second worker exits with code 2.
- `backend/tests/unit/test_gpu_lease.py`: exclusive and shared conflicts, timeout with holder info, `kill -9` release, unload success, model still loaded, Ollama unreachable, config derivation.
- `backend/tests/integration/test_worker_process.py`: SIGTERM while blocked on a held lease exits 0 and requeues the job with attempts unchanged.
- `tools/m1_verify/verify_m1.py`: end-to-end check of the M1 exit criterion through the CLI.
- `docs/contracts/jobs-cli.md`: CLI and JSON output.

## Gate / revisit when

Revisit when jobs must run in parallel (a second GPU, or CPU-only stages that should not wait), or when the single worker's strict ordering makes the demo or the user study wait noticeably.
