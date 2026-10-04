#!/usr/bin/env python3
"""
embed_bakeoff.py - Embedding-model bake-off evaluation script for Insightex.
Compares candidate embedding models on lecture transcript windows using FAISS retrieval.
"""

import argparse
import csv
import gc
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

# Constant query-side instruction for Qwen3-Embedding
QWEN_QUERY_INSTRUCTION = (
    "Instruct: Given a question about a lecture, retrieve the lecture transcript passage that answers it\nQuery: "
)

MODEL_REGISTRY = {
    "bge-m3": {
        "id": "BAAI/bge-m3",
        "query_prefix": "",
        "doc_prefix": "",
    },
    "qwen3-0.6b": {
        "id": "Qwen/Qwen3-Embedding-0.6B",
        "query_prefix": QWEN_QUERY_INSTRUCTION,
        "doc_prefix": "",
    },
}


@dataclass
class SRTCue:
    index: int
    start: float  # seconds
    end: float    # seconds
    text: str


@dataclass
class Window:
    window_id: int
    start_sec: float
    end_sec: float
    n_cues: int
    text: str


@dataclass
class Query:
    query_idx: int
    query: str
    start: float  # seconds
    end: float    # seconds
    kind: str


def parse_timestamp_srt(ts_str: str) -> float:
    """Parse SRT timestamp format HH:MM:SS,mmm to seconds as float."""
    ts_str = ts_str.strip().replace(" ", "")
    m = re.match(r"^(\d+):(\d{2}):(\d{2})[,.](\d{1,3})$", ts_str)
    if not m:
        raise ValueError(f"Malformed SRT timestamp: '{ts_str}'")
    hours, minutes, seconds, millis = m.groups()
    millis = millis.ljust(3, "0")[:3]
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def parse_time_str(time_str: str) -> float:
    """
    Parse query time strings such as mm:ss or h:mm:ss (or hh:mm:ss) with optional decimal.
    """
    s = time_str.strip()
    if not s:
        raise ValueError("Empty time string")

    # Split decimal if present
    dec = 0.0
    if "." in s or "," in s:
        # replace comma with dot
        s = s.replace(",", ".")
        parts = s.split(".")
        if len(parts) == 2:
            s, dec_str = parts
            dec = float("0." + dec_str)
        else:
            raise ValueError(f"Invalid decimal in time string: '{time_str}'")

    segments = s.split(":")
    if len(segments) == 2:
        minutes, seconds = segments
        if not (minutes.isdigit() and seconds.isdigit()):
            raise ValueError(f"Malformed mm:ss format: '{time_str}'")
        return int(minutes) * 60 + int(seconds) + dec
    elif len(segments) == 3:
        hours, minutes, seconds = segments
        if not (hours.isdigit() and minutes.isdigit() and seconds.isdigit()):
            raise ValueError(f"Malformed h:mm:ss format: '{time_str}'")
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + dec
    else:
        raise ValueError(f"Unrecognized time format: '{time_str}'")


def format_timestamp(seconds: float) -> str:
    """Format seconds into mm:ss format for reporting."""
    total_sec = int(round(seconds))
    mins = total_sec // 60
    secs = total_sec % 60
    return f"{mins:02d}:{secs:02d}"


def parse_srt(srt_path: str) -> List[SRTCue]:
    """
    Parse SRT file with UTF-8 BOM tolerance, multi-line cues, comma-decimal timestamps.
    Preserves text exactly without lowercasing, diacritic stripping, or transliteration.
    Normalizes only to NFC. Collapses internal newlines in a cue to a single space.
    Skips empty cues.
    """
    if not os.path.isfile(srt_path):
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    with open(srt_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    # Normalize unicode to NFC
    content = unicodedata.normalize("NFC", content)

    # Standardize newline characters
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Blocks separated by double (or more) newlines
    blocks = re.split(r"\n\s*\n", content.strip())
    cues: List[SRTCue] = []

    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        # Look for the timestamp arrow line
        arrow_idx = -1
        for idx, line in enumerate(lines):
            if "-->" in line:
                arrow_idx = idx
                break

        if arrow_idx == -1:
            continue

        # Cue index is before arrow if present
        cue_idx = len(cues) + 1
        if arrow_idx > 0 and lines[0].isdigit():
            cue_idx = int(lines[0])

        arrow_line = lines[arrow_idx]
        parts = arrow_line.split("-->")
        if len(parts) != 2:
            continue

        start_str = parts[0].strip()
        end_str = parts[1].strip()

        try:
            start_sec = parse_timestamp_srt(start_str)
            end_sec = parse_timestamp_srt(end_str)
        except ValueError:
            continue

        text_lines = lines[arrow_idx + 1:]
        # Join internal newlines with single space
        text = " ".join(text_lines).strip()
        if not text:
            # Skip empty cues
            continue

        cues.append(SRTCue(index=cue_idx, start=start_sec, end=end_sec, text=text))

    return cues


def create_windows(cues: List[SRTCue], window_sec: float, stride_sec: float) -> List[Window]:
    """
    Group cues into windows of length window_sec stepping by stride_sec.
    A cue belongs to a window if its START time falls inside [k*stride, k*stride + window_sec).
    Window text is cues joined with a single space.
    Window span:
      start_sec = k * stride
      end_sec = min(k * stride + window_sec, srt_duration)  # clipped to SRT duration
    Empty windows are dropped.
    """
    if not cues:
        return []

    srt_duration = cues[-1].end
    windows: List[Window] = []
    k = 0

    while True:
        win_start = round(k * stride_sec, 6)
        nominal_end = win_start + window_sec
        win_end = min(nominal_end, srt_duration)

        if win_start >= srt_duration:
            break

        # A cue belongs to a window if cue.start falls in [win_start, win_start + window_sec)
        win_cues = [c for c in cues if win_start <= c.start < nominal_end]
        if win_cues:
            win_text = " ".join(c.text for c in win_cues)
            windows.append(
                Window(
                    window_id=len(windows),
                    start_sec=win_start,
                    end_sec=win_end,
                    n_cues=len(win_cues),
                    text=win_text,
                )
            )

        k += 1
        if win_start + stride_sec >= srt_duration and not win_cues:
            break

    return windows


def load_and_validate_queries(csv_path: str, srt_duration: float) -> List[Query]:
    """
    Load queries from CSV. Columns must be exactly: query,start,end,kind.
    Fails loudly with clear messages listing row numbers if:
    - a column is missing
    - start >= end
    - malformed time
    - query is empty
    - range goes beyond srt_duration by more than 5.0 seconds
    """
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Queries file not found: {csv_path}")

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"Queries file is empty: {csv_path}")

    header = [h.strip() for h in header]
    expected_header = ["query", "start", "end", "kind"]
    if header != expected_header:
        raise ValueError(
            f"Invalid CSV header in {csv_path}.\n"
            f"Expected exactly: {expected_header}\n"
            f"Found: {header}"
        )

    queries: List[Query] = []
    errors: List[str] = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        dict_reader = csv.DictReader(f)
        for row_idx, row in enumerate(dict_reader, start=2):  # row 1 is header
            q_text = (row.get("query") or "").strip()
            start_str = (row.get("start") or "").strip()
            end_str = (row.get("end") or "").strip()
            kind_str = (row.get("kind") or "").strip()

            if not q_text:
                errors.append(f"Row {row_idx}: 'query' field is empty.")

            start_sec: Optional[float] = None
            try:
                start_sec = parse_time_str(start_str)
            except Exception as e:
                errors.append(f"Row {row_idx}: Invalid 'start' time '{start_str}': {e}")

            end_sec: Optional[float] = None
            try:
                end_sec = parse_time_str(end_str)
            except Exception as e:
                errors.append(f"Row {row_idx}: Invalid 'end' time '{end_str}': {e}")

            if start_sec is not None and end_sec is not None:
                if start_sec >= end_sec:
                    errors.append(
                        f"Row {row_idx}: start ({start_str}={start_sec}s) >= end ({end_str}={end_sec}s)."
                    )
                if end_sec > srt_duration + 5.0:
                    errors.append(
                        f"Row {row_idx}: end time ({end_str}={end_sec}s) exceeds SRT duration ({srt_duration:.2f}s) by >5s."
                    )

            if not errors or not any(err.startswith(f"Row {row_idx}:") for err in errors):
                queries.append(
                    Query(
                        query_idx=len(queries),
                        query=q_text,
                        start=start_sec,  # type: ignore
                        end=end_sec,      # type: ignore
                        kind=kind_str,
                    )
                )

    if errors:
        error_msg = f"Query validation failed for {csv_path} with {len(errors)} error(s):\n" + "\n".join(
            f"  - {err}" for err in errors
        )
        raise ValueError(error_msg)

    if not queries:
        raise ValueError(f"No valid query rows found in {csv_path}")

    return queries


def check_overlap(win_start: float, win_end: float, q_start: float, q_end: float) -> bool:
    """Strict overlap: win_start < q_end AND win_end > q_start."""
    return (win_start < q_end) and (win_end > q_start)


def fake_deterministic_embedder(texts: List[str], dim: int = 1024) -> np.ndarray:
    """
    Deterministic hash-based fake embedder for --dry-run.
    Produces unit-normalized 1024-d vectors seeded from text hashes.
    """
    vectors = np.zeros((len(texts), dim), dtype=np.float32)
    for i, t in enumerate(texts):
        # Hash text to uint32 seed
        h = int(hashlib.sha256(t.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.RandomState(h)
        vec = rng.randn(dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        vectors[i] = vec
    return vectors


def compute_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def count_truncations(model, texts: List[str], max_seq_length: int) -> int:
    """Count how many texts exceed max_seq_length using the model's tokenizer."""
    if not hasattr(model, "tokenizer") or model.tokenizer is None:
        return 0
    try:
        encoded = model.tokenizer(texts, truncation=False, add_special_tokens=True)["input_ids"]
        return sum(1 for ids in encoded if len(ids) > max_seq_length)
    except Exception as e:
        print(f"Warning: Failed to count truncations via tokenizer: {e}", file=sys.stderr)
        return 0


def run_bakeoff(args):
    start_time_iso = datetime.now().isoformat()
    np.random.seed(42)

    os.makedirs(args.out, exist_ok=True)

    print(f"Loading and parsing SRT: {args.srt}")
    cues = parse_srt(args.srt)
    if not cues:
        raise ValueError(f"No valid cues parsed from SRT: {args.srt}")

    srt_duration = cues[-1].end
    print(f"Parsed {len(cues)} cues. Total duration: {srt_duration:.2f}s ({format_timestamp(srt_duration)})")

    print(f"Loading and validating queries: {args.queries}")
    queries = load_and_validate_queries(args.queries, srt_duration)
    print(f"Validated {len(queries)} queries successfully.")

    # Parse window sizes
    window_sizes = [float(w.strip()) for w in args.windows.split(",") if w.strip()]
    model_names = [m.strip() for m in args.models.split(",") if m.strip()]

    for m in model_names:
        if m not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model: '{m}'. Allowed models: {list(MODEL_REGISTRY.keys())}")

    # Create and save windows for each window size
    windows_by_w: Dict[float, List[Window]] = {}
    for w in window_sizes:
        stride = float(args.stride) if args.stride is not None else w
        win_list = create_windows(cues, window_sec=w, stride_sec=stride)
        windows_by_w[w] = win_list

        win_file = os.path.join(args.out, f"windows_W{int(w) if w.is_integer() else w}.csv")
        with open(win_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["window_id", "start_sec", "end_sec", "n_cues", "text"])
            for win in win_list:
                writer.writerow([win.window_id, f"{win.start_sec:.3f}", f"{win.end_sec:.3f}", win.n_cues, win.text])
        print(f"Window W={w}s: {len(win_list)} windows generated -> {win_file}")

    per_query_results = []
    summary_rows = []

    # Run bakeoff across models and windows
    for model_name in model_names:
        print(f"\n=======================================================")
        print(f"Evaluating Model: {model_name}")
        print(f"=======================================================")

        model_info = MODEL_REGISTRY[model_name]
        model_id = model_info["id"]

        model = None
        device = "cuda"

        if not args.dry_run:
            import torch
            from sentence_transformers import SentenceTransformer
            import faiss

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
                device = "cuda"
            else:
                device = "cpu"

            print(f"Loading {model_id} in float16 on {device}...")
            model_kwargs = {"torch_dtype": torch.float16} if device == "cuda" else {}
            model = SentenceTransformer(model_id, model_kwargs=model_kwargs, device=device)
            model.max_seq_length = args.max_seq_length

            # Embed queries once for this model
            q_texts = [model_info["query_prefix"] + q.query for q in queries]
            t0_q = time.perf_counter()
            q_vecs = model.encode(
                q_texts,
                batch_size=args.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            embed_queries_sec = time.perf_counter() - t0_q

            # Verify query norms ~1.0
            q_norms = np.linalg.norm(q_vecs, axis=1)
            assert np.allclose(q_norms, 1.0, atol=1e-3), (
                f"Query embeddings not normalized! Min={q_norms.min():.4f}, Max={q_norms.max():.4f}"
            )
        else:
            import faiss
            # Dry-run fake embedder
            q_texts = [model_info["query_prefix"] + q.query for q in queries]
            q_vecs = fake_deterministic_embedder(q_texts, dim=1024)
            embed_queries_sec = None

        for w in window_sizes:
            w_label = int(w) if w.is_integer() else w
            windows = windows_by_w[w]
            win_texts = [win.text for win in windows]

            if not args.dry_run:
                import torch

                t0_w = time.perf_counter()
                win_vecs = model.encode(
                    win_texts,
                    batch_size=args.batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                embed_windows_sec = time.perf_counter() - t0_w

                # Verify window norms ~1.0
                win_norms = np.linalg.norm(win_vecs, axis=1)
                assert np.allclose(win_norms, 1.0, atol=1e-3), (
                    f"Window embeddings not normalized! Min={win_norms.min():.4f}, Max={win_norms.max():.4f}"
                )

                peak_vram_mb = (
                    round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2)
                    if device == "cuda"
                    else None
                )
                n_truncated = count_truncations(model, win_texts, args.max_seq_length)
            else:
                win_vecs = fake_deterministic_embedder(win_texts, dim=1024)
                embed_windows_sec = None
                peak_vram_mb = None
                n_truncated = 0

            # Build FAISS index (Inner Product on L2 normalized vectors = Cosine Similarity)
            dim = win_vecs.shape[1]
            index = faiss.IndexFlatIP(dim)
            index.add(win_vecs.astype(np.float32))

            # Full search over all windows for exact ranks
            k_search = len(windows)
            scores, indices = index.search(q_vecs.astype(np.float32), k_search)

            # Evaluate each query
            w_query_results = []
            for q_idx, q in enumerate(queries):
                retrieved_indices = indices[q_idx]
                retrieved_scores = scores[q_idx]

                first_hit_rank = None
                for rank_0, win_idx in enumerate(retrieved_indices):
                    win = windows[win_idx]
                    if check_overlap(win.start_sec, win.end_sec, q.start, q.end):
                        first_hit_rank = rank_0 + 1
                        break

                if first_hit_rank is None:
                    print(
                        f"Warning: No overlapping window found for query {q.query_idx} ('{q.query}') at [{q.start:.1f}, {q.end:.1f}]!",
                        file=sys.stderr,
                    )
                    first_hit_rank_val = None
                    mrr_val = 0.0
                    hit1 = 0
                    hit3 = 0
                    hit5 = 0
                else:
                    first_hit_rank_val = first_hit_rank
                    mrr_val = 1.0 / first_hit_rank
                    hit1 = 1 if first_hit_rank <= 1 else 0
                    hit3 = 1 if first_hit_rank <= 3 else 0
                    hit5 = 1 if first_hit_rank <= 5 else 0

                # Form top5_windows string: "start-end@score;..."
                top5_parts = []
                top5_count = min(5, len(retrieved_indices))
                for top_i in range(top5_count):
                    w_i = retrieved_indices[top_i]
                    sc = retrieved_scores[top_i]
                    target_win = windows[w_i]
                    t_str = f"{format_timestamp(target_win.start_sec)}-{format_timestamp(target_win.end_sec)}@{sc:.3f}"
                    top5_parts.append(t_str)
                top5_str = ";".join(top5_parts)

                res_row = {
                    "model": model_name,
                    "window_sec": w_label,
                    "query_idx": q.query_idx,
                    "query": q.query,
                    "kind": q.kind,
                    "start": format_timestamp(q.start),
                    "end": format_timestamp(q.end),
                    "first_hit_rank": first_hit_rank_val if first_hit_rank_val is not None else "",
                    "hit_at_1": hit1,
                    "hit_at_3": hit3,
                    "hit_at_5": hit5,
                    "mrr": mrr_val,
                    "top5_windows": top5_str,
                }
                w_query_results.append(res_row)
                per_query_results.append(res_row)

            # Compute summary stats (ALL plus per kind)
            kinds = sorted(list(set(q.kind for q in queries)))
            groups = [("ALL", w_query_results)] + [
                (k, [r for r in w_query_results if r["kind"] == k]) for k in kinds
            ]

            for kind_name, group_rows in groups:
                n_q = len(group_rows)
                if n_q == 0:
                    continue
                rec1 = sum(r["hit_at_1"] for r in group_rows) / n_q
                rec3 = sum(r["hit_at_3"] for r in group_rows) / n_q
                rec5 = sum(r["hit_at_5"] for r in group_rows) / n_q
                avg_mrr = sum(r["mrr"] for r in group_rows) / n_q

                summary_rows.append({
                    "model": model_name,
                    "window_sec": w_label,
                    "kind": kind_name,
                    "n_queries": n_q,
                    "recall_at_1": round(rec1, 4),
                    "recall_at_3": round(rec3, 4),
                    "recall_at_5": round(rec5, 4),
                    "mrr": round(avg_mrr, 4),
                    "embed_windows_sec": round(embed_windows_sec, 3) if embed_windows_sec is not None else None,
                    "embed_queries_sec": round(embed_queries_sec, 3) if embed_queries_sec is not None else None,
                    "peak_vram_mb": peak_vram_mb,
                    "n_windows": len(windows),
                    "n_truncated": n_truncated,
                })

        # Memory cleanup after model finishes all windows
        if not args.dry_run and model is not None:
            del model
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    # Write per_query_results.csv
    per_query_file = os.path.join(args.out, "per_query_results.csv")
    pq_cols = [
        "model", "window_sec", "query_idx", "query", "kind", "start", "end",
        "first_hit_rank", "hit_at_1", "hit_at_3", "hit_at_5", "top5_windows"
    ]
    with open(per_query_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=pq_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(per_query_results)

    # Write summary.csv
    summary_file = os.path.join(args.out, "summary.csv")
    sum_cols = [
        "model", "window_sec", "kind", "n_queries", "recall_at_1", "recall_at_3",
        "recall_at_5", "mrr", "embed_windows_sec", "embed_queries_sec",
        "peak_vram_mb", "n_windows", "n_truncated"
    ]
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sum_cols)
        writer.writeheader()
        writer.writerows(summary_rows)

    # Write summary.md
    summary_md_file = os.path.join(args.out, "summary.md")
    with open(summary_md_file, "w", encoding="utf-8") as f:
        f.write("# Embedding Bake-off Summary\n\n")
        f.write("| Model | Window (s) | Kind | N Queries | Recall@1 | Recall@3 | Recall@5 | MRR | Win Enc (s) | Qry Enc (s) | Peak VRAM (MB) | N Windows | Truncated |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in summary_rows:
            f.write(
                f"| {r['model']} | {r['window_sec']} | {r['kind']} | {r['n_queries']} | "
                f"{r['recall_at_1']:.4f} | {r['recall_at_3']:.4f} | {r['recall_at_5']:.4f} | {r['mrr']:.4f} | "
                f"{r['embed_windows_sec'] if r['embed_windows_sec'] is not None else 'null'} | "
                f"{r['embed_queries_sec'] if r['embed_queries_sec'] is not None else 'null'} | "
                f"{r['peak_vram_mb'] if r['peak_vram_mb'] is not None else 'null'} | "
                f"{r['n_windows']} | {r['n_truncated']} |\n"
            )

    # Package versions for run_config
    pkg_versions = {}
    for pkg in ["torch", "transformers", "sentence_transformers", "faiss", "numpy", "pandas"]:
        try:
            mod = __import__(pkg)
            pkg_versions[pkg] = getattr(mod, "__version__", "unknown")
        except ImportError:
            pkg_versions[pkg] = "not installed"

    run_config = {
        "timestamp": start_time_iso,
        "cli_args": vars(args),
        "model_definitions": MODEL_REGISTRY,
        "qwen_query_instruction": QWEN_QUERY_INSTRUCTION,
        "package_versions": pkg_versions,
        "srt_path": os.path.abspath(args.srt),
        "srt_sha256": compute_sha256(args.srt),
        "queries_path": os.path.abspath(args.queries),
        "queries_sha256": compute_sha256(args.queries),
    }

    config_file = os.path.join(args.out, "run_config.json")
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(run_config, f, indent=2)

    # Print compact summary table to console
    print("\n" + "=" * 105)
    print(f"{'Model':<12} {'Win':<5} {'Kind':<8} {'Queries':<8} {'R@1':<8} {'R@3':<8} {'R@5':<8} {'MRR':<8} {'Win(s)':<8} {'Qry(s)':<8} {'VRAM(MB)':<10}")
    print("-" * 105)
    for r in summary_rows:
        win_s = f"{r['embed_windows_sec']:.2f}" if r['embed_windows_sec'] is not None else "-"
        qry_s = f"{r['embed_queries_sec']:.2f}" if r['embed_queries_sec'] is not None else "-"
        vram_s = f"{r['peak_vram_mb']:.1f}" if r['peak_vram_mb'] is not None else "-"
        print(
            f"{r['model']:<12} {r['window_sec']:<5} {r['kind']:<8} {r['n_queries']:<8} "
            f"{r['recall_at_1']:<8.3f} {r['recall_at_3']:<8.3f} {r['recall_at_5']:<8.3f} {r['mrr']:<8.3f} "
            f"{win_s:<8} {qry_s:<8} {vram_s:<10}"
        )
    print("=" * 105 + "\n")
    print(f"Results successfully written to: {os.path.abspath(args.out)}")


def main():
    parser = argparse.ArgumentParser(description="Insightex Embedding Model Bake-Off")
    parser.add_argument("--srt", required=True, help="Path to Whisper SRT file")
    parser.add_argument("--queries", required=True, help="Path to queries CSV (query,start,end,kind)")
    parser.add_argument("--out", required=True, help="Directory to save output artifacts")
    parser.add_argument("--models", default="bge-m3,qwen3-0.6b", help="Comma-separated model names (bge-m3, qwen3-0.6b)")
    parser.add_argument("--windows", default="30,60,90", help="Comma-separated window lengths in seconds")
    parser.add_argument("--stride", type=float, default=None, help="Stride length in seconds (default: equal to window length)")
    parser.add_argument("--topk", type=int, default=5, help="Top-k retrieval cut-off (default: 5)")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size for embedding inference (default: 16)")
    parser.add_argument("--max-seq-length", type=int, default=512, help="Max sequence length for tokenizer (default: 512)")
    parser.add_argument("--dry-run", action="store_true", help="Deterministic fake embedder without downloading or GPU")

    args = parser.parse_args()
    run_bakeoff(args)


if __name__ == "__main__":
    main()
