# Documentation Updates: Insightex Embedding Evaluation

This document contains text updates ready to paste into project documentation files based on the bake-off results in `tools/eval_embeddings/results_seq1024/`.

---

## 1. Insightex_Final_Features.md
**Target Location:** Section F (GPU Rotation Bullet)

```markdown
- **GPU Model Lifecycle & Rotation:** Pipeline execution enforces strict sequential stage-wise loading and unloading (load model weights, perform inference, completely unload from VRAM and flush CUDA cache) rather than concurrent multi-model residency. Three committed models are rotated sequentially through GPU VRAM: Whisper (audio transcription), BAAI/bge-m3 (dense embedding generation for lecture transcript windows and incoming queries, measuring 1141.71 MB peak VRAM at 30-second windows and 1161.47 MB peak at 90-second windows), and the Ollama LLM (downstream reasoning and response synthesis), alongside optional PaddleOCR for visual text extraction. No two models occupy GPU VRAM concurrently, strictly adhering to the 8 GB VRAM budget.
```

---

## 2. Final_Proposal.tex
**Target Location:** Section 9.1 (VRAM Risk)

```latex
\item \textbf{Embedding Model VRAM Allocation and Lifecycle:} Empirical evaluation of the selected embedding model (\texttt{BAAI/bge-m3}) demonstrates a peak GPU VRAM footprint of 1141.71\,MB at the designated 30-second window duration (and an overall peak of 1161.47\,MB across all tested window configurations up to 90 seconds), evaluated at batch size 16 with a sequence length limit of 1024 tokens. In accordance with the system's strict stage-wise load/process/unload discipline, the embedding model is loaded exclusively for indexing transcript segments and encoding queries, and is purged from VRAM prior to initializing subsequent pipeline stages (such as the Ollama LLM), ensuring zero concurrent VRAM coexistence and preventing out-of-memory errors on the 8\,GB GPU.
```

---

## 3. Final_Proposal.tex
**Target Location:** Section 5.3 (Retrieval Evaluation)

```latex
An empirical embedding bake-off was conducted comparing \texttt{BAAI/bge-m3} and \texttt{Qwen/Qwen3-Embedding-0.6B} across three transcript window durations (30\,s, 60\,s, and 90\,s) at a maximum sequence length of 1024 tokens and batch size 16, with retrieval evaluated using FAISS exact inner-product search over normalized embeddings. Under the predetermined decision rule, the outcome between the two models was a tie, as neither model demonstrated a statistically significant advantage on difficult and transliterated queries ($\Delta < 3$ hits). \texttt{BAAI/bge-m3} was retained based on secondary architectural criteria: lower peak VRAM consumption across all windows (1141.71\,MB to 1161.47\,MB versus 1766.51\,MB to 2044.46\,MB) and native output of multi-lingual sparse lexical weights that can be directly reused by the downstream hybrid search router. Neither model experienced sequence truncation at 1024 tokens ($n_{\text{truncated}} = 0$). At the chosen 30-second window duration, \texttt{BAAI/bge-m3} achieves a Recall@3 of 92.86\% (26/28 queries) and an MRR of 0.7298; however, its Recall@1 is 57.14\% (16/28 queries), indicating that the correct window appears at rank 1 only about 57\% of the time. Consequently, the user interface should display the top 3 retrieved passages or incorporate a downstream reranking stage. Several evaluation constraints apply: (i) the benchmark is evaluated on a single 11-minute lecture with 28 queries; (ii) queries consist of English and Roman Urdu transliterations evaluated against native-script Whisper transcript segments, with several queries intentionally targeting the same segment such that queries are not strictly independent; and (iii) ground-truth target intervals were derived from Whisper segment timestamps and not independently verified against audio playback.

\begin{table}[htbp]
\centering
\caption{Retrieval performance and peak GPU memory footprint of candidate embedding models across transcript window sizes (28 queries, sequence length 1024, batch size 16).}
\label{tab:embedding_evaluation}
\begin{tabular}{lccccc}
\hline
\textbf{Model} & \textbf{Window (s)} & \textbf{Recall@1 (\%)} & \textbf{Recall@3 (\%)} & \textbf{MRR} & \textbf{Peak VRAM (MB)} \\
\hline
\texttt{BAAI/bge-m3} & 30 & 57.14 & 92.86 & 0.7298 & 1141.71 \\
\texttt{BAAI/bge-m3} & 60 & 67.86 & 89.29 & 0.8009 & 1160.80 \\
\texttt{BAAI/bge-m3} & 90 & 64.29 & 92.86 & 0.7899 & 1161.47 \\
\hline
\texttt{Qwen/Qwen3-Embedding-0.6B} & 30 & 46.43 & 89.29 & 0.6736 & 1766.51 \\
\texttt{Qwen/Qwen3-Embedding-0.6B} & 60 & 67.86 & 92.86 & 0.7988 & 2044.46 \\
\texttt{Qwen/Qwen3-Embedding-0.6B} & 90 & 67.86 & 92.86 & 0.8170 & 2044.46 \\
\hline
\end{tabular}
\end{table}
```

---

## 4. Final_Proposal.tex
**Target Location:** Table 3 (Tools and Technologies, two columns: Category & Tools/Technologies)

```latex
Embeddings & BAAI/bge-m3 (dense embeddings; sparse lexical weights retained for hybrid search router) \\
Reranker (planned, not evaluated) & Reranker from the BGE-M3 family, model to be confirmed, not yet evaluated \\
```

---

## 5. Defense Notes
**Target Location:** Plain-text defense preparation notes

- **Comparison & Model Result:** We evaluated `BAAI/bge-m3` against `Qwen/Qwen3-Embedding-0.6B` across 30s, 60s, and 90s transcript windows; under our evaluation decision rule, the result was an exact tie (both achieved 12/13 top-3 hits on difficult/Roman queries and 14/15 on English queries at their respective best windows).
- **Why BGE-M3 Was Kept:** BGE-M3 was selected on secondary criteria: significantly lower peak VRAM footprint (1141.71 MB vs 1766.51 MB at 30s) and multi-functionality, allowing its sparse weights to be reused directly in our hybrid BM25/dense router without loading a separate lexical model.
- **Window Size Chosen & Rationale:** We selected the 30-second window duration because it is the smallest window within 2 queries of the best performance (Recall@3 is identical to 90s at 26/28 hits [92.86%], with a 0-query gap), providing finer-grained transcript localization for the student.
- **Recall@1 Implication:** At 30s, Recall@1 is 57.14% (16/28), showing that the top-ranked result is correct only about 57% of the time; thus the UI must present top-3 candidates or pass them to a reranker.
- **Three Evaluation Limits:**
  1. *Benchmark Scale:* Tested on a single 11-minute lecture session with 28 total queries.
  2. *Query Dependency & Modality:* Queries are English and Roman Urdu transliterations queried against native Urdu-script Whisper output; several queries target the same passage and are not independent.
  3. *Ground Truth Derivation:* Target timestamp intervals were derived from Whisper segment boundaries and not independently verified against audio playback.
