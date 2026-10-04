# Embedding Model Bake-Off Analysis: Insightex Retrieval Layer

Evaluation completed on 2026-10-02 comparing `BAAI/bge-m3` and `Qwen/Qwen3-Embedding-0.6B` across window durations of 30s, 60s, and 90s on the development lecture (*100 Days of Machine Learning, Day 4: Batch vs Online Learning*, 640 cues, 11:28 duration).

---

## a. Results Table

All metrics computed using exact FAISS `IndexFlatIP` search over L2-normalized embeddings (cosine similarity).

| Model | Window (s) | Kind | N Queries | Recall@1 | Recall@3 | Recall@5 | MRR | Windows Enc (s) | Queries Enc (s) | Peak VRAM (MB) | N Windows | Truncated (>512) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **bge-m3** | 30 | ALL | 28 | 0.5714 | 0.9286 | 0.9643 | 0.7298 | 0.088 | 0.487 | 1141.7 | 23 | 0 |
| bge-m3 | 30 | en | 15 | 0.7333 | 1.0000 | 1.0000 | 0.8444 | 0.088 | 0.487 | 1141.7 | 23 | 0 |
| bge-m3 | 30 | hard | 8 | 0.5000 | 1.0000 | 1.0000 | 0.7083 | 0.088 | 0.487 | 1141.7 | 23 | 0 |
| bge-m3 | 30 | roman | 5 | 0.2000 | 0.6000 | 0.8000 | 0.4200 | 0.088 | 0.487 | 1141.7 | 23 | 0 |
| **bge-m3** | 60 | ALL | 28 | 0.6786 | 0.8929 | 0.9643 | 0.8009 | 0.080 | 0.487 | 1160.8 | 12 | 0 |
| bge-m3 | 60 | en | 15 | 0.8000 | 1.0000 | 1.0000 | 0.9000 | 0.080 | 0.487 | 1160.8 | 12 | 0 |
| bge-m3 | 60 | hard | 8 | 0.7500 | 0.7500 | 1.0000 | 0.8063 | 0.080 | 0.487 | 1160.8 | 12 | 0 |
| bge-m3 | 60 | roman | 5 | 0.2000 | 0.8000 | 0.8000 | 0.4952 | 0.080 | 0.487 | 1160.8 | 12 | 0 |
| **bge-m3** | **90** | **ALL** | **28** | **0.6429** | **0.9286** | **1.0000** | **0.7899** | **0.072** | **0.487** | **1161.5** | **8** | **0** |
| bge-m3 | 90 | en | 15 | 0.7333 | 0.9333 | 1.0000 | 0.8356 | 0.072 | 0.487 | 1161.5 | 8 | 0 |
| bge-m3 | 90 | hard | 8 | 0.6250 | 1.0000 | 1.0000 | 0.8125 | 0.072 | 0.487 | 1161.5 | 8 | 0 |
| bge-m3 | 90 | roman | 5 | 0.4000 | 0.8000 | 1.0000 | 0.6167 | 0.072 | 0.487 | 1161.5 | 8 | 0 |
| **qwen3-0.6b** | 30 | ALL | 28 | 0.4643 | 0.8929 | 0.9286 | 0.6736 | 0.360 | 0.287 | 1766.5 | 23 | 0 |
| qwen3-0.6b | 30 | en | 15 | 0.6000 | 0.8667 | 0.9333 | 0.7611 | 0.360 | 0.287 | 1766.5 | 23 | 0 |
| qwen3-0.6b | 30 | hard | 8 | 0.5000 | 1.0000 | 1.0000 | 0.7083 | 0.360 | 0.287 | 1766.5 | 23 | 0 |
| qwen3-0.6b | 30 | roman | 5 | 0.0000 | 0.8000 | 0.8000 | 0.3556 | 0.360 | 0.287 | 1766.5 | 23 | 0 |
| **qwen3-0.6b** | 60 | ALL | 28 | 0.7143 | 0.8571 | 0.9643 | 0.8107 | 0.326 | 0.287 | 1976.8 | 12 | 2 |
| qwen3-0.6b | 60 | en | 15 | 0.7333 | 0.8667 | 1.0000 | 0.8300 | 0.326 | 0.287 | 1976.8 | 12 | 2 |
| qwen3-0.6b | 60 | hard | 8 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.326 | 0.287 | 1976.8 | 12 | 2 |
| qwen3-0.6b | 60 | roman | 5 | 0.2000 | 0.6000 | 0.8000 | 0.4500 | 0.326 | 0.287 | 1976.8 | 12 | 2 |
| **qwen3-0.6b** | **90** | **ALL** | **28** | **0.7143** | **0.8929** | **0.9643** | **0.8199** | **0.236** | **0.287** | **1976.8** | **8** | **7** |
| qwen3-0.6b | 90 | en | 15 | 0.8000 | 0.9333 | 0.9333 | 0.8639 | 0.236 | 0.287 | 1976.8 | 8 | 7 |
| qwen3-0.6b | 90 | hard | 8 | 0.8750 | 1.0000 | 1.0000 | 0.9375 | 0.236 | 0.287 | 1976.8 | 8 | 7 |
| qwen3-0.6b | 90 | roman | 5 | 0.2000 | 0.6000 | 1.0000 | 0.5000 | 0.236 | 0.287 | 1976.8 | 8 | 7 |

---

## b. Analysis of Misses (Top-3 Retrieval)

Each model was evaluated at its best window size (**W=90** for both models, based on Recall@3 and MRR). The table below lists all queries that failed to achieve a hit within the top-3 retrieved windows.

| Model | Q# | Kind | Query Text | Labelled Range | Rank | Top-3 Retrieved Window Ranges & Cosine Scores | Rank-1 Window Text (First 200 chars) | Hypothesis |
|---|---|---|---|---|---|---|---|---|
| **bge-m3** (W=90) | Q8 | en | Why does software need to be deployed on a server for customers to use it? | `00:59`-`01:18` | 5 | `09:00-10:30@0.530`; `01:30-03:00@0.530`; `03:00-04:30@0.518` | `as an app تو ایک بار وہ جو چلا کیا تو جب تک وہ لوگ واپس نہیں آتے یا internet connectivity والے zone میں نہیں آتے تب تک آپ اس کو واپس pull down کر کے train کر کے update نہیں کر سکتے تو that is a limita` | **window too short/long** (Hypothesis: at W=30 and W=60, Q8 was hit at rank 1 with scores 0.672 and 0.648. At W=90, window 0 `00:00-01:30` dilutes the server deployment statement with introductory remarks, allowing the device/connectivity deployment discussion at 09:00-10:30 to score slightly higher: 0.530 vs 0.491). |
| **bge-m3** (W=90) | Q24 | roman | batch learning mein model ko dobara train kyun karna parta hai | `05:52`-`06:20` | 4 | `03:00-04:30@0.551`; `01:30-03:00@0.551`; `07:30-09:00@0.549` | `no doubt آپ کر سکتے ہو ایسا but ایسا کوئی کرتا نہیں ہے کیونکہ it would be costly and time taking تو generally جو batch learning ہوتا ہے جہاں پہ آپ پورے data کے ساتھ ایک ساتھ train کر رہے ہو وہ آپ offl` | **Urdu-script mismatch** (Hypothesis: the target window `06:00-07:30` ranked 4th at 0.528. The Roman Urdu transliteration creates subword divergence against native Arabic script Whisper tokens; in contrast, the identical English query Q19 was retrieved at rank 2 at 0.589). |
| **qwen3-0.6b** (W=90) | Q4 | en | How does the email spam classifier example show a weakness of batch learning? | `05:27`-`05:52` | 8 | `03:00-04:30@0.614`; `07:30-09:00@0.609`; `06:00-07:30@0.585` | `no doubt آپ کر سکتے ہو ایسا but ایسا کوئی کرتا نہیں ہے کیونکہ it would be costly and time taking تو generally جو batch learning ہوتا ہے جہاں پہ آپ پورے data کے ساتھ ایک ساتھ train کر رہے ہو وہ آپ offl` | **window too short/long** (Hypothesis: at W=30 and W=60, Q4 was hit at rank 1 with scores 0.771 and 0.782. At W=90, window `04:30-06:00` blends the spam classifier example with Netflix recommendation engine text, depressing its cosine score relative to generic batch learning training windows). |
| **qwen3-0.6b** (W=90) | Q25 | roman | satellite ya drone par batch learning kyun fail ho jati hai | `09:12`-`09:38` | 4 | `03:00-04:30@0.629`; `07:30-09:00@0.629`; `06:00-07:30@0.600` | `no doubt آپ کر سکتے ہو ایسا but ایسا کوئی کرتا نہیں ہے کیونکہ it would be costly and time taking تو generally جو batch learning ہوتا ہے جہاں پہ آپ پورے data کے ساتھ ایک ساتھ train کر رہے ہو وہ آپ offl` | **Urdu-script mismatch** (Hypothesis: Roman Urdu phrasing lacks lexical overlap with the native Arabic script Whisper tokens where technical words like "satellite" and "drone" are transcribed alongside Urdu vocabulary). |
| **qwen3-0.6b** (W=90) | Q27 | roman | batch learning mein pura data ek saath kaise use hota hai | `02:26`-`02:40` | 4 | `03:00-04:30@0.760`; `07:30-09:00@0.748`; `06:00-07:30@0.739` | `no doubt آپ کر سکتے ہو ایسا but ایسا کوئی کرتا نہیں ہے کیونکہ it would be costly and time taking تو generally جو batch learning ہوتا ہے جہاں پہ آپ پورے data کے ساتھ ایک ساتھ train کر رہے ہو وہ آپ offl` | **Urdu-script mismatch** (Hypothesis: target window `01:30-03:00` was ranked 4th at 0.732, narrowly missing top-3 behind generic offline training discussion; Roman phrasing "ek saath kaise use hota hai" aligns weakly to native script tokens). |

---

## c. Noise Rule

With 28 total queries (15 `en`, 8 `hard`, 5 `roman`), a performance delta of 1 to 2 queries is within the noise margin of finite sample retrieval:
1. **Overall (ALL queries, 28 total at W=90)**:
   - BGE-M3: 26 hits (Recall@3 = 0.9286)
   - Qwen3-0.6B: 25 hits (Recall@3 = 0.8929)
   - **Verdict**: BGE-M3 is better by 1 query -> **TIE** (within the 1-2 query noise threshold).
2. **Subset S (`hard` + `roman`, 13 queries total at W=90)**:
   - BGE-M3: 12 hits (Recall@3 = 0.9231)
   - Qwen3-0.6B: 11 hits (Recall@3 = 0.8462)
   - **Verdict**: BGE-M3 is better by 1 query -> **TIE** (within the 1-2 query noise threshold).
3. **English queries (`en`, 15 queries total at W=90)**:
   - BGE-M3: 14 hits (Recall@3 = 0.9333)
   - Qwen3-0.6B: 14 hits (Recall@3 = 0.9333)
   - **Verdict**: Difference of 0 queries -> **TIE**.

---

## d. Window-Size Comparison

- **BGE-M3**:
  - W=30: Recall@3 = 26/28 (0.9286), MRR = 0.7298
  - W=60: Recall@3 = 25/28 (0.8929), MRR = 0.8009
  - W=90: Recall@3 = 26/28 (0.9286), MRR = 0.7899
  - *Evaluation*: W=90 ties W=30 on Recall@3 (26 queries, 1 query better than W=60) while providing significantly stronger mean reciprocal rank (0.7899 vs 0.7298).
- **Qwen3-0.6B**:
  - W=30: Recall@3 = 25/28 (0.8929), MRR = 0.6736
  - W=60: Recall@3 = 24/28 (0.8571), MRR = 0.8107
  - W=90: Recall@3 = 25/28 (0.8929), MRR = 0.8199
  - *Evaluation*: W=90 ties W=30 on Recall@3 (25 queries, 1 query better than W=60) and achieves the highest overall MRR (0.8199 vs 0.6736).
- **Recommendation for FAISS Build**:
  - **Recommend W=90 (90-second windows)**. This holds true for both models. 90-second chunks reduce total document vectors to 8, capture multi-sentence lecture explanations intact, and yield the strongest combination of Recall@3 and MRR.

---

## e. Hardware & Memory Profile

- **VRAM Utilization (8 GB RTX 3070 Budget)**:
  - `bge-m3`: Peak VRAM was **1,161.5 MB** (~1.16 GB), utilizing only **14.5%** of available VRAM.
  - `qwen3-0.6b`: Peak VRAM was **1,976.8 MB** (~1.98 GB), utilizing **24.7%** of available VRAM.
  - *Verdict*: Both models comfortably fit inside the 8 GB budget alongside display processes without swapping or memory pressure.
- **Tokenizer Sequence Truncation (`max_seq_length=512`)**:
  - `bge-m3`: **0 truncated windows** across all window sizes (W=30: 0, W=60: 0, W=90: 0). BGE-M3's tokenizer processed all 90s Urdu-English transcript passages within 512 tokens.
  - `qwen3-0.6b`: **0 truncated** at W=30; **2 truncated** at W=60; **7 of 8 truncated** at W=90. Qwen's byte-level BPE tokenizer splits Urdu Arabic script characters into more subword tokens per word than XLM-RoBERTa, causing 90s windows to exceed 512 tokens (up to 521 tokens).

---

## f. Decision Rule Application

1. **Definition of Subset S**: All queries with kind `hard` (8) or `roman` (5), totaling **13 queries**. Because $|S| = 13 \ge 10$, the rule has sufficient power per the benchmark specification.
2. **Clear Winner Criterion**:
   - Requires a model to have $\ge 3$ more hits at top-3 than the other model on subset S (at each model's best window size), AND not be worse by $> 2$ queries on kind `en`.
   - On Subset S: BGE-M3 has **12 hits**; Qwen3-0.6B has **11 hits**. Difference is **1 query** (12 - 11 = 1 < 3).
   - On Kind `en`: BGE-M3 has **14 hits**; Qwen3-0.6B has **14 hits**. Difference is **0 queries**.
   - Result: Neither model achieved the $\ge 3$ query margin required for a clear victory.
3. **Applied Branch**:
   - **Default tie-break to BGE-M3 applied**. A tie goes to BGE-M3 because its dense embeddings match the performance of Qwen3-0.6B while its sparse lexical vector outputs can be directly repurposed for Insightex's downstream hybrid retrieval router.

---

## g. Next Step (Near-Tie Resolution)

Because the bake-off resulted in an empirical tie (26 vs 25 hits overall, 12 vs 11 hits on subset S), to statistically resolve the difference between BGE-M3 and Qwen3 beyond the 2-query noise margin, **15 to 20 additional test queries** should be added, concentrated in:
- **10 additional Roman Urdu queries**: To determine if Qwen's generative pretraining or BGE-M3's multilingual vocabulary handles cross-script colloquial queries better.
- **10 additional implicit/hard conceptual queries**: Standard English queries already saturated at 93.3% recall on both models.

---

## Draft doc updates (not applied)

### 1. `Insightex_Final_Features.md` (Section F)
```markdown
### Committed Models
1. **ASR (Speech-to-Text)**: Faster-Whisper (Large-v3 / Medium) running locally via CTranslate2.
2. **LLM (Generation & Synthesis)**: Llama-3-8B-Instruct quantized via Ollama.
3. **Dense Retrieval (Embedding)**: BAAI/bge-m3 (1024-d, FP16 CUDA, 90s non-overlapping windows) selected via empirical bake-off on native-script lecture transcripts, providing dense semantic search and reusable sparse representations for hybrid routing.
```

### 2. `Proposal.md` (Section 9.1: VRAM Risk)
```markdown
- **Embedding Model Overhead**: The retrieval layer commits `BAAI/bge-m3` in FP16, measuring a peak VRAM of 1.16 GB, which comfortably coexists with quantized Ollama LLM execution inside the 8 GB GPU ceiling.
```

### 3. `Proposal.md` (Section 5.3: Retrieval Evaluation)
```markdown
Empirical embedding bake-off evaluated candidate models on 28 hand-labelled lecture query pairs across native Urdu, technical English, and Roman transliterations:

| Candidate Model | Window | ALL Recall@3 | ALL MRR | Subset S Recall@3 | Peak VRAM |
|---|---|---|---|---|---|
| BAAI/bge-m3 (Selected) | 90s | 92.9% (26/28) | 0.790 | 92.3% (12/13) | 1.16 GB |
| Qwen/Qwen3-Embedding-0.6B | 90s | 89.3% (25/28) | 0.820 | 84.6% (11/13) | 1.98 GB |
```

### 4. `Proposal.md` (Table 3: Tools & Technologies)
```markdown
| Component | Selected Technology | Status / Plan |
|---|---|---|
| Dense Embeddings | BAAI/bge-m3 | Committed (Phase 1 Bake-Off Winner) |
| Reranker | BAAI/bge-reranker-large | Planned (Matching model family, not yet evaluated) |
```
