# PaddleOCR-VL Benchmark & Verification Report

## Environment
- **Host GPU:** NVIDIA GeForce RTX 3070 (8192 MiB VRAM, 8.0 GB dedicated)
- **NVIDIA Driver / CUDA:** Driver 616.64, CUDA UMD 13.4, Runtime API 12.6
- **Operating System:** Windows 11 with WSL2 (Distro: `Ubuntu-24.04`, disk located on `E:`)
- **Python Version:** 3.12.3 (inside `~/envs/paddleocr-vl`)
- **Installed Packages:**
  - `paddlepaddle-gpu`: 3.2.1 (cu126 build)
  - `paddleocr`: 3.7.0
  - `paddlex`: 3.7.2
- **Baseline Idle VRAM (Step 1):** `1600 MiB` (queried via `nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits`)

---

## run_check() result (verbatim)
```
/home/bilal_aamir/envs/paddleocr-vl/lib/python3.12/site-packages/paddle/utils/cpp_extension/extension_utils.py:718: UserWarning: No ccache found. Please be aware that recompiling all source files may be required. You can download and install ccache from: https://github.com/ccache/ccache/blob/master/doc/INSTALL.md
  warnings.warn(warning_message)
/home/bilal_aamir/envs/paddleocr-vl/lib/python3.12/site-packages/paddle/pir/math_op_patch.py:219: UserWarning: Value do not have 'place' interface for pir graph mode, try not to use it. None will be returned.
  warnings.warn(
I1001 13:04:01.395424  4169 pir_interpreter.cc:1524] New Executor is Running ...
W1001 13:04:01.395522  4169 gpu_resources.cc:114] Please NOTE: device: 0, GPU Compute Capability: 8.6, Driver API Version: 13.4, Runtime API Version: 12.6
W1001 13:04:01.396395  4169 dynamic_loader.cc:425] The third-party dynamic library (libcuda.so) that Paddle depends on is not configured correctly. (error code is libcuda.so: cannot open shared object file: No such file or directory)
  Suggestions:
  1. Check if the third-party dynamic library (e.g. CUDA, CUDNN) is installed correctly and its version is matched with paddlepaddle you installed.
  2. Configure third-party dynamic library environment variables as follows:
  - Linux: set LD_LIBRARY_PATH by `export LD_LIBRARY_PATH=...`
  - Windows: set PATH by `set PATH=XXX;%PATH%`
  - Mac: set  DYLD_LIBRARY_PATH by `export DYLD_LIBRARY_PATH=...` [Note: After Mac OS 10.11, using the DYLD_LIBRARY_PATH is impossible unless System Integrity Protection (SIP) is disabled.]
I1001 13:04:01.396791  4169 pir_interpreter.cc:1547] pir interpreter is running by multi-thread mode ...
Running verify PaddlePaddle program ... 
PaddlePaddle works well on 1 GPU.
PaddlePaddle is installed successfully! Let's start deep learning with PaddlePaddle now.
```

---

## Timings: load / inference call 1 / inference call 2, for run 1 and run 2

| Run | Type | Load Time (s) | Inference Call 1 (Warm-up) (s) | Inference Call 2 (Steady State) (s) |
|---|---|---|---|---|
| **Run 1** | Cold start (weights download) | 404.6577 | 6.2508 | 2.8333 |
| **Run 2** | Warm start (local disk cache) | 3.6086 | 4.1390 | 3.4090 |

---

## VRAM: baseline, peak, peak minus baseline, for run 1 and run 2

*Note: BASELINE is recorded as 1600 MiB (Step 1 preflight). Initial sampler levels prior to probe start were 1530 MiB (Run 1) and 551 MiB (Run 2).*

| Run | Baseline VRAM (MiB) | Post-Load / Pre-Inference VRAM (MiB) | Peak VRAM (MiB) | Peak minus BASELINE (1600 MiB) | Peak minus Run Initial VRAM |
|---|---|---|---|---|---|
| **Run 1** | 1530 | 7994 | 7998 | +6398 | +6468 |
| **Run 2** | 551 | 7969 | 7979 | +6379 | +7428 |

---

## Output fields
- **Export Methods Tested:**
  - `r.print()`: Supported (prints result dictionary and layout details)
  - `r.save_to_json(save_path=OUT)`: Supported & succeeded (`eq1_res.json`)
  - `r.save_to_markdown(save_path=OUT)`: Supported & succeeded (`eq1.md`)
  - `r.save_to_img(save_path=OUT)`: Supported & succeeded (`eq1_layout_det_res.png`)

- **Text & LaTeX Content:**
  - `res.parsing_res_list[0].block_content` -> `str`: `' $$ \\frac{-b\\pm\\sqrt{(b^{2}-4ac)}}{2a} $$ '`
  - `res.parsing_res_list[0].block_label` -> `str`: `'display_formula'`

- **Bounding Boxes & Polygon Coordinates:**
  - `res.parsing_res_list[0].block_bbox` -> `list[int]`: `[47, 94, 420, 275]`
  - `res.parsing_res_list[0].block_polygon_points` -> `list[list[float]]`: `[[47.0, 94.0], [420.0, 94.0], [420.0, 275.0], [47.0, 275.0]]`
  - `res.layout_det_res.boxes[0].coordinate` -> `list[int]`: `[47, 94, 420, 275]`
  - `res.layout_det_res.boxes[0].polygon_points` -> `list[list[float]]`: `[[47.0, 94.0], [420.0, 94.0], [420.0, 275.0], [47.0, 275.0]]`

- **Confidence / Score Signals:**
  - `res.layout_det_res.boxes[0].score` -> `float`: `0.531929612159729`
  - **Explicit Confidence Assessment:**
    **There is NO per-block or per-line OCR/recognition confidence score or token probability.** The only confidence signal present in the entire result object is the layout-detection block classification score (`0.531929612159729` under `res.layout_det_res.boxes[0].score`). The vision-language recognition output (`res.parsing_res_list`) contains no confidence values.

---

## Formula correctness
*(Agent judgement, NOT ground truth)*

- **Input Image:** Quadratic formula with multi-colored symbols:
  Numerator: `$-b \pm \sqrt{(b^2 - 4ac)}$` over division line, denominator `$2a$`.
- **Recognised LaTeX Output:**
  ```latex
  $$ \frac{-b\pm\sqrt{(b^{2}-4ac)}}{2a} $$
  ```
- **Evaluation & Symbol Comparison:**
  - Fraction construction `\frac{...}{...}` correctly established.
  - Numerator `-b`: correctly recognized (blue `-b` captured with leading minus).
  - Plus-minus `\pm`: correctly recognized.
  - Radical `\sqrt{...}`: correctly established over the entire parenthetical expression `(b^2 - 4ac)`.
  - Inner terms: `(b^{2}-4ac)` accurately transcribed (superscript `2`, subtraction sign `-`, coefficients and variables `4ac`, parentheses preserved).
  - Denominator: `2a` correctly recognized.
- **Wrong / Missing / Hallucinated Symbols:**
  None observed. In my judgement, the formula was transcribed completely accurately.

---

## Warnings and errors seen
1. `UserWarning: No ccache found. Please be aware that recompiling all source files may be required.` (from `extension_utils.py`)
2. `UserWarning: Value do not have 'place' interface for pir graph mode, try not to use it. None will be returned.` (from `pir/math_op_patch.py`)
3. `W1001 13:04:01.396395 4169 dynamic_loader.cc:425] The third-party dynamic library (libcuda.so) that Paddle depends on is not configured correctly. (error code is libcuda.so: cannot open shared object file: No such file or directory)`
4. `Warning: Non compatible API. Please refer to .../torch/torch.split.html first.` (from `decorator_utils.py`)
5. `UserWarning: To copy construct from a tensor, it is recommended to use sourceTensor.clone().detach(), rather than paddle.to_tensor(sourceTensor).` (from `tensor/creation.py`)
6. `Warning: Non compatible API. Please refer to .../torch/torch.max.html first.` (from `decorator_utils.py`)
7. `Bucketed engine_config has no entry for resolved engine 'paddle_dynamic'; using an empty config for that engine.`
8. In WSL `dmesg`: `misc dxg: dxgk: dxgkio_make_resident: Ioctl failed: -12` (-ENOMEM). Due to the ~7,998 MiB VRAM footprint, running back-to-back processes without letting the DirectX WDDM memory manager unmap previous allocations led to memory exhaustion until prior allocations were fully garbage-collected by the OS.

---

## Disk usage and whether anything landed on C:
- **WSL Disk Usage:**
  - `~/.paddlex`: `2.0G` (`official_models` has `PP-DocLayoutV3` and `PaddleOCR-VL-1.6`; `fonts` has `PingFang-SC-Regular.ttf`)
  - `~/.cache`: `3.9G` (pre-existing pip cache + 412K huggingface cache)
  - Ubuntu-24.04 VHDX is situated on `E:`.
- **Windows Profile (`C:\Users\Bilal Aamir`):**
  - Initial `C:\Users\Bilal Aamir\.paddlex`: 300.94 MB (LastWriteTime: 10/1/2026 11:47:04 AM)
  - Post-run `C:\Users\Bilal Aamir\.paddlex`: 300.94 MB (LastWriteTime: 10/1/2026 11:47:04 AM) — **Unchanged**
  - Initial `C:\Users\Bilal Aamir\.cache`: 468.03 MB (LastWriteTime: 10/1/2026 11:46:19 AM)
  - Post-run `C:\Users\Bilal Aamir\.cache`: 468.03 MB (LastWriteTime: 10/1/2026 11:46:19 AM) — **Unchanged**
  - **New Folders on C:** **None**. Zero files or folders landed on C:.

---

## Open questions / anything unexpected
1. **Severe VRAM Headroom Constraint (7,998 MiB peak on 8,192 MiB GPU):**
   Paddle's allocator reserves about 7.1 GB but actually allocates about 3.1 GB (max_memory_allocated 3096.67 MiB)
2. **Missing Recognition Confidence:**
   PaddleOCR-VL does not expose a confidence score for the generated text/LaTeX formula. The only confidence score available is for layout box classification (`score: 0.5319`). Downstream pipelines requiring validation or thresholding on formula recognition confidence will not have an explicit numerical confidence metric from PaddleOCR-VL.
3. **WSL2 Driver Memory Deallocation Lag:**
   Immediately starting a new process after one finishes can trigger `dxgkio_make_resident: -12` because the Windows/WSL2 virtualization layer takes several seconds to release physical GPU memory back to the global pool.

---

## Real VRAM need

| Run | Cap | Success/Fail | max_memory_allocated (MiB) | max_memory_reserved (MiB) | nvidia-smi peak (MiB) |
|---|---|---|---|---|---|
| **(a)** | Uncapped (`FLAGS_fraction_of_gpu_memory_to_use=0.92`, `FLAGS_allocator_strategy=auto_growth`) | Success | 3096.67 | 7141.22 | 7966 |
| **(b)** | `FLAGS_fraction_of_gpu_memory_to_use=0.5`, `FLAGS_allocator_strategy=auto_growth` | Success | 3096.67 | 7141.22 | 7954 |
| **(c)** | `FLAGS_fraction_of_gpu_memory_to_use=0.35`, `FLAGS_allocator_strategy=auto_growth` | Timed out at 600 s, cause unknown (no stage log); cap had no visible effect on reserved memory | N/A | N/A | 7967 |


