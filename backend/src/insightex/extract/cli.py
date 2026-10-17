"""`insightex extract-eval`: the M7 evaluation harness (ADR-0048).

    insightex extract-eval arms                                  the configured arms and which fields are still unset
    insightex extract-eval run --arm NAME --lecture ID --targets FILE [--windows FILE] [--out DIR] [--force]
    insightex extract-eval measure --lecture ID --model TAG [--prompt-file FILE] [--context-block-file FILE]
                                   [--k 1 3 4 5] [--context both|none|previous] [--num-ctx 4096 8192 ...]
                                   [--windows FILE] [--out FILE]

`run` extracts the target windows (a label_concepts sample.json or a JSON list of window indices) with one arm and
writes extraction.json, run.json and calls.jsonl to the run directory, which the scorer in tools/label_concepts reads.
It refuses to run until the extraction prompt is frozen (`extract.prompt_file` and `extract.prompt_sha256`).
Windows come from the lecture's index stage (windows.json) unless `--windows` names a file of the same shape.

`measure` makes real calls (one per case and num_ctx) under the exclusive GPU lease with the worst-case prompt for
each batch size k, with and without previous-window context, and reports VRAM, tokens/s, the real prompt tokens and
`ollama ps` (insightex.extract.measure). Before the freeze it takes a draft prompt with `--prompt-file` (its sha256 is
recorded and the report says it was not frozen).
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


def _measure(settings: Settings, args: argparse.Namespace, client: h.ModelClient | None = None) -> int:
    import datetime as dt
    import json

    from insightex.extract.measure import run_measurement
    from insightex.extract.prompts import draft_text, load_frozen

    x = settings.extract
    if args.prompt_file:
        prompt, frozen = draft_text(Path(args.prompt_file)), False
    else:
        prompt, frozen = load_frozen(x.prompt_file, x.prompt_sha256, "extraction prompt"), True
    contexts = {"both": [False, True], "none": [False], "previous": [True]}[args.context]
    block = None
    if True in contexts:
        block = (draft_text(Path(args.context_block_file)) if args.context_block_file
                 else load_frozen(x.context_block_file, x.context_block_sha256, "context block"))
    windows = lecture_windows(settings, args.lecture, args.windows)
    report = run_measurement(
        settings, client or h.OllamaModelClient(settings), lease_factory(settings),
        lambda: VramSampler(x.vram_poll_interval_s), lecture_id=args.lecture, model=args.model, windows=windows,
        prompt=prompt, prompt_frozen=frozen, context_block=block, ks=args.k, contexts=contexts,
        num_ctxs=args.num_ctx or [x.num_ctx], num_predict=args.num_predict or x.num_predict)
    print(f"{args.model} on {args.lecture} ({len(windows)} windows); prompt {prompt.sha256[:12]} "
          f"({'frozen' if frozen else 'DRAFT, not frozen'})")
    print(f"{'k':>2} {'ctx':>4} {'num_ctx':>7} {'est':>6} {'real':>6} {'tok/s':>6} {'gpu%':>5} {'peak MiB':>8} "
          f"{'+base':>6}  result")
    for c in report["cases"]:
        for r in c["runs"]:
            ps, vram = r.get("ollama_ps") or {}, r.get("vram") or {}
            tps = r.get("tokens_per_sec")
            cells = [r.get("prompt_eval_count"), f"{tps:.1f}" if tps else None, ps.get("gpu_pct"),
                     vram.get("peak_mib"), vram.get("peak_above_baseline_mib")]
            real, rate, gpu, peak, above = ("-" if v is None else v for v in cells)
            print(f"{c['k']:>2} {'yes' if c['context'] else 'no':>4} {r['num_ctx']:>7} {r['estimated_prompt_tokens']:>6} "
                  f"{real:>6} {rate:>6} {gpu:>5} {peak:>8} {above:>6}  "
                  f"{'PASS' if r['passes'] else 'fail: ' + str(r['reason'])}"
                  f"{' (output truncated)' if r.get('truncated') else ''}")
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_model = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in args.model)
    out = Path(args.out) if args.out else x.measure_dir / args.lecture / f"{safe_model}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
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
    p = sub.add_parser("measure", help="VRAM / num_ctx at the worst-case prompt (real Ollama calls)")
    p.add_argument("--lecture", required=True, help="workspace id")
    p.add_argument("--model", required=True, help="exact Ollama tag")
    p.add_argument("--prompt-file", help="draft extraction prompt (default: the frozen one from the config)")
    p.add_argument("--context-block-file", help="draft context block (default: the frozen one)")
    p.add_argument("--k", type=int, nargs="+", default=[1], help="batch sizes to measure (C3: 3 4 5)")
    p.add_argument("--context", choices=["both", "none", "previous"], default="none",
                   help="measure without, with, or both with and without previous-window context (C4)")
    p.add_argument("--num-ctx", type=int, nargs="+", help="context sizes to try (default: extract.num_ctx)")
    p.add_argument("--num-predict", type=int, help="output cap (default: extract.num_predict)")
    p.add_argument("--windows", help="windows.json-shaped file to use instead of the lecture's index stage")
    p.add_argument("--out", help="report file (default: <extract.measure_dir>/<lecture>/<model>_<time>.json)")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.action == "arms":
            return _arms(settings, args)
        if args.action == "measure":
            return _measure(settings, args, client)
        return _run(settings, args, client)
    except (ConfigError, ArmConfigError, PromptNotFrozen, h.HarnessError, OllamaError, OSError, ValueError,
            GpuBusy, GpuUnavailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
