# ADR-0031: Visual OCR engine and isolation

Status: Proposed
Date decided: not recorded; on or before 2026-10-04
Date recorded: 2026-10-08
Module: V1-V3

## Context

PaddleOCR-VL (0.9B vision-language model) was probed on 2026-10-01. One printed formula was recognised correctly. About 3.1 GB was actually used, but the Paddle allocator reserves about 7 GB. 2 hangs occurred in about 5 runs. There is no per-block recognition confidence.

## Decision

- Baseline OCR is PP-OCR.
- PaddleOCR-VL is considered only if the December visual gate passes (ADR-0006) and Phase 3 is on schedule, through a 30-frame bake-off against PP-OCR on text slides, equations, diagrams, whiteboard and notebook screens.
- Isolation: separate env `~/envs/paddleocr-vl` (paddlepaddle-gpu 3.2.1 cu126, paddleocr 3.7.0). It runs as a subprocess with a timeout of about 120 s and one retry, and waits for VRAM below about 800 MiB between runs.
- Frame reading uses sequential `cap.read()` with modulo skipping, because `CAP_PROP_POS_FRAMES` seeking returns stale frames on screen-recording codecs.

## Alternatives considered

PaddleOCR-VL as the baseline: not chosen, for the hangs, the allocator and the missing confidence above.

## Consequences

Feature 13 cannot take confidence from PaddleOCR-VL; if built, it takes confidence from PP-OCR. No worker code exists; `workers/ocr/` holds only a README.

## Evidence

`docs/reports/OCR_report.md`; `docs/reports/vl_probe_REPORT.md`; `tools/probe_paddleocr_vl/`; `workers/ocr/README.md`.

## Gate / revisit when

Gate: the December visual gate passes and Phase 3 is on schedule, then the 30-frame bake-off runs. Pass condition for adopting PaddleOCR-VL: it beats PP-OCR on the 30 frames; the margin is Not recorded.
