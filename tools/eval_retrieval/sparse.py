"""BGE-M3 sparse head on the plain transformers stack (gate G2, ADR-0043). Standalone: no imports from backend/src.

The head is BGE-M3's own: weight(token) = ReLU(sparse_linear(last_hidden_state)); per text, the largest weight for
each token id; the special tokens (cls, eos, pad, unk) are left out; a query and a window are scored by the sum of
weight products over the token ids they share. `sparse_linear.pt` is the model's own file, read from the offline Hugging
Face cache. Dense vectors come from the same forward pass (CLS pooling, L2-normalised), as in the model card.

Verified against `FlagEmbedding.BGEM3FlagModel` by `g2_verify.py`; this module does not import FlagEmbedding.
"""

from __future__ import annotations

import numpy as np

REPO = "BAAI/bge-m3"
REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


class SparseEncoder:
    def __init__(self, *, device: str = "cuda", dtype: str = "float16", max_length: int = 1024, batch_size: int = 16,
                 repo: str = REPO, revision: str = REVISION) -> None:
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModel, AutoTokenizer

        path = snapshot_download(repo, revision=revision, local_files_only=True)
        self.torch = torch
        self.device, self.max_length, self.batch_size = device, max_length, batch_size
        torch_dtype = {"float16": torch.float16, "float32": torch.float32}[dtype]
        self.tokenizer = AutoTokenizer.from_pretrained(path)
        self.model = AutoModel.from_pretrained(path, torch_dtype=torch_dtype).to(device).eval()
        state = torch.load(f"{path}/sparse_linear.pt", map_location="cpu")
        self.sparse_linear = torch.nn.Linear(self.model.config.hidden_size, 1)
        self.sparse_linear.load_state_dict(state)
        self.sparse_linear = self.sparse_linear.to(device=device, dtype=torch_dtype).eval()
        tok = self.tokenizer
        self.unused = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}

    def encode(self, texts: list[str]):
        """(dense, sparse): dense is (n, 1024) float32 unit vectors; sparse is a list of {token_id: weight} dicts.

        Texts are processed longest first in batches (as the reference does) and returned in input order.
        """
        torch = self.torch
        enc = [self.tokenizer(t, max_length=self.max_length, truncation=True, padding=False,
                              return_attention_mask=False, return_token_type_ids=False) for t in texts]
        order = np.argsort([-len(e["input_ids"]) for e in enc], kind="stable")
        dense = [None] * len(texts)
        sparse: list[dict[int, float] | None] = [None] * len(texts)
        with torch.no_grad():
            for s in range(0, len(texts), self.batch_size):
                idx = order[s:s + self.batch_size]
                batch = self.tokenizer.pad([enc[i] for i in idx], padding=True, return_tensors="pt").to(self.device)
                hidden = self.model(**batch).last_hidden_state
                vec = torch.nn.functional.normalize(hidden[:, 0], dim=-1).float().cpu().numpy()
                weights = torch.relu(self.sparse_linear(hidden)).squeeze(-1).float().cpu().numpy()
                ids = batch["input_ids"].cpu().numpy()
                for row, i in enumerate(idx):
                    dense[i] = vec[row]
                    out: dict[int, float] = {}
                    for w, tid in zip(weights[row], ids[row], strict=True):
                        tid = int(tid)
                        if tid not in self.unused and w > 0 and w > out.get(tid, 0.0):
                            out[tid] = float(w)
                    sparse[i] = out
        return np.stack(dense), sparse


def sparse_score(q: dict[int, float], d: dict[int, float]) -> float:
    """Lexical matching score: sum over shared token ids of the weight products."""
    if len(q) > len(d):
        q, d = d, q
    return sum(w * d[t] for t, w in q.items() if t in d)


def rrf(rankings: list[list[int]], k: int = 60) -> list[int]:
    """Reciprocal Rank Fusion: score(id) = sum over rankings of 1 / (k + rank), rank starting at 1; ties by smaller id."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, wid in enumerate(ranking, start=1):
            scores[wid] = scores.get(wid, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda w: (-scores[w], w))
