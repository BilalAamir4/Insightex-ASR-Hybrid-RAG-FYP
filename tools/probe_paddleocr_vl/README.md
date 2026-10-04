# tools/probe_paddleocr_vl

**Purpose:** Feasibility probe for PaddleOCR-VL: construction, latency, Paddle memory, JSON/LaTeX export on one frame.

**How to run:** From Windows: `scripts/windows/run_probe.ps1 -RunLabel <label>` (polls VRAM, runs probe.py in WSL under `~/envs/paddleocr-vl` with a 600 s timeout, samples nvidia-smi). Direct: activate `~/envs/paddleocr-vl` and run `python probe.py`. GPU job; one at a time.

**Inputs:** `$INSIGHTEX_DATA/eval/frames/eq1.png`.

**Outputs:** `$INSIGHTEX_DATA/eval/frames/out/` (eq1.md, eq1_res.json, layout overlay, `vram_run*.csv`). Write-up: `docs/reports/OCR_report.md`.

**Status:** Feasibility probe done on one frame; 2 of 5 runs hung (allocator). The 30-frame bake-off that gates adoption is pending.

Standalone tool: it must not import from `backend/`.
