# tools/label_concepts

**Purpose:** build the M7 gold set (ADR-0048). The tool samples a lecture's 30 s windows, gives you a browser page to label them (concepts with aliases, relations, importance and cue), validates the labels files, measures agreement on the shared windows, and merges the gold file. Since ADR-0048 Amendment 1 (17 Oct 2026) there is one labeller, Bilal: agreement is his intra-rater consistency (`bilal` against a blind repeat, `bilal_repeat`), and the gold file is his finished labels. Two-labeller mode (`fatima`, `consensus`) still works if a second labeller joins. It does no extraction and makes no LLM calls. Labelling rules: `docs/labelling/m7_concepts.md`.

**Standalone:** the tool imports nothing from `backend/`. It reads the lecture workspace directly: `$INSIGHTEX_DATA/workspaces/<lecture_id>/manifest.json`, the `asr` stage's `transcript.json` and the `normalise` stage's `video.mp4`. Two kinds of file are kept in step with production:

- **The schema files are a copy.** `extraction_schema.py` and `extraction.schema.json` are byte-identical copies of `backend/src/insightex/extract/` (extraction schema v1). Edit the production files, then copy them here. `backend/tests/unit/test_extraction_schema.py` fails while the copies differ.
- **The window grid is reimplemented** in `grid.py` and must match ADR-0045 and the index stage (`insightex/windows/build.py`, `build_windows`): a fixed 30 s grid with a 30 s stride; each segment goes to the window its start falls in; empty windows are dropped; window ids count only the kept windows. When the lecture has an index stage, `sample` compares the two windows by windows (ids, times and text) and refuses to run on any difference.

## Commands

Run from the repo root (`~/insightex`). The commands use the standard library only; the wrapper just provides Python 3.12 and `INSIGHTEX_DATA`.

```bash
LC="bash scripts/run_in_env.sh python tools/label_concepts/label_concepts.py"
DAY4=sha256-de27cb67c2acbedebd0c2c7416932b8a

# 1. Sample (once per lecture; commit the manifest). Day 4: census of 20 windows, guide examples 0, 3, 5 reserved.
$LC sample --lecture $DAY4 --n 40 --shared 10 --seed 7 \
    --exclude "0=guide example: passing mention, not labelled" \
    --exclude "3=guide example: explicit importance cue" \
    --exclude "5=guide example: stated relation (contrasts_with)"
#    (Day 4 was drawn for bilal + fatima, then reassigned to bilal alone on 17 Oct 2026, see below.)
#    Held-out lecture (once chosen; one labeller is the default): $LC sample --lecture <id> --n 40 --shared 10 --seed 7

# 2. First pass, then open http://127.0.0.1:8765/ (the machine must hold the lecture's workspace); validate, commit
$LC serve --lecture $DAY4 --labeller bilal
$LC validate --lecture $DAY4 --labeller bilal

# 3. (Day 4 only) the one guide rule update. 4. Revise everything and finish the remaining windows; validate
#    until it prints "valid"; commit bilal.json
$LC serve --lecture $DAY4 --labeller bilal
$LC validate --lecture $DAY4 --labeller bilal

# 5. At least 2 days later: blind repeat of the 10 shared windows (do not open bilal.json), validate, commit
$LC serve --lecture $DAY4 --labeller bilal_repeat
$LC validate --lecture $DAY4 --labeller bilal_repeat

# 6. Consistency figure (string rule only, on the finished bilal.json); commit the report
$LC agreement --lecture $DAY4 --a bilal --b bilal_repeat

# 7. Merge (gold = bilal.json alone); commit
$LC merge --lecture $DAY4
```

### Session 2: scoring model runs

The model runs come from `insightex extract-eval run` (production code, `backend/src/insightex/extract/`), which writes one run directory per arm: `extraction.json` (schema v1, `producer.kind = model`, the windows that came out valid) and `run.json` (per window: valid after at most one retry, the attempt used, relations dropped as dangling). These commands read only those files, `gold.json` and `adjudications.json`.

```bash
RUNS=docs/evidence/m7/$DAY4/C1
# 8. Blind adjudication sheet: unmatched model concepts of every arm in the comparison, pooled, deduplicated and
#    shuffled with a recorded seed; no arm is shown. Concepts that already have a decision are left out.
$LC adjudication-sheet --lecture $DAY4 --comparison C1 --arm qwen=$RUNS/qwen --arm gemma=$RUNS/gemma
# 9. Decide every entry in the terminal: a gold concept's number, n = no match, s = skip, q = quit. Each answer is
#    appended to adjudications.json at once; an entry is never changed. Commit adjudications.json and the sheet.
$LC adjudicate --lecture $DAY4 --sheet tools/label_concepts/labels/$DAY4/adjudication_sheets/C1-<time>.json
# 10. The ADR-0048 section 7 decision (arm A is the one a tie keeps); refuses while any concept is undecided
$LC compare --lecture $DAY4 --comparison C1 --a qwen=$RUNS/qwen --b gemma=$RUNS/gemma
#     Scores alone (also for one arm, e.g. the held-out run): $LC score --lecture <id> --arm NAME=RUN_DIR
```

- **Validity first:** an arm with any gold window lacking a valid record is rejected whatever its score; if both arms fail, `compare` gives no decision (fix the validation or retry handling, freeze a new prompt, re-run both).
- **Primary figure:** micro concept P/R/F1 with adjudication. Wins per window use the adjudicated per-window F1 (1.0 when both sides are empty). Net wins of 2 or fewer is a tie and keeps arm A. B is adopted only with net wins of 3 or more and a micro F1 that is not lower.
- **Also reported:** string-rule-only P/R/F1, relation P/R/F1, importance P/R, dropped relations and retried windows.
- **Consistency figure:** `bilal` against `bilal_repeat` on the shared windows, string rule only. It appears only in the report's `headline_string_rule` block, next to the model's string-rule-only F1 (on all gold windows and on those shared windows), and is described as single-annotator intra-rater consistency. The adjudicated F1 is never put next to it.
- The console shows counts and metrics only, never concept labels. Labels are in the JSON reports (`compare_<C>.json`, `score.json`, next to the run directories).

Two labellers (if one joins later): sample with `--labellers bilal fatima`, label with `--labeller fatima --port 8766`, measure `agreement --a bilal --b fatima`, enter the agreed shared windows with `--labeller consensus`; `merge` then takes the shared windows from `consensus.json` and the rest from each labeller.

`reassign --lecture <id> --labellers <name> ... --note TEXT` changes who labels which window without re-sampling (same windows, order, seed and shared flags). It appends the change to `amendments` in `sample.json` with the previous manifest's sha256 and the newly assigned windows. Labels files made against an earlier manifest in that chain stay valid, and `serve` writes the current sha256 on the next save. Day 4 was reassigned to `bilal` alone this way (ADR-0048 Amendment 1).

- `sample`:
  - refuses a lecture transcribed with an untested language (ADR-0040; `--allow-untested` for trials only);
  - refuses to overwrite `sample.json` (`--force` exists only for the case where no labelling has started);
  - when N is at least the number of eligible windows, the sample is the census and the manifest says so.
- `serve`:
  - binds 127.0.0.1 only and saves each window as you edit it, atomically;
  - rejects an invalid window with the reason, for example a relation endpoint that is not a concept of the window, or an important flag without a cue;
  - refuses to start if the transcript changed since the sample was drawn;
  - "Play window" plays exactly the window's span.
- `serve` accepts a name from the manifest, `<name>_repeat` (that labeller's shared windows, for the blind repeat), or `consensus`.
- `agreement` takes `--adjudications <file>`. The default uses the string rule only, which is how the consistency figure (or, with two labellers, the human ceiling) is reported.

## Files

All under `labels/<lecture_id>/`, committed:

| File | Content |
|---|---|
| `sample.json` | The manifest: seed, N, grid parameters and an index-match check; the transcript's asr key and language; excluded windows with reasons; the census flag; per window its index, start/end, text sha256, shared flag and assignment; `amendments` (reassignments, each with the previous sha256). No transcript text. |
| `<labeller>.json` | One extraction document (schema v1, `producer.kind = human`) per labeller; `bilal_repeat.json` for the blind repeat of the shared windows; with two labellers, `consensus.json` for the agreed shared windows. |
| `agreement_<a>_<b>.json` | Per-window and micro concept, relation and importance agreement, with the sha256 of both inputs. |
| `adjudications.json` | Session 2 onward: frozen match/no-match decisions for unmatched model concepts (ADR-0048), keyed by (window_index, normalised model label). Append-only: each entry records who decided, when, and the sha256 of the sheet it came from. |
| `adjudication_sheets/<C>-<time>.json` | One blind sheet per adjudication round: seed, gold sha256, the sorted sha256 of the arm files (no arm names), and the shuffled entries (window, model concept with aliases, the window's gold concepts). |
| `gold.json` | The merged gold set. One labeller: that labeller's finished file, every window. Two: consensus for the shared windows, each labeller's own windows for the rest. |

## Modules

| Module | Role |
|---|---|
| `label_concepts.py` | The CLI. |
| `grid.py` | Workspace access and the grid. |
| `sampling.py` | Seeded stratified sample, shared windows, assignment and reassignment. |
| `matching.py` | ADR-0048 concept and relation matching, adjudication and micro P/R/F1. |
| `scoring.py` | Session 2: loads arm runs, the validity rule, per-arm scores (adjudicated and string rule), the section 7 comparison. |
| `adjudication.py` | Session 2: the blind adjudication sheet and the append-only adjudications file. |
| `server.py` | The HTTP server. |
| `static/` | The page. |

## Tests

`tests/` run with the main suite (`pytest`; `testpaths` in `pyproject.toml`). They cover:

- sampling determinism and stratification;
- census and exclusions;
- schema validation, cross-checked against the JSON Schema with `jsonschema`;
- the matching rule cases;
- a toy agreement and merge;
- the server's save, reject and video range responses;
- scoring, the comparison rule (tie, adoption, validity), the adjudication sheet (pooling, dedupe, seed, no arm names) and append-only decisions, and a full sheet -> adjudicate -> compare run with the consistency figure.

All fixtures are synthetic.

**Status:** built in M7 Session 1 (15 Oct 2026); scoring and adjudication added in Session 2a (17 Oct 2026), tested on synthetic fixtures only.

The page was not checked in a browser in Session 1: the HTTP endpoints were tested, including byte ranges on the real Day 4 video. Before relying on the page, check it by hand: the video seeks to the window and stops at its end, and the Urdu text displays correctly.
