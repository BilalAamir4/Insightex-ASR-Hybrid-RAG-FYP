# ADR-0027: API server and UI stack

Status: Accepted
Date decided: not recorded; on or before 2026-10-06
Date recorded: 2026-10-08
Module: M3 / M6

## Context

The product is single-user. Remote demo access is planned in M19.

## Decision

FastAPI bound to `127.0.0.1:8000` (loopback only; binding `0.0.0.0` is refused in code), serving a static HTML page for ingest, library and player. There is no build step. Remote demo access is planned through Tailscale in M19, not by binding to other interfaces.

## Alternatives considered

Binding to other interfaces: rejected; Tailscale covers remote access.

## Consequences

- Background work goes through the single worker; GPU work never runs inside a request handler.
- The UI is `frontend/index.html`, `frontend/timestamp.js` and `frontend/timestamp_test.js`.

## Evidence

`backend/src/insightex/api/__main__.py` (refused hosts `0.0.0.0`, `::`, empty); `config/default.yaml` (`api.host`, `api.port`); `frontend/index.html`; `.claude/rules/api-ui.md`.

## Gate / revisit when

Revisit in M19 if the Tailscale demo path does not work.
