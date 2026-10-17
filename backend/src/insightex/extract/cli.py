"""`insightex extract-eval`: the M7 evaluation harness (ADR-0048).

    insightex extract-eval arms                                  the configured arms and which fields are still unset
    insightex extract-eval run --arm NAME --lecture ID --targets FILE [--windows FILE] [--out DIR] [--force]

`run` extracts the target windows (a label_concepts sample.json or a JSON list of window indices) with one arm and
writes extraction.json, run.json and calls.jsonl to the run directory, which the scorer in tools/label_concepts reads.
It refuses to run until the extraction prompt is frozen (`extract.prompt_file` and `extract.prompt_sha256`).
Windows come from the lecture's index stage (windows.json) unless `--windows` names a file of the same shape.
"""

from __future__ import annotations

import argparse
import sys
from contextlib import nullcontext
from pathlib import Path

from insightex.core.config import ConfigError, Settings, load_settings
from insightex.extract import harness as h
from insightex.extract.arms import ArmConfigError, load_arms
from insightex.extract.prompts import PromptNotFrozen
from insightex.extract.vram import VramSampler
from insightex.jobs.gpu_lease import GpuBusy, GpuUnavailable
from insightex.llm.ollama_client import OllamaError


def lecture_windows(settings: Settings, lecture_id: str, windows_file: str | None) -> list[h.WindowText]:
    if windows_file:
        return h.load_windows_json(Path(windows_file))
    from insightex.index.store import WINDOWS_JSON
    from insightex.jobs.workspace import Workspaces

    directory = Workspaces(settings.jobs.workspaces_dir).stage_output_dir(lecture_id, "index")
    if directory is None:
        raise h.HarnessError(f"lecture {lecture_id!r} has no index stage (windows.json); ingest it first")
    return h.load_windows_json(directory / WINDOWS_JSON)


def lease_factory(settings: Settings):
    if not settings.gpu.lease_enabled:
        return lambda purpose: nullcontext()
    from insightex.jobs.gpu_lease import FileGpuLease

    lease = FileGpuLease(settings)
    return lambda purpose: lease.exclusive(purpose, settings.extract.lease_timeout_s)


def make_context(settings: Settings, client: h.ModelClient | None = None) -> h.RunContext:
    return h.RunContext(settings=settings, client=client or h.OllamaModelClient(settings),
                        cache=h.ReplyCache(settings.extract.cache_dir), lease=lease_factory(settings),
                        sampler=VramSampler(settings.extract.vram_poll_interval_s))


def _arms(settings: Settings, _args: argparse.Namespace) -> int:
    for arm in load_arms(settings.extract.arms_file).values():
        unset = arm.missing()
        print(f"{arm.name:<16} {arm.comparison} model={arm.model} input={arm.input} batch_k={arm.batch_k} "
              f"context={arm.context}" + (f"   unset: {', '.join(unset)}" if unset else ""))
    return 0


def _run(settings: Settings, args: argparse.Namespace, client: h.ModelClient | None = None) -> int:
    arms = load_arms(settings.extract.arms_file)
    if args.arm not in arms:
        raise h.HarnessError(f"no arm {args.arm!r} in {settings.extract.arms_file}; known: {', '.join(arms)}")
    arm = arms[args.arm]
    arm.require_complete()
    prompts = h.load_prompts(settings, arm)
    windows = lecture_windows(settings, args.lecture, args.windows)
    targets = h.load_targets(Path(args.targets), {w.window_index: w for w in windows})
    out = Path(args.out) if args.out else h.default_out_dir(settings, args.lecture, arm)
    if (out / "run.json").exists() and not args.force:
        raise h.HarnessError(f"{out} already holds a run; pass --force to replace it (the cache keeps the replies)")
    ctx = make_context(settings, client)
    doc, run = h.run_arm(ctx, arm, prompts, args.lecture, windows, targets)
    h.write_evidence(out, doc, run, ctx.calls_log)
    t = run["totals"]
    print(f"{arm.name}: {t['windows']} windows, {t['invalid_windows']} invalid, {t['retried_windows']} retried, "
          f"{t['dropped_relations']} dangling relations dropped; {t['calls']} calls ({t['cache_hits']} from cache)")
    print(f"wrote {out}")
    return 0


def main(argv: list[str], client: h.ModelClient | None = None) -> int:
    parser = argparse.ArgumentParser(prog="insightex extract-eval", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("arms", help="list the configured arms")
    p = sub.add_parser("run", help="run one arm over the target windows and write the evidence")
    p.add_argument("--arm", required=True)
    p.add_argument("--lecture", required=True, help="workspace id")
    p.add_argument("--targets", required=True, help="label_concepts sample.json, or a JSON list of window indices")
    p.add_argument("--windows", help="windows.json-shaped file to use instead of the lecture's index stage")
    p.add_argument("--out", help="run directory (default: <extract.evidence_dir>/<lecture>/<comparison>/<arm>)")
    p.add_argument("--force", action="store_true", help="replace an existing run directory's files")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.action == "arms":
            return _arms(settings, args)
        return _run(settings, args, client)
    except (ConfigError, ArmConfigError, PromptNotFrozen, h.HarnessError, OllamaError, OSError, ValueError,
            GpuBusy, GpuUnavailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
