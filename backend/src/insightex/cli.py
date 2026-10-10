"""The `insightex` command.

    insightex config show        merged settings as YAML, each value tagged with where it came from
    insightex config validate    exit 0 if the settings and the language file load, else print the error and exit 1
    insightex languages list     the selectable lecture languages by tier (--json for machine output)
    insightex db migrate         create or upgrade the job database
    insightex worker             run the single job worker
    insightex gpu status         GPU lease free or busy
    insightex cache ...          list, delete, pin, unpin, gc
    insightex jobs ...           enqueue-dummy, list, show, cancel, retry (insightex.jobs.cli)
    insightex probe|ingest|ingest-file ...   link and local-file ingestion (insightex.ingest.cli)
"""

from __future__ import annotations

import argparse
import json
import sys

from insightex.core.config import ConfigError, load_settings_with_sources, render_effective


def _config(args: argparse.Namespace) -> int:
    from insightex.asr.languages import LanguageConfigError, languages_for

    try:
        settings, origins = load_settings_with_sources()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.action == "show":
        print(render_effective(settings, origins), end="")
        return 0
    try:
        langs = languages_for(settings)
    except LanguageConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    tested = sum(1 for e in langs.entries if e.tier == "tested")
    print(f"config OK (languages: {tested} tested, {len(langs.entries) - tested} untested, "
          f"from {settings.asr.languages_file})")
    return 0


def _languages(args: argparse.Namespace) -> int:
    from insightex.asr.languages import LanguageConfigError, languages_for

    try:
        settings = load_settings_with_sources()[0]
        groups = languages_for(settings).grouped()
    except (ConfigError, LanguageConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"groups": groups}, ensure_ascii=False, indent=2))
        return 0
    for group in groups:
        print(f"{group['label']} ({len(group['languages'])}):")
        for lang in group["languages"]:
            print(f"  {lang['id']:<20} {lang['label']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("probe", "ingest", "ingest-file", "-v", "--verbose"):
        from insightex.ingest.cli import main as ingest_main

        return ingest_main(argv)
    parser = argparse.ArgumentParser(prog="insightex")
    sub = parser.add_subparsers(dest="command", required=True)
    p_config = sub.add_parser("config", help="inspect or validate the configuration")
    p_config.add_argument("action", choices=["show", "validate"])
    p_config.set_defaults(func=_config)
    p_lang = sub.add_parser("languages", help="list the selectable lecture languages")
    p_lang.add_argument("action", choices=["list"])
    p_lang.add_argument("--json", action="store_true", help="print JSON grouped by tier")
    p_lang.set_defaults(func=_languages)
    from insightex.jobs import cli as jobs_cli

    jobs_cli.register(sub)
    sub.add_parser("probe", help="print metadata for a link (see: insightex probe <url>)")
    sub.add_parser("ingest", help="enqueue a link ingest job (see: insightex ingest <url> --confirm-rights)")
    sub.add_parser("ingest-file", help="ingest a local video (see: insightex ingest-file <path> --confirm-rights)")
    args = parser.parse_args(argv)
    if args.command in ("db", "worker", "jobs", "gpu", "cache"):
        return jobs_cli.run(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
