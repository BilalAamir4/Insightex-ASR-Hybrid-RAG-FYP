"""Throwaway textbook probe (M0b). Prints findings to stdout only; writes nothing to disk.

Usage: python probe.py meta|find|toc|topics <pdf>
Standalone: imports no production code.
"""
import re
import sys

import pymupdf


def labels(doc, i):
    return doc[i].get_label() or ""


def meta(doc):
    print("pages:", doc.page_count)
    print("metadata:", doc.metadata)
    print("has any page label:", any(labels(doc, i) for i in range(doc.page_count)))
    print("labels sample:", [(i, labels(doc, i)) for i in (0, 1, 2, 5, 20, 100, 400, doc.page_count - 1)])
    for i in range(0, 8):
        t = doc[i].get_text()
        print(f"--- idx {i} label {labels(doc, i)!r} chars {len(t)}")
        print(t[:500].replace("\n", " | "))


def toc(doc):
    for lvl, title, pg in doc.get_toc():
        if lvl <= 2:
            print(lvl, title, "-> idx0", pg - 1, "label", labels(doc, pg - 1) if pg > 0 else "")


def find(doc, pat):
    rx = re.compile(pat, re.I)
    for i in range(doc.page_count):
        t = doc[i].get_text()
        n = len(rx.findall(t))
        if n:
            print(f"idx0 {i} idx1 {i+1} label {labels(doc, i)!r} hits {n}")


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[-1]
    doc = pymupdf.open(path)
    if cmd == "meta":
        meta(doc)
    elif cmd == "toc":
        toc(doc)
    elif cmd == "find":
        find(doc, sys.argv[2])
