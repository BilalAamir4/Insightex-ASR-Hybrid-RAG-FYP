---
paths:
  - "backend/src/insightex/retrieval/**"
  - "backend/src/insightex/index/**"
  # No such folders yet (M5/M9 not started); most plausible homes for embedding and router code:
  - "backend/src/insightex/embed*/**"
  - "backend/src/insightex/router/**"
---
# Embeddings, index, router (M5, M9) — loaded only when touching retrieval code

The settled decisions and the open gates are listed separately. Settle each gate with numbers before building on it.

Decided:
- Use `BAAI/bge-m3`. Embed native-script Whisper text only, never Roman Urdu.
- Normalise with L2 and search with FAISS `IndexFlatIP`.
- Reference implementation: `docs/reports/embedding_bakeoff/embed_bakeoff.py`. Treat it as reference only and port it into `backend/src/insightex/` rather than importing it.

Gates (from the build-order review):
- **CPU queries.** Encode windows on GPU at ingest and encode queries on CPU in the API process. Rerun Test A with CPU queries. Recall@3 must not change.
- **Sparse weights.** Use FlagEmbedding `BGEM3FlagModel` (sentence-transformers gives dense only). Fuse dense and sparse rankings with Reciprocal Rank Fusion. If sparse adds nothing, say so, and drop the tie-break argument from the report.
- **Window edges.** Keep the 30 s target but snap edges to Whisper segment boundaries. Test 50% overlap and adopt it only if Recall@3 improves. Score hits by time overlap with the gold span, and dedupe overlapping hits.
- **Test B.** Concept → textbook page within ±2 pages. Blocked until the textbook is chosen.
- **Test C.** English concept summaries. Needs Ollama extraction first.
- **Reranker.** It should match the embedding family.
- **Router (M9).** It must beat vector-only on graph-shaped queries. Otherwise, simplify it.
