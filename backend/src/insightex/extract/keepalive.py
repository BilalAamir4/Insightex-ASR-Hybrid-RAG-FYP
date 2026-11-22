"""`insightex extract-eval keepalive`: the ADR-0056 test of keeping Gemma loaded between extract-stage calls.

One session, under the exclusive GPU lease (ADR-0056 decision 4):

  1. checks: the served Ollama version and Gemma digest are the frozen ones; every resident model is unloaded and
     /api/ps is empty; the VRAM baseline is read with no model loaded;
  2. the run-start self-test, once (ADR-0049 Amendment 2);
  3. references, `keep_alive` 0 (reload per call): Day 4 run 0 (23 windows in order; its records must equal the
     published stage v2 records), then the ADR-0049 synthetic case (k = 1, k = 3; each reply must have ADR-0049's
     fresh-load hash). If either does not reproduce, the session stops: a reproducibility problem, not a result;
  4. one loaded session at `extract.keepalive.keep_alive`: Day 4 repeats 1 and 2 in order and 3 reversed, then the
     synthetic case's repeats 1 and 2 in order and 3 reversed. Before every repeat after the first and after the
     last: exactly Gemma resident (frozen digest, num_ctx, not expiring) and idle VRAM above baseline at least
     `idle_vram_min_ratio` of the figure after Day 4 repeat 1. Every call's `load_duration` is checked: only the
     first call of Day 4 repeat 1 may load the model;
  5. the model is unloaded, and the evidence is written.

Outcome: `fail` if any reply or parsed result differed from its reference in any repeat (even in a void session:
reload per call cannot create a difference, so it can only come from the loaded state); otherwise `void` if a check
or Ollama failed; `stopped_reference` if a reference did not reproduce; `pass` otherwise.

Day 4 requests are the stage's own (`stage.window_request`, reply handling `stage.evaluate_attempt`) with only
`keep_alive` changed. The synthetic case is sent from the frozen file of its exact request bodies (pinned sha256).
Only the Day 4 lecture is accepted. Nothing is written into any workspace: Day 4's windows and v2 records are read
only. Evidence goes to `<extract.keepalive.out_dir>/<UTC stamp>/`: session.json and windows.json (counts, timings,
hashes, statuses, equalities) and replies.jsonl (the raw replies, Day 4 and the synthetic case only). The command
prints counts only.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from insightex.core.config import Settings
from insightex.extract import stage as extract_stage
from insightex.extract.calls import SelfTestFailed, WindowText, load_windows_json, run_self_test
from insightex.extract.prompts import FrozenText, load_frozen, split_extraction_prompt
from insightex.extract.vram import VramSampler
from insightex.index import store as index_store
from insightex.jobs.workspace import Workspaces
from insightex.llm import ollama_client
from insightex.llm.ollama_client import OllamaError, OutputTruncated, PromptTooLong

PURPOSE = "m7-keepalive (ADR-0056)"
HELD_OUT = "yt-5vqk6HnITko"  # the M7 held-out lecture: refused by name as well as by the Day 4-only rule
REPEATS = 3  # ADR-0056 decision 1: a rule, not a tunable (two in order, the last reversed)
CASE_BODY_KEYS = ("model", "messages", "stream", "think", "format", "options")


class KeepaliveRefused(Exception):
    """The session cannot start (wrong lecture, wrong synthetic file, missing inputs, frozen values not served).
    Raised before any model call; nothing is written."""


# -- the client ----------------------------------------------------------------------------------------------------


class SessionClient(Protocol):
    def version(self) -> str: ...

    def digest(self, model: str) -> str: ...

    def resident(self) -> list[dict[str, Any]]: ...

    def unload(self, model: str) -> bool: ...

    def chat(self, model: str, messages: list[dict], format_schema: dict, num_ctx: int, num_predict: int, *,
             keep_alive: int | str, truncate: bool | None, temperature: float | None = None,
             seed: int | None = None) -> tuple[str, dict[str, Any]]: ...


class OllamaSessionClient:
    """chat_raw with the call's keep_alive and truncate (None sends no `truncate` field, as ADR-0049's run did)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def version(self) -> str:
        return ollama_client.server_version(self.settings.ollama)

    def digest(self, model: str) -> str:
        return ollama_client.model_digest(model, self.settings.ollama)

    def resident(self) -> list[dict[str, Any]]:
        return ollama_client.loaded_models(self.settings.ollama)

    def unload(self, model: str) -> bool:
        s = self.settings
        return ollama_client.unload(s.ollama, model, poll_interval_s=s.gpu.ollama_poll_interval_s,
                                    timeout_s=s.ollama.unload_wait_s)

    def chat(self, model: str, messages: list[dict], format_schema: dict, num_ctx: int, num_predict: int, *,
             keep_alive: int | str, truncate: bool | None, temperature: float | None = None,
             seed: int | None = None) -> tuple[str, dict[str, Any]]:
        content, m = ollama_client.chat_raw(
            messages, format_schema, num_ctx, ollama=self.settings.ollama, keep_alive=keep_alive,
            temperature=temperature, seed=seed, num_predict=num_predict, model=model,
            estimate_scale=self.settings.extract.estimate_scale(model), truncate=truncate, budget_rule="warn")
        return content, asdict(m)


class _Bound:
    """A SessionClient with fixed keep_alive and truncate, in the ModelClient shape run_self_test expects."""

    def __init__(self, client: SessionClient, keep_alive: int | str, truncate: bool | None) -> None:
        self.client, self.keep_alive, self.truncate = client, keep_alive, truncate

    def chat(self, model: str, messages: list[dict], format_schema: dict, num_ctx: int,
             num_predict: int) -> tuple[str, dict[str, Any]]:
        return self.client.chat(model, messages, format_schema, num_ctx, num_predict, keep_alive=self.keep_alive,
                                truncate=self.truncate)


# -- inputs --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SyntheticCase:
    name: str
    body: dict[str, Any]
    reference_sha256: str


@dataclass(frozen=True)
class Inputs:
    lecture_id: str
    windows: list[WindowText]
    index_key: str
    reference_records: dict[int, str]  # window index -> canonical v2 record
    prompt: FrozenText
    cases: list[SyntheticCase]
    case_file_sha256: str


def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cases(settings: Settings) -> tuple[list[SyntheticCase], str]:
    ka = settings.extract.keepalive
    path = ka.synthetic_case_file
    if not path.is_file():
        raise KeepaliveRefused(f"synthetic case file {path} does not exist")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != ka.synthetic_case_sha256:
        raise KeepaliveRefused(f"synthetic case file {path} has sha256 {digest}, not the frozen "
                               f"{ka.synthetic_case_sha256}; only the frozen ADR-0049 case is accepted")
    doc = json.loads(path.read_text(encoding="utf-8"))
    cases = [SyntheticCase(c["name"], c["body"], c["reference_sha256"]) for c in doc["cases"]]
    if [c.name for c in cases] != ["k1", "k3"]:
        raise KeepaliveRefused("the synthetic case file must hold the cases k1 and k3, in that order")
    for c in cases:
        if tuple(c.body) != CASE_BODY_KEYS or c.body["stream"] is not False:
            raise KeepaliveRefused(f"synthetic case {c.name}: unexpected body keys {list(c.body)}")
        if c.body["model"] != settings.extract.stage.model or c.body["think"] != settings.ollama.think:
            raise KeepaliveRefused(f"synthetic case {c.name}: model or think differs from the stage's")
        if set(c.body["options"]) != {"num_ctx", "temperature", "seed", "num_predict"}:
            raise KeepaliveRefused(f"synthetic case {c.name}: unexpected options {sorted(c.body['options'])}")
    return cases, digest


def load_inputs(settings: Settings, lecture_id: str) -> Inputs:
    """Everything the session reads, read-only, with every refusal before any model call."""
    ka = settings.extract.keepalive
    if lecture_id == HELD_OUT:
        raise KeepaliveRefused(f"{HELD_OUT} is the M7 held-out lecture and is never used (ADR-0056 decision 7)")
    if lecture_id != ka.lecture_id:
        raise KeepaliveRefused(f"only the Day 4 lecture {ka.lecture_id} is accepted, not {lecture_id!r} "
                               "(ADR-0056 decision 7)")
    workspaces = Workspaces(settings.jobs.workspaces_dir)
    index_dir = workspaces.stage_output_dir(lecture_id, "index")
    if index_dir is None:
        raise KeepaliveRefused(f"lecture {lecture_id} has no index stage")
    windows = load_windows_json(index_dir / index_store.WINDOWS_JSON)
    ref_path = workspaces.path(lecture_id) / "stages" / "extract" / ka.reference_extract_key / "extraction.json"
    if not ref_path.is_file():
        raise KeepaliveRefused(f"the published v2 extraction {ka.reference_extract_key} is missing ({ref_path})")
    ref_doc = json.loads(ref_path.read_text(encoding="utf-8"))
    reference = {r["window"]["window_index"]: canon(r) for r in ref_doc["windows"]}
    if sorted(reference) != sorted(w.window_index for w in windows):
        raise KeepaliveRefused("the v2 records do not cover exactly the lecture's windows")
    x = settings.extract
    prompt = load_frozen(x.prompt_file, x.prompt_sha256, "extraction prompt")
    split_extraction_prompt(prompt)
    cases, case_sha = load_cases(settings)
    index_key = workspaces.read_manifest(lecture_id)["stages"]["index"]["key"]
    return Inputs(lecture_id, windows, index_key, reference, prompt, cases, case_sha)


# -- the session ---------------------------------------------------------------------------------------------------


@dataclass
class Call:
    run: str
    part: str  # day4 | synthetic
    item: int | str  # window index or case name
    position: int  # 0-based order within the run
    keep_alive: int | str
    raw_sha256: str | None = None
    parsed_sha256: str | None = None
    category: str | None = None  # Day 4: None when valid, else the stage's category; synthetic: not_json or None
    error: str | None = None
    raw_equal: bool | None = None  # against the reference (repeats only)
    parsed_equal: bool | None = None
    load_duration_s: float | None = None
    loaded: bool | None = None
    wall_s: float | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    eval_duration_s: float | None = None
    done_reason: str | None = None


class _Void(Exception):
    def __init__(self, check: str, **details: Any) -> None:
        super().__init__(check)
        self.cause = {"check": check, **details}


@dataclass
class Session:
    settings: Settings
    client: SessionClient
    inputs: Inputs
    out_dir: Path
    lease: Callable[[str], AbstractContextManager]
    vram_read: Callable[[], int | None]
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    calls: list[Call] = field(default_factory=list)
    runs: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    differences: list[dict[str, Any]] = field(default_factory=list)
    void_cause: dict[str, Any] | None = None
    reference_failure: dict[str, Any] | None = None
    references: dict[tuple[str, int | str], tuple[str | None, str | None]] = field(default_factory=dict)
    baseline_mib: int | None = None
    idle_reference_mib: int | None = None
    loads_allowed: int = 0

    @property
    def model(self) -> str:
        return self.settings.extract.stage.model

    # -- one call --

    def _replies(self) -> Path:
        return self.out_dir / "replies.jsonl"

    def _send(self, run: str, part: str, item: int | str, position: int, keep_alive: int | str) -> tuple[Call, str | None]:
        s = self.settings
        c = Call(run, part, item, position, keep_alive)
        if part == "day4":
            w = self.grid[item]
            messages, fmt, num_predict = extract_stage.window_request(s, self.inputs.prompt, w)
            kw = {"truncate": s.extract.truncate}
            num_ctx = s.extract.num_ctx
        else:
            body = self.cases[item].body
            messages, fmt, num_predict = body["messages"], body["format"], body["options"]["num_predict"]
            num_ctx = body["options"]["num_ctx"]
            kw = {"truncate": None, "temperature": body["options"]["temperature"], "seed": body["options"]["seed"]}
        t0 = time.monotonic()
        content: str | None
        metrics: dict[str, Any]
        try:
            content, metrics = self.client.chat(self.model, messages, fmt, num_ctx, num_predict,
                                                keep_alive=keep_alive, **kw)
            error = category = None
        except OutputTruncated as e:
            content, metrics, error, category = None, {"eval_count": e.eval_count, "done_reason": "length"}, str(e), \
                "truncated"
        except PromptTooLong as e:
            content, metrics, error, category = None, {}, str(e), "prompt_too_long"
        except (OllamaError, httpx.HTTPError) as e:
            raise _Void("ollama_error", run=run, part=part, item=item, error=type(e).__name__) from e
        c.wall_s = round(time.monotonic() - t0, 3)
        for k in ("load_duration_s", "prompt_eval_count", "eval_count", "eval_duration_s", "done_reason"):
            setattr(c, k, metrics.get(k))
        c.loaded = c.load_duration_s is not None and c.load_duration_s >= s.extract.keepalive.load_threshold_s
        c.raw_sha256, c.error = sha(content), error
        if part == "day4":
            outcome = extract_stage.evaluate_attempt(s, self.inputs.lecture_id, self.grid, item,
                                                     {"content": content, "error": error, "category": category,
                                                      "metrics": metrics}, num_predict)
            parsed = canon(outcome.record) if outcome.valid else None
            c.category = None if outcome.valid else (outcome.category or "invalid")
        else:
            try:
                parsed = canon(json.loads(content)) if content is not None else None
            except ValueError:
                parsed = None
            c.category = None if parsed is not None else (category or "not_json")
        c.parsed_sha256 = sha(parsed)
        with self._replies().open("a", encoding="utf-8") as f:
            f.write(json.dumps({"run": run, "part": part, "item": item, "attempt": 1, "content": content},
                               ensure_ascii=False) + "\n")
        self.calls.append(c)
        return c, parsed

    # -- checks --

    def _check(self, name: str, ok: bool, **values: Any) -> None:
        self.checks.append({"check": name, "ok": ok, **values})
        if not ok:
            raise _Void(name, **values)

    def _idle_above(self) -> int | None:
        v = self.vram_read()
        return None if v is None or self.baseline_mib is None else v - self.baseline_mib

    def _residency(self, before: str) -> int | None:
        s, ka = self.settings, self.settings.extract.keepalive
        models = self.client.resident()
        names = [m.get("name") for m in models]
        self._check("resident_only_gemma", names == [self.model], before=before, resident=names)
        m = models[0]
        self._check("resident_digest", m.get("digest") == s.extract.stage.frozen_model_digest, before=before,
                    digest=m.get("digest"))
        self._check("resident_num_ctx", m.get("context_length") == s.extract.num_ctx, before=before,
                    context_length=m.get("context_length"))
        expires = m.get("expires_at")
        try:
            future = expires is not None and datetime.fromisoformat(expires) > self.now()
        except ValueError:
            future = False
        self._check("resident_not_expiring", future, before=before, expires_at=expires)
        idle = self._idle_above()
        if self.idle_reference_mib is not None:
            floor = ka.idle_vram_min_ratio * self.idle_reference_mib
            self._check("idle_vram_above_baseline", idle is not None and idle >= floor, before=before,
                        idle_above_baseline_mib=idle, floor_mib=round(floor, 1))
        return idle

    def _load_check(self, c: Call, must_load: bool | None) -> None:
        """must_load True: a reload-per-call reference; False: a loaded repeat; None: the one call allowed to load."""
        if must_load is None:
            return
        self._check("load_per_call" if must_load else "no_load_in_session", c.loaded is must_load, run=c.run,
                    part=c.part, item=c.item, load_duration_s=c.load_duration_s)

    # -- runs --

    def _run(self, name: str, part: str, items: list, keep_alive: int | str, sampler: VramSampler,
             reference: bool) -> None:
        sampler.phase(name)
        t0 = time.monotonic()
        first = len(self.calls)
        for pos, item in enumerate(items):
            c, parsed = self._send(name, part, item, pos, keep_alive)
            if reference:
                self.references[(part, item)] = (c.raw_sha256, parsed)
                self._load_check(c, True)
                continue
            ref_raw, ref_parsed = self.references[(part, item)]
            c.raw_equal = c.raw_sha256 is not None and c.raw_sha256 == ref_raw
            c.parsed_equal = parsed is not None and parsed == ref_parsed
            if not (c.raw_equal and c.parsed_equal):
                self.differences.append({"run": name, "part": part, "item": item, "raw_equal": c.raw_equal,
                                         "parsed_equal": c.parsed_equal, "category": c.category})
            allowed = self.loads_allowed > 0
            self.loads_allowed = 0
            self._load_check(c, None if allowed else False)
        made = self.calls[first:]
        evals = [(c.eval_count or 0, c.eval_duration_s or 0.0) for c in made]
        decode = sum(d for _, d in evals)
        walls = [c.wall_s for c in made if c.wall_s is not None]
        self.runs.append({"run": name, "part": part, "keep_alive": keep_alive, "calls": len(made),
                          "order": items, "wall_s": round(time.monotonic() - t0, 3),
                          "mean_call_wall_s": round(sum(walls) / len(walls), 3) if walls else None,
                          "max_call_wall_s": max(walls) if walls else None,
                          "tokens_per_sec": round(sum(n for n, _ in evals) / decode, 1) if decode else None,
                          "idle_above_baseline_mib_after": self._idle_above()})

    def _reference_day4(self) -> None:
        bad_valid = [c.item for c in self.calls if c.run == "run0" and c.category is not None]
        changed = sorted(i for (part, i), (_, parsed) in self.references.items()
                         if part == "day4" and parsed != self.inputs.reference_records.get(i))
        if bad_valid or changed:
            self.reference_failure = {"reference": "day4_run0", "not_valid_on_attempt_1": bad_valid,
                                      "records_not_equal_to_v2": changed}

    def _reference_synthetic(self) -> None:
        wrong = [c.name for c in self.inputs.cases if self.references[("synthetic", c.name)][0] != c.reference_sha256]
        if wrong:
            self.reference_failure = {"reference": "adr0049_case", "hash_not_reproduced": wrong}

    def run(self) -> dict[str, Any]:
        s, st, ka = self.settings, self.settings.extract.stage, self.settings.extract.keepalive
        self.grid = {w.window_index: w for w in self.inputs.windows}
        self.cases = {c.name: c for c in self.inputs.cases}
        order = [w.window_index for w in self.inputs.windows]
        names = [c.name for c in self.inputs.cases]
        started = self.now()
        sampler = VramSampler(s.extract.vram_poll_interval_s, read=self.vram_read)
        meta: dict[str, Any] = {"self_test": None, "ollama_version_served": None, "digest_served": None}
        with self.lease(PURPOSE):
            version, digest = self.client.version(), self.client.digest(self.model)
            meta.update(ollama_version_served=version, digest_served=digest)
            if version != st.frozen_ollama_version or digest != st.frozen_model_digest:
                raise KeepaliveRefused(f"Ollama serves version {version} and digest {digest}, not the frozen "
                                       f"{st.frozen_ollama_version} / {st.frozen_model_digest}")
            self.out_dir.mkdir(parents=True, exist_ok=False)
            try:
                for m in self.client.resident():
                    self.client.unload(m["name"])
                self._check("ps_empty_at_start", self.client.resident() == [])
                self.baseline_mib = self.vram_read()
                sampler.start()
                sampler.phase("self_test")
                try:
                    meta["self_test"] = run_self_test(_Bound(self.client, 0, s.extract.truncate), s, self.model)
                except SelfTestFailed as e:
                    raise _Void("self_test_failed") from e
                self._run("run0", "day4", order, 0, sampler, reference=True)
                self._reference_day4()
                if self.reference_failure is None:
                    self._run("synthetic_reference", "synthetic", names, 0, sampler, reference=True)
                    self._reference_synthetic()
                if self.reference_failure is None:
                    self._check("ps_empty_after_references", self.client.resident() == [])
                    plan = [(f"day4_repeat_{n}", "day4", order if n < REPEATS else order[::-1])
                            for n in range(1, REPEATS + 1)]
                    plan += [(f"synthetic_repeat_{n}", "synthetic", names if n < REPEATS else names[::-1])
                             for n in range(1, REPEATS + 1)]
                    self.loads_allowed = 1  # the first call of Day 4 repeat 1 loads the model
                    for i, (name, part, items) in enumerate(plan):
                        if i > 0:
                            self._residency(before=name)
                        self._run(name, part, items, ka.keep_alive, sampler, reference=False)
                        if i == 0:
                            self.idle_reference_mib = self.runs[-1]["idle_above_baseline_mib_after"]
                    self._residency(before="end")
            except _Void as v:
                self.void_cause = v.cause
            finally:
                sampler.stop()
                try:
                    self.client.unload(self.model)
                except Exception as e:  # noqa: BLE001 - the session's own record matters more
                    meta["final_unload_error"] = type(e).__name__
                meta["final_vram_mib"] = self.vram_read()
                result = self._write(started, meta, sampler.report())
        return result

    def outcome(self) -> str:
        if self.differences:
            return "fail"
        if self.void_cause is not None:
            return "void"
        if self.reference_failure is not None:
            return "stopped_reference"
        return "pass"

    def _write(self, started: datetime, meta: dict[str, Any], vram: dict[str, Any]) -> dict[str, Any]:
        s, ka = self.settings, self.settings.extract.keepalive
        session = {
            "adr": "ADR-0056", "outcome": self.outcome(), "started_at": started.isoformat(),
            "finished_at": self.now().isoformat(), "lecture_id": self.inputs.lecture_id,
            "index_key": self.inputs.index_key, "reference_extract_key": ka.reference_extract_key,
            "synthetic_case_sha256": self.inputs.case_file_sha256, "model": self.model, **meta,
            "settings": {"keep_alive_repeats": ka.keep_alive, "keep_alive_references": 0,
                         "load_threshold_s": ka.load_threshold_s, "idle_vram_min_ratio": ka.idle_vram_min_ratio,
                         "num_ctx": s.extract.num_ctx, "prompt_sha256": self.inputs.prompt.sha256,
                         "stage_fingerprint": extract_stage.extract_fingerprint(s)},
            "vram": {**vram, "session_baseline_mib": self.baseline_mib,
                     "idle_reference_mib": self.idle_reference_mib},
            "runs": self.runs, "checks": self.checks, "reference_failure": self.reference_failure,
            "void_cause": self.void_cause, "differences": self.differences,
            "totals": {"calls": len(self.calls), "repeat_calls": sum(c.raw_equal is not None for c in self.calls),
                       "repeat_calls_identical": sum(bool(c.raw_equal and c.parsed_equal) for c in self.calls),
                       "differences": len(self.differences)},
            "note": None,
        }
        (self.out_dir / "session.json").write_text(json.dumps(session, indent=1) + "\n", encoding="utf-8")
        (self.out_dir / "windows.json").write_text(
            json.dumps([asdict(c) for c in self.calls], indent=1) + "\n", encoding="utf-8")
        return session


def unrecorded_sessions(out_root: Path) -> list[str]:
    """Earlier session folders whose cause is not recorded (no session.json and no cause.md, e.g. after a kill)."""
    if not out_root.is_dir():
        return []
    return sorted(d.name for d in out_root.iterdir()
                  if d.is_dir() and (d / "replies.jsonl").exists()
                  and not (d / "session.json").exists() and not (d / "cause.md").exists())


def run_session(settings: Settings, client: SessionClient, lecture_id: str,
                lease: Callable[[str], AbstractContextManager], vram_read: Callable[[], int | None],
                now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> dict[str, Any]:
    inputs = load_inputs(settings, lecture_id)
    root = settings.extract.keepalive.out_dir
    pending = unrecorded_sessions(root)
    if pending:
        raise KeepaliveRefused(f"earlier session(s) {pending} under {root} have no recorded cause; write their "
                               "cause.md first (ADR-0056 decision 4)")
    out_dir = root / now().strftime("%Y%m%dT%H%M%SZ")
    return Session(settings, client, inputs, out_dir, lease, vram_read, now).run()
