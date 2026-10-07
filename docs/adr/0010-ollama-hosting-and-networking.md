# ADR-0010: Ollama hosting and networking

Status: Accepted
Date decided: not recorded; on or before 2026-10-04
Date recorded: 2026-10-08
Module: M0

## Context

The LLM runs through Ollama. WSL2 on Windows 11 24H2 offers mirrored networking, so WSL can reach a loopback service on the Windows host.

## Decision

- Ollama runs on the Windows host with models at `E:\FYP\LLMs`, bound to `127.0.0.1:11434` only.
- WSL reaches it at `http://localhost:11434` through mirrored networking.
- Ollama starts at Windows logon through the Task Scheduler task `Insightex Ollama`, which runs `E:\FYP\start_ollama.ps1`.
- `scripts/windows/start_ollama.ps1` in the repo is the source of truth; the `E:\FYP` file is a deployed copy that is re-copied by hand after any change.

## Alternatives considered

`OLLAMA_HOST=0.0.0.0`: rejected, because it exposes Ollama to the whole network.

## Consequences

- Ollama must be running before the pipeline; the Task Scheduler task does this at logon.
- Windows Ollama auto-updates. After any update, re-run `tools/ollama_contract_probe.py` and compare with `docs/measurements/`.
- The call contract is in ADR-0002.

## Evidence

- `docs/ENVIRONMENT.md` section 5, measured 2026-10-07: `ollama.exe` is the only listener on `127.0.0.1:11434`; Windows booted 23:30:30 and `ollama.exe` started 23:30:56 with no manual step.
- `scripts/windows/start_ollama.ps1`.

## Gate / revisit when

Revisit when Ollama moves off the Windows host or the networking mode changes.
