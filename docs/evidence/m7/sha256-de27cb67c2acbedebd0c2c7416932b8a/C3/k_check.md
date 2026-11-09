# C3 k check (ADR-0048 section 8 and Amendment 9, decision 4), 9 Nov 2026

**Result: k = 5.** It is the largest k in 5 to 3 that passes, with a margin of 140 tokens. That is at least the 100 tokens below which Bilal would choose between 5 and 4, so `C3-batch` is set to `batch_k: 5` in `config/m7_arms.yaml`.

Measurement: `extract-eval measure --model gemma4:e4b --k 5 4 3`.
- **Setup:** frozen prompt `c7e061fc…4648`, `num_ctx` 8192, Gemma digest `dc35e8d9c606…`, Ollama 0.40.2.
- **The worst case:** each case is the retry call (first attempt plus the retry template, with errors at the 1,500-character cap) on the longest k windows of the whole lecture.
- **Report:** `docs/measurements/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/gemma4_e4b_20261109T135953Z.json`.

| k | Worst-case windows | Real prompt tokens | `num_predict` (k × 1,024) | Total / 8,192 | Margin | Gate (scale 0.761) | `ollama ps` | VRAM peak (above baseline) | Result |
|---|---|---|---|---|---|---|---|---|---|
| 5 | 10, 16, 18, 20, 21 | 2,932 | 5,120 | 8,052 | **140** | allows; no refusal of a real fit | 100% GPU | 7,112 MiB (4,783) | PASS |
| 4 | 10, 18, 20, 21 | 2,796 | 4,096 | 6,892 | 1,300 | allows | 100% GPU | 7,105 MiB (4,760) | PASS |
| 3 | 18, 20, 21 | 2,655 | 3,072 | 5,727 | 2,465 | allows | 100% GPU | 7,104 MiB (4,764) | PASS |

- **The margin is a bound on the worst case.** C3's real batches (1, 2, 4, 6, 7), (8–12), (13–17) and (18–22) cannot have more text than the five longest windows of the lecture, and a real retry's error text is capped at the same 1,500 characters. So no real C3 call has a longer prompt than the measured one, and every margin is at least 140 tokens. The real token counts are not computed per batch here, so this bound is the figure recorded.
- **Output used:** the worst-case k = 5 reply used 282 of its 5,120 output tokens.
- **Residency** (ADR-0049 decision 6): `ollama ps` alone is not evidence for Gemma. The peak above baseline (4,783 MiB at k = 5) matches the C1 Gemma run (4,828 MiB above baseline), so all layers were on the GPU.
  - Today's desktop baseline is higher: 2,329 MiB, against 1,520 at C1. So the whole-GPU peak (7,112 MiB) is not comparable with the 6,198 MiB reference.
  - Headroom on the 8 GB card at the peak is about 1,080 MiB.
- **Same as 18 Oct:** the real prompt counts equal the 18 Oct 2026 measurement exactly (2,932 / 2,796 / 2,655), with the same prompt, digest and windows.
