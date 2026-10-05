# backend/tests

`pytest` from the repo root runs the offline suites (`unit/`). Media fixtures are synthetic clips generated
with ffmpeg at test time; no media is committed. Network tests (`integration/`, marked `network`) are
deselected by default: `pytest -m network` with `INSIGHTEX_TEST_{YT,DRIVE,DIRECT}_URL` set.
