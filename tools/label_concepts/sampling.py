"""Deterministic, seeded, stratified window sample for M7 gold labels (ADR-0048).

Eligible windows are the lecture's grid windows minus any excluded ones, in time order. If N >= the number eligible,
the sample is the census of all eligible windows (the manifest says so). Otherwise the eligible list is cut into N
contiguous strata of near-equal size (stratum i is eligible[floor(i*E/N) : floor((i+1)*E/N)]) and one window is drawn
from each with random.Random(seed), so the sample spreads across the lecture's timeline.

The shared (double-labelled) windows are drawn the same way from the sample: n_shared strata over the sampled windows
in time order, one draw each, continuing the same random generator. They come first in the labelling order (in time
order), then the rest (in time order). Every non-shared window is assigned to one labeller, alternating through the
labeller list in time order, so each labeller's part also spreads across the lecture.
"""

from __future__ import annotations

import random
from typing import Any

from grid import STRIDE_S, WINDOW_S, GridWindow

MANIFEST_VERSION = 1


def stratified_pick(items: list[Any], n: int, rng: random.Random) -> list[Any]:
    """n items, one from each of n contiguous near-equal strata; all items (in order) when n >= len(items)."""
    if n >= len(items):
        return list(items)
    e = len(items)
    return [items[rng.randrange(i * e // n, (i + 1) * e // n)] for i in range(n)]


def build_manifest(*, lecture_id: str, windows: list[GridWindow], transcript_info: dict[str, Any], index_check: str,
                   seed: int, n: int, n_shared: int, labellers: list[str], excluded: dict[int, str],
                   created_at: str) -> dict[str, Any]:
    if n < 1 or n_shared < 0:
        raise ValueError("N must be >= 1 and the shared count >= 0")
    if len(labellers) < 2 or len(set(labellers)) != len(labellers):
        raise ValueError("need at least two distinct labeller names")
    known = {w.index for w in windows}
    unknown = sorted(set(excluded) - known)
    if unknown:
        raise ValueError(f"excluded window indices not in the lecture: {unknown}")
    eligible = [w for w in windows if w.index not in excluded]
    rng = random.Random(seed)
    sampled = stratified_pick(eligible, n, rng)
    census = n >= len(eligible)
    if n_shared > len(sampled):
        raise ValueError(f"{n_shared} shared windows requested but only {len(sampled)} sampled")
    shared = {w.index for w in stratified_pick(sampled, n_shared, rng)}
    order = [w for w in sampled if w.index in shared] + [w for w in sampled if w.index not in shared]
    rows = []
    k = 0
    for pos, w in enumerate(order):
        if w.index in shared:
            assigned = list(labellers)
        else:
            assigned = [labellers[k % len(labellers)]]
            k += 1
        rows.append({"order": pos, "window_index": w.index, "start_s": w.start_s, "end_s": w.end_s,
                     "text_sha256": w.text_sha256, "shared": w.index in shared, "assigned_to": assigned})
    return {
        "manifest_version": MANIFEST_VERSION,
        "lecture_id": lecture_id,
        "created_at": created_at,
        "seed": seed,
        "n_requested": n,
        "n_sampled": len(sampled),
        "n_shared": n_shared,
        "labellers": list(labellers),
        "grid": {"window_s": WINDOW_S, "stride_s": STRIDE_S, "rule": "ADR-0045 fixed time grid, no overlap, segment "
                 "assigned by start time, empty windows dropped, ids count kept windows", "index_check": index_check},
        "transcript": transcript_info,
        "n_windows_total": len(windows),
        "excluded": [{"window_index": i, "reason": excluded[i]} for i in sorted(excluded)],
        "n_eligible": len(eligible),
        "census": census,
        "census_note": (f"N={n} >= {len(eligible)} eligible windows: the sample is every eligible window"
                        if census else None),
        "windows": rows,
    }


def windows_for(manifest: dict[str, Any], labeller: str) -> list[dict[str, Any]]:
    """The manifest rows a labeller must label. The name 'consensus' (the reconciled labels of the shared windows,
    made after the agreement discussion) gets the shared windows only."""
    if labeller == "consensus":
        return [r for r in manifest["windows"] if r["shared"]]
    if labeller not in manifest["labellers"]:
        raise SystemExit(f"labeller {labeller!r} is not in the sample manifest ({', '.join(manifest['labellers'])}, "
                         "or 'consensus')")
    return [r for r in manifest["windows"] if labeller in r["assigned_to"]]
