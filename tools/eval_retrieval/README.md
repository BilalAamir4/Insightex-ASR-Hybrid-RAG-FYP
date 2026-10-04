# tools/eval_retrieval

**Purpose:** Retrieval evaluation (Test B: concept to textbook page, +-2 pages; Test C: English concept summaries).

**How to run:** Not written yet.

**Inputs:** Labelled queries (`queries.csv`), indexes.

**Outputs:** Recall and MRR tables.

**Status:** Planned. Test B is blocked until a textbook is chosen; Test C needs Ollama extraction. The finished bake-off is archived in `docs/reports/embedding_bakeoff/`.

Standalone tool: it must not import from `backend/`.
