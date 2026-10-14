# tools/eval_extraction

**Purpose:** Evaluation of LLM concept extraction quality.

**How to run:** Not written yet.

**Inputs:** Extraction output in schema v1 (`backend/src/insightex/extract/extraction.schema.json`, ADR-0048) and the gold files from `tools/label_concepts/labels/`. Matching and metrics: ADR-0048, implemented in `tools/label_concepts/matching.py`.

**Outputs:** Quality report.

**Status:** Planned. Extraction quality is provisional pending human inspection (see `docs/adr/0002-ollama-call-contract.md`, open items for M7).

Standalone tool: it must not import from `backend/`.
