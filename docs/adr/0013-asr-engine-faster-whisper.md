# ADR-0013: ASR engine: faster-whisper

Status: Accepted
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M4

## Context

The pipeline needs ASR for code-switched Urdu/English lectures on an 8 GB GPU. faster-whisper can silently drift into translation mode on South Asian content, especially on smaller checkpoints. Whisper labelling Urdu audio as "hi" is cosmetic metadata only.

## Decision

faster-whisper on CUDA float16. The checkpoint and language setting are open (ADR-0014).

## Alternatives considered

Other ASR engines: Not recorded.

## Consequences

- Transcription must confirm `task=transcribe` before WER is computed.
- The ASR stage runs as its own process under ADR-0011.

## Evidence

Benchmark on one real 30 s code-switched clip (`language=ur`, beam 5, VAD on), register figures, not re-run:

| Checkpoint | Load (s) | Inference (s) | Peak VRAM (MiB) |
|---|---|---|---|
| medium | 3.53 | 11.36 | 4,532 |
| large-v3 | 7.43 | 3.59 | 5,895 |

VRAM returned to baseline after each run. Medium ran first, so the speed gap is cold vs warm, not a quality comparison. Scripts: `tools/bench_models/asr/`. The repo holds no results file with these figures.

## Gate / revisit when

Superseded in part by ADR-0014 once the WER gate picks a checkpoint. Revisit if faster-whisper cannot hold `task=transcribe` on the lecture set.
