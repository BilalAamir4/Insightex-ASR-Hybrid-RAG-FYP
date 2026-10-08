"""Stage interface, stage keys, the pipeline registry and the GPU lease hook (ADR-0033, ADR-0034)."""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from insightex.core.config import Settings
from insightex.jobs.workspace import validate_stage_name

log = logging.getLogger(__name__)


class JobCancelled(Exception):
    """Raised by `ctx.progress` when cancellation was requested for the job."""


class WorkerStopping(Exception):
    """Raised by `ctx.progress` when the worker received SIGINT/SIGTERM; the job goes back to the queue."""


class UnknownJobKind(KeyError):
    """No pipeline is registered for the job kind."""


def stage_key(stage_name: str, stage_version: str, config_fingerprint: dict[str, Any], upstream_key: str) -> str:
    """Chained cache key of a stage: 16 hex characters of SHA-256 over the canonical JSON of the four inputs.

    `upstream_key` is the previous stage's key, or the workspace id for the first stage. A change to a
    stage's version or fingerprint changes its key and, through the chain, every later key.
    """
    canonical = json.dumps(
        {"stage": stage_name, "version": stage_version, "config": config_fingerprint, "upstream": upstream_key},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class KeyContext:
    """What a stage may look at to build its config fingerprint (no files exist yet at that point)."""

    job_id: str
    payload: dict[str, Any]
    workspace_id: str
    settings: Settings


class StageContext:
    """What `Stage.run` receives.

    Attributes: `job_id`, `payload`, `workspace_id`, `settings`; `staging_dir` (write every output
    here and nowhere else); `upstream` (stage name -> completed output directory, for earlier stages).
    """

    def __init__(
        self,
        *,
        job_id: str,
        payload: dict[str, Any],
        workspace_id: str,
        settings: Settings,
        staging_dir: Path,
        upstream: dict[str, Path],
        reporter: Callable[[float, str | None], None],
    ) -> None:
        self.job_id = job_id
        self.payload = payload
        self.workspace_id = workspace_id
        self.settings = settings
        self.staging_dir = staging_dir
        self.upstream = upstream
        self._reporter = reporter

    def progress(self, fraction: float, message: str | None = None) -> None:
        """Report progress (0 to 1) and check for cancellation and shutdown.

        Raises JobCancelled if the job was cancelled and WorkerStopping if the worker is shutting down;
        let both propagate. The database write is throttled to `jobs.progress_min_interval_s`, but the
        checks run on every call, and 0 and 1 are always written.
        """
        self._reporter(min(1.0, max(0.0, fraction)), message)


class Stage(ABC):
    """One step of a pipeline. Subclass it and set the class attributes.

    - `name`: lowercase identifier, unique within the pipeline; it is a directory name.
    - `version`: string; bump it whenever a code change alters this stage's outputs.
    - `needs_gpu`: the runner holds the GPU lease for the duration of `run`.
    - `outputs`: file names (relative to the stage directory) that `run` must create.

    `run` must be idempotent: it writes only into `ctx.staging_dir`, and a rerun after a crash starts
    from an empty staging directory. It must call `ctx.progress` at least every few seconds. Cancel and
    SIGTERM are noticed only inside that call, so a stage that goes silent delays them until it returns.
    """

    name: str
    version: str
    needs_gpu: bool = False
    outputs: tuple[str, ...] = ()

    @abstractmethod
    def config_fingerprint(self, ctx: KeyContext) -> dict[str, Any]:
        """The settings and payload fields that change this stage's outputs (JSON-serialisable), and only those."""

    @abstractmethod
    def run(self, ctx: StageContext) -> None:
        """Do the work and write every declared output into `ctx.staging_dir`."""


class GpuLease(ABC):
    """Serialises GPU stages across processes. Session 2 implements it with an OS file lock."""

    @abstractmethod
    @contextmanager
    def hold(self, job_id: str, stage_name: str) -> Iterator[None]:
        """Block until the GPU is free, hold it for the body, release on exit (also on exception)."""


class NullGpuLease(GpuLease):
    """Placeholder until the real lease exists: grants immediately."""

    @contextmanager
    def hold(self, job_id: str, stage_name: str) -> Iterator[None]:
        log.debug("null gpu lease: job=%s stage=%s", job_id, stage_name)
        yield


_PIPELINES: dict[str, tuple[Stage, ...]] = {}
SourceFor = Callable[[dict[str, Any]], tuple[str, str]]
_SOURCES: dict[str, SourceFor] = {}
_BUILTIN_MODULES = ("insightex.jobs.dummy",)
_builtins_loaded = False


def register_pipeline(
    kind: str, stages: list[Stage], *, replace: bool = False, source_for: SourceFor | None = None
) -> None:
    """Register the ordered, linear stage list that runs for jobs of `kind`.

    `source_for(payload)` returns `(source_kind, source_ref)` for the cache index (see jobs/cache.py);
    the runner calls it at job start. Without it the workspace is not indexed.
    """
    if kind in _PIPELINES and not replace:
        raise ValueError(f"a pipeline for kind {kind!r} is already registered")
    names = [validate_stage_name(s.name) for s in stages]
    if not stages or len(set(names)) != len(names):
        raise ValueError(f"pipeline {kind!r} needs at least one stage and unique stage names")
    _PIPELINES[kind] = tuple(stages)
    if source_for is not None:
        _SOURCES[kind] = source_for
    else:
        _SOURCES.pop(kind, None)


def get_source_for(kind: str) -> SourceFor | None:
    """The `source_for` callable declared by the pipeline for `kind`, or None."""
    get_pipeline(kind)
    return _SOURCES.get(kind)


def get_pipeline(kind: str) -> tuple[Stage, ...]:
    """The stages for `kind`; raises UnknownJobKind. Built-in pipelines register on first lookup."""
    global _builtins_loaded
    if not _builtins_loaded:
        _builtins_loaded = True
        for module in _BUILTIN_MODULES:
            importlib.import_module(module)
    try:
        return _PIPELINES[kind]
    except KeyError:
        raise UnknownJobKind(f"no pipeline registered for job kind {kind!r}") from None
