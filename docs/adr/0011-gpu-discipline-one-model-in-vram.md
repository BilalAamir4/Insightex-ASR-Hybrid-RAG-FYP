# ADR-0011: GPU discipline: one model in VRAM at a time

Status: Accepted
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: Project

## Context

Hardware: RTX 3070 with 8 GB VRAM and 32 GB RAM. The Ollama model `qwen3.5` peaks at about 7.7 to 7.8 GB and cannot share the GPU with another model.

## Decision

Models load, process and unload one stage at a time and never coexist in VRAM. Each stage runs as a separate process, which released VRAM cleanly in the environment audit. The GPU lease that enforces this is built in M1 (ADR-0022).

## Alternatives considered

Running stages in one process or letting models coexist: rejected, because `qwen3.5` alone leaves under 1 GB free.

## Consequences

- No two CUDA stages run at once.
- Before a GPU run, `ollama ps` is checked and a loaded model is unloaded.
- At query time the GPU belongs to Ollama (ADR-0015).

## Evidence

The two peak figures below come from different measurements and are both kept; neither is chosen over the other.

- Whole-GPU peak of the sequential environment test: 7,759 MiB, net drift +38 MiB (register figure; the repo holds the check script `tools/audit_env/verify_6e_sequential.py` but no results file with this number).
- `qwen3.5` probe runs at `num_ctx` 8192: peak 7,394 to 7,682 MiB, 510 to 818 MiB free (`docs/measurements/2026-10-07_ollama_contract.md`, ADR-0002).

## Gate / revisit when

Revisit when the GPU changes or a measured stage no longer fits alone.
