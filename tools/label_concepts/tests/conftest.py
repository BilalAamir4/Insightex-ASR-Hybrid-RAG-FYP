"""Tests for tools/label_concepts. The tool is standalone (no package), so its directory goes on sys.path."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
