# Insightex: OCR / PaddleOCR-VL Evaluation Report

**Date:** 1 October 2026
**Project:** Insightex (FYP), optional visual pipeline
**Status:** Feasibility check complete. PaddleOCR-VL is **viable but unproven** on lecture content. No commitment to the Baseline.

---

## 1. What we are doing

We are testing whether **PaddleOCR-VL** (a 0.9B vision-language document parser) can read equations, text and layout from lecture frames, and whether it fits our hardware. It is a candidate upgrade for the **optional visual pipeline** (scene-change detection + OCR), which sits behind the `visual.enabled` flag.

This report covers one experiment: set up PaddleOCR-VL, run it on one equation-heavy frame, and measure speed, memory, output format and stability.

## 2. Why we are doing it

- **Scope decision (defense, 30 Sep 2026):** the panel advised against promising both pipelines. The **ASR pipeline is the committed Baseline**. The visual pipeline and Feature 13 (OCR-confidence legibility flag) are **Optional**: time-boxed, never blocking a Baseline milestone.
- **Open question from the roadmap:** standard PaddleOCR (PP-OCR) is a text-line engine. It does not turn equations into structure. PaddleOCR-VL claims to recognise text, tables and formulas (as LaTeX), so we needed to know whether it is worth the extra compute and setup cost.
- **Unknown to settle:** the VRAM cost on an RTX 3070 (8 GB) was never measured, and Proposal Section 4.2's "mathematical notation" wording needs real evidence behind it or should be softened.

## 3. What we are using

| Item | Detail |
|---|---|
| GPU / RAM | NVIDIA RTX 3070 (8 GB VRAM), 32 GB system RAM |
| OS | Windows, with WSL2 distro `Ubuntu-24.04` |
| Python env | `~/envs/paddleocr-vl` (Python 3.12.3), separate from the Whisper/Ollama stacks |
| Packages | `paddlepaddle-gpu` 3.2.1 (cu126 build), `paddleocr` 3.7.0, `paddlex` 3.7.2 |
| Models (in `~/.paddlex`, about 2.0 GB) | `PaddleOCR-VL-1.6`, `PP-DocLayoutV3` (layout detection) |
| Driver | 616.64, CUDA UMD 13.4 (the `cu126` Paddle build ran fine on it) |
| Test input | `E:\FYP\data\frames\eq1.png`, one frame showing the quadratic formula |
| Tooling | Antigravity IDE agent ran the probe script; results saved in `E:\FYP\data\frames\out\` |
| Probe code | `E:\FYP\tools\vl_probe\` (`probe.py`, `run_probe.ps1`) |

**Storage rule:** everything for the project lives under `E:\FYP`, except globally installed tools such as FFmpeg.

| What | Location |
|---|---|
| WSL Ubuntu disk (`ext4.vhdx`, about 1.4 GB at move time) | `E:\FYP\wsl\Ubuntu-24.04\` |
| Hugging Face, pip and torch caches (Windows) | `E:\FYP\cache\` (set via `HF_HOME`, `PIP_CACHE_DIR`, `TORCH_HOME`) |
| Windows `.paddlex` and `.cache\paddle` | Junctions pointing into `E:\FYP\cache\` |
| Ollama models | Moved to E: (Qwen 3.5) |
| PaddleOCR-VL weights (inside Ubuntu) | Inside the vhdx, therefore on E: |

The probe run did not grow anything on C:.

## 4. How we did it

1. Moved the Ubuntu distro to E: (`wsl --manage ... --move`) and relocated the model caches.
2. Created a separate Python venv inside Ubuntu, installing `setuptools`, then PaddlePaddle (GPU), then `paddleocr[doc-parser]`.
3. Confirmed the GPU is usable with `paddle.utils.run_check()`.
4. Ran a probe script on one frame: load time, two inference calls in one process, exports (JSON, Markdown, annotated image), and a recursive dump of every output field.
5. Sampled `nvidia-smi` memory every 500 ms during runs, and read Paddle's own allocator counters (`max_memory_allocated`, `max_memory_reserved`).
6. Tried allocator caps (`FLAGS_fraction_of_gpu_memory_to_use`) to find the real memory need.
7. The equation output was checked **by the team member against the image** (not just by the agent).

## 5. What we tested

- GPU readiness (`run_check()`).
- Cold start (first run, weights download) and warm start (cached weights).
- Per-frame inference time.
- VRAM behaviour: `nvidia-smi` peak and Paddle allocator counters.
- Output structure: text, LaTeX, boxes, scores.
- Recognition accuracy on **one** display-formula frame.
- Stability across repeated and back-to-back runs.
- Whether anything landed on C:.

## 6. Results

### 6.1 GPU check
`run_check()` reported *"PaddlePaddle works well on 1 GPU."* A `libcuda.so` warning appeared in the same output, but the GPU path worked, so treat it as noise on WSL.

### 6.2 Speed

| Run | Load (s) | Inference call 1 (s) | Inference call 2 (s) |
|---|---|---|---|
| 1, cold (weights download) | 404.7 | 6.25 | 2.83 |
| 2, warm | 3.6 | 4.14 | 3.41 |

The 405 s on run 1 was the one-time download. Warm, loading takes about 4 s and a frame takes **about 3 to 4 s**.

### 6.3 Memory

| Measure | Value |
|---|---|
| Idle VRAM with desktop apps open | about 1.5 to 1.9 GB |
| Idle VRAM with nothing running | about 0.5 GB |
| `nvidia-smi` peak during inference | about 7,950 to 8,000 MiB (looks like "the whole card") |
| **`max_memory_allocated`** (what the model actually used) | **about 3,097 MiB** |
| `max_memory_reserved` (what Paddle's allocator held) | about 7,141 MiB |
| After the process exits | VRAM returns to baseline |

**Reading:** the near-full-card reading is Paddle's allocator reserving free memory. The working need was about **3.1 GB for one frame**. The allocator cap flags had **no visible effect** (runs with 0.92 and 0.5 gave identical counters), so we could not force a smaller footprint, and we did not need to.

### 6.4 Output format
- **Recognised content:** `\frac{-b\pm\sqrt{(b^{2}-4ac)}}{2a}` as a display formula (Markdown `$$ ... $$`), block label `display_formula`.
- **Geometry:** bounding box `[47, 94, 420, 275]`, polygon points and reading order.
- **Exports that worked:** JSON, Markdown, annotated layout image.
- **Confidence:** the only score anywhere is the **layout detector's score (0.53)** on the formula region. There is **no per-block or per-token recognition confidence**. The 0.53 was attached to a *correct* result, so it is not a usable correctness signal.

### 6.5 Accuracy
The formula was **recognised correctly** (checked by the team member against the source image). This is **one clean, printed display formula**. It says nothing yet about messy slides, handwriting or diagrams.

### 6.6 Stability
- **Run 2 (first attempt) hung:** 25+ minutes at 100% CPU while GPU utilisation was about 2%. It was started right after run 1, while the GPU still held about 8 GB. WSL logged `dxgkio_make_resident: Ioctl failed: -12` (out of memory). Killing the process cleared it, and the re-run worked (load 3.6 s).
- **Run (c) hung again:** timed out at 600 s with no stage log, so **the cause is unknown**. It repeated the same symptom (about 7,967 MiB held, no result) even though the script was meant to wait for the GPU to be free. The back-to-back explanation is therefore **not confirmed**.
- Observed: **2 hangs in about 5 runs**, both with the process holding nearly the whole card.

### 6.7 Storage
Nothing new landed on C:. `~/.paddlex` holds about 2.0 GB and the Ubuntu `~/.cache` about 3.9 GB, both inside the vhdx on E:.

## 7. Risks

| Risk | Detail | Mitigation |
|---|---|---|
| **Intermittent hang** | 2 of about 5 runs hung, cause unknown | Run PaddleOCR-VL as a separate subprocess with a hard timeout (about 120 s per frame, one retry); wait for VRAM below about 800 MiB between runs |
| **Allocator takes the whole card** | Paddle reserves about 7 GB even though it needs about 3 GB; could clash with anything else on the GPU | Run it alone (load, process, unload); close other GPU apps for measurements; check once with normal desktop apps open |
| **Tiny sample** | One printed formula | Run the 30-frame bake-off before any claim |
| **No lecture benchmark** | Built for document pages, not lecture frames or screen recordings | Measure on our own frames |
| **No recognition confidence** | Feature 13 cannot use PaddleOCR-VL scores | If Feature 13 is built, take confidence from the standard PP-OCR path |
| **Conceptual diagrams** | Charts are supported (bar, line, pie); conceptual diagrams are not | State as a limitation |
| **Scope creep** | Visual side is Optional; a large parallel effort risks the over-promising the panel flagged | Fixed time box with a stop rule |
| **Version drift** | Install pins came from late-2025 docs; they worked, but newer releases exist | Record the exact working versions (Section 3) |
| **Setup friction** | WSL + GPU passthrough, separate envs, large first download | Documented here; setup is now done |

## 8. What to note

- **Nothing here touches the Baseline.** ASR, retrieval evaluation and the user study do not depend on PaddleOCR-VL.
- **The committed build is audio plus a frame grabbed at the cited timestamp** (Feature 6). State the limitation openly: equations spoken but not read aloud, or shown only on screen, will not reach the graph without the visual pipeline.
- **Not tested:** tables, charts, whiteboard or handwriting, notebook screens, Urdu-script on-screen text, the standard PP-OCR models on the same frame, PaddleOCR-VL running alongside Ollama, and the effect of other GPU apps on its stability.
- **Wording to adjust in the Proposal:** Section 4.2 refers to "mathematical notation". Standard PP-OCR is a text-line engine. Soften the wording, or tie it to this result.
- **Procedure rule:** wait for VRAM to fall below about 800 MiB between GPU runs, and run every experiment under a timeout.
- **The recorded cap experiment shows no effect.** Do not claim a "smallest working cap".

## 9. Recommendation

1. **Committed build:** audio plus frame-at-timestamp. No visual pipeline needed.
2. **Optional track, baseline:** standard PP-OCR (v5/v6) behind `visual.enabled` for plain text.
3. **Optional track, upgrade (gated):** PaddleOCR-VL, only for equation- or table-heavy frames, run as a timed-out subprocess.
4. **Gate before adopting it:** a bake-off on about 30 frames (text slides, equations, diagrams, whiteboard, notebook screens), comparing PP-OCR, PaddleOCR-VL and optionally a small general VLM. Use the Proposal Section 5.2 metrics plus a manual "was the concept captured?" check. Adopt PaddleOCR-VL only if it clearly wins on equations, stays stable, and fits inside the VRAM rotation.
5. **Timing:** start the bake-off only after ASR validation, retrieval evaluation and the user study are on track.

## 10. Open items

- [ ] Cause of the intermittent hang (needs stage logging in the probe).
- [ ] One run with normal desktop apps open, to confirm it still completes.
- [ ] The 30-frame bake-off (gated, see Section 9).
- [ ] Soften Proposal Section 4.2 wording.
- [ ] Next Baseline decision: the embedding bake-off (BGE-M3 vs Qwen3-Embedding-0.6B) on the labelled retrieval pairs.

## Appendix: raw files

All raw outputs are in `E:\FYP\data\frames\out\`: `REPORT.md` (agent log), `eq1.md`, `eq1_res.json`, `eq1_layout_det_res.png`, `key_inventory.txt`, and the `vram_run*.csv` samples.
