"""Start `insightex worker` with the fake transcriber and fake GPU installed (for tests that spawn real workers).

    python backend/tests/fake_asr_worker.py      same as `python -m insightex.cli worker`, but no Whisper and no GPU
"""

from __future__ import annotations

import sys

from asr_fakes import FakeGpu, FakeTranscriber

from insightex.asr import stage as asr_stage
from insightex.cli import main

if __name__ == "__main__":
    transcriber = FakeTranscriber()
    asr_stage.make_transcriber = lambda settings: transcriber
    asr_stage.gpu_vram = FakeGpu()
    sys.exit(main(["worker"]))
