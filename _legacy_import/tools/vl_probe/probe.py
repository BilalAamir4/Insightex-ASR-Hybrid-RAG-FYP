import os
import sys
import time
import json

def format_val_preview(val, max_len=120):
    s = repr(val)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s

def walk_keys(node, path=""):
    if isinstance(node, dict):
        if not node:
            yield (path, "dict (empty)", "{}")
        for k, v in node.items():
            subpath = f"{path}.{k}" if path else str(k)
            if isinstance(v, dict):
                yield from walk_keys(v, subpath)
            elif isinstance(v, list):
                if not v:
                    yield (f"{subpath}[]", "list (empty)", "[]")
                else:
                    for i, item in enumerate(v):
                        item_path = f"{subpath}[{i}]"
                        if isinstance(item, (dict, list)):
                            yield from walk_keys(item, item_path)
                        else:
                            yield (item_path, type(item).__name__, item)
            else:
                yield (subpath, type(v).__name__, v)
    elif isinstance(node, list):
        if not node:
            yield (path, "list (empty)", "[]")
        for i, item in enumerate(node):
            item_path = f"{path}[{i}]"
            if isinstance(item, (dict, list)):
                yield from walk_keys(item, item_path)
            else:
                yield (item_path, type(item).__name__, item)
    else:
        yield (path, type(node).__name__, node)

def main():
    print("=" * 60)
    print("Starting PaddleOCR-VL Real VRAM Probe")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    import paddle
    from paddleocr import PaddleOCRVL

    # Report effective flags
    target_flags = ["FLAGS_fraction_of_gpu_memory_to_use", "FLAGS_allocator_strategy"]
    try:
        flags = paddle.get_flags(target_flags)
        print(f"[PADDLE_FLAGS] Effective values: {flags}")
    except Exception as e:
        print(f"[PADDLE_FLAGS] Error reading flags: {e}")

    img_path = "/mnt/e/FYP/data/frames/eq1.png"
    out_dir = "/mnt/e/FYP/data/frames/out"
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(img_path):
        print(f"ERROR: Image not found at {img_path}")
        sys.exit(1)

    print(f"Test image: {img_path}")
    print(f"Output directory: {out_dir}")

    # Model load timing
    print("\n--- Constructing PaddleOCRVL() ---")
    t0 = time.perf_counter()
    pipeline = PaddleOCRVL()
    load_time = time.perf_counter() - t0
    print(f"[TIMING] Model load time: {load_time:.4f} s")

    # Post-load stabilization pause
    print("Post-load stabilization pause (2.0s)...")
    time.sleep(2.0)

    # Call resets if available right before warm-up call
    if hasattr(paddle.device.cuda, 'reset_max_memory_allocated'):
        try:
            paddle.device.cuda.reset_max_memory_allocated()
            print("[CUDA_MEM] reset_max_memory_allocated() succeeded")
        except Exception as e:
            print(f"[CUDA_MEM] reset_max_memory_allocated() error: {e}")

    if hasattr(paddle.device.cuda, 'reset_max_memory_reserved'):
        try:
            paddle.device.cuda.reset_max_memory_reserved()
            print("[CUDA_MEM] reset_max_memory_reserved() succeeded")
        except Exception as e:
            print(f"[CUDA_MEM] reset_max_memory_reserved() error: {e}")

    # Call 1 (warm-up)
    print("\n--- Running Inference Call 1 (Warm-up) ---")
    t1 = time.perf_counter()
    results1 = list(pipeline.predict(img_path))
    infer_time_1 = time.perf_counter() - t1
    alloc1 = paddle.device.cuda.max_memory_allocated() / (1024 * 1024)
    resv1 = paddle.device.cuda.max_memory_reserved() / (1024 * 1024)
    print(f"[TIMING] Inference call 1 (warm-up): {infer_time_1:.4f} s")
    print(f"[PADDLE_CUDA_MEM Call 1] max_memory_allocated: {alloc1:.2f} MiB | max_memory_reserved: {resv1:.2f} MiB")

    time.sleep(1.0)

    # Call 2 (steady 1)
    print("\n--- Running Inference Call 2 ---")
    t2 = time.perf_counter()
    results2 = list(pipeline.predict(img_path))
    infer_time_2 = time.perf_counter() - t2
    alloc2 = paddle.device.cuda.max_memory_allocated() / (1024 * 1024)
    resv2 = paddle.device.cuda.max_memory_reserved() / (1024 * 1024)
    print(f"[TIMING] Inference call 2: {infer_time_2:.4f} s")
    print(f"[PADDLE_CUDA_MEM Call 2] max_memory_allocated: {alloc2:.2f} MiB | max_memory_reserved: {resv2:.2f} MiB")

    time.sleep(1.0)

    # Call 3 (steady 2)
    print("\n--- Running Inference Call 3 ---")
    t3 = time.perf_counter()
    results3 = list(pipeline.predict(img_path))
    infer_time_3 = time.perf_counter() - t3
    alloc3 = paddle.device.cuda.max_memory_allocated() / (1024 * 1024)
    resv3 = paddle.device.cuda.max_memory_reserved() / (1024 * 1024)
    print(f"[TIMING] Inference call 3: {infer_time_3:.4f} s")
    print(f"[PADDLE_CUDA_MEM Call 3] max_memory_allocated: {alloc3:.2f} MiB | max_memory_reserved: {resv3:.2f} MiB")

    print("\n" + "=" * 60)
    print("SUMMARY TIMINGS & PADDLE MEMORY:")
    print(f"  Load Time:           {load_time:.4f} s")
    print(f"  Call 1 (warm-up):    {infer_time_1:.4f} s | alloc: {alloc1:.2f} MiB | reserved: {resv1:.2f} MiB")
    print(f"  Call 2 (steady):     {infer_time_2:.4f} s | alloc: {alloc2:.2f} MiB | reserved: {resv2:.2f} MiB")
    print(f"  Call 3 (steady):     {infer_time_3:.4f} s | alloc: {alloc3:.2f} MiB | reserved: {resv3:.2f} MiB")
    print("=" * 60 + "\n")

    # Result verification on results3
    for idx, r in enumerate(results3):
        print(f"\n================ Processing Result Object {idx} ================")
        try:
            r.print()
        except Exception as e:
            print(f"r.print() error: {e}")

        for method_name in ["save_to_json", "save_to_markdown", "save_to_img"]:
            try:
                method = getattr(r, method_name, None)
                if method is not None and callable(method):
                    method(save_path=out_dir)
                    print(f"SUCCESS: r.{method_name}(save_path='{out_dir}')")
            except Exception as e:
                print(f"FAILED / UNSUPPORTED: r.{method_name} error: {e}")

        # Extract blocks
        data = None
        if hasattr(r, 'json'):
            raw_json = r.json
            if callable(raw_json):
                raw_json = raw_json()
            if isinstance(raw_json, str):
                try:
                    data = json.loads(raw_json)
                except Exception:
                    pass
            elif isinstance(raw_json, dict):
                data = raw_json
        if data is None and isinstance(r, dict):
            data = dict(r)

        if data and isinstance(data, dict):
            d = data.get("res", data)
            blocks = d.get("parsing_res_list", [])
            for b_idx, block in enumerate(blocks):
                print(f"Block [{b_idx}] label='{block.get('block_label')}', bbox={block.get('block_bbox')}:")
                print(f"  Content: {block.get('block_content')}")

if __name__ == "__main__":
    main()
