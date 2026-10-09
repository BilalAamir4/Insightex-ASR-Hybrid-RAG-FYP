# backend/tests

`pytest` from the repo root runs the offline suites (`unit/`). Media fixtures are synthetic clips generated
with ffmpeg at test time; no media is committed. Network tests (`integration/`, marked `network`) are
deselected by default: `pytest -m network` with `INSIGHTEX_TEST_{YT,DRIVE,DIRECT}_URL` set.

Media suite: `pytest -m media` builds a synthetic corpus with ffmpeg (`media_corpus.py`) and runs the real normalise engine on it (about 35 s). A missing encoder skips the affected case with its name. `pytest -m 'not media'` leaves it out.
