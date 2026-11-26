# Fresh lecture `yt-YyXP7yCfOIU`: labelling runbook

For Bilal (gold labeller, all 48 windows) and Fatima (second annotator, 10 shared windows). Rules: ADR-0048 Amendment 12 (Accepted 26 Nov 2026), the frozen guide `docs/labelling/m7_concepts.md`, and the tool README `tools/label_concepts/README.md`. If this runbook and the amendment disagree, the amendment wins. Stop and ask Claude (a procedure question, never a label) if any step does something this runbook does not describe.

## 0. Facts

| Item | Value |
|---|---|
| Lecture | codebasics Hindi, "Hindi Machine Learning Tutorial 14 - K Means Clustering", workspace `yt-YyXP7yCfOIU` |
| Duration | 1,439.846 s, 48 windows of 30 s (window `i` covers `30·i` to `30·i + 30` s; window 47 is the last) |
| Sample | `tools/label_concepts/labels/yt-YyXP7yCfOIU/sample.json`: census of all 48 windows, seed 20261126, sha256 `1307741c2f97c64b4c8f89bfe2abeeb417e11aad2c5a7c5111a44be2c9c1e6fd` (after `add-annotator`). Never re-run `sample` |
| **Bilal labels** | **all 48 windows, 0 to 47** |
| **Fatima labels** | **the 10 shared windows: 3, 7, 9, 18, 19, 26, 30, 34, 40, 43** |
| Extraction | **held** (job `3c57591e…`). No model output for this lecture exists, and none may exist until the gold is merged and decisions (c) and (e) have Accepted ADRs (Amendment 12, decisions 9 and 10) |

## 1. Never do these

- Do not open, run or look at any model output for this lecture. None exists; keep it that way.
- Do not release the hold (`insightex extract-hold release …`), do not re-add or re-ingest this lecture, and do not run `insightex extract-eval` or anything that runs `extract`.
- Do not open, label or look at anything for `yt-5vqk6HnITko` (the used-up held-out lecture).
- Do not paste window text, transcript text or video into Claude or any other LLM, and never ask any LLM for a label. Guide-rule questions in general terms are allowed and are logged (section 6).
- Do not run `sample` again, and do not edit `sample.json` or any labels file by hand.
- Fatima never opens `bilal.json` (in an editor, the file browser, GitHub or anywhere). Bilal never opens `fatima.json` until both freezes in section 7 are done. Neither discusses any window of this lecture with the other until then.
- Do not run `agreement`, `log-correction` or `merge` yet. They come after you report back to Claude.

## 2. Before every labelling session

The labelling tool is standalone: it reads the workspace's transcript and video directly. It needs **no** worker, **no** API, **no** `dev_run.sh`, **no** lecture player page and **no** Ollama. So none of those should be running: with no API there is no lecture page and no qwen3.5 warm-up. Ollama being open on Windows does no harm (the tool never calls it), but nothing needs it.

Open a WSL terminal (Ubuntu), then:

```bash
cd ~/insightex
pgrep -af "insightex worker|insightex.api|dev_run|uvicorn" | grep -v pgrep || echo "OK: nothing running"
```

If it prints a process instead of `OK: nothing running`, stop it first: `Ctrl+C` in the terminal running it, or `kill -TERM <pid>`. Do not start one.

Every tool command below runs from `~/insightex` through the wrapper `scripts/run_in_env.sh`, which sets `INSIGHTEX_DATA` and activates the venv `~/envs/insightex`. Do not activate the venv by hand. Define the shortcut once per terminal:

```bash
cd ~/insightex
LC="bash scripts/run_in_env.sh python tools/label_concepts/label_concepts.py"
L=yt-YyXP7yCfOIU
```

## 3. Read first (both labellers)

1. The whole guide, `docs/labelling/m7_concepts.md` (Fatima: re-read it in full, especially the explanation rule and canonical names).
2. ADR-0048 Amendment 12, **decision 6 ("Code-only windows")** in `docs/adr/0048-m7-extraction-schema-gold-set-and-gate-rules.md`. It is the only instruction beyond the guide. In short: a window that only talks about writing or running code, with no concept explained or used substantively, gets no concepts and no relations; code names are not concepts by themselves; a concept explained while coding is labelled normally; only the spoken text counts; importance is unchanged.

Also from the guide: label the **text shown** for each window (the audio only helps you read it), relations only when the speaker states or clearly implies them in the window (no quota; when unsure, leave it out), `important` only for an explicit teacher signal (with a cue), and `is_recap` is not labelled.

## 4. Bilal: label all 48 windows

### Start the tool

```bash
cd ~/insightex
LC="bash scripts/run_in_env.sh python tools/label_concepts/label_concepts.py"
L=yt-YyXP7yCfOIU
$LC serve --lecture $L --labeller bilal
```

It prints `labelling yt-YyXP7yCfOIU as bilal: http://127.0.0.1:8765/  (Ctrl+C to stop)` and `labels are saved to …/tools/label_concepts/labels/yt-YyXP7yCfOIU/bilal.json`. Leave that terminal open.

**Open in a browser on Windows (Chrome or Edge): http://127.0.0.1:8765/**. WSL's mirrored networking makes it reachable from Windows. The server listens on 127.0.0.1 only.

**Stop the tool:** `Ctrl+C` in its terminal. Everything already shows "Saved" is on disk.

### In the page

- The window list shows each window with `✓` (saved) or `–` (not yet), and the word `shared` on the 10 shared windows. Use **Previous** / **Next** or click a window.
- **Play window** plays exactly that window's span of the video. Segments that start in the window but run past 30 s are shown in its text and belong to it (guide, "Label the text shown").
- **Add concept** (label + aliases), **Add relation** (head, type, tail; both must be concepts of this window), **Importance** (tick, then write the cue).
- **Saving:** the page saves automatically about half a second after each edit and shows `Saved <time>`. A window with **no concepts** (for example a code-only window) is saved only when you press **Save this window**; press it so the window gets its `✓`. If the status shows `Not saved:` with a reason (for example a relation endpoint that is not a concept, or important without a cue), fix it; an invalid window is not written.

### Partial progress and resuming

- Stop any time with `Ctrl+C`; every window showing `Saved` is in `bilal.json`.
- To resume, run the same `serve` command and reload http://127.0.0.1:8765/. Your saved windows reload with their `✓`.
- Optional local backup between sessions (not a freeze; does not push): `git add tools/label_concepts/labels/$L/bilal.json && git commit -m "fresh lecture: bilal.json in progress"`. Do **not** push before section 7's freezes (it keeps your labels off GitHub while Fatima labels).

### Check you are done

```bash
cd ~/insightex
$LC validate --lecture $L --labeller bilal
```

- While windows are missing it prints `N problem(s)` and `… assigned window(s) not labelled yet: [list]`. Go back and finish (or fix) those windows.
- Done means exactly: `…/bilal.json: valid, 48 windows`.

### If something goes wrong

- **The tool crashes or the page stops responding:** `Ctrl+C`, run `serve` again, reload the page. Only an unsaved edit in progress is lost; check that window again.
- **`serve` refuses to start** (for example "transcript changed since the sample was drawn"): stop and tell Claude. Do not re-sample or edit files.
- **Port 8765 is in use:** another `serve` is still running; stop it with `Ctrl+C` in its terminal (or `pgrep -af label_concepts`, then `kill -TERM <pid>`). Do not run two at once.
- **The video does not play:** reload the page; try the other browser; check the file exists with `ls -la ~/insightex-data/workspaces/yt-YyXP7yCfOIU/stages/normalise/*/video.mp4` (about 58.8 MB). If it still does not play, label from the text as shown (the text is the unit; the audio only helps reading) and record the window index in `labelling.md` (section 6). Do not re-ingest or touch the workspace.
- **The text is unusable** (for example garbled or empty speech recognition): record the window index (no text) in `labelling.md` and label what the text supports, which may be nothing (Amendment 12, recorded properties).

## 5. Fatima: label the 10 shared windows (only after Bilal's freeze, section 7 step A)

Fatima labels on Bilal's machine, in the same tool, which serves **only her own file** (`fatima.json`) and only her 10 windows. She never sees Bilal's labels.

**Bilal, before handing over:** close any editor tab, file browser or terminal that shows `tools/label_concepts/labels/yt-YyXP7yCfOIU/` or a `git` diff or log of it, then start her session and step away (do not watch her screen):

```bash
cd ~/insightex
LC="bash scripts/run_in_env.sh python tools/label_concepts/label_concepts.py"
L=yt-YyXP7yCfOIU
$LC serve --lecture $L --labeller fatima
```

It prints `labelling yt-YyXP7yCfOIU as fatima: http://127.0.0.1:8765/` and that labels go to `…/fatima.json`.

**Fatima:**

1. Read the guide in full and Amendment 12 decision 6 (section 3). No other instruction or examples.
2. Open **http://127.0.0.1:8765/** in the browser. The list shows only windows 3, 7, 9, 18, 19, 26, 30, 34, 40, 43.
3. Label them exactly as in section 4 (autosave; **Save this window** for a window with no concepts; **Play window** for the video).
4. Do not open any file in `tools/label_concepts/labels/`, the repo on GitHub or the git history.
5. Pausing and resuming: `Ctrl+C`, later the same `serve` command, reload the page.
6. Check you are done:

```bash
cd ~/insightex
$LC validate --lecture $L --labeller fatima
```

Done means `…/fatima.json: valid, 10 windows`. Then stop the tool with `Ctrl+C`.

Video or crash problems: as in section 4. Fatima does **not** open `labelling.md` (it may name windows Bilal found unusable). She writes her own notes (unusable-text windows, video problems, guide questions to Claude; indices and general descriptions only) in `docs/evidence/m7/fresh_lecture/labelling_fatima.md`, a new file she creates.

## 6. `docs/evidence/m7/fresh_lecture/labelling.md`

The file exists with empty headings. Write in it, **never window text, transcript text or labels**:

- **Guide-rule questions to Claude:** who asked, the date, the question in general terms (for example "how does the guide treat a window where the speaker only reads out code?"), and which guide rule or decision Claude pointed to. Claude gives rules, never labels. No question about a shared window before both freezes.
- **Unusable-text windows:** window index and one line on why (for example "speech recognition text empty or garbled"), by labeller.
- **Video not playing:** window index, by labeller.
- **Self-containment (Bilal, required):** your confirmation that the lecture introduces k-means itself rather than treating it as taught in an earlier part, with one line of reason (no transcript text). If it is not self-contained, stop labelling and decide whether it is kept (Amendment 12, decision 2).
- **Who labelled what, when:** dates of your sessions; that Fatima labelled without seeing `bilal.json` and that you did not discuss windows.

## 7. Freezes (in this order), then report

### A. Bilal's freeze (when `validate --labeller bilal` prints `valid, 48 windows`)

```bash
cd ~/insightex
LC="bash scripts/run_in_env.sh python tools/label_concepts/label_concepts.py"
L=yt-YyXP7yCfOIU
D=tools/label_concepts/labels/$L
$LC validate --lecture $L --labeller bilal
cp $D/bilal.json $D/bilal_pre_review.json
cmp $D/bilal.json $D/bilal_pre_review.json && echo "byte-identical"
sha256sum $D/bilal.json $D/bilal_pre_review.json
git add $D/bilal.json $D/bilal_pre_review.json docs/evidence/m7/fresh_lecture/labelling.md
git commit -m "Fresh lecture (yt-YyXP7yCfOIU): bilal.json 48 windows valid; bilal_pre_review.json byte-identical copy (ADR-0048 Amendment 12, decision 7)"
git tag m7-fresh-bilal-labels-frozen
```

Do not push yet. From now on `validate` compares `bilal.json` with `bilal_pre_review.json`, so any later change is refused unless it is a logged correction (that comes later, not now). Then do section 5 with Fatima.

### B. Fatima's freeze (when `validate --labeller fatima` prints `valid, 10 windows`)

```bash
cd ~/insightex
LC="bash scripts/run_in_env.sh python tools/label_concepts/label_concepts.py"
L=yt-YyXP7yCfOIU
D=tools/label_concepts/labels/$L
$LC validate --lecture $L --labeller fatima
$LC validate --lecture $L --labeller bilal
sha256sum $D/fatima.json
git add $D/fatima.json docs/evidence/m7/fresh_lecture/labelling_fatima.md   # leave the second path out if Fatima wrote no notes
git commit -m "Fresh lecture (yt-YyXP7yCfOIU): fatima.json 10 shared windows valid; labels frozen before agreement (ADR-0048 Amendment 12, decision 7)"
git tag m7-fresh-labels-frozen
git push
git push origin m7-fresh-bilal-labels-frozen m7-fresh-labels-frozen
```

`m7-fresh-labels-frozen` is the amendment's tag: it covers `bilal_pre_review.json` and `fatima.json` together.

### C. Report to Claude

Send: the two commit hashes, both tags, the three sha256 lines, the two `validate` outputs, and whether `labelling.md` and `labelling_fatima.md` have any entries (counts only, no text). Do **not** run `agreement`, the review (`log-correction`) or `merge`; Claude prepares those next. Nobody looks at the other labeller's file until Claude's next step says so.
