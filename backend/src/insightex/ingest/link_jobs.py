"""Enqueue an `ingest_link` job: validate the URL, pick the workspace id, de-duplicate active jobs."""

from __future__ import annotations

import sqlite3
import threading
import uuid

from insightex.asr.languages import require_language
from insightex.core.config import Settings
from insightex.ingest.errors import IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.urls import parse_url
from insightex.jobs import store
from insightex.jobs.stages import PENDING_PREFIX
from insightex.sources.identity import workspace_id_for_youtube

KIND = "ingest_link"
_lock = threading.Lock()  # check-then-enqueue must not interleave between API worker threads


def enqueue_link(conn: sqlite3.Connection, settings: Settings, url: str, language: str | None) -> tuple[str, str, bool]:
    """Return (job_id, workspace_id, deduplicated).

    `language` is a language id from the language config (ADR-0040); a missing or unknown one raises
    IngestError before anything is enqueued. Only an active job for the same link *and* language is returned.

    YouTube: the workspace id (`yt-<id>`) is known now, and a queued or running job for it is returned
    instead of a new one. Any other link: the content hash is unknown until `fetch` finishes, so the job
    starts in `pending-<job id>` and is de-duplicated on the normalised URL. Raises IngestError for a link
    that cannot be ingested (nothing is enqueued).
    """
    lang = require_language(settings, language)
    parsed = parse_url(url, IngestSettings.from_settings(settings).max_url_length)
    youtube = parsed.source_type == "youtube"
    workspace_id = workspace_id_for_youtube(parsed.media_id) if youtube else None
    with _lock:
        for status in ("running", "queued"):
            for job in store.list_jobs(conn, limit=1000, status=status):
                if job.kind != KIND or job.payload.get("language") != lang.id:
                    continue
                if youtube:
                    same = job.workspace_id == workspace_id
                else:
                    try:
                        same = parse_url(job.payload["url"], 1 << 20).normalized_url == parsed.normalized_url
                    except IngestError:
                        same = False
                if same:
                    return job.id, job.workspace_id, True
        job_id = uuid.uuid4().hex
        workspace_id = workspace_id or f"{PENDING_PREFIX}{job_id}"
        store.enqueue(conn, KIND, {"url": parsed.source_url, "language": lang.id}, workspace_id, job_id=job_id)
    return job_id, workspace_id, False


