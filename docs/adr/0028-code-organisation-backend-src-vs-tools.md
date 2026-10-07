# ADR-0028: Code organisation: backend/src vs tools/

Status: Accepted
Date decided: not recorded; on or before 2026-10-06
Date recorded: 2026-10-08
Module: Project

## Context

The repository holds production code and diagnostic, tuning and evaluation scripts.

## Decision

- Production code lives in `backend/src/insightex/` (src layout, `pyproject.toml` at the repo root). Tests live in `backend/tests/`.
- Diagnostic, tuning and evaluation scripts live in `tools/`. They are standalone, never import production code, and document how their findings integrate.
- Coding agent: Claude Code, guided by `CLAUDE.md` and `.claude/rules/`.

## Alternatives considered

Not recorded.

## Consequences

Logic a tool proves out is ported into `backend/src/insightex/` with a note left behind; it is not imported from `tools/`.

## Evidence

`tools/CLAUDE.md`; `pyproject.toml`; `.claude/rules/`; `CLAUDE.md`.

## Gate / revisit when

Revisit if a tool must share code with production.
