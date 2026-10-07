# ADR-0023: Workspace caching and session rule

Status: Proposed
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M1

## Context

Processed workspaces are cached, and the product rule is that nothing is stored between sessions. The two need one stated rule.

## Decision

- Processed workspaces are cached per video, keyed by content hash or YouTube ID, with the pipeline version in the key.
- "Nothing stored between sessions" is a product/UI rule: one video per session, no cross-session or cross-student data, no user history kept.
- This is the phrasing for the defense (M20).

## Alternatives considered

Not recorded.

## Consequences

The key includes the pipeline version, so a pipeline change invalidates cached workspaces.

## Evidence

`.claude/rules/ingest.md` ("Planned (M1)"); `.claude/rules/api-ui.md` (product rule); `docs/BUILD_ORDER.md` (pending decision "M1: Session rule").

## Gate / revisit when

Gate: M1 implements the cache key, and Bilal confirms the phrasing. Pass condition: both are done and this ADR is superseded by an Accepted ADR.
