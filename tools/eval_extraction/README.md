# tools/eval_extraction

**Purpose:** Evaluation of LLM concept extraction quality.

**Where it lives:** the M7 scorer and the blind adjudication sheet were built inside `tools/label_concepts/` (Session 2a, 17 Oct 2026) because they reuse its matching code and gold files: `label_concepts.py score|compare|adjudication-sheet|adjudicate` (`scoring.py`, `adjudication.py`). The model runs they score are written by `insightex extract-eval run` (`backend/src/insightex/extract/`). See `tools/label_concepts/README.md`.

This folder holds nothing else yet.
