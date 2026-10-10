"""Metrics for the M4 WER gate: alignment, WER/CER, dropped speech, drift, bootstrap.

Standalone (no backend imports). Alignment is word-level Levenshtein (sub=del=ins=1) over the
reference tokens. A reference "[unclear]" span is a wildcard: it absorbs any number of
hypothesis tokens at no cost and counts no errors. The hypothesis tail after the optimal end of
the alignment is free (the reference ends mid-lecture at the audio cut), and its size is reported.
"""
import numpy as np

import textnorm as tn

# --- energy VAD (independent of Whisper's Silero vad_filter) -----------------------------
VAD = dict(frame_ms=25, hop_ms=10, above_noise_db=12.0, noise_percentile=10,
           fill_gap_s=0.3, min_speech_s=0.2, gap_merge_s=0.5)


def energy_vad(audio, sr=16000, p=VAD):
    """Return a boolean speech mask at hop resolution (10 ms)."""
    fl, hop = int(sr * p["frame_ms"] / 1000), int(sr * p["hop_ms"] / 1000)
    n = max(0, (len(audio) - fl) // hop + 1)
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    rms = np.sqrt((audio[idx] ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    thr = np.percentile(db, p["noise_percentile"]) + p["above_noise_db"]
    mask = db > thr
    return fill_runs(mask, int(p["fill_gap_s"] * 1000 / p["hop_ms"]), int(p["min_speech_s"] * 1000 / p["hop_ms"])), thr


def runs(mask):
    """[(start, end)) index runs of True."""
    m = np.concatenate([[0], mask.astype(np.int8), [0]])
    d = np.diff(m)
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def fill_runs(mask, fill, minlen):
    out = mask.copy()
    for a, b in runs(~mask):  # close short non-speech gaps between speech
        if b - a < fill and a > 0 and b < len(mask):
            out[a:b] = True
    for a, b in runs(out):  # drop short speech blips
        if b - a < minlen:
            out[a:b] = False
    return out


def dropped_speech(speech, segments, hop_s=0.01, merge_s=VAD["gap_merge_s"]):
    cov = np.zeros(len(speech), dtype=bool)
    for s in segments:
        cov[int(s["start"] / hop_s):int(np.ceil(s["end"] / hop_s))] = True
    unc = speech & ~cov
    total = speech.sum() * hop_s
    merged = fill_runs(unc, int(merge_s / hop_s), 1)
    gaps = [(a * hop_s, b * hop_s) for a, b in runs(merged)]
    longest = max(((b - a) for a, b in gaps), default=0.0)
    return dict(speech_s=total, uncovered_s=unc.sum() * hop_s, pct=100 * unc.sum() * hop_s / total if total else 0.0,
                longest_gap_s=longest, gaps=sorted(gaps, key=lambda g: g[0] - g[1])[:5])


# --- alignment ----------------------------------------------------------------------------
def align(ref, hyp, wild):
    """ops: (kind, ref_idx, hyp_idx); kind in M S D I W (W = hyp token absorbed by a wildcard)."""
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    ptr = []
    for i in range(1, n + 1):
        r, row, pr = ref[i - 1], [0] * (m + 1), bytearray(m + 1)
        if wild[i - 1]:
            row[0], pr[0] = prev[0], 3
            for j in range(1, m + 1):
                best, c = prev[j - 1], 4
                if prev[j] < best:
                    best, c = prev[j], 3
                if row[j - 1] < best:
                    best, c = row[j - 1], 5
                row[j], pr[j] = best, c
        else:
            row[0], pr[0] = prev[0] + 1, 1
            for j in range(1, m + 1):
                best, c = prev[j - 1] + (r != hyp[j - 1]), 0
                d = prev[j] + 1
                if d < best:
                    best, c = d, 1
                x = row[j - 1] + 1
                if x < best:
                    best, c = x, 2
                row[j], pr[j] = best, c
        ptr.append(pr)
        prev = row
    j = min(range(m + 1), key=lambda k: (prev[k], k)) if n else 0
    trimmed, ops, i = m - j, [], n
    while i > 0 or j > 0:
        c = ptr[i - 1][j] if i > 0 else 2
        if c == 0:
            ops.append(("M" if ref[i - 1] == hyp[j - 1] else "S", i - 1, j - 1)); i -= 1; j -= 1
        elif c == 1:
            ops.append(("D", i - 1, -1)); i -= 1
        elif c == 2:
            ops.append(("I", i - 1, j - 1)); j -= 1  # i-1: the preceding reference word
        elif c == 3:
            i -= 1
        elif c == 4:
            ops.append(("W", i - 1, j - 1)); i -= 1; j -= 1
        else:
            ops.append(("W", i - 1, j - 1)); j -= 1
    ops.reverse()
    return ops, trimmed


def lev(a, b):
    """Exact Levenshtein distance (Myers bit-vector, Python big ints)."""
    if not a or not b:
        return len(a) + len(b)
    m = len(a)
    mask, hi = (1 << m) - 1, 1 << (m - 1)
    peq = {}
    for i, c in enumerate(a):
        peq[c] = peq.get(c, 0) | (1 << i)
    pv, mv, score = mask, 0, m
    for c in b:
        eq = peq.get(c, 0)
        xv = eq | mv
        xh = (((eq & pv) + pv) ^ pv) | eq
        ph = (mv | ~(xh | pv)) & mask
        mh = pv & xh
        if ph & hi:
            score += 1
        elif mh & hi:
            score -= 1
        ph = ((ph << 1) | 1) & mask
        mh = (mh << 1) & mask
        pv = (mh | ~(xv | ph)) & mask
        mv = ph & xv
    return score


def score(ref, hyp, wild, block=50):
    """WER/CER and per-block error counts for one normalisation level."""
    ops, trimmed = align(ref, hyp, wild)
    cnt = {k: sum(1 for o in ops if o[0] == k) for k in "MSDI"}
    n_ref = sum(1 for w in wild if not w)
    # blocks of `block` non-wild reference words
    pos, k = [], 0
    for w in wild:
        pos.append(k // block)
        k += 0 if w else 1
    nb = (k + block - 1) // block
    err, nref = np.zeros(nb), np.zeros(nb)
    for i, w in enumerate(wild):
        if not w:
            nref[pos[i]] += 1
    for kind, ri, _ in ops:
        if kind in "SDI" and ri >= 0:
            err[pos[ri]] += 1
    absorbed = {o[2] for o in ops if o[0] == "W"}
    used = [j for kind, _, j in ops if kind in "MSI" and j >= 0]  # hyp tokens that count
    rc = "".join(t for t, w in zip(ref, wild) if not w)
    hc = "".join(hyp[j] for j in used)
    return dict(ops=ops, trimmed=trimmed, S=cnt["S"], D=cnt["D"], I=cnt["I"], N=n_ref,
                wer=(cnt["S"] + cnt["D"] + cnt["I"]) / n_ref,
                cer=lev(rc, hc) / max(1, len(rc)), err=err, nref=nref, absorbed=len(absorbed))


def deletion_runs(sc, hyp_times, minlen=8):
    """Runs of >= minlen consecutive deleted reference words with the approximate gap in audio time."""
    ops, out, run = sc["ops"], [], []
    flush = lambda: None
    for idx, (kind, ri, hj) in enumerate(ops + [("X", -1, -1)]):
        if kind == "D" and (not run or ri == run[-1][1] + 1):
            run.append((idx, ri))
        elif kind == "I":
            continue
        else:
            if len(run) >= minlen:
                before = next((hyp_times[o[2]][1] for o in reversed(ops[:run[0][0]]) if o[2] >= 0), 0.0)
                after = next((hyp_times[o[2]][0] for o in ops[run[-1][0] + 1:] if o[2] >= 0), None)
                out.append(dict(ref_from=run[0][1], ref_to=run[-1][1], words=len(run), t_from=before, t_to=after))
            run = [(idx, ri)] if kind == "D" else []
    return out


# --- drift ---------------------------------------------------------------------------------
def drift(raw_words):
    """raw_words: [(word, start)] before romanisation. Latin-script share and longest Latin stretches."""
    alpha = [(w, t) for w, t in raw_words if any(c.isalpha() for c in w)]
    lat = [tn.is_latin_word(w) for w, _ in alpha]
    stretches, i = [], 0
    while i < len(alpha):
        if lat[i]:
            j = i
            while j < len(alpha) and lat[j]:
                j += 1
            stretches.append((j - i, alpha[i][1], " ".join(w for w, _ in alpha[i:j])))
            i = j
        else:
            i += 1
    stretches.sort(key=lambda s: -s[0])
    return dict(share=sum(lat) / max(1, len(alpha)), words=len(alpha), stretches=stretches[:5])


# --- bootstrap -----------------------------------------------------------------------------
def paired_bootstrap(sc_a, sc_b, n=10000, seed=12345):
    """Paired block bootstrap of WER(a) - WER(b). Returns (point, lo, hi) with a 95% interval."""
    rng = np.random.default_rng(seed)
    nb = len(sc_a["err"])
    pick = rng.integers(0, nb, size=(n, nb))
    ea, eb, nr = sc_a["err"][pick].sum(1), sc_b["err"][pick].sum(1), sc_a["nref"][pick].sum(1)
    d = (ea - eb) / nr
    point = (sc_a["err"].sum() - sc_b["err"].sum()) / sc_a["nref"].sum()
    return point, float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
