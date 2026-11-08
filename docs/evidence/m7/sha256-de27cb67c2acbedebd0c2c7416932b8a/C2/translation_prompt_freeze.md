# C2 translation prompt freeze (9 Nov 2026)

**Frozen: draft v2,** `config/prompts/m7_translate_v2.txt`, sha256 `dfc9aa5cd90405ac7307bdd6943b84f7a8f019be44bd27c84d4cef82158749a8`. It is pinned in `config/default.yaml` (`extract.translate_prompt_file` / `translate_prompt_sha256`) and tagged `m7-c2-translate-prompt-frozen`. Approved by Bilal on 9 Nov 2026, before any C2 arm B run. No change is made after seeing any C2 output (ADR-0048 section 2 freeze rule; Amendment 8).

**How it was checked** (reserved guide windows 0, 3 and 5 only, which are not in the gold set; `extract-eval translate-check`, Gemma 4 E4B `dc35e8d9…0c9c`, same call rules as a run):

| Draft | sha256 | Gold overlap (3/4/5-word sequences) | Valid (0 / 3 / 5) | Report |
|---|---|---|---|---|
| v1 | `10635f98…0e09` | 0 / 0 / 0 | first attempt, all three | `translate_check/10635f982da5_20261108T223235Z.json` |
| v2 | `dfc9aa5c…49a8` | 0 / 0 / 0 | first attempt, all three | `translate_check/translate_check_v2.json` |

v2 is v1 plus, in rule 2: "Do not add counts, facts or connections that are not in the source. Translate a sentence that starts mid-way as a fragment, without completing it."

## Known limit of arm B (recorded at the freeze)

Bilal and Claude read the three translations against the source. Window 3 is faithful and complete under both drafts. Two errors remain under v2:

1. **Window 0 adds a count.** "تو ہم نے کل الگ لگ types دیکھے" ("so yesterday we saw different types"; "الگ لگ" is an ASR slip for "الگ الگ") is translated as "So we saw **three** types yesterday", followed by a list of four types. The speaker gives no count.
2. **Window 5's opening fragment has the wrong meaning.** The window starts mid-sentence: "use کرتے ہو machine learning کو train کرنے کے لئے, machine learning model کو train کرنے کے لئے", which means "(…that) you use to train machine learning, to train the machine learning model". It is translated as "you use machine learning to train the machine learning model", so machine learning becomes the tool. The rest of the window is faithful.

**Two prompt versions did not change Gemma's output at temperature 0.** v2's added rule targets both errors directly, but under it Gemma reproduced both errors and gave nearly the same text in all three windows (one pronoun changed in window 3, "my" to "our", which fits "اپنے" either way). No v3 was made. C2 measures the C1 winner's own translation, so these errors are part of what arm B is. More tuning on three windows would risk fitting the prompt to them.

Translations are internal (ADR-0041). These were shown to Bilal for the freeze only (Amendment 8, decision 3).
