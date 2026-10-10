"""flagged.md: for every flagged config, show each flagged passage side by side.

Reference text (located through the large-v3_ur / large-v3_auto L1 alignment, since the
reference is not time-aligned) next to the raw and romanised output of the two large-v3 configs.
"""
import numpy as np

import gate_metrics as gm

ANCHORS = ("large-v3_ur", "large-v3_auto")
SHOW = ("large-v3_ur", "large-v3_auto")


def events(res):
    ev = [("uncovered speech gap", a, b) for a, b in res["drop"]["gaps"] if b - a >= 3.0][:3]
    for r in sorted(res["delruns"], key=lambda r: -r["words"])[:4]:
        if r["t_to"] is not None:
            ev.append((f"{r['words']} reference words deleted in a row", r["t_from"], r["t_to"]))
    st = res["drift"]["stretches"]
    if st:
        n, t, _ = st[0]
        ev.append((f"longest Latin-script stretch ({n} words)", t, t + n * 0.5))
    return ev


def window_rows(res, t0, t1):
    return [r for r in res["rows"] if t0 <= r["start"] <= t1]


def ref_span(by_name, ref, t0, t1, pad=3):
    for a in ANCHORS:
        if a not in by_name:
            continue
        ops = by_name[a]["l1"]["ops"]
        rows = by_name[a]["rows"]
        idx = [o[1] for o in ops if o[0] in "MS" and t0 - 1 <= rows[o[2]]["start"] <= t1 + 1]
        if idx:
            return max(0, min(idx) - pad), min(len(ref["l1"]), max(idx) + pad + 1), a
    return None


def write(out, results, ref, speech):
    by = {r["name"]: r for r in results}
    L = ["# Flagged passages\n", "Reference windows are located through the anchor config's alignment (the reference has no timestamps), so their edges are approximate. "
         "`covered` = share of the window's VAD speech inside a Whisper segment of that config; `Latin` = share of the config's raw words in the window written in Latin script.\n"]
    for res in results:
        if not res["flags"]:
            continue
        L.append(f"\n## {res['name']}\nFlags: " + "; ".join(res["flags"]) + "\n")
        for label, t0, t1 in events(res):
            t0, t1 = max(0.0, t0 - 0.5), t1 + 0.5
            L.append(f"\n### {label}: {t0:.1f}s - {t1:.1f}s\n")
            span = ref_span(by, ref, t0, t1)
            L.append("- reference (approx.): " + (" ".join(ref["l1"][span[0]:span[1]]) + f"  [ref {span[0]}-{span[1] - 1}, anchored by {span[2]}]" if span else "(no anchor)"))
            names = list(dict.fromkeys([res["name"], *SHOW]))
            for n in names:
                r = by.get(n)
                if not r:
                    continue
                rows = window_rows(r, t0, t1)
                raw, last = [], None
                for x in rows:
                    if (x["raw"], x["start"]) != last:
                        raw.append(x["raw"])
                    last = (x["raw"], x["start"])
                lat = sum(1 for w in raw if w.isascii()) / max(1, len(raw))
                sp = speech[int(t0 * 100):int(t1 * 100)]
                cov = np.zeros(len(speech), dtype=bool)
                for s in r["d"]["segments"]:
                    cov[int(s["start"] * 100):int(np.ceil(s["end"] * 100))] = True
                c = (sp & cov[int(t0 * 100):int(t1 * 100)]).sum() / max(1, sp.sum())
                segs = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}" for s in r["d"]["segments"] if s["end"] > t0 and s["start"] < t1]
                L.append(f"- **{n}**: {len(raw)} words, covered {100 * c:.0f}%, Latin {100 * lat:.0f}%\n"
                         f"  - segments: {' | '.join(segs) or '(none)'}\n"
                         f"  - raw: {' '.join(raw) or '-'}\n  - romanised: {' '.join(x['l1'] for x in rows) or '-'}")
    (out / "flagged.md").write_text("\n".join(L) + "\n", encoding="utf-8")
