# ADR-0015: Query-time embedding on CPU

Status: Proposed
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M5

## Context

`bge-m3` (about 1.1 GB; the bake-off measured a 1,141.7 MB peak) and `qwen3.5` (about 7.7 GB) cannot share 8 GB during Q&A.

## Decision

- Documents are encoded on the GPU at ingest.
- Queries are encoded on the CPU in the API process (fp32, about 2.3 GB RAM).
- The reranker also runs on the CPU.
- The GPU belongs to Ollama during Q&A.

## Alternatives considered

Encoding queries on the GPU: rejected by ADR-0011; it would put `bge-m3` and `qwen3.5` in VRAM together.

## Consequences

The API process holds `bge-m3` in RAM. CPU encoding latency: Not recorded.

## Evidence

`docs/reports/Embedding_Report.md`; `docs/reports/embedding_bakeoff/results_seq1024/summary.md` (peak VRAM 1,141.71 MB at 30 s windows); `.claude/rules/retrieval.md`.

## Gate / revisit when

Gate (M5): rerun Test A with CPU-encoded queries against GPU-encoded windows. Pass condition: Recall@3 is unchanged.
