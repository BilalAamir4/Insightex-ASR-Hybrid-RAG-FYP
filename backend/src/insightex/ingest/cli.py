"""Test CLI for URL ingestion.

    python -m insightex.ingest.cli probe <url>
    python -m insightex.ingest.cli ingest <url> --confirm-rights

Full error details go to <paths.data_dir>/logs/ingest/ingest.log; the terminal shows the user-facing message.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from insightex.core.config import get_settings
from insightex.ingest.engine import ingest, probe
from insightex.ingest.errors import IngestError
from insightex.ingest.settings import IngestSettings


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


class _TerminalProgress:
    def __init__(self) -> None:
        self.stage: str | None = None
        self.started = time.monotonic()
        self.tty = sys.stderr.isatty()

    def __call__(self, stage: str, fraction: float | None, message: str) -> None:
        pct = f"{fraction * 100:5.1f}%" if fraction is not None else "  ... "
        line = f"[{stage:<16}] {pct}  {message}"
        if self.tty:
            if stage != self.stage and self.stage is not None:
                sys.stderr.write("\n")
            sys.stderr.write("\r" + line[:110].ljust(110))
            sys.stderr.flush()
        elif stage != self.stage or fraction in (0.0, 1.0):
            print(line, file=sys.stderr)
        self.stage = stage

    def finish(self) -> None:
        if self.tty and self.stage is not None:
            sys.stderr.write("\n")
        print(f"elapsed: {time.monotonic() - self.started:.1f}s", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m insightex.ingest.cli")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging to the terminal")
    sub = parser.add_subparsers(dest="command", required=True)
    p_probe = sub.add_parser("probe", help="print metadata as JSON without downloading media")
    p_probe.add_argument("url")
    p_ingest = sub.add_parser("ingest", help="download and process a lecture video")
    p_ingest.add_argument("url")
    p_ingest.add_argument("--confirm-rights", action="store_true",
                          help="confirm you have the right to use this video (required)")
    args = parser.parse_args(argv)

    app_settings = get_settings()
    log_file = _setup_logging(args.verbose, app_settings.paths.logs_dir)
    settings = IngestSettings.from_settings(app_settings)
    try:
        if args.command == "probe":
            result = probe(args.url, settings=settings)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0
        bar = _TerminalProgress()
        try:
            manifest = ingest(args.url, rights_confirmed=args.confirm_rights, progress_cb=bar, settings=settings)
        finally:
            bar.finish()
        print(Path(settings.lectures_dir) / manifest.lecture_id / "manifest.json")
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
