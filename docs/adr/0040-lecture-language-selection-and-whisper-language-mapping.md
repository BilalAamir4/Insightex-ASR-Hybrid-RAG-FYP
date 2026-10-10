# ADR-0040: Lecture language selection and Whisper language mapping

Status: Proposed
Date decided: 2026-10-10
Date recorded: 2026-10-10
Module: M4

Amends ADR-0039: its language decision ("always `language="ur"`") is replaced by the per-lecture choice below. ADR-0039's checkpoint decision (large-v3), its gate numbers and its limitations stay in force.

## Context

ADR-0039 chose `language="ur"` from a gate on one lecture, Day 4. Day 4 is Hindi with English ML terms. On that lecture `ur` transcribed the speech without skipping any of it, while auto-detect picked `hi` and skipped passages (5.7% dropped speech, a 10.2 s gap). One fixed code for every lecture does not hold up once users bring lectures in other languages: forcing `ur` on English or Pashto speech would ask Whisper to write the wrong language. The gate measured Hindi only, so nothing is known about how well any other language transcribes.

## Decision

- **The user picks the lecture's spoken language** at submission (CLI `--language`, link API `language`, upload header `X-Insightex-Language`, a required dropdown in the UI). There is **no default**, and a missing or unknown id is rejected before anything is staged or queued (`MISSING_LANGUAGE`, `UNKNOWN_LANGUAGE`). The id is stored in the job payload and, once transcribed, in the workspace manifest (`stages.asr.language`).
- **Two tiers, one config file.** `config/languages.yaml` (path `asr.languages_file`) lists every selectable language: `id`, English `label`, `whisper_language`, `tier` (`tested` or `untested`), and `evidence` (required for tested entries, absent otherwise). It is validated at startup of the API, the worker and the CLI (ids unique, every code supported by the installed faster-whisper, tested entries have evidence); a bad file stops startup with a message naming each problem. The file is re-read when it changes, with the same validation; if an edit of a running system is invalid, the last valid list keeps being served and the error and its reason are logged once per edit (a restart would still refuse to start). Moving a language between tiers, or changing its code, is an edit of this file only.
- **Tested at launch: exactly one entry**, `hindi`, label "Hindi (including Hindi-English mixed)", `whisper_language: ur`, evidence ADR-0039 (the gate numbers live there).
- **Untested: every other language the installed faster-whisper supports**, each with its own code and Whisper's English name as the label, Urdu (`ur`) and English (`en`) included. The list is generated once by `tools/gen_languages` from faster-whisper 1.2.1 (100 codes) and committed, so a library upgrade never changes it silently; a test fails if the committed list and the installed library disagree. The code `hi` has no entry of its own: Hindi appears only as the tested entry.
- **Auto-detect is not offered.** It was disqualified in the gate for skipping speech (ADR-0039: large-v3 auto, 5.7% dropped, a 10.2 s gap), which would remove material the knowledge base must be able to cite.
- **Untested lectures are marked in the UI**: the language label plus an "Untested language" badge with the tooltip "Transcription for this language has not been measured; results may be less reliable." The tier shown is read from the current config, so promoting a language updates existing lectures without reprocessing (the tier is not part of the ASR cache key, ADR-0042).
- **Promotion procedure.** A language moves to `tested` only after a WER gate with the `tools/eval_wer` harness on 3 lectures from 3 different speakers, using a 5-minute excerpt from the middle of each lecture; at least one excerpt should have imperfect audio. References follow the existing rules: verbatim, Roman script, English terms in English spelling, `[unclear]` where inaudible. Configs compared: Hindi `ur` vs forced `hi` (Day 4 counts as one Hindi lecture); Urdu `ur` vs auto; English `en` vs auto. Pass rule: the winning config must pass the dropped-speech rule (at most 2% of speech time and no gap of 10 s or longer) on every lecture; among passing configs, the lowest pooled L2 WER across all excerpts wins. The promotion is recorded in a new ADR, which becomes the entry's `evidence`.
- **Evaluation rule.** Lectures processed with an untested language are excluded from thesis evaluation numbers.
- **Future requirement (M11).** When answers exist, an answer that cites a lecture with an untested language shows the same badge.

## Alternatives considered

- **Keep "always `ur`".** Correct for the one measured lecture; wrong code for every non-Hindi/Urdu lecture, with no warning to the user.
- **Auto-detect, or auto-detect as the default.** Disqualified by the gate for dropped speech; a default would also hide the choice from the user.
- **A default language (Hindi).** A lecture submitted without thought would be transcribed with the wrong code and look fine. Forcing a choice costs one click.
- **Offer only tested languages.** Would refuse every non-Hindi lecture until a gate is run for its language; marking them untested keeps them usable and honest.
- **Hand-write the untested list.** Error-prone (100 codes) and can drift from the installed library; generating and committing it is checkable.

## Consequences

- Every submitter (UI, API, CLI, tools) must send a language. Existing callers were updated to send `hindi`.
- Submitting the same file in another language runs ASR again; the new transcript replaces the old one (ADR-0042).
- `config/languages.yaml` is a reviewed artifact: regenerate it only after a faster-whisper upgrade and review the diff.
- Workspaces from before this change have no transcript and no language; the UI shows "Not transcribed. Add it again and choose its language."

## Evidence

- Gate numbers for Hindi → `ur`: ADR-0039 and `tools/eval_wer/results/m4/`.
- Generator: `tools/gen_languages/gen_languages.py`; config: `config/languages.yaml`; validation and tests: `backend/src/insightex/asr/languages.py`, `backend/tests/unit/test_languages.py`, `backend/tests/api/test_languages_api.py`.
- End-to-end check: `tools/m4_verify` (checks 1, 11, 12) and `docs/evidence/m4/`.

## Gate / revisit when

Accepted when the M4 session 2 verification passes (`tools/m4_verify` checks 1, 11 and 12) and the human completes `docs/evidence/m4/manual_checklist.md` (dropdown, groups, badge). Revisit a language's tier whenever its promotion gate is run; revisit the whole design if auto-detect is re-measured and passes the dropped-speech rule.
