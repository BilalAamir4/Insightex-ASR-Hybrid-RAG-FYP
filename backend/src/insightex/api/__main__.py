"""Start the web server: bash scripts/run_in_env.sh python -m insightex.api"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import uvicorn

from insightex.api.app import create_app
from insightex.asr.languages import LanguageConfigError
from insightex.core.config import ConfigError, get_settings

_REFUSED_HOSTS = {"0.0.0.0", "::", ""}


def _setup_logging(logs_dir: Path) -> None:
    root = logging.getLogger("insightex")
    root.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)
    log_dir = logs_dir / "api"
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / "api.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)


def main() -> None:
    cfg = get_settings()
    host, port = cfg.api.host, cfg.api.port
    if host in _REFUSED_HOSTS:
        raise ConfigError(f"api.host {host!r} would expose the server on the network; use 127.0.0.1")
    _setup_logging(cfg.paths.logs_dir)
    try:
        app = create_app(app_settings=cfg)
    except LanguageConfigError as exc:
        sys.exit(f"error: {exc}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
