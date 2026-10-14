# M6 manual browser checklist (ADR-0047)

Browser behaviour is not proved by the automated check (ADR-0038). `tools/m6_verify` already passed 13/13 (see `m6_verify_20261014T173206Z.json`); this list covers what only a person can judge: the page, the click, and what you hear.

**Day 4 link.** No URL was supplied, so the five-question check runs on the uploaded Day 4 file (the lecture the gold spans belong to), and the link path is tested separately with the public canary `https://youtu.be/a7YHpixqiUg` (19 min; its transcript is not judged, only the page behaviour). If you have the Day 4 URL, add it as Part B2 and compare its duration (688 s ±1) and first 20 transcript segments with the upload's before trusting the gold spans on it.

## Setup (a separate data folder, so your real Day 4 workspace is not touched)

Nothing else may use the GPU, and Ollama must have no model loaded (`curl -s localhost:11434/api/ps` prints `{"models":[]}`).

```bash
source ~/insightex/env/insightex_env.sh
export INSIGHTEX_DATA=$HOME/insightex-data/m6_manual
export INSIGHTEX__GPU__LEASE_PATH=$HOME/insightex-data/run/gpu.lock
export INSIGHTEX__API__PORT=8013
source ~/envs/insightex/bin/activate
mkdir -p $INSIGHTEX_DATA && insightex worker 2>>$INSIGHTEX_DATA/worker.stderr.log &
python -m insightex.api          # leave this running; open http://127.0.0.1:8013
```

The API takes about 5 s to start (it loads the question model). To follow the model: `watch -n2 'curl -s localhost:11434/api/ps | head -c 200'`.

## Part A: the page

- [ ] The library is empty. The "Add" area shows the link box and the upload box, each with a language dropdown that starts on a placeholder.

## Part B: link path (canary)

- [ ] Paste `https://youtu.be/a7YHpixqiUg`, press Check link: a preview appears (title, length).
- [ ] Choose a language, tick the rights box, press Add lecture.
- [ ] Progress shows four rows: Download, Convert video and audio, Transcribe, **Prepare for search**, each with a bar; all end "Done"; the title line says "Ready".
- [ ] "Open in player": the video plays; the **ask box is enabled** (it was disabled until the lecture finished).
- [ ] Ask any question about the video (for example "what is this video about"): up to three buttons appear, each reading `Moment N: m:ss–m:ss` and nothing else (no text from the lecture, no number like a score). Pressing one moves the video to that time (the picture jumps; press play).

## Part C: Day 4 upload, then the five questions

- [ ] Go back to the library, upload `~/insightex-data/eval/day04_batch_vs_online/raw/lecture_test.mp4` with language Hindi and the rights box ticked. Progress reaches "Ready" with the same four rows.
- [ ] Open it in the player. Within about 20 s the model loads in the background (`api/ps` lists `qwen3.5:latest`). **Wait until it is listed** before the questions.
- [ ] For each question below: type it exactly, press Ask, pick the citation whose range covers the gold moment, press it, press play and listen. "Expected rank" is where the automated check found a covering citation; yours should match. Tick the first box when the ranked citation list is as expected, the second when you hear the answer being spoken at (or right after) the point the video jumps to.

| Id | Question | Gold moment | Expected rank | List as expected | Heard it |
|---|---|---|---|---|---|
| A01 | `How does the lecturer define "production" in simple terms?` | 0:51–0:59 | 1 | [ ] | [ ] |
| A14 | `Which two types of machine learning will be covered in this video?` | 1:44–1:56 | 2 | [ ] | [ ] |
| A16 | `Why can't a model on a remote device just be refreshed when new data arrives?` | 8:20–8:37, 9:01–9:11, 9:12–9:37 | 3 | [ ] | [ ] |
| A26 | `satellite ya drone par batch learning kyun fail ho jati hai` | 9:12–9:37 | 3 | [ ] | [ ] |
| A19r | `jab data itna bara ho jaye ke tools handle na kar sakein to kya hota hai` | 7:54–8:17 | 2 | [ ] | [ ] |

- [ ] No citation jumps to a place in the middle of a pause or mid-word: each jump lands at the start of a spoken phrase (the citation seeks to the first transcript segment of the window, not the window's grid start).

## Part D: fallbacks and limits

- [ ] **Unloaded model.** In a WSL terminal: `curl -s localhost:11434/api/generate -d '{"model":"qwen3.5:latest","keep_alive":0}'`, then check `api/ps` is empty. Ask the A19r question again. **Results still appear, with no error message.** (They may be different, and the gold moment may be missing: the question was searched without the English rewrite.)
- [ ] **Re-warm.** At least 30 s after you opened the player, ask once more; then within about 30 s `api/ps` lists the model again, without you doing anything. Ask A19r a third time: the gold moment is among the citations again.
- [ ] **Limits.** Press Ask with the box empty: "Type a question first." Paste a 301-character text: a message says the question is too long and how many characters it has, and no request is sent. The counter next to the box shows e.g. `12 / 300`.
- [ ] **Old lecture.** (Needs your real library, not this folder: start the normal `bash ~/insightex/scripts/dev_run.sh` later.) A lecture with no search index shows the ask box disabled and the note "Questions aren't available for this lecture yet." — tick this when you have seen it, or mark "not tried".

## Part E: privacy

- [ ] In another terminal: `grep -ci "batch\|production\|satellite\|kyun" $HOME/insightex-data/m6_manual/logs/api/api.log` prints `0`, and `grep -c "insightex.ask" $HOME/insightex-data/m6_manual/logs/api/api.log` shows one line per question you asked.

## Clean up

Stop the API (Ctrl-C) and the worker (`kill %1`), then `curl -s localhost:11434/api/generate -d '{"model":"qwen3.5:latest","keep_alive":0}'`. The folder `~/insightex-data/m6_manual` can be deleted or kept.

## Sign-off

Signed by: ______________________  Date: ____________  Result: pass / fail (note the failing items above)
