# ADR-0008: Feature tiers and numbering

Status: Accepted
Date decided: not recorded; on or before 2026-10-06
Date recorded: 2026-10-08
Module: Project

## Context

The proposal lists Features 1 to 20. The panel does not track the feature list, so dropping proposal features is acceptable.

## Decision

Feature numbering follows the proposal (Features 1 to 20) as the single source of truth. Tiers:

| Tier | Features |
|---|---|
| Baseline | 1 to 15, except 13 |
| Optional | the visual pipeline; Feature 13 (OCR-confidence legibility flag) |
| Stretch Goal | 16, 17, 18, 19; only if milestones 1 to 9 finish early; order F17, F18, F19, F16 |
| Exploratory | 16.1, 20 |
| Cut | visual content narration, sign-language generation, free-form continuous sign recognition |

## Alternatives considered

- Treating every proposal feature as committed: rejected; the project scope is too large (ADR-0006).
- Renumbering features: rejected; the proposal is the single source of truth.

## Consequences

- Per-feature notes live in `docs/features/`.
- Stretch work starts only after milestones 1 to 9 finish.

## Evidence

`docs/features/README.md` (tiers and per-feature notes).

## Gate / revisit when

Revisit when a stretch goal is promoted or a Baseline feature is dropped.
