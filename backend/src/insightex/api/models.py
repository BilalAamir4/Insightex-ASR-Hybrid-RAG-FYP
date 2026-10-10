"""Response models of the HTTP API. Field names are stable (docs/contracts/api.md)."""

from __future__ import annotations

from pydantic import BaseModel

from insightex.asr.languages import Languages
from insightex.jobs import store
from insightex.jobs.workspace import Workspaces


class LanguageOut(BaseModel):
    """A lecture language as the UI shows it. `tier` comes from the current config (null if the id was removed)."""

    id: str
    label: str
    tier: str | None


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
    language: LanguageOut | None = None
    warnings: list[dict] = []


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
    language: LanguageOut | None = None  # null: no transcript yet (for example a lecture added before M4)


class LectureOut(LectureItem):
    video_url: str
    warnings: list[dict] = []
    external_timestamp_url_template: str | None


class LectureList(BaseModel):
    lectures: list[LectureItem]


def language_out(languages: Languages, language_id: object) -> LanguageOut | None:
    """The current label and tier of a stored language id; None when there is no id."""
    if not isinstance(language_id, str) or not language_id:
        return None
    entry = languages.get(language_id)
    return LanguageOut(**entry.public()) if entry else LanguageOut(id=language_id, label=language_id, tier=None)


def _asr_warnings(job: store.Job, workspaces: Workspaces) -> list[dict]:
    """Warnings of the transcript this job produced or reused (the manifest entry at the job's asr key)."""
    stage = next((s for s in job.stages if s.name == "asr"), None)
    if stage is None or stage.status not in ("succeeded", "cached") or not stage.stage_key:
        return []
    try:
        entry = workspaces.read_manifest(job.workspace_id)["stages"].get("asr") or {}
    except (OSError, ValueError, KeyError):
        return []
    warnings = entry.get("warnings") if entry.get("key") == stage.stage_key else None
    return warnings if isinstance(warnings, list) else []


def job_out(job: store.Job, workspaces: Workspaces, languages: Languages | None = None) -> JobOut:
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
        language=language_out(languages, job.payload.get("language")) if languages is not None else None,
        warnings=[] if gone else _asr_warnings(job, workspaces),
    )
