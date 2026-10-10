# tools/gen_languages

**Purpose:** generates `config/languages.yaml`, the list of spoken languages a lecture can be submitted with (ADR-0040).

```bash
bash ~/insightex/scripts/run_in_env.sh python ~/insightex/tools/gen_languages/gen_languages.py --out ~/insightex/config/languages.yaml
```

- One untested entry per language code of the installed faster-whisper (English label from Whisper's own name table), plus the fixed tested entries in `TESTED`. Hindi appears only as its tested entry (`whisper_language: ur`); the code `hi` gets no entry.
- The generated file is committed. Rerun only after a faster-whisper upgrade and review the diff, so the list never changes silently.
- Moving a language between tiers or changing its `whisper_language` is a hand edit of `config/languages.yaml`; no code change. A move to `tested` needs the WER gate in ADR-0040 and an `evidence` ADR.
- `backend/tests/unit/test_languages.py` fails if the committed list no longer matches the installed library.

Standalone: it does not import from `backend/`.
