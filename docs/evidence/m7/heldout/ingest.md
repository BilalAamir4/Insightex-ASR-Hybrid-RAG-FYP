# M7 held-out lecture: ingest record (handoff 4, step 2)

13 Nov 2026. Counts and ids only: no transcript or window text was printed or read by anyone (ADR-0048 section 3; the gold is not yet labelled). `extract-eval` was not run.

## The job

- **Submitted:** `POST /api/ingest/link` with `{"url": "https://youtu.be/5vqk6HnITko", "rights_confirmed": true, "language": "hindi"}`, on Bilal's instruction.
- **Ids:** job `2cfefab5d04c4d8787b31997a5122830`, workspace **`yt-5vqk6HnITko`**.
- **Timeline** (local time):

  | Stage | Start | End |
  |---|---|---|
  | `fetch` | 20:11:41 | 20:12:54 |
  | `normalise` | 20:12:54 | 20:13:09 |
  | `asr` | 20:13:09 | 20:16:05 |
  | `index` | 20:16:05 | 20:16:19 |

  The job succeeded with no warnings.
- **Language:** `hindi` (Whisper `ur`), tier `tested` at processing.
- **Before the job:** `ollama ps` showed no model loaded; GPU memory was 1,755 MiB (desktop baseline). Ollama 0.40.2, `check_ollama_frozen.py` OK.

## Counts

| Item | Value |
|---|---|
| `transcript.json` | present |
| Segments | 1,148 |
| Duration | 1,414.838 s |
| 30 s grid slots | 48 |
| Non-empty windows (the sampler's grid, `tools/label_concepts/grid.py`) | **48** |
| `windows.json` (index stage) | present, 48 windows |
| Sampler grid vs `windows.json` | match |
| At least 40 non-empty windows (selection rule) | **yes** |

Sampling 40 of 48 windows leaves 8 out (`selection.md`, near-census).

## ASR shape (numbers only, compared with Day 4; no WER measured)

| | Held-out `yt-5vqk6HnITko` | Day 4 `sha256-de27…` |
|---|---|---|
| Segments | 1,148 | 351 |
| Time covered by segments | 1,298 of 1,414 s | 667 of 688 s |
| Median segment duration | 1.02 s (0.08–7.87) | 1.94 s (0.54–3.62) |
| Characters per second | 14.3 | 16.6 |
| Distinct segment texts | 936 of 1,148 | 351 of 351 |
| Consecutive identical segments / longest identical run | 6 / 2 | 0 / 1 |
| Median `avg_logprob` | −0.139 | −0.101 |
| Segments with `no_speech_prob` > 0.5 | 15 | 58 |

- **No sign of a repetition loop:** the longest run of identical segments is 2.
- **Shorter segments:** the held-out transcript has segments about half as long as Day 4's.
- **Repeated texts:** 212 segment texts repeat somewhere in the lecture; what they are was not looked at.
- **Quality is unmeasured:** there is no WER reference for this lecture. Bilal will see the transcript's quality only through the windows he labels.
