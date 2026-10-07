# ADR-0006: Scope: ASR pipeline is Baseline, visual pipeline is Optional

Status: Accepted
Date decided: 2026-09-30
Date recorded: 2026-10-08
Module: Project

## Context

After the idea defense on 2026-09-30 the panel judged the project too large. The proposal combined an ASR pipeline with a visual pipeline (scene-change detection and OCR).

## Decision

- The ASR pipeline is the committed Baseline.
- The visual pipeline (scene-change detection + OCR) is Optional. It sits behind the config flag `visual.enabled` (default false) and never blocks a Baseline milestone.
- Visual gate at the end of December: scene detection + PP-OCR on 30 frames must be usable on most slide frames for the Optional track to continue. Otherwise the visual pipeline is frozen as a documented limitation.

## Alternatives considered

- Full scope as proposed: rejected by the panel's judgement that the project is too large.
- Dropping the visual pipeline now: not chosen; the Optional track stays open until the December gate.

## Consequences

- Baseline milestones do not depend on any visual code.
- Visual work is time-boxed; see ADR-0007 for the effort allocation, which is still open.
- Feature tiers that follow from this scope are in ADR-0008.

## Evidence

- `config/default.yaml`: `visual.enabled: false`.
- `docs/BUILD_ORDER.md`: "Visual gate (end of December)".

## Gate / revisit when

Revisit at the end-of-December visual gate (pass condition above).
