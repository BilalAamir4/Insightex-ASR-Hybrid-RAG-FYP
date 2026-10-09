"""CLI for link ingestion.

    insightex probe <url>                         metadata without downloading
    insightex ingest <url> --confirm-rights       enqueue an ingest_link job (a running `insightex worker` does it)

Full error details go to <paths.data_dir>/logs/ingest/ingest.log; the terminal shows the user-facing message.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from insightex.core.config import get_settings
from insightex.ingest.link_jobs import enqueue_link
from insightex.ingest.probe import probe
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.jobs import db
from insightex.jobs.workspace import Workspaces


def _setup_logging(verbose: bool, logs_dir: Path) -> Path:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if verbose else logging.ERROR + 10)  # quiet unless -v
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)
    log_dir = logs_dir / "ingest"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ingest.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    return log_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="insightex")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging to the terminal")
    sub = parser.add_subparsers(dest="command", required=True)
    p_probe = sub.add_parser("probe", help="print metadata as JSON without downloading media")
    p_probe.add_argument("url")
    p_ingest = sub.add_parser("ingest", help="enqueue an ingest_link job; prints the job id")
    p_ingest.add_argument("url")
    p_ingest.add_argument("--confirm-rights", action="store_true",
                          help="confirm you have the right to use this video (required)")
    args = parser.parse_args(argv)

    app_settings = get_settings()
    log_file = _setup_logging(args.verbose, app_settings.paths.logs_dir)
    settings = IngestSettings.from_settings(app_settings)
    try:
        if args.command == "probe":
            result = probe(args.url, settings, Workspaces(app_settings.jobs.workspaces_dir))
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if not args.confirm_rights:
            raise IngestError(ErrorCode.RIGHTS_NOT_CONFIRMED)
        conn = db.open_connection(app_settings.jobs.db_path, app_settings.jobs.busy_timeout_ms)
        db.migrate(conn)
        job_id, workspace_id, deduplicated = enqueue_link(conn, app_settings, args.url)
        print(json.dumps({"job_id": job_id, "workspace_id": workspace_id, "deduplicated": deduplicated}))
        return 0
    except IngestError as exc:
        print(json.dumps({"error": exc.to_dict()}, ensure_ascii=False), file=sys.stderr)
        if log_file:
            print(f"details: {log_file}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
