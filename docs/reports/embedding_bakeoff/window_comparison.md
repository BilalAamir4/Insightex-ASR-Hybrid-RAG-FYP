# Window & Sequence Length Comparison: Insightex Embedding Bake-Off

Evaluation comparing `BAAI/bge-m3` and `Qwen/Qwen3-Embedding-0.6B` across sequence length limits (512 vs 1024) and window durations (30s, 60s, 90s) on lecture data (*100 Days of Machine Learning, Day 4*, 640 cues, 11:28 duration, 28 queries).

---

## a. Overall Results Table (512 vs 1024 Sequence Length)

*All metrics computed using exact FAISS `IndexFlatIP` retrieval over normalized embeddings.*

| Model | Window (s) | Seq Limit | N Windows | N Truncated | Chance R@3 | Recall@1 | Recall@3 | Recall@5 | MRR | Peak VRAM (MB) |
|---|---|---|---|---|---|---|---|---|---|---|
| **bge-m3** | 30 | 512 | 23 | 0 | 13.04% | 16/28 (57.1%) | 26/28 (92.9%) | 27/28 (96.4%) | 0.7298 | 1141.7 |
| **bge-m3** | 30 | 1024 | 23 | 0 | 13.04% | 16/28 (57.1%) | 26/28 (92.9%) | 27/28 (96.4%) | 0.7298 | 1141.7 |
| **bge-m3** | 60 | 512 | 12 | 0 | 25.00% | 19/28 (67.9%) | 25/28 (89.3%) | 27/28 (96.4%) | 0.8009 | 1160.8 |
| **bge-m3** | 60 | 1024 | 12 | 0 | 25.00% | 19/28 (67.9%) | 25/28 (89.3%) | 27/28 (96.4%) | 0.8009 | 1160.8 |
| **bge-m3** | 90 | 512 | 8 | 0 | 37.50% | 18/28 (64.3%) | 26/28 (92.9%) | 28/28 (100.0%) | 0.7899 | 1161.5 |
| **bge-m3** | 90 | 1024 | 8 | 0 | 37.50% | 18/28 (64.3%) | 26/28 (92.9%) | 28/28 (100.0%) | 0.7899 | 1161.5 |
| **qwen3-0.6b** | 30 | 512 | 23 | 0 | 13.04% | 13/28 (46.4%) | 25/28 (89.3%) | 26/28 (92.9%) | 0.6736 | 1766.5 |
| **qwen3-0.6b** | 30 | 1024 | 23 | 0 | 13.04% | 13/28 (46.4%) | 25/28 (89.3%) | 26/28 (92.9%) | 0.6736 | 1766.5 |
| **qwen3-0.6b** | 60 | 512 | 12 | 2 | 25.00% | 20/28 (71.4%) | 24/28 (85.7%) | 27/28 (96.4%) | 0.8107 | 1976.8 |
| **qwen3-0.6b** | 60 | 1024 | 12 | 0 | 25.00% | 19/28 (67.9%) | 26/28 (92.9%) | 27/28 (96.4%) | 0.7988 | 2044.5 |
| **qwen3-0.6b** | 90 | 512 | 8 | 7 | 37.50% | 20/28 (71.4%) | 25/28 (89.3%) | 27/28 (96.4%) | 0.8199 | 1976.8 |
| **qwen3-0.6b** | 90 | 1024 | 8 | 0 | 37.50% | 19/28 (67.9%) | 26/28 (92.9%) | 27/28 (96.4%) | 0.8170 | 2044.5 |

---

## b. Recall@3 Split by Query Kind (1024 Sequence Length Run)

*Breakdown for the 1024 run across query categories: `en` (15 queries), `hard` (8 queries), `roman` (5 queries).*

| Model | Window (s) | N Windows | Chance R@3 | en R@3 (hits/15, %) | hard R@3 (hits/8, %) | roman R@3 (hits/5, %) | ALL R@3 (hits/28, %) |
|---|---|---|---|---|---|---|---|
| **bge-m3** | 30 | 23 | 13.04% | 15/15 (100.0%) | 8/8 (100.0%) | 3/5 (60.0%) | 26/28 (92.9%) |
| **bge-m3** | 60 | 12 | 25.00% | 15/15 (100.0%) | 6/8 (75.0%) | 4/5 (80.0%) | 25/28 (89.3%) |
| **bge-m3** | 90 | 8 | 37.50% | 14/15 (93.3%) | 8/8 (100.0%) | 4/5 (80.0%) | 26/28 (92.9%) |
| **qwen3-0.6b** | 30 | 23 | 13.04% | 13/15 (86.7%) | 8/8 (100.0%) | 4/5 (80.0%) | 25/28 (89.3%) |
| **qwen3-0.6b** | 60 | 12 | 25.00% | 14/15 (93.3%) | 8/8 (100.0%) | 4/5 (80.0%) | 26/28 (92.9%) |
| **qwen3-0.6b** | 90 | 8 | 37.50% | 14/15 (93.3%) | 8/8 (100.0%) | 4/5 (80.0%) | 26/28 (92.9%) |

---

## c. Chance Level Definition & Formula

The chance level represents the expected Recall@3 of a random ranker choosing without replacement:

$$\text{Chance Level (Recall@3)} = \min\left(1.0, \frac{3}{N_{\text{windows}}}\right)$$

- **Window W=30s** ($N = 23$ windows): $\frac{3}{23} \approx \mathbf{13.04\%}$
- **Window W=60s** ($N = 12$ windows): $\frac{3}{12} = \mathbf{25.00\%}$
- **Window W=90s** ($N = 8$ windows): $\frac{3}{8} = \mathbf{37.50\%}$

*Note: While larger windows (e.g. 90s) have higher nominal retrieval scores, their baseline random chance level is nearly 3x higher than 30s windows because there are only 8 candidate targets in the lecture.*

---

## d. Verdict

### (i) Impact of Raising Length Limit to 1024
- **BGE-M3**: Absolutely **no change** across any window size (0 queries changed). BGE-M3 had 0 truncated sequences at 512, so increasing the limit to 1024 had zero effect on metrics, ranks, or peak VRAM.
- **Qwen3-0.6B**:
  - **W=30s**: 0 truncations at 512 $\to$ **no change** (0 queries changed).
  - **W=60s**: Truncations dropped from 2 to 0. Recall@3 increased from 24/28 to 26/28 (**+2 queries gained at top-3**: Q6 moved from rank 4 to 3; Q25 moved from rank 4 to 3). Peak VRAM increased from 1,976.8 MB to 2,044.5 MB.
  - **W=90s**: Truncations dropped from 7 to 0. Recall@3 increased from 25/28 to 26/28 (**+1 query gained at top-3**: Q25 made a dramatic jump from rank 4 to rank 1). Peak VRAM increased from 1,976.8 MB to 2,044.5 MB.

### (ii) Best Window and Smallest-Reasonable Window per Model
- **BGE-M3**:
  - **Best window**: **W=90s** (Recall@3 = 26/28 [92.86%], MRR = 0.7899; tied on R@3 with W=30s which has MRR = 0.7298).
  - **Smallest window within 2 queries of best**: **W=30s** (26/28 hits, exactly 0 queries difference from best).
- **Qwen3-0.6B**:
  - **Best window**: **W=90s** (Recall@3 = 26/28 [92.86%], MRR = 0.8170; tied on R@3 with W=60s which has MRR = 0.7988).
  - **Smallest window within 2 queries of best**: **W=30s** (25/28 hits, 1 query difference from best).

### (iii) Noise Rule Application
Under the noise rule, a difference of 1–2 queries in Recall@3 is within finite-sample noise and constitutes a tie:
- At W=90s: BGE-M3 (26 hits) vs Qwen3-0.6B (26 hits) $\to$ **0 query difference $\to$ DEAD HEAT TIE**.
- At W=60s: BGE-M3 (25 hits) vs Qwen3-0.6B (26 hits) $\to$ Qwen3 better by 1 query $\to$ **TIE**.
- At W=30s: BGE-M3 (26 hits) vs Qwen3-0.6B (25 hits) $\to$ BGE-M3 better by 1 query $\to$ **TIE**.

### (iv) Decision Rule on 1024 Run
- **Subset S**: All queries with kind `hard` (8) or `roman` (5) $\to$ **13 queries total**.
  - **BGE-M3** (best window W=90s): 8/8 hard + 4/5 roman = **12 / 13 hits on S** (missed Q24 at rank 4).
  - **Qwen3-0.6B** (best window W=90s): 8/8 hard + 4/5 roman = **12 / 13 hits on S** (missed Q27 at rank 4; Q25 was hit at rank 1).
  - **Difference on Subset S**: $12 - 12 = \mathbf{0\text{ queries}}$.
- **Kind `en` (15 queries total)**:
  - BGE-M3 at W=90s: **14 / 15 hits** (missed Q8 at rank 5).
  - Qwen3-0.6B at W=90s: **14 / 15 hits** (missed Q4 at rank 8).
  - **Difference on `en`**: $14 - 14 = \mathbf{0\text{ queries}}$.
- **Applied Branch**: Neither model achieved a $\ge 3$ query lead on Subset S. The **default tie-breaking branch to BGE-M3 applies**. A tie goes to BGE-M3 because its sparse representations are directly reusable for Insightex's hybrid router, it exhibits lower VRAM footprint (1.16 GB vs 2.04 GB), and its tokenizer natively fits Urdu without requiring context expansion.

---

## e. Re-Check of Flagged Queries (Windows 30s & 60s)

*Queries are referenced by 1-based CSV row number (header excluded, where Row $N$ corresponds to `query_idx` $N-1$).*

### 1. CSV Row 9 (`query_idx` 8)
- **Query Text**: `"Why does software need to be deployed on a server for customers to use it?"`
- **Labelled Range**: `00:59` – `01:18` (Kind: `en`)
- **Retrieval Performance at W=30s and W=60s**:
  - **bge-m3 (W=30s)**: Rank = **1** | Top-3 Spans: `01:00-01:30@0.634`; `04:00-04:30@0.581`; `09:00-09:30@0.529`
  - **bge-m3 (W=60s)**: Rank = **1** | Top-3 Spans: `01:00-02:00@0.615`; `04:00-05:00@0.571`; `09:00-10:00@0.530`
  - **qwen3-0.6b (W=30s)**: Rank = **1** | Top-3 Spans: `01:00-01:30@0.658`; `04:00-04:30@0.493`; `03:30-04:00@0.477`
  - **qwen3-0.6b (W=60s)**: Rank = **1** | Top-3 Spans: `01:00-02:00@0.593`; `04:00-05:00@0.444`; `02:00-03:00@0.424`
- **Hypothesis**: The query and labelled timestamp range are completely accurate. In all 4 conditions at W=30s and W=60s, both models placed the correct passage at **Rank 1**. The earlier miss at W=90s (Rank 5 on BGE-M3) was strictly a consequence of window-length dilution when window 0 (`00:00-01:30`) merged introductory remarks with server deployment.

### 2. CSV Row 5 (`query_idx` 4)
- **Query Text**: `"How does the email spam classifier example show a weakness of batch learning?"`
- **Labelled Range**: `05:27` – `05:52` (Kind: `en`)
- **Retrieval Performance at W=30s and W=60s**:
  - **bge-m3 (W=30s)**: Rank = **1** | Top-3 Spans: `05:30-06:00@0.621`; `07:30-08:00@0.604`; `11:00-11:28@0.588`
  - **bge-m3 (W=60s)**: Rank = **1** | Top-3 Spans: `05:00-06:00@0.647`; `11:00-11:28@0.588`; `07:00-08:00@0.583`
  - **qwen3-0.6b (W=30s)**: Rank = **1** | Top-3 Spans: `05:30-06:00@0.612`; `07:30-08:00@0.588`; `07:00-07:30@0.583`
  - **qwen3-0.6b (W=60s)**: Rank = **1** | Top-3 Spans: `05:00-06:00@0.613`; `03:00-04:00@0.610`; `07:00-08:00@0.609`
- **Hypothesis**: The query and label are completely sound. Across both models at W=30s and W=60s, the target window was retrieved at **Rank 1**. The previous rank 8 drop on Qwen3 occurred exclusively at W=90s (`04:30-06:00`), where the spam classifier discussion was diluted by the preceding Netflix recommendation example.

### 3. CSV Row 25 (`query_idx` 24)
- **Query Text**: `"batch learning mein model ko dobara train kyun karna parta hai"`
- **Labelled Range**: `05:52` – `06:20` (Kind: `roman`)
- **Retrieval Performance at W=30s and W=60s**:
  - **bge-m3 (W=30s)**: Rank = **15** | Top-3 Spans: `03:30-04:00@0.601`; `03:00-03:30@0.563`; `11:00-11:28@0.549`
  - **bge-m3 (W=60s)**: Rank = **7**  | Top-3 Spans: `03:00-04:00@0.578`; `07:00-08:00@0.551`; `11:00-11:28@0.549`
  - **qwen3-0.6b (W=30s)**: Rank = **9**  | Top-3 Spans: `03:00-03:30@0.772`; `02:00-02:30@0.757`; `07:00-07:30@0.753`
  - **qwen3-0.6b (W=60s)**: Rank = **6**  | Top-3 Spans: `03:00-04:00@0.794`; `02:00-03:00@0.753`; `07:00-08:00@0.734`
- **Hypothesis**: This query missed top-3 across all 4 conditions. In contrast, its English counterpart Q19 (CSV Row 20: *"How do teams stop a deployed model from going out of date?"*, identical range `05:52-06:20`) achieved Rank 2 (W=30s) and Rank 1 (W=60s) on BGE-M3, and Rank 1 (W=30s) and Rank 2 (W=60s) on Qwen3.
  - *Hypothesis*: The miss is primarily driven by **Urdu-script mismatch**: colloquial Roman Urdu ("dobara train kyun karna parta hai") exhibits poor subword lexical overlap against the transcript's native Arabic script Urdu, whereas English terminology matches the spoken technical loanwords directly.
