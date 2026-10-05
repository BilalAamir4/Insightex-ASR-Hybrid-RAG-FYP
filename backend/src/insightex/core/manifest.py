"""Per-lecture manifest.json: the output contract of ingestion, written atomically at every status change."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"
# mkstemp creates 0600; published files must be readable by whatever serves them (not umask-dependent).
FILE_MODE = 0o644
SCHEMA_VERSION = 1

STATUSES = ("probed", "downloading", "transcoding", "ready", "failed")
# Forward-only pipeline; any non-terminal status may fail. "ready" and "failed" are terminal.
_TRANSITIONS = {
    "probed": {"downloading", "failed"},
    "downloading": {"transcoding", "failed"},
    "transcoding": {"ready", "failed"},
    "ready": set(),
    "failed": set(),
}
IN_PROGRESS = frozenset({"probed", "downloading", "transcoding"})


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class ManifestError(Exception):
    pass


@dataclass
class Manifest:
    lecture_id: str
    canonical_id: str
    source_type: str
    source_url: str
    normalized_url: str
    rights_confirmed: bool
    status: str = "probed"
    title: str | None = None
    uploader: str | None = None
    duration_s: float | None = None
    error: dict[str, str] | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    # {codec, width, height, fps} of video.mp4
    video: dict[str, Any] | None = None
    # {sample_rate, channels, codec} of audio.wav
    audio: dict[str, Any] | None = None
    # "remux" | "transcode"
    processing: str | None = None
    # Paths relative to the lecture folder; null until the file exists.
    files: dict[str, str | None] = field(
        default_factory=lambda: {"video": None, "audio": None, "thumbnail": None, "source": None}
    )
    external_timestamp_url_template: str | None = None
    schema_version: int = SCHEMA_VERSION

    def set_status(self, status: str) -> None:
        if status not in STATUSES:
            raise ManifestError(f"unknown status {status!r}")
        if status not in _TRANSITIONS[self.status]:
            raise ManifestError(f"illegal status transition {self.status} -> {status}")
        self.status = status
        self.updated_at = utc_now()

    def fail(self, code: str, message: str) -> None:
        if self.status != "failed":
            self.set_status("failed")
        self.error = {"code": code, "message": message}
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def write_manifest(lecture_path: Path, manifest: Manifest) -> Path:
    """Write via a temp file in the same directory, fsync, then os.replace (atomic on POSIX)."""
    lecture_path = Path(lecture_path)
    target = lecture_path / MANIFEST_NAME
    fd, tmp = tempfile.mkstemp(prefix=".manifest.", suffix=".tmp", dir=lecture_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            os.fchmod(f.fileno(), FILE_MODE)
            json.dump(manifest.to_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    dir_fd = os.open(lecture_path, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return target


def read_manifest(lecture_path: Path) -> Manifest | None:
    """The manifest, or None if absent or unreadable (callers treat unreadable as interrupted)."""
    path = Path(lecture_path) / MANIFEST_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Manifest.from_dict(data)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError):
        return None
