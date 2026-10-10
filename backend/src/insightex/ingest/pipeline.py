"""The `ingest_link` pipeline: `fetch` (download the whole file), `normalise` (H.264/AAC mp4 + 16 kHz audio), then `asr`.

`fetch` and `normalise` are CPU stages; the logic is the former `engine.ingest`, split at the download boundary so
each half is cached on its own (ADR-0034). `asr` (insightex.asr.stage, ADR-0042) is the GPU stage that both
pipelines share. Payload: {"url": str, "language": str}. Outputs land in the workspace under
stages/fetch/<key>/, stages/normalise/<key>/ and stages/asr/<key>/.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

import yt_dlp

from insightex.asr.stage import AsrStage
from insightex.ingest import netguard, staging
from insightex.ingest.errors import ErrorCode, IngestError, IngestRejected
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
from insightex.media import engine
from insightex.media.engine import NORMALISER_VERSION
from insightex.sources.identity import (
    HashingWriter,
    sha256_file,
    workspace_id_for_bytes,
    workspace_id_for_youtube,
)

log = logging.getLogger(__name__)

SOURCE_NAME, SOURCE_JSON = "source", "source.json"
VIDEO_NAME, AUDIO_NAME, THUMB_NAME, NORMALISE_JSON = "video.mp4", "audio.wav", "thumbnail.jpg", "normalise.json"
THUMB_SRC_NAME = "thumbnail.src"
SOURCE_BLOCK_KEYS = ("kind", "via", "original_filename", "size_bytes", "sha256", "received_at")
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
            "kind": "link",
            "via": None,
            "original_filename": None,
            "received_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
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
    """The shared second stage of `ingest_link` and `ingest_file`: a thin wrapper around `media.engine.normalise_media`."""

    name = "normalise"
    version = NORMALISER_VERSION
    needs_gpu = False
    outputs = (VIDEO_NAME, AUDIO_NAME, THUMB_NAME, NORMALISE_JSON)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        i = ctx.settings.ingest
        return {
            "preset": i.transcode.preset,
            "crf": i.transcode.crf,
            "max_height": i.transcode.max_height,
            "audio_bitrate_kbps": i.transcode.audio_bitrate_kbps,
            "keyframe_interval_s": i.transcode.keyframe_interval_s,
            "thumb_max_width": i.thumbnail.max_width,
            "thumb_quality": i.thumbnail.quality,
        }

    def run(self, ctx: StageContext) -> None:
        cfg = IngestSettings.from_settings(ctx.settings)
        fetched = ctx.upstream["fetch"]
        source_info = _read_json(fetched / SOURCE_JSON)
        record = engine.normalise_media(
            fetched / SOURCE_NAME, ctx.staging_dir, cfg,
            max_bytes=cfg.max_download_bytes, thumbnail_src=fetched / THUMB_SRC_NAME, progress=ctx.progress,
        )
        _write_json(ctx.staging_dir / NORMALISE_JSON, {
            "schema": 2,
            "duration_s": record["verify"]["video_mp4_duration_s"],
            "source": {k: source_info.get(k) for k in SOURCE_BLOCK_KEYS},
            **record,
        })

    def after_stage(self, ctx: KeyContext, upstream: dict[str, Path]) -> None:
        """An uploaded original is deleted once `video.mp4` is published, unless ingest.file.keep_original (ADR-0036).

        A link's `source` is kept (ADR-0035): it cannot be re-fetched cheaply. Idempotent.
        """
        fetched = upstream.get("fetch")
        if fetched is None or ctx.settings.ingest.file.keep_original:
            return
        if _read_json(fetched / SOURCE_JSON).get("kind") == "upload":
            (fetched / SOURCE_NAME).unlink(missing_ok=True)


class UploadFetchStage(Stage):
    """First stage of `ingest_file`: adopt the staged copy (hard link, else copy) as this workspace's `source`."""

    name = "fetch"
    version = "1"
    needs_gpu = False
    outputs = (SOURCE_NAME, SOURCE_JSON)

    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        return {"sha256": ctx.payload["sha256"]}

    def run(self, ctx: StageContext) -> None:
        staged = staging.staged_path(ctx.settings, ctx.payload["staged"])
        if not staged.is_file():
            raise FileNotFoundError(f"staged copy {staged.name} is missing")
        dst = ctx.staging_dir / SOURCE_NAME
        try:
            os.link(staged, dst)  # the staged copy is deleted in after_stage, once this stage is published
        except OSError:
            shutil.copyfile(staged, dst)
        ctx.progress(0.5, "Received file")
        _write_json(ctx.staging_dir / SOURCE_JSON, {
            "kind": "upload",
            "via": ctx.payload.get("via"),
            "source_type": "upload",
            "original_filename": ctx.payload.get("original_filename"),
            "title": _display_title(ctx.payload.get("original_filename")),
            "size_bytes": ctx.payload["size_bytes"],
            "sha256": ctx.payload["sha256"],
            "received_at": ctx.payload.get("received_at"),
            "url": None, "normalized_url": None, "uploader": None, "duration_s": None, "ext": None, "downloader": None,
            "external_timestamp_url_template": None,
        })

    def after_stage(self, ctx: KeyContext, upstream: dict[str, Path]) -> None:
        staging.remove_staged(ctx.settings, ctx.payload["staged"])


def _display_title(filename: str | None) -> str | None:
    return Path(filename).stem or filename if filename else None


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


def file_source_for(payload: dict[str, Any]) -> tuple[str, str]:
    """Cache-index source of an `ingest_file` job: ("upload", the display name or the content hash)."""
    return "upload", payload.get("original_filename") or payload["sha256"]


def reject_cleanup(conn, workspaces, job, settings, exc: BaseException) -> None:
    """A rejected upload leaves nothing behind: no staged copy, no workspace, no cache row.

    A workspace that already holds a finished `normalise` (re-normalising an older lecture) is left alone.
    Internal errors keep the staged copy so the job can be retried.
    """
    if not isinstance(exc, IngestRejected):
        return
    staging.remove_staged(settings, job.payload.get("staged", ""))
    if workspaces.stage_output_dir(job.workspace_id, "normalise") is None:
        shutil.rmtree(workspaces.path(job.workspace_id), ignore_errors=True)
        conn.execute("DELETE FROM workspaces WHERE id = ?", (job.workspace_id,))


register_pipeline("ingest_link", [FetchStage(), NormaliseStage(), AsrStage()], source_for=source_for,
                  chain_root=chain_root)
register_pipeline("ingest_file", [UploadFetchStage(), NormaliseStage(), AsrStage()], source_for=file_source_for,
                  on_failure=reject_cleanup)
