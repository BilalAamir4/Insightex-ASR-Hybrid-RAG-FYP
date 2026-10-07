# ADR-0021: Deferred infrastructure

Status: Accepted
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: Project

## Context

Core pipeline output has not been validated yet (Current state: Phase 0 in `CLAUDE.md`).

## Decision

Celery, Redis, Docker Compose, Neo4j and nginx are deferred until the core pipeline is validated. Core output is validated before infrastructure is added. nginx is added only if FastAPI range requests misbehave (M19).

## Alternatives considered

- Celery and Redis: replaced by the SQLite jobs table and one worker (ADR-0022).
- Neo4j: replaced by NetworkX (ADR-0018).

## Consequences

Background jobs, the graph and the API run as plain Python processes on one machine.

## Evidence

`CLAUDE.md` ("Decisions already made", Infrastructure); `docs/BUILD_ORDER.md` (M19).

## Gate / revisit when

Revisit when the core pipeline is validated, or in M19 if FastAPI range requests misbehave (nginx).
