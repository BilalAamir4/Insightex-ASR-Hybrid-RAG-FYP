import os
import sys
import time

try:
    import paddle
    from paddleocr import PaddleOCR
except Exception as e:
    print(f"Import error: {e}")
    sys.exit(1)

img_path = "/mnt/e/FYP/data/frames/eq1.png"

try:
    t0 = time.time()
    ocr = PaddleOCR(device="gpu", lang="en")
    init_time = time.time() - t0
    print(f"PaddleOCR initialized in {init_time:.2f}s", flush=True)
    
    t1 = time.time()
    result = ocr.ocr(img_path)
    infer_time = time.time() - t1
    print(f"PaddleOCR inference completed in {infer_time:.2f}s!", flush=True)
    if result and len(result) > 0 and result[0]:
        print(f"Extracted {len(result[0])} lines. Line 1: {result[0][0][1]}", flush=True)
    else:
        print("Empty or no text result.", flush=True)
except Exception as e:
    print(f"Execution error: {e}", flush=True)
    import traceback
    traceback.print_exc()
