"""Response models of the HTTP API. Field names are stable (docs/contracts/api.md)."""

from __future__ import annotations

from pydantic import BaseModel

from insightex.jobs import store
from insightex.jobs.workspace import Workspaces


class StageOut(BaseModel):
    name: str
    status: str
    progress: float
    message: str | None
    error: str | None


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    workspace_id: str
    workspace_deleted: bool
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    stages: list[StageOut]


class LinkAccepted(BaseModel):
    job_id: str
    workspace_id: str
    deduplicated: bool


class UploadAccepted(BaseModel):
    lecture_id: str
    job_id: str | None
    deduplicated: bool


class LectureItem(BaseModel):
    lecture_id: str
    title: str | None
    duration_s: float | None
    thumbnail_url: str | None
    created_at: str | None


class LectureOut(LectureItem):
    video_url: str
    warnings: list[dict] = []
    external_timestamp_url_template: str | None


class LectureList(BaseModel):
    lectures: list[LectureItem]


def job_out(job: store.Job, workspaces: Workspaces) -> JobOut:
    """A finished job whose workspace directory is gone reports `workspace_deleted`; a waiting one never does."""
    try:
        gone = job.status in store.FINAL_STATUSES and not workspaces.path(job.workspace_id).exists()
    except ValueError:
        gone = True
    return JobOut(
        id=job.id, kind=job.kind, status=job.status, workspace_id=job.workspace_id, workspace_deleted=gone,
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at, error=job.error,
        stages=[StageOut(name=s.name, status=s.status, progress=s.progress, message=s.message, error=s.error)
                for s in job.stages],
    )
