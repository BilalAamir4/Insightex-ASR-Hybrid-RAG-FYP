"""Load BGE-M3 from the offline cache and encode text with it (ADR-0001, ADR-0044).

Used in two places with the same code: the index-stage subprocess (GPU, at ingest) and the query encoder
(CPU, in the API process or the `search` command). Heavy imports happen inside the functions, so importing
this module costs nothing.
"""

from __future__ import annotations

from typing import Any


def resolve_snapshot(repo: str, revision: str) -> str:
    """Path of the pinned snapshot in the local Hugging Face cache. Never touches the network."""
    from huggingface_hub import snapshot_download

    return snapshot_download(repo, revision=revision, local_files_only=True)


def load_model(repo: str, revision: str, *, device: str, device_index: int, dtype: str, max_seq_length: int) -> Any:
    """A SentenceTransformer on `device` at precision `dtype` ("float16" or "float32"), sequence limit set."""
    import torch
    from sentence_transformers import SentenceTransformer

    torch_dtype = {"float16": torch.float16, "float32": torch.float32}[dtype]
    target = f"cuda:{device_index}" if device == "cuda" else device
    model = SentenceTransformer(resolve_snapshot(repo, revision), device=target, model_kwargs={"torch_dtype": torch_dtype})
    model.max_seq_length = max_seq_length
    return model


def encode(model: Any, texts: list[str], batch_size: int):
    """Unit-length float32 vectors, shape (len(texts), dim). Cosine similarity is then an inner product."""
    return model.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False).astype("float32")


def count_truncated(model: Any, texts: list[str], max_seq_length: int) -> int:
    """How many texts are longer than `max_seq_length` tokens (those lose their tail when encoded)."""
    ids = model.tokenizer(texts, truncation=False, add_special_tokens=True)["input_ids"]
    return sum(1 for i in ids if len(i) > max_seq_length)
