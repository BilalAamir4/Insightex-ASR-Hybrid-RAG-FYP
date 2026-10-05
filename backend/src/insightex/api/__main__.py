"""Start the web server: bash scripts/run_in_env.sh python -m insightex.api"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

from insightex.api.app import create_app
from insightex.core.config import ConfigError, load_config

_REFUSED_HOSTS = {"0.0.0.0", "::", ""}


def _setup_logging() -> None:
    root = logging.getLogger("insightex")
    root.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)
    data = os.environ.get("INSIGHTEX_DATA")
    if data:
        log_dir = Path(data) / "logs" / "api"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "api.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(fh)


def main() -> None:
    cfg = load_config()
    api = cfg.get("api") or {}
    host, port = str(api.get("host", "127.0.0.1")), int(api.get("port", 8000))
    if host in _REFUSED_HOSTS:
        raise ConfigError(f"api.host {host!r} would expose the server on the network; use 127.0.0.1")
    _setup_logging()
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
