"""The `insightex` command.

    insightex config show        merged settings as YAML, each value tagged with where it came from
    insightex config validate    exit 0 if the settings load, else print the error and exit 1
    insightex probe|ingest ...   link ingestion (insightex.ingest.cli)
"""

from __future__ import annotations

import argparse
import sys

from insightex.core.config import ConfigError, load_settings_with_sources, render_effective


def _config(args: argparse.Namespace) -> int:
    try:
        settings, origins = load_settings_with_sources()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.action == "show":
        print(render_effective(settings, origins), end="")
    else:
        print("config OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("probe", "ingest", "-v", "--verbose"):
        from insightex.ingest.cli import main as ingest_main

        return ingest_main(argv)
    parser = argparse.ArgumentParser(prog="insightex")
    sub = parser.add_subparsers(dest="command", required=True)
    p_config = sub.add_parser("config", help="inspect or validate the configuration")
    p_config.add_argument("action", choices=["show", "validate"])
    p_config.set_defaults(func=_config)
    sub.add_parser("probe", help="print metadata for a link (see: insightex probe <url>)")
    sub.add_parser("ingest", help="download and process a lecture video (see: insightex ingest <url> --confirm-rights)")
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
