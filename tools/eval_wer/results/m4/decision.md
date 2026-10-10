# M4 gate: review of the flags (rerun on the full 688 s lecture)

Status: proposed by the tool author, **pending human confirmation**. Numbers: `results.md`. Passages: `flagged.md`, `samples.md`.

| config | outcome | reason |
|---|---|---|
| medium_ur | disqualified | dropped speech 21.9% (threshold 2%), longest uncovered gap 32.1 s. Whisper emits no segment between 375.4 s and 495.4 s (120 s), and the uncovered gaps include 393-424 s, 431-464 s, 477-495 s inside the VAD speech. See `flagged.md`. |
| medium_auto | disqualified | translates. The whole output is Latin script (100%) and the text is English, e.g. 12-16 s: "Okay, so in the last video we read types of machine learning" for the spoken Hinglish "pichle video mein humne types of machine learning padha tha". It ran with `task="transcribe"`. Also 5.1% dropped speech. |
| large-v3_auto | disqualified | dropped speech 5.7% (threshold 2%), longest uncovered gap 10.2 s (threshold 10 s). At 287-298 s the audio was **skipped, not translated**: the segments are [285.5-287.4] and [297.6-299.4] with nothing between, 9% of the VAD speech covered, while large-v3_ur transcribed the same span (47 words, 100% covered). Other skips: 51-60 s (12% covered), 663-672 s (6% covered), and a content drop inside one 17.9 s segment (345.0-362.9 s, ~56 reference words missing). |
| large-v3_ur | **proposed winner** | dropped speech 1.9% (below 2%), longest uncovered gap 1.0 s, no deleted reference run of 8 or more words. The only flag is the Latin-script excess; reading `flagged.md` shows the 65-word Latin stretch at 431-464 s is English the speaker really said, with the same words in the reference. The excess is also not drift relative to large-v3_auto (39.4% vs 40.4%). Flag reviewed and dismissed. |

Tie rule: with large-v3_auto disqualified there is no tie-break. For information only, the L2 WER/CER split between the two large-v3 configs (auto lower WER, ur lower CER) is **structural**: Devanagari romanises with full vowels, Urdu script without short vowels, so L2 favours auto at word level and ur at character level. A second lecture would not resolve it; a choice between scripts is a product decision (target users read Urdu script).

Run-to-run note: medium_ur changed a lot between the 600 s run and the 688 s run (Latin share 66.5% to 5.6%, dropped speech 11.2% to 21.9%), because decoding falls back to sampled temperatures. Both runs were above the threshold. large-v3 run-to-run variation was not measured.
