# ADR-0016: Dense + sparse retrieval with Reciprocal Rank Fusion

Status: Proposed
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M5 / M9

## Context

sentence-transformers returns dense vectors only. FlagEmbedding `BGEM3FlagModel` returns dense and sparse weights in one pass. FlagEmbedding is not installed and not in `requirements.lock.txt`; installing it needs approval and a lockfile update.

## Decision

Use `BGEM3FlagModel` for dense and sparse weights. Fuse the dense and sparse rankings with Reciprocal Rank Fusion (RRF).

## Alternatives considered

Dense only through sentence-transformers: the current baseline, and the fallback if the gate fails.

## Consequences

The bge-m3 tie-break in ADR-0001 cites sparse weights; if sparse is dropped, that argument is removed from the report.

## Evidence

`docs/BUILD_ORDER.md` (M5 prerequisite note); `docs/ENVIRONMENT.md` section 4; ADR-0001.

## Gate / revisit when

Gate: if sparse adds nothing measurable, or is never wired in, drop sparse and remove the tie-break argument from the report. Pass condition for keeping it: a measurable gain over dense alone on the retrieval harness.
