"""M4 Whisper WER/CER gate: run every config, score it, write results.

usage: run_gate.py --audio A.wav --reference manual_roman.txt --warmup-audio clip.wav --out results/m4 [--reuse]

Each config runs in its own subprocess (transcribe_one.py); peak VRAM is polled with nvidia-smi
(torch counters do not see CTranslate2) and the GPU must return to baseline between runs.
Standalone: no imports from backend/.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import flagged
import gate_metrics as gm
import textnorm as tn

HERE = Path(__file__).parent
CONFIGS = [("medium", "ur"), ("medium", "auto"), ("large-v3", "ur"), ("large-v3", "auto")]
OPTIONAL = [("large-v3-turbo", "ur"), ("large-v3-turbo", "auto")]  # only if already cached
DROP_PCT, DROP_GAP_S = 2.0, 10.0           # starting thresholds (human confirms)
DRIFT_PP, DRIFT_STRETCH = 20.0, 30         # starting thresholds (human reviews)
BOOT_N, BLOCK = 10000, 50


# --- GPU helpers ----------------------------------------------------------------------------
def vram_used():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True).stdout
    return int(out.split()[0])


def wait_baseline(base, tol=150, timeout=90):
    t0 = time.time()
    while vram_used() > base + tol:
        if time.time() - t0 > timeout:
            sys.exit(f"VRAM did not return to baseline ({base} MiB); used={vram_used()}")
        time.sleep(1)


def ollama_loaded():
    url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434") + "/api/ps"
    try:
        return json.load(urllib.request.urlopen(url, timeout=3)).get("models", [])
    except (OSError, ValueError):
        return []


def model_cached(name):
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"
    return (hub / f"models--Systran--faster-whisper-{name}").exists()


def run_config(model, lang, a, out_json, base):
    peak, stop = [base], threading.Event()

    def poll():
        while not stop.is_set():
            peak[0] = max(peak[0], vram_used())
            time.sleep(0.2)

    th = threading.Thread(target=poll)
    th.start()
    try:
        p = subprocess.run([sys.executable, str(HERE / "transcribe_one.py"), "--model", model, "--language", lang,
                            "--audio", a.audio, "--warmup-audio", a.warmup_audio, "--out", str(out_json)],
                           capture_output=True, text=True, check=False)
    finally:
        stop.set()
        th.join()
    if p.returncode:
        sys.exit(f"{model} {lang} failed:\n{p.stderr[-2000:]}")
    wait_baseline(base)
    return peak[0] - base


# --- scoring --------------------------------------------------------------------------------
def ref_tokens(text):
    toks, wild = [], []
    for k, part in enumerate(re.split(r"\[unclear\]", text, flags=re.IGNORECASE)):
        if k:
            toks.append("?"); wild.append(True)
        for t in tn.l1_tokens(part):
            toks.append(t); wild.append(False)
    return toks, wild


def hyp_tokens(d):
    rows, raw_words = [], []
    for s in d["segments"]:
        words = s["words"] or [{"word": w, "start": s["start"], "end": s["end"]} for w in s["text"].split()]
        for w in words:
            raw = w["word"].strip()
            raw_words.append((raw, w["start"]))
            rom = tn.romanise_word(raw)
            for t in tn.l1_tokens(rom):
                rows.append({"l1": t, "l2": tn.l2_token(t), "start": w["start"], "end": w["end"], "raw": raw, "rom": rom})
    return rows, raw_words


def pct(x):
    return f"{100 * x:.1f}%"


def analyse(name, d, ref, wild, speech):
    rows, raw_words = hyp_tokens(d)
    res = {"name": name, "d": d, "rows": rows, "drift": gm.drift(raw_words)}
    times = [(r["start"], r["end"]) for r in rows]
    for lv in ("l1", "l2"):
        res[lv] = gm.score(ref[lv], [r[lv] for r in rows], wild, BLOCK)
    res["delruns"] = gm.deletion_runs(res["l2"], times)
    res["drop"] = gm.dropped_speech(speech, d["segments"])
    return res


def flags(res, min_share):
    f = []
    dr = res["drop"]
    if dr["pct"] > DROP_PCT:
        f.append(f"dropped speech {dr['pct']:.1f}% > {DROP_PCT}%")
    if dr["longest_gap_s"] >= DROP_GAP_S:
        f.append(f"uncovered speech gap {dr['longest_gap_s']:.1f}s >= {DROP_GAP_S}s")
    for r in res["delruns"]:
        if r["t_to"] is not None and r["t_to"] - r["t_from"] >= DROP_GAP_S:
            f.append(f"{r['words']} reference words deleted in a row (~{r['t_to'] - r['t_from']:.0f}s gap at {r['t_from']:.0f}s)")
    df = res["drift"]
    if 100 * (df["share"] - min_share) > DRIFT_PP:
        f.append(f"Latin-script share {pct(df['share'])} is {100 * (df['share'] - min_share):.0f} pp above the lowest config (translation drift?)")
    if df["stretches"] and df["stretches"][0][0] >= DRIFT_STRETCH:
        f.append(f"Latin-script stretch of {df['stretches'][0][0]} words")
    return f


def write_outputs(out, res):
    c = out / res["name"]
    c.mkdir(parents=True, exist_ok=True)
    segs = res["d"]["segments"]
    (c / "romanised.txt").write_text("\n".join(
        " ".join(tn.romanise_word(w["word"].strip()) for w in s["words"]) if s["words"] else s["text"] for s in segs) + "\n", encoding="utf-8")
    (c / "normalised_l1.txt").write_text(" ".join(r["l1"] for r in res["rows"]) + "\n")
    (c / "normalised_l2.txt").write_text(" ".join(r["l2"] for r in res["rows"]) + "\n")


def samples(results, ref, out, n=20, span=15):
    N = len(ref["l1"])
    lines = ["# M4 aligned samples (L1 alignment)\n",
             (f"{n} reference windows of {span} words at evenly spaced positions, the same for every config. "
             "`raw` is the Whisper output for the aligned hypothesis words (before romanisation).\n")]
    for r in results:
        lines.append(f"\n## {r['name']}\n")
        ops = r["l1"]["ops"]
        for k in range(n):
            a = k * (N // n)
            b = min(N, a + span)
            hs = [o[2] for o in ops if o[0] in "MSIW" and a <= o[1] < b and o[2] >= 0]
            hyp_rom = " ".join(r["rows"][j]["l1"] for j in hs)
            raw, last = [], None
            for j in hs:
                key = (r["rows"][j]["raw"], r["rows"][j]["start"])
                if key != last:
                    raw.append(r["rows"][j]["raw"])
                last = key
            lines.append(f"{k + 1}. [ref {a}-{b - 1}]\n   - ref: {' '.join(ref['l1'][a:b])}\n"
                         f"   - hyp (romanised): {hyp_rom or '(nothing aligned)'}\n   - hyp raw: {' '.join(raw) or '-'}")
    (out / "samples.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def vad_report(clip, out):
    from faster_whisper.audio import decode_audio
    x = decode_audio(clip)
    mask, thr = gm.energy_vad(x)
    n = len(mask)
    cells = "".join("#" if mask[i:i + 25].mean() > 0.5 else "." for i in range(0, n, 25))
    iv = [f"{a / 100:.2f}-{b / 100:.2f}s" for a, b in gm.runs(mask)]
    (out / "vad_clip30s.md").write_text(
        f"# Energy VAD on the 30 s clip\n\nParameters: {gm.VAD}\nThreshold: {thr:.1f} dBFS (noise floor + {gm.VAD['above_noise_db']} dB)\n"
        f"Speech {mask.sum() / 100:.1f}s of {n / 100:.1f}s ({100 * mask.mean():.0f}%)\n\n"
        f"Timeline, one character per 0.25 s (# speech, . silence):\n\n```\n{cells}\n```\n\nIntervals: {', '.join(iv)}\n")
    return mask.mean()


# --- main -----------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--warmup-audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reuse", action="store_true", help="re-score existing raw.json instead of re-running Whisper")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if ollama_loaded():
        sys.exit("An Ollama model is loaded; free VRAM first (ask before stopping Ollama).")
    base = vram_used()
    configs, skipped = list(CONFIGS), []
    for m, l in OPTIONAL:
        (configs if model_cached(m) else skipped).append((m, l))
    from faster_whisper.audio import decode_audio
    audio = decode_audio(a.audio)
    speech, thr = gm.energy_vad(audio)
    clip_speech = vad_report(a.warmup_audio, out)

    ref_text = Path(a.reference).read_text(encoding="utf-8")
    r1, wild = ref_tokens(ref_text)
    ref = {"l1": r1, "l2": [tn.l2_token(t) if not w else "?" for t, w in zip(r1, wild)]}
    (out / "reference_l1.txt").write_text(" ".join(ref["l1"]) + "\n")
    (out / "reference_l2.txt").write_text(" ".join(ref["l2"]) + "\n")
    coll = tn.collision_rate([t for t, w in zip(r1, wild) if not w])

    results = []
    for model, lang in configs:
        name = f"{model}_{lang}"
        raw = out / name / "raw.json"
        raw.parent.mkdir(parents=True, exist_ok=True)
        vram = None
        if not (a.reuse and raw.exists()):
            print(f"[{name}] transcribing", flush=True)
            vram = run_config(model, lang, a, raw, base)
        d = json.loads(raw.read_text(encoding="utf-8"))
        d["peak_vram_mib"] = vram if vram is not None else d.get("peak_vram_mib")
        raw.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{name}] scoring", flush=True)
        res = analyse(name, d, ref, wild, speech)
        write_outputs(out, res)
        results.append(res)

    min_share = min(r["drift"]["share"] for r in results)
    for r in results:
        r["flags"] = flags(r, min_share)
    samples(results, ref, out)
    flagged.write(out, results, ref, speech)
    write_results(out, results, ref, wild, coll, skipped, base, clip_speech, thr, speech, a)


def sdi(s):
    return f"{s['S']}/{s['D']}/{s['I']}"


def boot_section(results, label, pool):
    if len(pool) < 2:
        return [f"- {label}: fewer than two configs, no bootstrap.\n"]
    by_wer = sorted(pool, key=lambda r: r["l2"]["wer"])
    by_cer = sorted(pool, key=lambda r: r["l2"]["cer"])
    best, runner = by_wer[0], by_wer[1]
    pt, lo, hi = gm.paired_bootstrap(best["l2"], runner["l2"], BOOT_N)
    pt1, lo1, hi1 = gm.paired_bootstrap(best["l1"], runner["l1"], BOOT_N)
    tie = lo <= 0 <= hi
    agree = by_wer[0]["name"] == by_cer[0]["name"]
    verdict = "TIE" if (tie or not agree) else f"{best['name']} wins"
    return [(f"- **{label}**: best by L2 WER = `{best['name']}`, runner-up = `{runner['name']}`. "
            f"WER(best) - WER(runner-up) at L2 = {100 * pt:+.2f} pp, 95% CI [{100 * lo:+.2f}, {100 * hi:+.2f}] pp "
            f"({BOOT_N} paired resamples of {len(best['l2']['err'])} blocks of ~{BLOCK} reference words, seed 12345). "
            f"CI includes 0: **{'yes' if tie else 'no'}**. Best by L2 CER = `{by_cer[0]['name']}` "
            f"(L2 WER and CER {'agree' if agree else 'DISAGREE, treated as a tie'}). **Verdict: {verdict}.** "
            f"For information, L1: {100 * pt1:+.2f} pp, CI [{100 * lo1:+.2f}, {100 * hi1:+.2f}].\n")]


def write_results(out, results, ref, wild, coll, skipped, base, clip_speech, thr, speech, a):
    L = ["# M4 Whisper WER/CER gate: results\n",
         ("**L2 WER is a comparison metric between configs on this lecture, not an absolute accuracy figure. "
         "It must not be quoted as the system's ASR accuracy.**\n"),
         (f"Audio: `{a.audio}` ({results[0]['d']['audio_seconds']:.0f} s). Reference: `{a.reference}` "
         f"({sum(1 for w in wild if not w)} words, {sum(wild)} `[unclear]` wildcards).\n"),
         "## Table\n",
         "| config | L1 WER | L1 CER | L2 WER | L2 CER | L1 S/D/I | L2 S/D/I | dropped speech (longest gap) | Latin share (raw) | warm RTF | peak VRAM | detected language |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        d = r["d"]
        L.append(f"| {r['name']} | {pct(r['l1']['wer'])} | {pct(r['l1']['cer'])} | {pct(r['l2']['wer'])} | {pct(r['l2']['cer'])} | "
                 f"{sdi(r['l1'])} | {sdi(r['l2'])} | {r['drop']['pct']:.1f}% ({r['drop']['longest_gap_s']:.1f}s) | {pct(r['drift']['share'])} | "
                 f"{d['warm_rtf']:.3f} | {d['peak_vram_mib']} MiB | {d['detected_language']} ({d['language_probability']:.3f}) |")
    L += ["", f"Not evaluated: {', '.join(f'{m} x {l}' for m, l in skipped) or 'none'} (large-v3-turbo is not in the offline cache; skipped by decision).",
          "Hypothesis words after the last aligned reference word are excluded (cut tail): "
          + ", ".join(f"{r['name']} {r['l2']['trimmed']}" for r in results) + " tokens (L2 alignment).",
          ("Peak VRAM = max `nvidia-smi` memory.used during the whole run (load + warm-up + transcription) minus the idle baseline "
          f"({base} MiB, includes the Windows desktop). Warm RTF = transcribe seconds / audio seconds after one discarded warm-up run."),
          "", "## Flags (thresholds are starting values; a human confirms disqualification)\n"]
    for r in results:
        L.append(f"- `{r['name']}`: " + ("; ".join(r["flags"]) if r["flags"] else "none"))
    L += ["", "## Bootstrap and tie rule (on L2 WER)\n"]
    clean = [r for r in results if not r["flags"]]
    L += boot_section(results, "all configs", results)
    L += boot_section(results, "unflagged configs only", clean) if clean else ["- unflagged configs: none.\n"]
    L += ["## Dropped speech detail\n",
          f"Independent energy VAD ({gm.VAD}); threshold {thr:.1f} dBFS on this file; speech = {speech.sum() / 100:.0f} s of {len(speech) / 100:.0f} s.\n",
          "| config | speech s | uncovered s | longest uncovered gap | deleted reference runs >= 8 words (L2 alignment) |", "|---|---|---|---|---|"]
    for r in results:
        dr = r["drop"]
        runs_txt = "; ".join(f"ref {x['ref_from']}-{x['ref_to']} ({x['words']} words, audio ~{x['t_from']:.0f}s to ~{('{:.0f}'.format(x['t_to'])) if x['t_to'] is not None else 'end'}s)" for x in r["delruns"]) or "none"
        L.append(f"| {r['name']} | {dr['speech_s']:.0f} | {dr['uncovered_s']:.1f} | {dr['longest_gap_s']:.1f}s | {runs_txt} |")
    L += ["", "## Translation drift (raw output, before romanisation)\n",
          "Reference English-term share: n/a (no English lexicon available; approved). Compared across configs instead.\n"]
    for r in results:
        dfr = r["drift"]
        L.append(f"- `{r['name']}`: {pct(dfr['share'])} of {dfr['words']} words in Latin script. Longest Latin stretches: "
                 + " | ".join(f"{n} words @ {t:.0f}s: \"{txt[:90]}\"" for n, t, txt in dfr["stretches"][:3]))
    L += ["", "## Normalisation\n",
          (f"L2 collision rate on the reference: {coll[1]}/{coll[2]} distinct words = {pct(coll[0])} (see `refwords.py` for the groups). "
          f"Energy VAD speech share on the 30 s clip: {pct(clip_speech)} (see `vad_clip30s.md`).\n"),
          "## Parameters (identical for every config)\n"]
    d0 = results[0]["d"]
    L += [f"- faster-whisper {d0['faster_whisper']}, device {d0['device']}, compute_type {d0['compute_type']}",
          f"- explicit: {d0['fixed_params']}", f"- resulting transcription options: {d0['transcription_options']}",
          f"- VAD options: {d0['vad_options']}", "- warm-up: one discarded transcription of the 30 s clip per run (model loaded once per config subprocess)",
          "- romanisation: uroman, word by word; L1/L2 per `textnorm.py`; alignment per `gate_metrics.py`; CER is computed on space-free strings (exact Levenshtein) after dropping wildcard-absorbed and trimmed tokens"]
    (out / "results.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", out / "results.md")


if __name__ == "__main__":
    main()
