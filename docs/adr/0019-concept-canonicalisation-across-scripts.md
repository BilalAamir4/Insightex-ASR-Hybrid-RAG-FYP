# ADR-0019: Concept canonicalisation across scripts

Status: Proposed
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M8

## Context

Lecture concepts appear in Urdu script, Roman Urdu and English variants.

## Decision

Canonicalisation is its own module. Each node is a canonical English label plus an alias list (Urdu script, Roman Urdu, English variants). Merge candidates are found by embedding similarity and confirmed by the LLM.

## Alternatives considered

Not recorded.

## Consequences

The LLM confirmation step is an extra GPU stage under ADR-0011.

## Evidence

`docs/BUILD_ORDER.md` (M8 exit and pending decision "M8: Concept identity across scripts").

## Gate / revisit when

Gate (M8 exit): the duplicate-node rate is measured on 2 lectures, and the graph JSON passes schema checks.
