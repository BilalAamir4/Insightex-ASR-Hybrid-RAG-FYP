# ADR-0026: Player integration point: seekTo(seconds)

Status: Accepted
Date decided: not recorded; on or before 2026-10-06
Date recorded: 2026-10-08
Module: M3 / M6

## Context

Citations, graph navigation (F5) and highlight reels (F15) all move the video position.

## Decision

The player exposes one function, `seekTo(seconds)`. Citations, graph navigation (F5) and highlight reels (F15) all integrate through it.

## Alternatives considered

Per-feature seek logic: rejected; new features call `seekTo`.

## Consequences

`seekTo` is the only place the page changes playback position programmatically.

## Evidence

`frontend/index.html` (defines `seekTo`, exposed as `window.insightex.seekTo`); `frontend/timestamp.js`; `.claude/rules/api-ui.md`.

## Gate / revisit when

Revisit if a feature needs a playback control that `seekTo(seconds)` cannot express.
