# ADR-0022: Job queue: SQLite + single GPU worker

Status: Superseded by ADR-0033
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M1

## Context

One-worker background jobs already exist from link ingestion (`backend/src/insightex/jobs/ingest_jobs.py`). The GPU lease, resume-after-kill and a generic stage runner do not exist yet. `workers/` holds only `workers/ocr/README.md`; there is no worker or lease code.

## Decision

A SQLite jobs table and one worker that holds the GPU lease, with SSE progress. About 150 lines, no Celery. On worker start, stale jobs left in "running" are requeued or failed.

## Alternatives considered

Celery with Redis: deferred (ADR-0021).

## Consequences

The lease is the mechanism that enforces ADR-0011.

## Evidence

`backend/src/insightex/jobs/ingest_jobs.py`; `docs/BUILD_ORDER.md` (M1 exit and pending decision "M1: Job queue").

## Gate / revisit when

Gate (M1 exit): a dummy two-stage job runs, resumes after the worker is killed, and holds the lease.
