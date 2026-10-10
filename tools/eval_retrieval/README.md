# tools/eval_retrieval

**Purpose:** Retrieval evaluation. Test A (question to lecture window, gold spans in seconds) is built; Test B (concept to textbook page, +-2 pages) and Test C (English concept summaries) are planned.

**Rules:** `docs/adr/0043-m5-retrieval-gate-rules.md` (hit rule, de-duplication, net-count rule, gates G0 to G4).

**How to run (Test A):**

```bash
python tools/eval_retrieval/score.py questions                      # writes gold_questions.json from the gold file
python tools/eval_retrieval/score.py run --lecture <workspace_id> --out run.json [--device cuda]   # calls `insightex search`
python tools/eval_retrieval/score.py score --search run.json --table
python tools/eval_retrieval/score.py compare --a runA.json --b runB.json --subset g23
```

`g0_compare.py` checks the production encoder against the legacy bake-off encoder (rank order and cosine scores).

**Inputs:** `gold_spans.json` (frozen at commit `0f5e5ab`; never edited by M5), a lecture with a search index.

**Outputs:** Recall@3 and MRR per subset, per-query hits, wins/losses/net between two configs. Gate evidence is committed under `docs/evidence/m5/`.

**Status:** Test A scorer built in M5 session A. Test B is blocked until the textbook pipeline exists (M10); Test C needs Ollama extraction.

Standalone tool: it must not import from `backend/`. It reaches production code only through the `insightex` CLI or API.
