"""Staging area for local-file ingest: `<ingest.file.staging_dir>/<uuid>.part` (ADR-0036).

The user's file is only ever read. It is copied here while its SHA-256 is computed, fsynced and renamed,
so a job never sees a half-written copy. The `fetch` stage of an `ingest_file` job adopts the copy and
deletes it once the stage is published. A user-supplied file name is display text; it never reaches a path.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from insightex.core.config import Settings
from insightex.jobs import store

log = logging.getLogger(__name__)

STAGED_NAME_RE = re.compile(r"^[0-9a-f]{32}\.part$")
_DISPLAY_NAME_MAX = 200


@dataclass(frozen=True)
class StagedFile:
    name: str  # "<uuid>.part"
    path: Path
    size_bytes: int
    sha256: str


def staging_dir(settings: Settings) -> Path:
    return settings.ingest.file.staging_dir


def staged_path(settings: Settings, name: str) -> Path:
    """Path of a staged copy by name; raises ValueError unless `name` is exactly `<32 hex>.part`."""
    if not isinstance(name, str) or not STAGED_NAME_RE.match(name):
        raise ValueError(f"invalid staged file name {name!r}")
    return staging_dir(settings) / name


def sanitise_filename(name: str | None) -> str | None:
    """A file name safe to show: base name only, control characters removed, length capped. Never used in a path."""
    if not name:
        return None
    base = re.split(r"[\\/]", name)[-1]
    base = "".join(ch for ch in unicodedata.normalize("NFC", base) if unicodedata.category(ch)[0] != "C").strip()
    return base[:_DISPLAY_NAME_MAX] or None


def copy_to_staging(src: Path, settings: Settings) -> StagedFile:
    """Copy `src` into the staging directory, hashing as it goes (chunked); never touches `src` otherwise."""
    directory = staging_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.part"
    final, tmp = directory / name, directory / (name[:-5] + ".tmp")
    digest = hashlib.sha256()
    size = 0
    chunk = settings.ingest.file.copy_chunk_bytes
    try:
        with open(src, "rb") as fin, open(tmp, "xb") as fout:
            while block := fin.read(chunk):
                digest.update(block)
                fout.write(block)
                size += len(block)
            fout.flush()
            os.fsync(fout.fileno())
        os.replace(tmp, final)
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return StagedFile(name, final, size, digest.hexdigest())


def remove_staged(settings: Settings, name: str) -> None:
    try:
        staged_path(settings, name).unlink(missing_ok=True)
    except ValueError:
        pass


def sweep_staging(conn, settings: Settings) -> int:
    """Delete staging files older than `staging_max_age_h` that no queued or running job refers to; return how many."""
    directory = staging_dir(settings)
    if not directory.is_dir():
        return 0
    in_use = {
        job.payload.get("staged")
        for status in ("queued", "running")
        for job in store.list_jobs(conn, limit=100000, status=status)
        if job.kind == "ingest_file"
    }
    cutoff = time.time() - settings.ingest.file.staging_max_age_h * 3600
    removed = 0
    for entry in directory.iterdir():
        try:
            if entry.is_file() and entry.name not in in_use and entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError as exc:
            log.warning("could not remove stale staging file %s: %s", entry, exc)
    return removed
