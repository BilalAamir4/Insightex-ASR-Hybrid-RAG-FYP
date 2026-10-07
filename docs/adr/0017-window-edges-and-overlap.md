# ADR-0017: Window edges and overlap

Status: Proposed
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M5

## Context

ADR-0001 fixes 30 s non-overlapping windows.

## Decision

Keep the 30 s target but snap window edges to Whisper segment boundaries. Test 50% overlap (15 s stride).

## Alternatives considered

50% overlap: adopted only if the gate passes. Non-overlapping 30 s windows: the current baseline.

## Consequences

With overlap, hits overlap each other, so results are deduplicated; hits are scored by time overlap with the gold span.

## Evidence

`.claude/rules/retrieval.md`; `docs/reports/embedding_bakeoff/results_seq1024/windows_W30.csv`; ADR-0001.

## Gate / revisit when

Gate (M5): adopt overlap only if Recall@3 improves. Score hits by time overlap with the gold span and dedupe overlapping hits.
