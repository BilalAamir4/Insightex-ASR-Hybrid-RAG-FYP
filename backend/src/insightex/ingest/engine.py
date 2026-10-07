"""URL ingestion engine: probe(url) and ingest(url, rights_confirmed, progress_cb).

Output contract (per lecture, under paths.lectures):
    <lecture_id>/video.mp4, audio.wav (16 kHz mono s16le), thumbnail.jpg, manifest.json,
    source.<ext> only when keep_source.
Every file is produced in <lecture_id>/.tmp/ and moved into place with os.replace once complete.
"""

from __future__ import annotations

import fcntl
import logging
import os
import shutil
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from insightex.core import ids
from insightex.core.manifest import FILE_MODE, IN_PROGRESS, Manifest, read_manifest, write_manifest
from insightex.ingest import netguard
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources import direct, gdrive, youtube
from insightex.ingest.sources.base import SourceMeta
from insightex.ingest.urls import ParsedUrl, parse_url
from insightex.media import ffmpeg

log = logging.getLogger(__name__)

# progress_cb(stage, fraction_or_None, message)
ProgressCb = Callable[[str, float | None, str], None]

STAGES = ("probing", "downloading", "transcoding", "extracting_audio", "done")
TMP_DIR = ".tmp"
LOCKS_DIR = ".locks"
VIDEO_NAME, AUDIO_NAME, THUMB_NAME = "video.mp4", "audio.wav", "thumbnail.jpg"

SOURCES: dict[str, Any] = {
    "youtube": SimpleNamespace(probe=youtube.probe, download=youtube.download),
    "gdrive": SimpleNamespace(probe=gdrive.probe, download=gdrive.download),
    "direct": SimpleNamespace(probe=direct.probe, download=direct.download),
}


@dataclass
class ProbeResult:
    canonical_id: str
    lecture_id: str
    source_type: str
    normalized_url: str
    title: str | None
    uploader: str | None
    duration_s: float | None
    thumbnail_url: str | None
    exists_locally: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _settings(settings: IngestSettings | None) -> IngestSettings:
    return settings or IngestSettings.current()


def _lecture_path(settings: IngestSettings, parsed: ParsedUrl) -> Path:
    return ids.lecture_dir(settings.lectures_dir, parsed.lecture_id)


def _is_ready(path: Path, manifest: Manifest | None) -> bool:
    if manifest is None or manifest.status != "ready":
        return False
    files = manifest.files or {}
    return all(files.get(k) and (path / files[k]).is_file() for k in ("video", "audio"))


def _too_long_message(limit_s: int) -> str:
    hours = limit_s / 3600
    limit = f"{hours:g} hours" if hours >= 1 else f"{limit_s // 60} minutes"
    return f"This video is longer than the {limit} limit."


def _check_duration(duration_s: float | None, settings: IngestSettings) -> None:
    if duration_s is not None and duration_s > settings.max_duration_s:
        raise IngestError(ErrorCode.TOO_LONG, _too_long_message(settings.max_duration_s))


def probe(url: str, settings: IngestSettings | None = None) -> ProbeResult:
    """Metadata without downloading media. Raises IngestError (TOO_LONG when the duration is known)."""
    settings = _settings(settings)
    parsed = parse_url(url, settings.max_url_length)
    path = _lecture_path(settings, parsed)
    existing = read_manifest(path)
    if _is_ready(path, existing):
        assert existing is not None
        return ProbeResult(
            canonical_id=parsed.canonical_id, lecture_id=parsed.lecture_id, source_type=parsed.source_type,
            normalized_url=parsed.normalized_url, title=existing.title, uploader=existing.uploader,
            duration_s=existing.duration_s, thumbnail_url=None, exists_locally=True,
        )
    meta = SOURCES[parsed.source_type].probe(parsed, settings)
    _check_duration(meta.duration_s, settings)
    return ProbeResult(
        canonical_id=parsed.canonical_id, lecture_id=parsed.lecture_id, source_type=parsed.source_type,
        normalized_url=parsed.normalized_url, title=meta.title, uploader=meta.uploader,
        duration_s=meta.duration_s, thumbnail_url=meta.thumbnail_url, exists_locally=False,
    )


@contextmanager
def _lecture_lock(settings: IngestSettings, lecture_id: str) -> Iterator[None]:
    """Exclusive per-lecture lock. A second ingest of the same lecture waits, then sees its result."""
    locks = Path(settings.lectures_dir) / LOCKS_DIR
    locks.mkdir(parents=True, exist_ok=True)
    with open(locks / f"{ids.validate_lecture_id(lecture_id)}.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


class _Progress:
    def __init__(self, cb: ProgressCb | None, min_interval_s: float = 0.25) -> None:
        self.cb = cb
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def __call__(self, stage: str, fraction: float | None, message: str, force: bool = True) -> None:
        if self.cb is None:
            return
        now = time.monotonic()
        if not force and now - self._last < self.min_interval_s:
            return
        self._last = now
        self.cb(stage, fraction, message)


def _mb(n: int) -> str:
    return f"{n / 1024**2:.1f} MB"


def ingest(
    url: str,
    rights_confirmed: bool,
    progress_cb: ProgressCb | None = None,
    settings: IngestSettings | None = None,
) -> Manifest:
    """Download, normalize to H.264/AAC mp4, extract ASR audio and a thumbnail. Returns the manifest.

    A lecture already "ready" is returned as-is. A failed or interrupted one is removed and redone.
    """
    if rights_confirmed is not True:
        raise IngestError(ErrorCode.RIGHTS_NOT_CONFIRMED)
    settings = _settings(settings)
    parsed = parse_url(url, settings.max_url_length)
    progress = _Progress(progress_cb)
    path = _lecture_path(settings, parsed)

    with _lecture_lock(settings, parsed.lecture_id):
        existing = read_manifest(path)
        if _is_ready(path, existing):
            assert existing is not None
            log.info("lecture %s already ready; not re-downloading", parsed.lecture_id)
            progress("done", 1.0, "Already in the library")
            return existing
        if path.exists():
            state = existing.status if existing else "unreadable manifest"
            log.info("removing previous attempt of %s (%s)", parsed.lecture_id, state)
            shutil.rmtree(path)
        path.mkdir(parents=True)
        tmp = path / TMP_DIR
        tmp.mkdir()

        manifest = Manifest(
            lecture_id=parsed.lecture_id,
            canonical_id=parsed.canonical_id,
            source_type=parsed.source_type,
            source_url=parsed.source_url,
            normalized_url=parsed.normalized_url,
            rights_confirmed=True,
            external_timestamp_url_template=parsed.external_timestamp_url_template,
        )
        stage = "probing"
        try:
            progress(stage, None, "Reading video details")
            meta = SOURCES[parsed.source_type].probe(parsed, settings)
            _check_duration(meta.duration_s, settings)
            manifest.title, manifest.uploader, manifest.duration_s = meta.title, meta.uploader, meta.duration_s
            write_manifest(path, manifest)

            stage = "downloading"
            manifest.set_status("downloading")
            write_manifest(path, manifest)
            source = _download(parsed, tmp, settings, meta, progress)

            stage = "transcoding"
            manifest.set_status("transcoding")
            write_manifest(path, manifest)
            _process(source, path, tmp, settings, meta, manifest, progress)
            stage = "finishing"

            if settings.keep_source:
                final_source = path / f"source{source.suffix}"
                _publish(source, final_source)
                manifest.files["source"] = final_source.name
            manifest.set_status("ready")
            manifest.error = None
            write_manifest(path, manifest)
        except IngestError as exc:
            log.warning("ingest of %s failed at %s: %s", parsed.lecture_id, stage, exc)
            _fail(path, manifest, exc)
            raise
        except Exception as exc:
            log.exception("unexpected error ingesting %s at %s", parsed.lecture_id, stage)
            code = ErrorCode.DOWNLOAD_FAILED if stage in ("probing", "downloading") else ErrorCode.TRANSCODE_FAILED
            err = IngestError(code)
            _fail(path, manifest, err)
            raise err from exc
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    progress("done", 1.0, "Ready")
    return manifest


def _publish(src: Path, dst: Path) -> None:
    """Move a finished file into its final place with explicit permissions (not umask-dependent)."""
    os.chmod(src, FILE_MODE)
    os.replace(src, dst)


def _fail(path: Path, manifest: Manifest, exc: IngestError) -> None:
    """Mark failed and drop media already moved into place; the manifest stays for diagnosis."""
    for key, name in list((manifest.files or {}).items()):
        if name:
            (path / name).unlink(missing_ok=True)
            manifest.files[key] = None
    manifest.fail(str(exc.code), exc.message)
    try:
        write_manifest(path, manifest)
    except OSError:
        log.exception("could not write failed manifest for %s", manifest.lecture_id)


def _download(parsed: ParsedUrl, tmp: Path, settings: IngestSettings, meta: SourceMeta, progress: _Progress) -> Path:
    progress("downloading", 0.0 if meta.size_bytes else None, "Starting download")

    def on_bytes(received: int, total: int | None) -> None:
        total = total or meta.size_bytes
        if total:
            progress("downloading", min(received / total, 1.0), f"{_mb(received)} of {_mb(total)}", force=False)
        else:
            progress("downloading", None, f"{_mb(received)} downloaded", force=False)

    source = SOURCES[parsed.source_type].download(parsed, tmp, settings, meta, on_bytes)
    size = source.stat().st_size
    if size > settings.max_download_bytes:
        raise IngestError(ErrorCode.TOO_LARGE)
    progress("downloading", 1.0, f"Downloaded {_mb(size)}")
    return source


def _process(
    source: Path,
    path: Path,
    tmp: Path,
    settings: IngestSettings,
    meta: SourceMeta,
    manifest: Manifest,
    progress: _Progress,
) -> None:
    try:
        info = ffmpeg.ffprobe(source, settings)
    except ffmpeg.FFmpegError as exc:
        log.warning("ffprobe rejected %s: %s\n%s", source.name, exc, exc.stderr)
        raise IngestError(ErrorCode.NOT_A_VIDEO, "This file couldn't be read as a video.") from exc
    if info.video is None:
        raise IngestError(ErrorCode.NOT_A_VIDEO, "This file has no video track.")
    if info.audio is None:
        raise IngestError(ErrorCode.NO_AUDIO_STREAM)
    _check_duration(info.duration_s, settings)

    manifest.source = {
        "codec": info.video.codec,
        "width": info.video.width,
        "height": info.video.height,
        "fps": round(info.video.fps, 3) if info.video.fps else None,
        "container": info.format_name,
    }
    mode = ffmpeg.decide_processing(info, settings.max_video_height)
    tmp_video = tmp / VIDEO_NAME

    def on_fraction(stage: str, message: str) -> Callable[[float | None], None]:
        return lambda frac: progress(stage, frac, message, force=False)

    progress("transcoding", 0.0, "Copying video" if mode == "remux" else "Converting video")
    try:
        if mode == "remux":
            try:
                ffmpeg.run_ffmpeg(ffmpeg.remux_args(source, tmp_video), info.duration_s,
                                  on_fraction("transcoding", "Copying video"))
            except ffmpeg.FFmpegError as exc:
                log.warning("remux failed, falling back to transcode: %s\n%s", exc, exc.stderr)
                mode = "transcode"
        if mode == "transcode":
            ffmpeg.run_ffmpeg(ffmpeg.transcode_args(source, tmp_video, info, settings.max_video_height),
                              info.duration_s, on_fraction("transcoding", "Converting video"))
        out = ffmpeg.ffprobe(tmp_video, settings)
    except ffmpeg.FFmpegError as exc:
        log.error("transcode failed for %s: %s\n%s", source.name, exc, exc.stderr)
        raise IngestError(ErrorCode.TRANSCODE_FAILED) from exc
    if out.video is None or out.audio is None:
        raise IngestError(ErrorCode.TRANSCODE_FAILED)
    _publish(tmp_video, path / VIDEO_NAME)
    manifest.files["video"] = VIDEO_NAME
    manifest.decision = mode
    manifest.duration_s = round(out.duration_s, 3) if out.duration_s else manifest.duration_s
    manifest.video = {
        "codec": out.video.codec,
        "width": out.video.width,
        "height": out.video.height,
        "fps": round(out.video.fps, 3) if out.video.fps else None,
    }

    # Audio comes from video.mp4, so ASR timestamps share the player's timeline.
    final_video = path / VIDEO_NAME
    progress("extracting_audio", 0.0, "Extracting audio for transcription")
    try:
        ffmpeg.run_ffmpeg(ffmpeg.audio_args(final_video, tmp / AUDIO_NAME), out.duration_s,
                          on_fraction("extracting_audio", "Extracting audio for transcription"))
    except ffmpeg.FFmpegError as exc:
        log.error("audio extraction failed: %s\n%s", exc, exc.stderr)
        raise IngestError(ErrorCode.TRANSCODE_FAILED) from exc
    _publish(tmp / AUDIO_NAME, path / AUDIO_NAME)
    manifest.files["audio"] = AUDIO_NAME
    manifest.audio = {"sample_rate": ffmpeg.ASR_SAMPLE_RATE, "channels": ffmpeg.ASR_CHANNELS, "codec": ffmpeg.ASR_CODEC}

    progress("extracting_audio", None, "Saving thumbnail")
    if _thumbnail(final_video, tmp, meta.thumbnail_url, out.duration_s, settings):
        _publish(tmp / THUMB_NAME, path / THUMB_NAME)
        manifest.files["thumbnail"] = THUMB_NAME


def _thumbnail(video: Path, tmp: Path, thumbnail_url: str | None, duration_s: float | None,
               settings: IngestSettings) -> bool:
    """Source thumbnail if available, else a frame at 10% of the duration. Best effort: never fails ingest."""
    dst = tmp / THUMB_NAME
    if thumbnail_url:
        try:
            raw = tmp / "thumbnail.src"
            _fetch_small(thumbnail_url, raw, settings.thumb_max_bytes, settings)
            ffmpeg.image_to_jpeg(raw, dst, settings)
            return True
        except (IngestError, ffmpeg.FFmpegError, OSError) as exc:
            log.info("source thumbnail unusable (%s); using a video frame", exc)
    try:
        ffmpeg.extract_frame_jpeg(video, dst, (duration_s or 0) * 0.10, settings)
        return dst.is_file()
    except ffmpeg.FFmpegError as exc:
        log.warning("thumbnail frame extraction failed: %s\n%s", exc, exc.stderr)
        return False


def _fetch_small(url: str, dst: Path, limit: int, settings: IngestSettings) -> None:
    import httpx

    with netguard.make_client(settings=settings) as client:
        try:
            with netguard.guarded_stream(client, url) as response:
                if response.status_code >= 400:
                    raise netguard.map_http_status(response.status_code)
                received = 0
                with dst.open("wb") as f:
                    for chunk in response.iter_bytes(64 * 1024):
                        received += len(chunk)
                        if received > limit:
                            raise IngestError(ErrorCode.TOO_LARGE)
                        f.write(chunk)
        except httpx.HTTPError as exc:
            raise netguard.map_httpx_error(exc) from exc
