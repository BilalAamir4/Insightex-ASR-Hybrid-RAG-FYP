# ADR-0012: LLM selection and VRAM headroom

Status: Proposed
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M7 / M11

## Context

The current model `qwen3.5` (9B) peaks around 7.7 GB from one short prompt and leaves about 450 MiB. The KV cache grows with context, and Urdu script is token-expensive. The risk is a silent CPU offload or prompt truncation. ADR-0002 fixes how calls are made; the model choice itself is open.

## Decision

Keep `qwen3.5:latest` as the working model until the gate below decides between it and Gemma 4 E4B.

## Alternatives considered

- Gemma 4 E4B: not measured; the candidate in the gate.
- A split (the larger model for offline extraction only, the smaller for interactive Q&A): valid if the two models are within noise.
- KV-cache quantisation (`q8_0`): optional lever, not tested.

## Consequences

The model name is a single config value (`ollama.model`), so a change of model re-runs the probe and nothing else.

## Evidence

- `docs/BUILD_ORDER.md`, pending decision "M0 / M7 / M11".
- ADR-0002 (headroom 510 to 818 MiB at `num_ctx` 8192).

## Gate / revisit when

Gate (M7, before the LLM is fixed):
1. Measure VRAM, tokens/s and `ollama ps` at the worst-case prompt (3 to 5 Urdu windows + 2 textbook chunks).
2. Run concept extraction on 10 labelled windows with `qwen3.5` vs Gemma 4 E4B.

Pass condition: results within noise means the smaller model serves interactive Q&A.
