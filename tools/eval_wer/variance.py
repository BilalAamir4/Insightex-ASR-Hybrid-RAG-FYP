"""Run-to-run variation of one config: extra runs plus min/mean/max against the gate's run 1.

usage: variance.py --audio A --reference R --warmup-audio W --out results/m4 [--config large-v3_ur] [--extra 2]
Run 1 is <out>/<config>/raw.json from run_gate.py (its segments carry no temperature field).
Extra runs go to <out>/variance/<config>_run<N>/raw.json. Writes <out>/variance.md.
Pass rule (fixed before the runs): mean dropped speech <= 2% and no run with a gap >= 10 s.
"""
import argparse
import json
import statistics as st
from pathlib import Path
from types import SimpleNamespace

import gate_metrics as gm
import run_gate as rg
import textnorm as tn


def main():
    ap = argparse.ArgumentParser()
    for k in ("audio", "reference", "warmup_audio", "out"):
        ap.add_argument("--" + k.replace("_", "-"), required=True)
    ap.add_argument("--config", default="large-v3_ur")
    ap.add_argument("--extra", type=int, default=2)
    a = ap.parse_args()
    out = Path(a.out)
    model, lang = a.config.rsplit("_", 1)
    from faster_whisper.audio import decode_audio
    speech, _ = gm.energy_vad(decode_audio(a.audio))
    r1, wild = rg.ref_tokens(Path(a.reference).read_text(encoding="utf-8"))
    ref = dict(l1=r1, l2=[tn.l2_token(t) for t in r1])
    base = rg.vram_used()
    runs = [(1, out / a.config / "raw.json")]
    for n in range(2, 2 + a.extra):
        p = out / "variance" / f"{a.config}_run{n}" / "raw.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        print(f"run {n}", flush=True)
        vram = rg.run_config(model, lang, a, p, base)
        d = json.load(open(p)); d["peak_vram_mib"] = vram
        json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)
        runs.append((n, p))
    rows = []
    for n, p in runs:
        d = json.load(open(p))
        res = rg.analyse(f"{a.config}_run{n}", d, ref, wild, speech)
        fb = [s for s in d["segments"] if s.get("temperature") not in (None, 0.0)]
        rows.append(dict(run=n, wer=res["l2"]["wer"], cer=res["l2"]["cer"], l1wer=res["l1"]["wer"], drop=res["drop"]["pct"],
                         gap=res["drop"]["longest_gap_s"], segs=len(d["segments"]),
                         fb=len(fb) if "temperature" in (d["segments"][0] if d["segments"] else {}) else None,
                         delruns=len(res["delruns"]), rtf=d["warm_rtf"]))
    L = [f"# Run-to-run variation: {a.config}\n", f"Same audio, parameters and scoring as the gate. Run 1 is the gate run; runs 2-{1 + a.extra} are repeats.\n",
         "| run | L2 WER | L1 WER | L2 CER | dropped speech | longest gap | deleted runs >= 8 words | segments | segments with temperature fallback | warm RTF |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['run']} | {100 * r['wer']:.1f}% | {100 * r['l1wer']:.1f}% | {100 * r['cer']:.1f}% | {r['drop']:.2f}% | {r['gap']:.1f}s | {r['delruns']} | {r['segs']} | "
                 f"{r['fb'] if r['fb'] is not None else 'not recorded (run 1 predates the field)'} | {r['rtf']:.3f} |")
    for lab, k, fmt in (("L2 WER", "wer", lambda x: f"{100 * x:.1f}%"), ("L2 CER", "cer", lambda x: f"{100 * x:.1f}%"),
                        ("dropped speech", "drop", lambda x: f"{x:.2f}%"), ("longest gap", "gap", lambda x: f"{x:.1f}s")):
        v = [r[k] for r in rows]
        L.append(f"- {lab}: min {fmt(min(v))}, mean {fmt(st.mean(v))}, max {fmt(max(v))}")
    mean_drop, max_gap = st.mean(r["drop"] for r in rows), max(r["gap"] for r in rows)
    ok = mean_drop <= 2.0 and max_gap < 10.0
    L.append(f"\n**Pass rule** (mean dropped speech <= 2% and no gap >= 10 s): mean {mean_drop:.2f}%, max gap {max_gap:.1f}s -> **{'PASS' if ok else 'FAIL'}**.")
    (out / "variance.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
