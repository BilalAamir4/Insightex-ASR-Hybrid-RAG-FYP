"""The `index` stage's files: windows.json, dense.faiss, index.json (ADR-0044).

`dense.faiss` is a FAISS `IndexFlatIP` over L2-normalised BGE-M3 vectors; row i is window id i. `windows.json` holds
the window texts and times, so a hit can be shown and seeked to without the transcript. Both are internal: nothing
serves the text to users (ADR-0041).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from insightex.asr.transcript import write_atomic
from insightex.windows.build import SCHEMA_VERSION, Window

WINDOWS_JSON, DENSE_FAISS, INDEX_JSON = "windows.json", "dense.faiss", "index.json"


def write_index(directory: Path, windows: list[Window], vectors: Any, meta: dict[str, Any]) -> None:
    """Write the three files into `directory` (the runner's staging directory, itself published by rename)."""
    import faiss

    if vectors.shape[0] != len(windows):
        raise ValueError(f"{vectors.shape[0]} vectors for {len(windows)} windows")
    index = faiss.IndexFlatIP(int(vectors.shape[1]))
    index.add(vectors)
    faiss.write_index(index, str(directory / DENSE_FAISS))
    doc = {"schema_version": SCHEMA_VERSION, "windows": [w.to_json() for w in windows]}
    write_atomic(directory / WINDOWS_JSON, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    write_atomic(directory / INDEX_JSON, json.dumps(meta, ensure_ascii=False, indent=1) + "\n")


@dataclass
class LectureIndex:
    directory: Path
    windows: list[dict[str, Any]]
    meta: dict[str, Any]
    faiss_index: Any

    @property
    def size(self) -> int:
        return len(self.windows)


def load_index(directory: Path) -> LectureIndex:
    import faiss

    windows = json.loads((directory / WINDOWS_JSON).read_text(encoding="utf-8"))["windows"]
    meta = json.loads((directory / INDEX_JSON).read_text(encoding="utf-8"))
    index = faiss.read_index(str(directory / DENSE_FAISS))
    if index.ntotal != len(windows):
        raise ValueError(f"{directory}: {index.ntotal} vectors but {len(windows)} windows")
    return LectureIndex(directory, windows, meta, index)
