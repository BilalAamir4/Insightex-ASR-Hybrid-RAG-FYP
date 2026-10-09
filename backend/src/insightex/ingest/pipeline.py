"""The `ingest_link` pipeline: `fetch` (download the whole file) then `normalise` (H.264/AAC mp4 + 16 kHz audio).

Both stages are CPU stages. The logic is the former `engine.ingest`, split at the download boundary so each
half is cached on its own (ADR-0034). Payload: {"url": str}. Outputs land in the workspace under
stages/fetch/<key>/ and stages/normalise/<key>/.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, BinaryIO

import yt_dlp

from insightex.ingest import netguard
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.probe import SOURCES, check_duration
from insightex.ingest.settings import IngestSettings
from insightex.ingest.urls import ParsedUrl, parse_url
from insightex.jobs.stages import (
    JobCancelled,
    KeyContext,
    Stage,
    StageContext,
    WorkerStopping,
    register_pipeline,
)
from insightex.media import ffmpeg
from insightex.sources.identity import HashingWriter, sha256_file, workspace_id_for_bytes, workspace_id_for_youtube

log = logging.getLogger(__name__)

SOURCE_NAME, SOURCE_JSON = "source", "source.json"
VIDEO_NAME, AUDIO_NAME, THUMB_NAME, NORMALISE_JSON = "video.mp4", "audio.wav", "thumbnail.jpg", "normalise.json"
THUMB_SRC_NAME = "thumbnail.src"
_URL_MAX_LENGTH = 1 << 20  # length limits are enforced at the API; here the URL was already accepted


def _mb(n: int) -> str:
    return f"{n / 1024**2:.1f} MB"


def _parse(payload: dict[str, Any], max_length: int = _URL_MAX_LENGTH) -> ParsedUrl:
    return parse_url(payload["url"], max_length)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _downloader_version(source_type: str) -> str:
    return f"yt-dlp {yt_dlp.version.__version__}" if source_type in ("youtube", "gdrive") else "httpx"


class FetchStage(Stage):
    name = "fetch"
    version = "1"
    needs_gpu = False
    outputs = (SOURCE_NAME, SOURCE_JSON)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {"max_video_height": ctx.settings.ingest.url.max_video_height}

    def run(self, ctx: StageContext) -> None:
        cfg = IngestSettings.from_settings(ctx.settings)
        parsed = _parse(ctx.payload, cfg.max_url_length)
        adapter = SOURCES[parsed.source_type]
        ctx.progress(0.0, "Reading video details")
        meta = adapter.probe(parsed, cfg)
        check_duration(meta.duration_s, cfg)

        control: list[BaseException] = []  # a cancel/stop raised inside a downloader callback

        def on_bytes(received: int, total: int | None) -> None:
            total = total or meta.size_bytes
            try:
                if total:
                    ctx.progress(min(received / total, 1.0), f"{_mb(received)} of {_mb(total)}")
                else:
                    ctx.progress(0.0, f"{_mb(received)} downloaded")
            except (JobCancelled, WorkerStopping) as exc:
                control.append(exc)
                raise

        writers: list[HashingWriter] = []

        def wrap(f: BinaryIO) -> HashingWriter:
            writers.append(HashingWriter(f, ctx.settings.sources.hash_chunk_bytes))
            return writers[0]

        try:
            if parsed.source_type == "direct":
                downloaded = adapter.download(parsed, ctx.staging_dir, cfg, meta, on_bytes, wrap_output=wrap)
            else:
                downloaded = adapter.download(parsed, ctx.staging_dir, cfg, meta, on_bytes)
        except Exception:
            if control:
                raise control[0] from None
            raise
        size = downloaded.stat().st_size
        if size > cfg.max_download_bytes:
            raise IngestError(ErrorCode.TOO_LARGE)
        digest = writers[0].hexdigest() if writers else sha256_file(downloaded, ctx.settings.sources.hash_chunk_bytes)
        ext = downloaded.suffix.lstrip(".") or None
        os.replace(downloaded, ctx.staging_dir / SOURCE_NAME)  # one fixed name; the container is probed, not guessed
        ctx.progress(1.0, f"Downloaded {_mb(size)}")

        if meta.thumbnail_url:
            try:
                _fetch_small(meta.thumbnail_url, ctx.staging_dir / THUMB_SRC_NAME, cfg.thumb_max_bytes, cfg)
            except (IngestError, OSError) as exc:  # optional output: normalise falls back to a video frame
                log.info("source thumbnail unavailable (%s)", exc)
                (ctx.staging_dir / THUMB_SRC_NAME).unlink(missing_ok=True)

        _write_json(ctx.staging_dir / SOURCE_JSON, {
            "url": ctx.payload["url"],
            "normalized_url": parsed.normalized_url,
            "source_type": parsed.source_type,
            "title": meta.title,
            "uploader": meta.uploader,
            "duration_s": meta.duration_s,
            "ext": ext,
            "size_bytes": size,
            "sha256": digest,
            "downloader": _downloader_version(parsed.source_type),
            "external_timestamp_url_template": parsed.external_timestamp_url_template,
        })
        if parsed.source_type != "youtube":
            ctx.rebind_workspace(workspace_id_for_bytes(digest))

    def workspace_id_after(self, stage_dir: Path) -> str | None:
        info = _read_json(stage_dir / SOURCE_JSON)
        return None if info["source_type"] == "youtube" else workspace_id_for_bytes(info["sha256"])


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


class NormaliseStage(Stage):
    name = "normalise"
    version = "1"
    needs_gpu = False
    outputs = (VIDEO_NAME, AUDIO_NAME, THUMB_NAME, NORMALISE_JSON)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        i = ctx.settings.ingest
        return {
            "max_video_height": i.url.max_video_height,
            "preset": i.transcode.preset,
            "crf": i.transcode.crf,
            "thumb_max_width": i.thumbnail.max_width,
            "thumb_quality": i.thumbnail.quality,
        }

    def run(self, ctx: StageContext) -> None:
        cfg = IngestSettings.from_settings(ctx.settings)
        fetched = ctx.upstream["fetch"]
        source = fetched / SOURCE_NAME
        out_dir = ctx.staging_dir
        try:
            info = ffmpeg.ffprobe(source, cfg)
        except ffmpeg.FFmpegError as exc:
            log.warning("ffprobe rejected the source: %s\n%s", exc, exc.stderr)
            raise IngestError(ErrorCode.NOT_A_VIDEO, "This file couldn't be read as a video.") from exc
        if info.video is None:
            raise IngestError(ErrorCode.NOT_A_VIDEO, "This file has no video track.")
        if info.audio is None:
            raise IngestError(ErrorCode.NO_AUDIO_STREAM)
        check_duration(info.duration_s, cfg)
        ctx.progress(0.0, "Reading video details")

        def stage_progress(lo: float, hi: float, message: str):
            return lambda frac: ctx.progress(lo + (hi - lo) * (frac or 0.0), message)

        mode = ffmpeg.decide_processing(info, cfg.max_video_height)
        video = out_dir / VIDEO_NAME
        try:
            if mode == "remux":
                try:
                    ffmpeg.run_ffmpeg(ffmpeg.remux_args(source, video), info.duration_s,
                                      stage_progress(0.0, 0.8, "Copying video"))
                except ffmpeg.FFmpegError as exc:
                    log.warning("remux failed, falling back to transcode: %s\n%s", exc, exc.stderr)
                    mode = "transcode"
            if mode == "transcode":
                ffmpeg.run_ffmpeg(ffmpeg.transcode_args(source, video, info, cfg.max_video_height, cfg),
                                  info.duration_s, stage_progress(0.0, 0.8, "Converting video"))
            out = ffmpeg.ffprobe(video, cfg)
        except ffmpeg.FFmpegError as exc:
            log.error("transcode failed: %s\n%s", exc, exc.stderr)
            raise IngestError(ErrorCode.TRANSCODE_FAILED) from exc
        if out.video is None or out.audio is None:
            raise IngestError(ErrorCode.TRANSCODE_FAILED)

        # Audio comes from video.mp4, so ASR timestamps share the player's timeline.
        audio = out_dir / AUDIO_NAME
        try:
            ffmpeg.run_ffmpeg(ffmpeg.audio_args(video, audio), out.duration_s,
                              stage_progress(0.8, 0.95, "Extracting audio for transcription"))
            wav = ffmpeg.ffprobe(audio, cfg)
        except ffmpeg.FFmpegError as exc:
            log.error("audio extraction failed: %s\n%s", exc, exc.stderr)
            raise IngestError(ErrorCode.TRANSCODE_FAILED) from exc
        if (wav.audio is None or wav.audio.sample_rate != ffmpeg.ASR_SAMPLE_RATE
                or wav.audio.channels != ffmpeg.ASR_CHANNELS):
            raise IngestError(ErrorCode.TRANSCODE_FAILED)

        ctx.progress(0.95, "Saving thumbnail")
        self._thumbnail(video, fetched / THUMB_SRC_NAME, out_dir / THUMB_NAME, out.duration_s, cfg)
        _write_json(out_dir / NORMALISE_JSON, {
            "decision": mode,
            "duration_s": round(out.duration_s, 3) if out.duration_s else None,
            "source": {
                "codec": info.video.codec, "width": info.video.width, "height": info.video.height,
                "fps": round(info.video.fps, 3) if info.video.fps else None, "container": info.format_name,
            },
            "video": {
                "codec": out.video.codec, "width": out.video.width, "height": out.video.height,
                "fps": round(out.video.fps, 3) if out.video.fps else None,
            },
            "audio": {"sample_rate": ffmpeg.ASR_SAMPLE_RATE, "channels": ffmpeg.ASR_CHANNELS, "codec": ffmpeg.ASR_CODEC},
        })
        ctx.progress(1.0, "Done")

    @staticmethod
    def _thumbnail(video: Path, source_image: Path, dst: Path, duration_s: float | None, cfg: IngestSettings) -> None:
        """Source thumbnail if fetch saved one, else a frame at 10% of the duration."""
        if source_image.is_file():
            try:
                ffmpeg.image_to_jpeg(source_image, dst, cfg)
                return
            except (ffmpeg.FFmpegError, OSError) as exc:
                log.info("source thumbnail unusable (%s); using a video frame", exc)
        try:
            ffmpeg.extract_frame_jpeg(video, dst, (duration_s or 0) * 0.10, cfg)
        except ffmpeg.FFmpegError as exc:
            log.warning("thumbnail frame extraction failed: %s\n%s", exc, exc.stderr)
            raise IngestError(ErrorCode.TRANSCODE_FAILED, "A thumbnail couldn't be created.") from exc
        if not dst.is_file():
            raise IngestError(ErrorCode.TRANSCODE_FAILED, "A thumbnail couldn't be created.")


def source_for(payload: dict[str, Any]) -> tuple[str, str]:
    """Cache-index source of a job: ("youtube" | "gdrive" | "url", the pasted URL)."""
    kind = {"youtube": "youtube", "gdrive": "gdrive"}.get(_parse(payload).source_type, "url")
    return kind, payload["url"]


def chain_root(payload: dict[str, Any], workspace_id: str) -> str:
    """Upstream key of `fetch`: yt-<id> for YouTube, else the normalised URL.

    It must not be the workspace id: for a direct link that is `pending-<job id>` until the bytes are
    hashed, and a key built from it would differ on every run and after the rename.
    """
    parsed = _parse(payload)
    return workspace_id_for_youtube(parsed.media_id) if parsed.source_type == "youtube" else parsed.normalized_url


register_pipeline("ingest_link", [FetchStage(), NormaliseStage()], source_for=source_for, chain_root=chain_root)
