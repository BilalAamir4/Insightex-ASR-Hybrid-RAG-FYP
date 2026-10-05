"""In-memory job manager for URL ingestion: one download/transcode at a time, polled by the web UI.

Job state lives only in memory and is lost on restart; manifests on disk are the source of truth for
lectures (see recover_interrupted for what happens to work cut off by a restart). Specific to ingestion:
the GPU staging queue is a separate, later design.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from insightex.core import ids
from insightex.core.manifest import IN_PROGRESS, read_manifest, write_manifest
from insightex.ingest import engine
from insightex.ingest.errors import DEFAULT_MESSAGES, ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.urls import parse_url

log = logging.getLogger(__name__)

INTERRUPTED_CODE = "INTERRUPTED"
INTERRUPTED_MESSAGE = "This download was interrupted when the server restarted. Please add the lecture again."

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
_ACTIVE = (QUEUED, RUNNING)

Runner = Callable[..., object]  # same signature as engine.ingest


@dataclass
class Job:
    job_id: str
    lecture_id: str
    url: str
    status: str = QUEUED
    stage: str | None = None
    fraction: float | None = None
    message: str = "Waiting for other lectures to finish"
    error: dict[str, str] | None = None

    def snapshot(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "stage": self.stage,
            "fraction": self.fraction,
            "message": self.message,
            "lecture_id": self.lecture_id,
            "error": self.error,
        }


def is_ready(settings: IngestSettings, lecture_id: str) -> bool:
    """A lecture is ready when its manifest says so and the video file is on disk."""
    path = ids.lecture_dir(settings.lectures_dir, lecture_id)
    manifest = read_manifest(path)
    if manifest is None or manifest.status != "ready":
        return False
    video = (manifest.files or {}).get("video")
    return bool(video) and (path / video).is_file()


def recover_interrupted(lectures_dir: Path) -> list[str]:
    """Mark manifests left mid-ingest by a previous process as failed. Returns the affected lecture ids.

    Covers every non-terminal status (probed, downloading, transcoding). Directories whose name is not
    a valid lecture id, and unreadable manifests, are left alone.
    """
    recovered: list[str] = []
    if not Path(lectures_dir).is_dir():
        return recovered
    for entry in sorted(Path(lectures_dir).iterdir()):
        if not entry.is_dir() or not ids.LECTURE_ID_RE.fullmatch(entry.name):
            continue
        manifest = read_manifest(entry)
        if manifest is None or manifest.status not in IN_PROGRESS:
            continue
        manifest.fail(INTERRUPTED_CODE, INTERRUPTED_MESSAGE)
        try:
            write_manifest(entry, manifest)
        except OSError:
            log.exception("could not mark %s as interrupted", entry.name)
            continue
        log.warning("marked interrupted ingest %s as failed", entry.name)
        recovered.append(entry.name)
    return recovered


class IngestJobs:
    def __init__(self, settings: IngestSettings, runner: Runner | None = None) -> None:
        self.settings = settings
        # Resolved at call time so tests (and the CLI-equivalent path) use engine.ingest as it is then.
        self._runner = runner
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active: dict[str, str] = {}  # lecture_id -> job_id of the queued/running job
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")

    def submit(self, url: str) -> tuple[str | None, str]:
        """Queue an ingest. Returns (job_id, lecture_id); job_id is None if the lecture is already ready.

        A lecture that is already queued or running returns that job instead of a second one.
        Raises IngestError (UNSUPPORTED_URL etc.) if the URL cannot be parsed.
        """
        lecture_id = parse_url(url).lecture_id
        with self._lock:
            if is_ready(self.settings, lecture_id):
                return None, lecture_id
            existing = self._active.get(lecture_id)
            if existing:
                return existing, lecture_id
            job = Job(job_id=uuid.uuid4().hex, lecture_id=lecture_id, url=url)
            self._jobs[job.job_id] = job
            self._active[lecture_id] = job.job_id
        self._pool.submit(self._run, job)
        return job.job_id, lecture_id

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job else None

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _update(self, job: Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)

    def _run(self, job: Job) -> None:
        self._update(job, status=RUNNING, message="Starting")

        def on_progress(stage: str, fraction: float | None, message: str) -> None:
            self._update(job, stage=stage, fraction=fraction, message=message)

        runner = self._runner or engine.ingest
        try:
            runner(job.url, True, on_progress, settings=self.settings)
        except IngestError as exc:
            self._finish(job, FAILED, error=exc.to_dict(), message=exc.message)
        except Exception:
            log.exception("unexpected error in ingest job %s", job.job_id)
            err = IngestError(ErrorCode.DOWNLOAD_FAILED)
            self._finish(job, FAILED, error=err.to_dict(), message=DEFAULT_MESSAGES[ErrorCode.DOWNLOAD_FAILED])
        else:
            self._finish(job, DONE, stage="done", fraction=1.0, message="Ready")

    def _finish(self, job: Job, status: str, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)
            job.status = status
            if self._active.get(job.lecture_id) == job.job_id:
                del self._active[job.lecture_id]
