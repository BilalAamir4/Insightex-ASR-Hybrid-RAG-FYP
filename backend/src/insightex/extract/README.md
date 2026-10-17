# insightex.extract

**Purpose:** Concept extraction, importance tagging (F4) and recap (F20); uses llm/.

**Model used:** Ollama qwen3.5:latest via llm/

**Feature numbers:** F4, F20

**Status:** M7 Session 1 (15 Oct 2026): extraction schema v1 only (`extraction.schema.json`, validator `extraction_schema.py`, ADR-0048). The same schema holds gold labels and model output. A byte-identical copy lives in `tools/label_concepts/` (tools never import backend/); `backend/tests/unit/test_extraction_schema.py` keeps the copies equal. No extraction stage yet (Session 3).

M7 Session 2a (17 Oct 2026): the evaluation harness, `insightex extract-eval` (tested on synthetic fixtures only; no run on a real lecture yet):

| Module | Role |
|---|---|
| `arms.py` | Arms C1 to C4 from `config/m7_arms.yaml`: model, input (original or English), batch size k, previous-window context. A null field is set from the earlier comparison's winner, and the arm refuses to run until then. |
| `prompts.py` | Frozen prompt files (used only with their pinned sha256), the request layout (system prompt, plus the context block only when a call has context; user message = JSON of the windows and context), and the Ollama `format` (one record per target window). No prompt wording. |
| `harness.py` | One arm over the target windows: call plan (batches, Amendment 2 context rules), exclusive GPU lease, unload every resident model first, translation (C2 arm B), extraction through `ollama_client.chat_raw`, dangling relations dropped and counted, v1 validation, one retry of the same call, model unloaded in `finally`; reply cache keyed by the full request (model digest, messages, format, options), harness version and attempt; evidence `extraction.json`, `run.json`, `calls.jsonl`. |
| `vram.py` | nvidia-smi VRAM peak sampler (baseline, peak, difference). |
| `measure.py` | Worst-case prompt VRAM / `num_ctx` measurement for Session 2b (`insightex extract-eval measure`): per batch size k, with and without previous-window context, one real call per `num_ctx`; passes when real prompt tokens + `num_predict` fit and `ollama ps` shows 100% GPU. Accepts a draft prompt before the freeze (recorded as not frozen). |
| `cli.py` | `insightex extract-eval arms|run|measure`. |

Evidence layout: `docs/evidence/m7/README.md`. The scorer that reads it: `tools/label_concepts/` (`score`, `compare`, `adjudication-sheet`, `adjudicate`).
