# ADR-0007: Visual track effort allocation

Status: Proposed
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: V1-V3

## Context

Two positions on effort for the Optional visual track (ADR-0006) are recorded and unresolved:

- Bilal intends to develop the visual side alongside Baseline at roughly 80% effort.
- The October 2026 review proposes a fixed time box: one owner, about one day per week, with the December gate deciding continue vs freeze.

## Decision

No decision yet. Both options are recorded here.

## Alternatives considered

1. Roughly 80% effort on the visual side alongside Baseline.
2. Fixed time box: one owner, about one day per week, and a hard gate that decides continue vs freeze. The review's reasoning: scene detection and PP-OCR are cheap, and PaddleOCR-VL is the time sink.

## Consequences

Until the decision is made, the visual track follows ADR-0006: Optional, behind `visual.enabled`, never blocking Baseline.

## Evidence

`docs/BUILD_ORDER.md`: "Pending decisions by module", entry "Visual gate / V1-V3: Effort".

## Gate / revisit when

Bilal decides before Phase 3 starts (Phase 3 begins in January per `docs/BUILD_ORDER.md`; no earlier deadline is recorded). Pass condition: this ADR is superseded by an Accepted ADR naming option 1 or 2.
