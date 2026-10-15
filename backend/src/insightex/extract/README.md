# insightex.extract

**Purpose:** Concept extraction, importance tagging (F4) and recap (F20); uses llm/.

**Model used:** Ollama qwen3.5:latest via llm/

**Feature numbers:** F4, F20

**Status:** M7 Session 1 (15 Oct 2026): extraction schema v1 only (`extraction.schema.json`, validator `extraction_schema.py`, ADR-0048). The same schema holds gold labels and model output. A byte-identical copy lives in `tools/label_concepts/` (tools never import backend/); `backend/tests/unit/test_extraction_schema.py` keeps the copies equal. No extraction stage yet (Session 3).
