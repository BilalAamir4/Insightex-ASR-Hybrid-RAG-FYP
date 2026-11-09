"""Arm A reuse check for C4 (ADR-0048 Amendment 10, decision 2; the identity rule of Amendment 8, decision 2).

Copied from ../C2/scripts/arm_a_reuse_check.py; only the comparison, the arm name and the output path differ.

Compares everything that affects original-language extraction between the C1 Gemma run and the current code and
config. Makes no generation call: Ollama is asked only for its version and the model digest.

    bash scripts/run_in_env.sh python docs/evidence/m7/<lecture>/C4/scripts/arm_a_reuse_check.py

Writes arm_a_reuse_check.json next to scripts/. Exit 0 when every item matches, 1 otherwise.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from insightex.core.config import load_settings, repo_root
from insightex.extract import harness as h
from insightex.extract.extraction_schema import check_document
from insightex.extract.prompts import extraction_format, extraction_messages, sha256_text

LECTURE = "sha256-de27cb67c2acbedebd0c2c7416932b8a"
RUN_COMMIT = "bd6e9db"  # last commit touching extract/ or llm/ before the C1 run (2026-10-18T17:38Z; run 18:00:07Z)
REPO = repo_root()
C1 = REPO / "docs/evidence/m7" / LECTURE / "C1" / "C1-gemma4-e4b"
ARM = "C4-window"
OUT = Path(__file__).resolve().parents[1] / "arm_a_reuse_check.json"

# The code on the original-language extraction path: request building, the call, reply parsing and validation.
FUNCTIONS = {
    "backend/src/insightex/extract/prompts.py": ["load_frozen", "split_extraction_prompt", "split_prompt",
                                                  "errors_text", "retry_messages", "system_message",
                                                  "extraction_messages", "_name", "extraction_format"],
    "backend/src/insightex/extract/harness.py": ["load_prompts", "plan_calls", "canonical", "drop_dangling",
                                                  "parse_reply", "extraction_num_predict", "_options",
                                                  "prompt_overflow", "truncate_self_test"],
}
WHOLE_FILES = ["backend/src/insightex/extract/extraction_schema.py", "backend/src/insightex/llm/ollama_client.py",
               "backend/src/insightex/extract/extraction.schema.json", "config/prompts/m7_extraction_v2.txt"]


def git_show(commit: str, path: str) -> str | None:
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def function_sources(src: str) -> dict[str, str]:
    tree = ast.parse(src)
    return {n.name: ast.unparse(n) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def module_constants(src: str) -> dict[str, str]:
    out = {}
    for n in ast.parse(src).body:
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    out[t.id] = ast.unparse(n.value) if n.value is not None else ""
    return out


def item(name: str, c1, now, note: str = "") -> dict:
    return {"item": name, "c1": c1, "now": now, "same": c1 == now, **({"note": note} if note else {})}


def main() -> int:
    settings = load_settings()
    run = json.loads((C1 / "run.json").read_text(encoding="utf-8"))
    calls = [json.loads(line) for line in (C1 / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line]
    extraction = json.loads((C1 / "extraction.json").read_text(encoding="utf-8"))
    items = []

    # model and Ollama
    client = h.OllamaModelClient(settings)
    with urllib.request.urlopen(settings.ollama.base_url.rstrip("/") + "/api/version", timeout=5) as r:
        version = json.loads(r.read())["version"]
    items.append(item("Ollama version", "0.40.2", version,
                      "C1 run.json does not record it; 0.40.2 is the version of every Session 2b measurement "
                      "(ADR-0049) and no upgrade has been made since"))
    items.append(item("model digest", run["model_digest"], client.digest("gemma4:e4b")))

    # prompt, options
    prompts = h.load_prompts(settings, next(a for a in __import__("insightex.extract.arms", fromlist=["x"])
                                            .load_arms(settings.extract.arms_file).values() if a.name == ARM))
    items.append(item("extraction prompt sha256", run["prompt_sha256"], prompts.extraction.sha256))
    opts_now = {**h._options(settings, h.extraction_num_predict(settings, 1)),
                "num_predict_per_window": settings.extract.num_predict_per_window,
                "num_predict_rule": "num_predict_per_window x target windows in the call",
                "token_estimate_scale": settings.extract.estimate_scale("gemma4:e4b")}
    items.append(item("options", run["options"], opts_now))
    items.append(item("retry_error_chars", run["retry_error_chars"], settings.extract.retry_error_chars))
    items.append(item("self-test num_ctx / probe", (run["truncate_self_test"]["num_ctx"],
                                                     run["truncate_self_test"]["probe_chars"]),
                      (settings.extract.self_test_num_ctx,
                       len("\n".join(h.SELF_TEST_LINE.format(i=i)
                                     for i in range(1, settings.extract.self_test_probe_lines + 1))))))
    items.append(item("arm (model, input, batch_k, context)",
                      {k: run["arm"][k] for k in ("model", "input", "batch_k", "context")},
                      {"model": "gemma4:e4b", "input": "original", "batch_k": 1, "context": "none"}))

    # window texts and the full requests
    from insightex.extract.cli import lecture_windows

    windows = lecture_windows(settings, LECTURE, None)
    grid = {w.window_index: w for w in windows}
    sample = REPO / "tools/label_concepts/labels" / LECTURE / "sample.json"
    targets = h.load_targets(sample, grid)  # checks start/end and text sha256 against the sample
    items.append(item("targets", run["targets"], targets, "load_targets checked each window's text sha256 against "
                                                          "sample.json"))
    systems = set()
    key_rows = []
    saved = h.HARNESS_VERSION
    h.HARNESS_VERSION = run["harness_version"]  # compare requests, not the version number
    try:
        c1_keys = {tuple(c["targets"]): c["key"] for c in calls if c["kind"] == "extract" and c["attempt"] == 1}
        cache = h.ReplyCache(Path("/nonexistent"))
        for t in targets:
            messages = extraction_messages(prompts.extraction, None, [(t, grid[t].text)], [])
            systems.add(sha256_text(messages[0]["content"]))
            request = {"model": "gemma4:e4b", "model_digest": client.digest("gemma4:e4b"), "messages": messages,
                       "format": extraction_format([t]), "options": h._options(settings, h.extraction_num_predict(
                           settings, 1))}
            key_rows.append({"window_index": t, "c1_key": c1_keys.get((t,)), "now_key": cache.key("extract", request, 1)})
    finally:
        h.HARNESS_VERSION = saved
    items.append(item("system message sha256", run["system_message_sha256"], sorted(systems)))
    same_keys = sum(1 for r in key_rows if r["c1_key"] == r["now_key"])
    items.append(item("extraction request keys (attempt 1, rebuilt with current code, harness version set to 7)",
                      f"{len(key_rows)} keys", f"{same_keys} of {len(key_rows)} equal",
                      "a key is the sha256 of model, digest, messages, format and options; equal keys mean "
                      "byte-identical requests"))
    items[-1]["same"] = same_keys == len(key_rows) == len(targets)

    # reply handling: re-parse every C1 reply with the current code and compare with C1's extraction.json
    reparsed = []
    for t in targets:
        att = [c for c in calls if c["kind"] == "extract" and c.get("targets") == [t]]
        used = next(w["attempt_used"] for w in run["windows"] if w["window_index"] == t)
        c = next(a for a in att if a["attempt"] == used)
        plan = h.CallPlan((t,), ())
        out = h.parse_reply(c["content"], c["error"], plan, LECTURE, grid)[t]
        reparsed.append(out.record if out.valid else None)
    doc = {**extraction, "windows": [r for r in reparsed if r is not None]}
    items.append(item("C1 replies re-parsed and validated with the current code == C1 extraction.json",
                      "C1 extraction.json", "equal" if doc == extraction and not check_document(doc) else "differs"))
    items[-1]["same"] = doc == extraction and not check_document(doc)

    # code on the extraction path
    code_rows = []
    for path, names in FUNCTIONS.items():
        old_src, new_src = git_show(RUN_COMMIT, path), (REPO / path).read_text(encoding="utf-8")
        old_f, new_f = function_sources(old_src), function_sources(new_src)
        old_c, new_c = module_constants(old_src), module_constants(new_src)
        for n in names:
            code_rows.append({"what": f"{path}:{n}", "same": old_f.get(n) == new_f.get(n),
                              "in_c1": n in old_f, "now": n in new_f})
        for const in ("USER_FORMAT_VERSION", "FORMAT_VERSION", "RETRY_MARKER", "ERRORS_SLOT", "RETRIES",
                      "SELF_TEST_FORMAT", "SELF_TEST_LINE"):
            if const in old_c or const in new_c:
                code_rows.append({"what": f"{path}:{const}", "same": old_c.get(const) == new_c.get(const),
                                  "c1": old_c.get(const), "now": new_c.get(const)})
    # behaviour of the prompt helpers whose source changed in the C2 refactor (split_prompt generalised for the
    # translation prompt): the C1-era module is loaded from git and both are run on the frozen extraction prompt
    import types

    old_mod = types.ModuleType("prompts_c1")
    sys.modules["prompts_c1"] = old_mod  # dataclasses looks the module up
    exec(compile(git_show(RUN_COMMIT, "backend/src/insightex/extract/prompts.py"), "prompts_c1", "exec"),
         old_mod.__dict__)
    from insightex.extract import prompts as new_mod

    old_frozen = old_mod.load_frozen(prompts.extraction.path, prompts.extraction.sha256, "extraction prompt")
    errs = ["window 4: concepts[0].label is empty", "x" * 2000]
    base = new_mod.extraction_messages(prompts.extraction, None, [(1, "synthetic")], [])
    behaviour = {
        "split_extraction_prompt": old_mod.split_extraction_prompt(old_frozen)
        == new_mod.split_extraction_prompt(prompts.extraction),
        "retry_messages": old_mod.retry_messages(base, old_frozen, errs, settings.extract.retry_error_chars)
        == new_mod.retry_messages(base, prompts.extraction, errs, settings.extract.retry_error_chars),
        "extraction_messages": old_mod.extraction_messages(old_frozen, None, [(1, "synthetic")], []) == base,
    }
    for n, ok in behaviour.items():
        code_rows.append({"what": f"behaviour on the frozen prompt: {n} (C1 code vs now)", "same": ok})
    report_note = ("A source difference in split_extraction_prompt or retry_messages is the C2 refactor "
                   "(split_prompt shared with the translation prompt); the behaviour rows run the C1-era and current "
                   "functions on the frozen prompt. C1 Gemma needed no retry (0 of 20), so retry_messages was not "
                   "used in the run.")
    for path in WHOLE_FILES:
        old, new = git_show(RUN_COMMIT, path), (REPO / path).read_text(encoding="utf-8")
        code_rows.append({"what": path, "same": old == new,
                          "c1_sha256": hashlib.sha256((old or "").encode()).hexdigest(),
                          "now_sha256": hashlib.sha256(new.encode()).hexdigest()})
    report = {"lecture_id": LECTURE, "c1_run": str(C1.relative_to(REPO)), "c1_run_created_at": run["created_at"],
              "c1_code_commit": RUN_COMMIT, "c1_harness_version": run["harness_version"],
              "now_harness_version": h.HARNESS_VERSION, "items": items, "code": code_rows,
              "request_keys": key_rows, "note": report_note}
    # changed in the C2 refactor, behaviour on the extraction path covered by the behaviour rows above:
    # split_prompt is new (split_extraction_prompt now calls it); retry_messages takes an optional `what`;
    # load_prompts wraps only the translation prompt (english arms); its extraction branch is unchanged
    source_only = {f"backend/src/insightex/extract/prompts.py:{n}"
                   for n in ("split_extraction_prompt", "split_prompt", "retry_messages")}
    source_only.add("backend/src/insightex/extract/harness.py:load_prompts")
    report["identical_requests_and_parsing"] = all(i["same"] for i in items) and all(
        r["same"] for r in code_rows if r["what"] not in source_only)
    report["source_only_differences"] = [r["what"] for r in code_rows if r["what"] in source_only and not r["same"]]
    report["identical"] = report["identical_requests_and_parsing"]
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for i in items:
        print(f"{'SAME' if i['same'] else 'DIFF'}  {i['item']}")
    for r in code_rows:
        if not r["same"]:
            print(f"DIFF  code {r['what']}{' (source only)' if r['what'] in source_only else ''}")
    for r in code_rows:
        if r['what'].startswith('behaviour'):
            print(f"{'SAME' if r['same'] else 'DIFF'}  {r['what']}")
    print(f"code items: {sum(r['same'] for r in code_rows)} of {len(code_rows)} same")
    print(f"source-only differences (refactor; behaviour rows above): {report['source_only_differences']}")
    print(f"identical requests and parsing: {report['identical']}; wrote {OUT}")
    return 0 if report["identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
