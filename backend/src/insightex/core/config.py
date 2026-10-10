"""Typed settings. Defaults live only in config/default.yaml (see docs/adr/0004-configuration-system.md).

Precedence, lowest first: config/default.yaml, the local override file ($INSIGHTEX_CONFIG, else
config/local.yaml if present), INSIGHTEX__<SECTION>__<KEY> env vars, explicit `overrides`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

ENV_PREFIX = "INSIGHTEX__"
CONFIG_ENV = "INSIGHTEX_CONFIG"
# Old env var -> config key it aliases. Both set to different values is an error.
ALIASES: dict[str, tuple[str, ...]] = {
    "INSIGHTEX_DATA": ("paths", "data_dir"),
    "OLLAMA_BASE_URL": ("ollama", "base_url"),
}


class ConfigError(Exception):
    pass


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Paths(_Section):
    data_dir: Path

    @field_validator("data_dir", mode="after")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return Path(os.path.expandvars(str(v))).expanduser().resolve()

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"


class Api(_Section):
    host: str
    port: int
    sse_poll_interval_s: float
    sse_keepalive_s: float
    touch_min_interval_s: float


class IngestUrl(_Section):
    max_duration_s: int
    max_download_bytes: int
    max_video_height: int
    deno_path: str | None
    socket_timeout_s: float
    connect_timeout_s: float
    read_timeout_s: float


class Transcode(_Section):
    preset: str
    crf: int
    max_height: int
    audio_bitrate_kbps: int
    keyframe_interval_s: float


class Thumbnail(_Section):
    max_width: int
    quality: int
    max_bytes: int


class Verify(_Section):
    duration_tolerance_s: float
    duration_tolerance_frac: float
    sync_tolerance_s: float
    av_mismatch_warn_s: float


class IngestFile(_Section):
    keep_original: bool
    staging_dir: Path
    staging_max_age_h: float
    copy_chunk_bytes: int

    @field_validator("staging_dir", mode="after")
    @classmethod
    def _local_absolute(cls, v: Path) -> Path:
        return _local_path(v)


class Ingest(_Section):
    url: IngestUrl
    transcode: Transcode
    thumbnail: Thumbnail
    verify: Verify
    file: IngestFile
    ffprobe_timeout_s: float
    max_url_length: int
    min_duration_s: float
    silence_warn_dbfs: float
    disk_free_factor: float
    disk_free_reserve_bytes: int
    ffmpeg_timeout_factor: float
    ffmpeg_timeout_min_s: float


class Ollama(_Section):
    base_url: str
    model: str
    think: bool
    num_ctx: int
    num_predict: int
    keep_alive: str
    temperature: float
    seed: int
    request_timeout_s: float
    ps_timeout_s: float
    unload_timeout_s: float
    unload_wait_s: float


class Visual(_Section):
    enabled: bool


# jobs.* path keys that default (null in YAML) to a name under paths.data_dir.
_JOBS_DERIVED = {"db_path": "insightex.db", "workspaces_dir": "workspaces", "run_dir": "run"}


def _local_path(v: Path) -> Path:
    """Expand, resolve and reject paths under /mnt/ (Windows DrvFS)."""
    v = Path(os.path.expandvars(str(v))).expanduser().resolve()
    if v == Path("/mnt") or Path("/mnt") in v.parents:
        raise ValueError(
            f"{v} is under /mnt/ (Windows DrvFS); SQLite WAL and file locks are unreliable there. "
            f"Use a path on the WSL ext4 disk"
        )
    return v


class Jobs(_Section):
    """Job queue, worker and workspaces (ADR-0033, ADR-0034). Paths are absolute and never under /mnt/."""

    db_path: Path
    workspaces_dir: Path
    run_dir: Path
    poll_interval_s: float
    max_attempts: int
    progress_min_interval_s: float
    busy_timeout_ms: int
    error_traceback_chars: int

    @field_validator("db_path", "workspaces_dir", "run_dir", mode="after")
    @classmethod
    def _local_absolute(cls, v: Path) -> Path:
        return _local_path(v)


class Gpu(_Section):
    """GPU lease (ADR-0033). `lease_path` is absolute and never under /mnt/."""

    lease_enabled: bool
    lease_path: Path
    lock_retry_interval_s: float
    ollama_poll_interval_s: float
    ollama_unload_timeout_s: float
    qa_lease_timeout_s: float

    @field_validator("lease_path", mode="after")
    @classmethod
    def _local_absolute(cls, v: Path) -> Path:
        return _local_path(v)


class Sources(_Section):
    hash_chunk_bytes: int


class Cache(_Section):
    max_bytes: int


class VadParameters(_Section):
    threshold: float
    neg_threshold: float | None
    min_speech_duration_ms: int
    max_speech_duration_s: float
    min_silence_duration_ms: int
    speech_pad_ms: int


class Transcribe(_Section):
    """Every keyword argument of `WhisperModel.transcribe` except `language` (ADR-0042). Defaults: the M4 gate."""

    task: str
    beam_size: int
    best_of: int
    patience: float
    length_penalty: float
    repetition_penalty: float
    no_repeat_ngram_size: int
    temperature: list[float]
    compression_ratio_threshold: float | None
    log_prob_threshold: float | None
    no_speech_threshold: float | None
    condition_on_previous_text: bool
    prompt_reset_on_temperature: float
    initial_prompt: str | None
    prefix: str | None
    suppress_blank: bool
    suppress_tokens: list[int] | None
    without_timestamps: bool
    max_initial_timestamp: float
    word_timestamps: bool
    prepend_punctuations: str
    append_punctuations: str
    multilingual: bool
    max_new_tokens: int | None
    chunk_length: int | None
    clip_timestamps: str | list[float]
    hallucination_silence_threshold: float | None
    hotwords: str | None
    language_detection_threshold: float | None
    language_detection_segments: int
    log_progress: bool
    vad_filter: bool
    vad_parameters: VadParameters

    @field_validator("task")
    @classmethod
    def _transcribe_only(cls, v: str) -> str:
        if v != "transcribe":
            raise ValueError("task must be 'transcribe'; transcripts stay in the spoken language (ADR-0041)")
        return v


class Asr(_Section):
    """ASR stage (ADR-0042). `languages_file` is resolved against the repo root when relative."""

    languages_file: Path
    model: str
    model_repo: str
    model_revision: str
    device: str
    device_index: int
    compute_type: str
    cpu_threads: int
    num_workers: int
    min_free_vram_mib: int
    timeout_min_s: float
    timeout_factor: float
    kill_grace_s: float
    vram_poll_interval_s: float
    progress_min_interval_s: float
    progress_min_step: float
    empty_min_duration_s: float
    warn_compression_ratio: float
    transcribe: Transcribe

    @field_validator("languages_file", mode="after")
    @classmethod
    def _under_repo(cls, v: Path) -> Path:
        v = Path(os.path.expandvars(str(v))).expanduser()
        return v if v.is_absolute() else repo_root() / v


class Settings(_Section):
    paths: Paths
    api: Api
    ingest: Ingest
    ollama: Ollama
    visual: Visual
    jobs: Jobs
    gpu: Gpu
    sources: Sources
    cache: Cache
    asr: Asr

    @model_validator(mode="before")
    @classmethod
    def _derive_jobs_paths(cls, data: Any) -> Any:
        """Fill null jobs.* paths from paths.data_dir, so jobs code only sees concrete absolute paths."""
        if isinstance(data, dict) and isinstance(data.get("jobs"), dict) and isinstance(data.get("paths"), dict):
            data_dir = data["paths"].get("data_dir")
            if data_dir is not None:
                jobs = dict(data["jobs"])
                for key, name in _JOBS_DERIVED.items():
                    if jobs.get(key) is None:
                        jobs[key] = str(Path(str(data_dir)) / name)
                data = {**data, "jobs": jobs}
                gpu = data.get("gpu")
                if isinstance(gpu, dict) and gpu.get("lease_path") is None:
                    data = {**data, "gpu": {**gpu, "lease_path": str(Path(str(jobs["run_dir"])) / "gpu.lock")}}
                ingest = data.get("ingest")
                file_cfg = ingest.get("file") if isinstance(ingest, dict) else None
                if isinstance(file_cfg, dict) and file_cfg.get("staging_dir") is None:
                    data = {**data, "ingest": {**ingest, "file": {**file_cfg, "staging_dir": str(Path(str(data_dir)) / "staging")}}}
        return data


def repo_root() -> Path:
    """Repo checkout: $INSIGHTEX_HOME, else derived from this file (backend/src/insightex/core/)."""
    env = os.environ.get("INSIGHTEX_HOME")
    return Path(env) if env else Path(__file__).resolve().parents[4]


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"cannot read config file {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"config file {path} must hold a mapping at the top level")
    return data


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _leaves(d: dict, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    return [p for k, v in d.items() for p in (_leaves(v, (*prefix, k)) if isinstance(v, dict) and v else [(*prefix, k)])]


def _nest(path: tuple[str, ...], value: Any) -> dict:
    for part in reversed(path):
        value = {part: value}
    return value


def _env_layer(environ: dict[str, str]) -> dict:
    layer: dict = {}
    canonical: dict[tuple[str, ...], tuple[str, str]] = {}
    for name, value in environ.items():
        if name.upper().startswith(ENV_PREFIX):
            path = tuple(p.lower() for p in name[len(ENV_PREFIX):].split("__"))
            if not all(path):
                raise ConfigError(f"env var {name}: expected {ENV_PREFIX}<SECTION>__<KEY>")
            canonical[path] = (name, value)
            layer = _merge(layer, _nest(path, value))
    for alias, path in ALIASES.items():
        if environ.get(alias):
            if path in canonical and canonical[path][1] != environ[alias]:
                raise ConfigError(
                    f"env vars {alias}={environ[alias]!r} and {canonical[path][0]}={canonical[path][1]!r} "
                    f"both set {'.'.join(path)} to different values; unset one"
                )
            if path not in canonical:
                layer = _merge(layer, _nest(path, environ[alias]))
    return layer


def _env_labels(environ: dict[str, str]) -> dict[tuple[str, ...], str]:
    labels = {tuple(p.lower() for p in n[len(ENV_PREFIX):].split("__")): f"env {n}"
              for n in environ if n.upper().startswith(ENV_PREFIX)}
    for alias, path in ALIASES.items():
        if environ.get(alias):
            labels.setdefault(path, f"env {alias}")
    return labels


def load_settings_with_sources(
    overrides: dict | None = None, environ: dict[str, str] | None = None
) -> tuple[Settings, dict[tuple[str, ...], str]]:
    """Return (settings, origin of every key) where origin is 'default', 'file <path>', 'env <VAR>' or 'override'."""
    environ = dict(os.environ if environ is None else environ)
    default_path = repo_root() / "config" / "default.yaml"
    if not default_path.is_file():
        raise ConfigError(f"default config not found: {default_path}")
    layers: list[tuple[dict, str | dict]] = [(_read_yaml(default_path), "default")]
    explicit = environ.get(CONFIG_ENV)
    local = Path(explicit).expanduser() if explicit else repo_root() / "config" / "local.yaml"
    if explicit and not local.is_file():
        raise ConfigError(f"{CONFIG_ENV} points at a missing file: {local}")
    if local.is_file():
        layers.append((_read_yaml(local), f"file {local}"))
    layers.append((_env_layer(environ), _env_labels(environ)))
    layers.append((overrides or {}, "override"))

    merged: dict = {}
    origins: dict[tuple[str, ...], str] = {}
    for layer, label in layers:
        merged = _merge(merged, layer)
        for path in _leaves(layer):
            origins[path] = label if isinstance(label, str) else label.get(path, "env")
    try:
        return Settings.model_validate(merged), origins
    except ValidationError as e:
        lines = []
        for err in e.errors():
            loc = tuple(str(p) for p in err["loc"])
            lines.append(f"{'.'.join(loc) or '<root>'}: {err['msg']} (from {origins.get(loc, 'default')})")
        raise ConfigError("invalid configuration:\n  " + "\n  ".join(lines)) from None


def load_settings(overrides: dict | None = None) -> Settings:
    return load_settings_with_sources(overrides)[0]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def render_effective(settings: Settings, origins: dict[tuple[str, ...], str]) -> str:
    """The merged config as YAML; each value is followed by a comment naming where it came from."""

    def scalar(v: Any) -> str:
        return yaml.safe_dump(v, default_flow_style=True, width=10**6).strip().removesuffix("\n...").strip()

    def walk(d: dict, prefix: tuple[str, ...], indent: int) -> list[str]:
        lines = []
        for k, v in d.items():
            if isinstance(v, dict):
                lines += [f"{' ' * indent}{k}:", *walk(v, (*prefix, k), indent + 2)]
            else:
                lines.append(f"{' ' * indent}{k}: {scalar(v)}  # {origins.get((*prefix, k), 'default')}")
        return lines

    return "\n".join(walk(settings.model_dump(mode="json"), (), 0)) + "\n"
