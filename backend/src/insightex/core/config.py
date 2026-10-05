"""Config loading: config/default.yaml deep-merged with config/local.yaml, ${VAR} expanded from the env."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(Exception):
    pass


def repo_root() -> Path:
    """Repo checkout: $INSIGHTEX_HOME, else derived from this file (backend/src/insightex/core/)."""
    env = os.environ.get("INSIGHTEX_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4]


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        # Unset variables are left as ${VAR}; require_path() reports them when the value is used.
        return _VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(config_dir: Path | None = None) -> dict:
    config_dir = config_dir or repo_root() / "config"
    default = config_dir / "default.yaml"
    if not default.is_file():
        raise ConfigError(f"config file not found: {default}")
    cfg = yaml.safe_load(default.read_text(encoding="utf-8")) or {}
    local = config_dir / "local.yaml"
    if local.is_file():
        cfg = _merge(cfg, yaml.safe_load(local.read_text(encoding="utf-8")) or {})
    return _expand(cfg)


def require_path(value: Any, key: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"config key {key} is missing")
    if _VAR_RE.search(value):
        raise ConfigError(f"config key {key} has an unset variable: {value} (source env/insightex_env.sh)")
    return Path(value).expanduser()
