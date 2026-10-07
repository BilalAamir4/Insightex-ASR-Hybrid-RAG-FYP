"""Throwaway: per-topic keyword hits on a page range. Prints counts and page labels only."""
import sys

import pymupdf

TOPICS = {
    "batch (offline) learning": ["batch learning", "offline learning"],
    "online (incremental) learning": ["online learning", "incrementally"],
    "mini-batches": ["mini-batch"],
    "learning rate in online learning": ["learning rate"],
    "out-of-core learning": ["out-of-core"],
    "bad data degrading online system": ["bad data", "performance will gradually decline", "garbage"],
}

if __name__ == "__main__":
    path, lo, hi = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    doc = pymupdf.open(path)
    for name, kws in TOPICS.items():
        pages = []
        for i in range(lo, hi + 1):
            t = " ".join(doc[i].get_text().lower().split())
            if any(k in t for k in kws):
                pages.append(f"idx0 {i} label {doc[i].get_label()}")
        print(name, "->", pages or "NOT FOUND")
    for i in range(lo, hi + 1):
        t = doc[i].get_text()
        for l in t.split("\n"):
            if l.strip() in ("Batch and Online Learning", "Batch learning", "Online learning", "Batch Learning", "Online Learning") or l.startswith("Batch and Online"):
                print("heading-ish line:", l.strip(), "| idx0", i, "label", doc[i].get_label())
