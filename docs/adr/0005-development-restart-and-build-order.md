# ADR-0005: Development restart and walking-skeleton build order

Status: Accepted
Date decided: not recorded; on or before 2026-10-06
Date recorded: 2026-10-08
Module: Project

## Context

Development restarted from scratch on 2026-09-28. Earlier prototyping was used for decisions only, not as a code base. The earlier build order, `Insightex_Build_Order.md`, listed 21 modules.

## Decision

The build plan adopted in October 2026 replaces the 21-module list. Principle: build a walking skeleton first (video in, cited answer out, the citation seeks the video), then thicken the system in order of risk. Shared engines come before the features that use them.

- **Phase 0, Foundation:** M0, M0b.
- **Phase 1, Walking skeleton:** M1 core, M2 upload ingest, M3 URL ingest, M4 ASR + WER gate, M5 windows + embedding + FAISS, M6 minimal API and UI.
- **Phase 2, Knowledge layer:** M7 to M11.
- **Phase 3, Features:** M12 to M16, plus the visual track V1 to V3.
- **Phase 4, Evaluation, hardening, demo:** M17 to M20.

## Alternatives considered

- The earlier 21-module `Insightex_Build_Order.md`: replaced.
- Building features module by module without an end-to-end path first: not chosen.

## Consequences

- Every module has an exit criterion and a list of pending decisions in `docs/BUILD_ORDER.md`.
- Each pending decision is settled, and recorded as an ADR, before its module starts.

## Evidence

- `docs/BUILD_ORDER.md` (phases, module exits, pending decisions).
- `CLAUDE.md` state block.

## Gate / revisit when

Revisit when a phase boundary moves or a module is added or removed.
