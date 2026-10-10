# M4 session 2: manual checklist

For the human reviewer. Fill in each **Result** line (PASS / FAIL and a note), then approve at stop point 2. ffmpeg-based checks do not prove what a person sees and hears (ADR-0038), so these are done by hand.

Setup: `bash ~/insightex/scripts/dev_run.sh` (worker + API on 127.0.0.1:8000), browser on http://127.0.0.1:8000. For the VLC item, run `tools/m4_verify/m4_verify.py --keep` first, or submit Day 4 with `hindi` in the real library.

## 1. Subtitles in time with speech (VLC)

Open the workspace `video.mp4` (`stages/normalise/<key>/video.mp4`) in VLC and load `transcript.vtt` (`stages/asr/<key>/transcript.vtt`) of the same workspace as subtitles (Subtitle > Add Subtitle File). Check that subtitles appear in time with the speech at about:

- 0:15 — Result: PASS. Subtitles appear in time with speech.
- 4:47 — Result: PASS. Subtitles appear in time with speech.
- 7:15 — Result: PASS. Subtitles appear in time with speech.
- the last minute — Result: PASS. Subtitles appear in time with speech.

## 2. Language dropdown (browser)

On the home page, for **both** the upload form and the link form (paste a link and press "Check link" to see the link form):

- The language dropdown is required: Upload / Add lecture stays disabled until a language is chosen, even with a file or link and the rights box ticked. — Result: PASS (both forms).
- It has no preselected value: it shows "Select the lecture's language". — Result: PASS (both forms).
- "Tested" lists only "Hindi (including Hindi-English mixed)". — Result: PASS (both forms).
- "Not tested — transcription quality unknown" lists the other languages alphabetically. — Result: PASS (both forms).
- Submitting without choosing a language is blocked. — Result: PASS (both forms).

## 3. Language label and badge (browser)

- Job progress view and library: a Hindi job/lecture shows "Language: Hindi (including Hindi-English mixed)" with **no** badge. — Result: PASS.
- A job/lecture added with English (for example the 30 s clip, or any short video submitted as English) shows "Language: English" **with** the "Untested language" badge; hovering (or focusing with Tab) shows "Transcription for this language has not been measured; results may be less reliable." — Result: PASS. Badge and tooltip shown on hover and on Tab focus.
- The player page shows the same label (and badge for English). — Result: PASS.

## 4. Lecture from before this change (browser)

The existing Day 4 lecture in the real library (`sha256-de27cb67c2acbedebd0c2c7416932b8a`, normalised before M4 session 2, no transcript) shows "Not transcribed. Add it again and choose its language." in place of the language label, with no badge and no error, in the library and on its player page. Do this **before** re-adding Day 4 to the real library. — Result: PASS. Checked in the library and on the player page before re-adding Day 4.

## Approval

Reviewer: Bilal Aamir  Date: 2026-10-10  All items PASS / notes: All items PASS. No issues found.
Lease unloading Ollama before ASR: not exercised in M4 (Ollama not loaded during the run).
