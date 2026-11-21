"""Start `insightex worker` with the fake transcriber, encoder, extraction client and GPU installed (for tests that
spawn real workers).

    python backend/tests/fake_asr_worker.py      same as `python -m insightex.cli worker`, but no Whisper, no GPU, no Ollama
"""

from __future__ import annotations

import sys

from asr_fakes import FakeEncoder, FakeGpu, FakeTranscriber
from extract_fakes import FakeExtractClient

from insightex.asr import stage as asr_stage
from insightex.cli import main
from insightex.extract import stage as extract_stage
from insightex.index import stage as index_stage

if __name__ == "__main__":
    transcriber = FakeTranscriber()
    asr_stage.make_transcriber = lambda settings: transcriber
    gpu = FakeGpu()
    asr_stage.gpu_vram = gpu
    index_stage.make_encoder = lambda settings: FakeEncoder()
    index_stage.gpu_vram = gpu
    client = FakeExtractClient()
    extract_stage.make_client = lambda settings: client
    extract_stage.gpu_vram = gpu
    extract_stage.vram_used = lambda: 1000
    sys.exit(main(["worker"]))
