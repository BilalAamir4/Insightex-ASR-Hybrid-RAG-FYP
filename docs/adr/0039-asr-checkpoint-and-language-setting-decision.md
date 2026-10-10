# ADR-0039: ASR checkpoint and language setting: large-v3 with `language="ur"`

Status: Proposed
Date decided: not decided; pending human confirmation of the gate results
Date recorded: 2026-10-10
Module: M4

Supersedes ADR-0014 once Accepted.

## Context

ADR-0014 left the Whisper checkpoint and language open, and two earlier notes conflicted: one said auto-detect beat forced `ur` because forcing dropped lines; the other said `ur` was forced because auto-detect produced Devanagari. The gate in `tools/eval_wer` (M4 session 1) tests medium and large-v3, each with `ur` forced and with auto-detect, on the Day 4 lecture ("100 days of ML", batch vs online learning, 688 s, Hindi with English ML terms) against `manual_roman.txt`, typed by a human while listening. large-v3-turbo was **not evaluated**: it is not in the offline cache and no download was approved.

The old Gemini-transliteration pipeline numbers (Whisper Urdu script, Gemini transliteration, hand-fixed spelling) are **superseded** by this gate and are not comparable.

## Decision

Proposed: **large-v3 (`Systran/faster-whisper-large-v3`), `language="ur"`, `task="transcribe"`, float16**. Pending human confirmation.

Method summary: faster-whisper 1.2.1, beam 5, `vad_filter=True`, `word_timestamps=True`, other parameters at library defaults (listed in `results.md`); each config in its own subprocess after one discarded warm-up; uroman romanisation; L1 and L2 normalisation (L2 decides, frozen at commit `c883b9e`); word alignment with exact CER; independent energy-VAD dropped-speech check; Latin-script drift check; paired block bootstrap for ties. Everything is in `tools/eval_wer/results/m4/` and reruns with one command (`tools/eval_wer/README.md`).

| config | L1 WER | L2 WER | L2 CER | dropped speech (longest gap) | Latin share | warm RTF | peak VRAM | outcome |
|---|---|---|---|---|---|---|---|---|
| medium ur | 92.9% | 68.4% | 47.3% | 21.9% (32.1 s) | 5.6% | 0.240 | 3294 MiB | disqualified: dropped speech |
| medium auto | 67.6% | 67.6% | 53.0% | 5.1% (2.1 s) | 100% | 0.049 | 2974 MiB | disqualified: translates to English |
| large-v3 ur | 57.7% | 24.7% | 6.6% | 1.9% (1.0 s) | 39.4% | 0.119 | 4638 MiB | proposed winner |
| large-v3 auto | 27.9% | 18.2% | 11.1% | 5.7% (10.2 s) | 40.4% | 0.180 | 5310 MiB | disqualified: dropped speech |

Reasons are in `results/m4/decision.md`, with the passages in `flagged.md`. In short:
- medium ur emits no segments for long stretches of speech (for example 375-495 s).
- medium auto detects `hi` and then writes English translations although `task="transcribe"`.
- large-v3 auto skips speech without translating it (for example 287-298 s, where large-v3 ur transcribes 47 words) and loses content inside a long segment (345-363 s).
- large-v3 ur passes the dropped-speech thresholds (2% of speech time, 10 s gap). Its Latin-script flag was reviewed and dismissed: the long Latin stretches are English the speaker said.

**The earlier conflict is resolved.** "Forcing `ur` dropped lines" is what medium `ur` does; large-v3 `ur` does not show it. "Auto-detect produced Devanagari" is true for large-v3 auto (detected `hi`), and medium auto avoids it only by translating.

L2 WER and CER disagree between the two large-v3 configs (auto lower WER, ur lower CER); with large-v3 auto disqualified no tie-break is needed. For information only, the paired bootstrap on L2 WER (large-v3 auto minus large-v3 ur) was -6.48 pp, 95% CI [-11.68, -0.50].

## Alternatives considered

- Medium: disqualified as above.
- Auto-detect on large-v3: lower L2 WER, but 5.7% dropped speech and a 10.2 s skipped span; it would silently remove material that the knowledge base must be able to cite.
- large-v3-turbo: not evaluated (not cached, no download approved). It can be tested later with the same command.

## Consequences

- The ASR stage (M4 session 2) transcribes in native script: Urdu script for Hindi/Urdu speech, with English terms in either script, as Whisper writes them. This matches the existing rule to embed native-script Whisper text and never Roman Urdu.
- Peak VRAM is about 4.6 GiB above the 1.5 GiB Windows baseline in this measurement, so large-v3 fits alone on the 8 GB GPU; the GPU contract (one CUDA stage at a time) still applies.
- Mixed-script output is expected: about 40% of the words in this lecture are written in Latin script.

## Limitations

**Read before quoting any number.**

1. **L2 WER is a comparison metric between configs on this lecture, not an absolute accuracy figure. It must not be quoted as the system's ASR accuracy in reports.**
2. **L2 key collisions push WER down.** 78 of 555 distinct reference words (14.1%) share their L2 key with a different reference word. Largest groups (key: words, reference tokens):

   | key | words | tokens | members |
   |---|---|---|---|
   | bnA | 3 | 8 | banaya x6, bana x1, banana x1 |
   | fr | 3 | 11 | fir x9, for x1, four x1 |
   | kA | 3 | 27 | kya x14, ka x10, kiya x3 |
   | krtE | 3 | 16 | karte x13, karwate x2, karate x1 |
   | mn | 3 | 45 | mein x35, main x7, man x3 |
   | nO | 3 | 10 | now x4, no x4, new x2 |
   | I | 2 | 5 | i x4, ayi x1 |
   | br | 2 | 9 | bar x8, bhar x1 |
   | bt | 2 | 19 | but x15, bat x4 |
   | cld | 2 | 4 | could x3, caled x1 |
   | dE | 2 | 2 | day x1, de x1 |
   | dn | 2 | 4 | don x2, down x2 |
   | dtA | 2 | 38 | data x36, deta x2 |
   | gs | 2 | 2 | guys x1, guess x1 |
   | hI | 2 | 16 | hi x15, hui x1 |

   `kya`/`ka` (27 tokens) is the main meaningful collision; `fir`/`for`/`four` and `but`/`bat` are the others. The rules are frozen and were not tuned after seeing results.
3. **English terms written in Urdu script do not fully match the English-spelled reference** (for example `machine` gives `mcnE` in the reference but `mshn` from the Urdu-script `مشین`). This pushes the WER of `ur` configs up, while the collisions above push it down. The two effects are not separated.
4. **The WER/CER split between scripts is structural.** Devanagari romanises with full vowels and Urdu script omits short vowels, so L2 favours auto-detect at word level and `ur` at character level. A second lecture would not resolve it. The choice between scripts is a product decision (target users read Urdu script).
5. One lecture, one speaker, one run per config. medium `ur` changed a lot between two runs (sampled temperature fallback); large-v3 run-to-run variation was not measured.
6. The reference is human-typed and not time-aligned; its English/Hindi spelling choices are the author's. It has no `[unclear]` markers, so the wildcard path in the aligner was only tested on synthetic data.
7. The Latin-script drift check has no reference English share (no lexicon was available); it compares configs and lists the longest Latin stretches for human reading.
8. The audio was extracted with the M2 normaliser's audio arguments directly from the source mp4, not through the full `normalise_media` path (no `video.mp4`). Word error rates do not depend on this; timestamps may differ slightly from a normalised workspace.
9. The energy VAD is a crude independent check. Its threshold (noise floor + 12 dB) classes 94% of the lecture as speech.

## Evidence

`tools/eval_wer/results/m4/`: `results.md`, `decision.md`, `flagged.md`, `samples.md`, `vad_clip30s.md`, per-config `raw.json`, `romanised.txt`, `normalised_l1.txt`, `normalised_l2.txt`, and `preview_stop1/` (the stop-point-1 raw outputs showing medium auto translating). Code: commits `3abb0b5`, `c883b9e` (frozen L2 rules), `c028253` and later on branch `m4-s1-wer-gate`.

## Gate / revisit when

Revisit if large-v3-turbo is added to the cache and tested, if a second lecture shows large-v3 `ur` dropping speech, or if the product chooses Roman or Devanagari output. Accepting this ADR needs the human to confirm the disqualifications in `decision.md`.
