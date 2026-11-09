# C4 context block and budget check (ADR-0048 Amendment 2 and Amendment 10), 9 Nov 2026

**Draft block:** `config/prompts/m7_context_block_v1.txt`, sha256 `3132e2f93793cb338e27aff1de23ae6e4de4c12bfc90119bab5bef553c47912e`. It is **not frozen yet**: it is frozen after Bilal's approval, before any C4 run.

- **Gold overlap:** no 3-, 4- or 5-word sequence is shared with the 20 gold windows (`overlap_m7_context_block_v1.txt`).
- **No reply test** (Amendment 10, decision 5): no model output was produced for any window.

**System messages** (computed by building requests; no model call):

| Arm | System message | sha256 |
|---|---|---|
| A, `C4-window` (no context) | frozen prompt instructions | `f2d8742f5155f1d1afef4ebc0324cfb0108a05de97185ff2167e4d30bac1a35f` (as C1–C3) |
| B, `C4-previous` (with context) | frozen prompt instructions + blank line + block v1 | `57536dad3a45b66ea5e9aa956c84c0f8f8dfb211cc40f072eca300b8b84ad68e` |

**Budget check:** `extract-eval measure --model gemma4:e4b --k 1 --context both --context-block-file <draft>`.
- **Setup:** `num_ctx` 8192, Gemma digest `dc35e8d9c606…`, Ollama 0.40.2.
- **The worst case:** each case is a retry call with errors at the 1,500-character cap.
- **Report:** `docs/measurements/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/gemma4_e4b_20261109T142239Z.json`.

| Case | Target (context) | Real prompt tokens | + `num_predict` | Total / 8,192 | Margin | Gate (scale 0.761) | `ollama ps` | VRAM above baseline (peak, baseline) | Result |
|---|---|---|---|---|---|---|---|---|---|
| Without context | 18 (largest window) | 2,360 | 1,024 | 3,384 | 4,808 | allows | 100% GPU | 4,759 MiB (7,462, 2,703) | PASS |
| **With context** | **21 (20)** | **2,760** | **1,024** | **3,784** | **4,408** | allows; no refusal of a real fit | 100% GPU | **4,765 MiB** (7,462, 2,697) | **PASS** |

- **The worst pair:** the measure tool picks "the largest window with its previous window". To confirm that this is the largest window-plus-previous pair, every target's retry prompt with its previous window was estimated, with no model call. Target 21 with window 20 is the largest (estimate 3,097; next are 11 and 19, at 3,075 and 3,072).
- **Context cost:** the block and the previous window add 400 real tokens at the worst case.
- **Residency** (ADR-0049 decision 6): the VRAM above baseline (4,765 MiB) matches the C1 Gemma run (4,828) and the C3 k check (4,783). Nothing indicates that layers left the GPU.
  - Today's desktop baseline is 2,697 MiB, so the whole-GPU peak (7,462 MiB) leaves about 730 MiB free on the 8 GB card. It is comparable across days only above baseline.
