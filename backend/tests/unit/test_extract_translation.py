"""C2 translation stage (ADR-0048 section 8, Amendment 8) on synthetic windows with a fake model client.

No Ollama, no GPU, no real lecture text, no real prompt. The `setup` fixture is imported from test_extract_harness.
"""

# ruff: noqa: F811

from __future__ import annotations

import json

import pytest
from test_extract_harness import (
    LECTURE,
    FakeClient,
    arm,
    default_respond,
    frozen,
    setup,  # noqa: F401 - pytest fixture
    windows,
)

from insightex.core.config import ConfigError, load_settings
from insightex.extract import harness as h
from insightex.extract.prompts import PromptNotFrozen
from insightex.extract.translation import (
    TranslationCache,
    check_translation,
    non_latin_fraction,
    translation_key,
)
from insightex.extract.vram import VramSampler

EN = {"input": "english"}


def translate_chats(client):
    return [c for c in client.chats if "text" in c["user"]]


def stage_files(tmp_path):
    return sorted((tmp_path / "translations").rglob("*.json"))


# -- the key -------------------------------------------------------------------------------------------------------


def test_key_is_window_text_model_digest_and_prompt_only(monkeypatch):
    k = translation_key("t" * 64, "d" * 64, "p" * 64)
    assert k == translation_key("t" * 64, "d" * 64, "p" * 64)
    assert len({k, translation_key("u" * 64, "d" * 64, "p" * 64), translation_key("t" * 64, "e" * 64, "p" * 64),
                translation_key("t" * 64, "d" * 64, "q" * 64)}) == 4
    monkeypatch.setattr(h, "HARNESS_VERSION", 999)
    assert translation_key("t" * 64, "d" * 64, "p" * 64) == k  # no harness version in the key


# -- reuse ---------------------------------------------------------------------------------------------------------


def test_extraction_rerun_reuses_translations_and_marks_cost_unmeasured(setup, tmp_path):
    _, prompts, ctx = setup
    client = FakeClient()
    _, first = h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(3), [0, 1, 2])
    assert len(translate_chats(client)) == 3 and first["cost"]["measured"] is True
    assert first["totals"]["translation_calls"] == 3 and len(stage_files(tmp_path)) == 3
    _, second = h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(3), [0, 1, 2])
    assert len(translate_chats(client)) == 3  # no new translation call
    assert second["totals"]["translation_cache_hits"] == 3 and second["cost"]["measured"] is False
    assert all(t["from_cache"] for t in second["translations"])
    extraction = [c for c in client.chats if "windows" in c["user"]]
    assert extraction[-1]["user"]["windows"][0]["text"] == "EN synthetic window 2 text"


def test_translations_survive_a_harness_version_bump(setup, tmp_path, monkeypatch):
    _, prompts, ctx = setup
    client = FakeClient()
    h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    n_extract = len([c for c in client.chats if "windows" in c["user"]])
    monkeypatch.setattr(h, "HARNESS_VERSION", h.HARNESS_VERSION + 1)
    _, run = h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    assert len(translate_chats(client)) == 2  # translations reused from the stage
    assert len([c for c in client.chats if "windows" in c["user"]]) == 2 * n_extract  # extraction replies were not
    assert run["totals"]["translation_cache_hits"] == 2


def test_changed_text_model_or_prompt_translates_again(setup, tmp_path):
    _, prompts, ctx = setup
    client = FakeClient()
    h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    assert len(translate_chats(client)) == 2
    edited = [h.WindowText(0, 0.0, 30.0, "synthetic window 0 text, edited"), windows(2)[1]]
    h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, edited, [0, 1])
    assert len(translate_chats(client)) == 3  # only the edited window
    h.run_arm(ctx(client), arm(model="other:tag", **EN), prompts, LECTURE, windows(2), [0, 1])
    assert len(translate_chats(client)) == 5  # a different model digest
    p2 = h.Prompts(prompts.extraction, None,
                   frozen(tmp_path, "translate2.txt", "PLACEHOLDER TRANSLATION PROMPT v2\n"
                          "<<<RETRY>>>\nRETRY {errors}\n"))
    h.run_arm(ctx(client), arm(**EN), p2, LECTURE, windows(2), [0, 1])
    assert len(translate_chats(client)) == 7  # a different prompt hash


def test_fresh_reads_no_cache_and_measures_the_cost(setup, tmp_path):
    _, prompts, ctx = setup
    client = FakeClient()
    h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    n = len(client.chats)
    _, run = h.run_arm(ctx(client, fresh=True), arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    assert len(client.chats) == 2 * n  # every translation and extraction call made again
    assert run["fresh"] is True and run["cost"]["measured"] is True and run["totals"]["cache_hits"] == 0
    assert run["totals"]["translation_cache_hits"] == 0 and run["totals"]["translation_calls"] == 2


def test_fresh_original_arm_makes_every_call(setup):
    _, prompts, ctx = setup
    client = FakeClient()
    h.run_arm(ctx(client), arm(), prompts, LECTURE, windows(2), [0, 1])
    _, run = h.run_arm(ctx(client, fresh=True), arm(), prompts, LECTURE, windows(2), [0, 1])
    assert len(client.chats) == 4 and run["cost"]["measured"] is True and run["translations"] == []


# -- the check and fail-closed -------------------------------------------------------------------------------------


def test_blank_translation_twice_fails_closed_and_is_not_stored(setup, tmp_path):
    _, prompts, ctx = setup

    def respond(user, messages, attempt):
        if "text" in user and user["text"].startswith("synthetic window 1"):
            return json.dumps({"english": "   "})
        return default_respond(user, messages, attempt)

    client = FakeClient(respond)
    _, run = h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    w1 = [c for c in translate_chats(client) if c["user"]["text"].startswith("synthetic window 1")]
    assert len(w1) == 2
    assert "PLACEHOLDER TRANSLATION RETRY" in w1[1]["messages"][2]["content"]  # the retry carries the errors
    assert "blank" in w1[1]["messages"][2]["content"]
    status = {w["window_index"]: w for w in run["windows"]}
    assert status[0]["valid"] and not status[1]["valid"]
    assert run["totals"]["translation_failed_windows"] == 1 and run["totals"]["invalid_windows"] == 1
    assert len(stage_files(tmp_path)) == 1  # only window 0 stored
    h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    assert len([c for c in translate_chats(client) if c["user"]["text"].startswith("synthetic window 1")]) == 4


def test_untranslated_reply_is_retried_and_the_retry_can_recover(setup, tmp_path):
    _, prompts, ctx = setup

    def respond(user, messages, attempt):
        if "text" in user:
            return json.dumps({"english": "یہ ترجمہ نہیں ہے" if attempt == 1 else "EN " + user["text"]})
        return default_respond(user, messages, attempt)

    client = FakeClient(respond)
    _, run = h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(1), [0])
    chats = translate_chats(client)
    assert len(chats) == 2 and "not English" in chats[1]["messages"][2]["content"]
    assert chats[1]["messages"][:2] == chats[0]["messages"]  # same request plus the retry message
    assert run["windows"][0]["valid"] and run["translations"][0]["attempt_used"] == 2
    assert run["totals"]["translation_retried_windows"] == 1
    assert json.loads(stage_files(tmp_path)[0].read_text())["attempt_used"] == 2


def test_check_translation_rules():
    def ok(s):
        return check_translation(json.dumps({"english": s}), None, 0.1)

    assert ok("Gradient descent, in English.")[0] == "Gradient descent, in English."
    assert ok("a" * 9 + "ب")[0] is not None  # 1 of 10 letters: exactly the allowed share
    assert ok("a" * 8 + "بب")[0] is None  # 2 of 10
    assert ok("a" * 8 + "कक")[0] is None  # Devanagari counts too
    assert ok("1234 ...")[0] is None and ok("")[0] is None
    assert check_translation("not json", None, 0.1)[0] is None
    assert check_translation(json.dumps({"other": "x"}), None, 0.1)[0] is None
    assert check_translation(None, "truncated", 0.1) == (None, ["truncated"])
    assert non_latin_fraction("abc") == 0.0 and non_latin_fraction("...") is None
    with pytest.raises(ConfigError, match="translate_max_non_latin_fraction"):
        load_settings({"extract": {"translate_max_non_latin_fraction": 1.0}})


# -- the freeze ----------------------------------------------------------------------------------------------------


def test_unpinned_mismatched_or_retryless_translation_prompt_is_refused(tmp_path):
    english = arm(**EN)
    with pytest.raises(PromptNotFrozen, match="no frozen translation prompt"):
        h.load_prompts(load_settings({"extract": {"translate_prompt_file": None, "translate_prompt_sha256": None}}),
                       english)
    p = tmp_path / "t.txt"
    p.write_text("PLACEHOLDER\n<<<RETRY>>>\nRETRY {errors}\n")
    with pytest.raises(PromptNotFrozen, match="new freeze"):
        h.load_prompts(load_settings({"extract": {"translate_prompt_file": str(p), "translate_prompt_sha256": "0" * 64}}),
                       english)
    q = tmp_path / "noretry.txt"
    q.write_text("PLACEHOLDER WITHOUT A RETRY SECTION\n")
    import hashlib

    sha = hashlib.sha256(q.read_bytes()).hexdigest()
    with pytest.raises(PromptNotFrozen, match="RETRY"):
        h.load_prompts(load_settings({"extract": {"translate_prompt_file": str(q), "translate_prompt_sha256": sha}}),
                       english)
    # an original-input arm never needs the translation prompt
    h.load_prompts(load_settings({"extract": {"translate_prompt_file": None, "translate_prompt_sha256": None}}), arm())


# -- the call rules ------------------------------------------------------------------------------------------------


class OrderClient(FakeClient):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.events: list[str] = []

    def chat(self, model, messages, format_schema, num_ctx, num_predict):
        self.events.append("probe" if format_schema == h.SELF_TEST_FORMAT
                           else "translate" if "text" in json.loads(messages[1]["content"]) else "extract")
        return super().chat(model, messages, format_schema, num_ctx, num_predict)


def test_self_test_comes_before_the_first_translation(setup):
    _, prompts, ctx = setup
    client = OrderClient()
    _, run = h.run_arm(ctx(client), arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    assert client.events == ["probe", "translate", "translate", "extract", "extract"]
    assert run["truncate_self_test"]["refused"] is True


def test_translation_calls_send_truncate_false_and_keep_alive_zero(monkeypatch, tmp_path):
    from insightex.llm import ollama_client

    settings = load_settings()
    sent = []

    def fake_chat_raw(messages, fmt, num_ctx, **kw):
        sent.append({"fmt": fmt, **kw})
        from insightex.llm.ollama_client import ChatMetrics

        return json.dumps({"english": "EN"}), ChatMetrics(prompt_eval_count=10, eval_count=2, eval_duration_s=0.1,
                                                          tokens_per_sec=20.0, total_duration_s=0.2,
                                                          load_duration_s=0.0, done_reason="stop", num_ctx=num_ctx)

    monkeypatch.setattr(ollama_client, "chat_raw", fake_chat_raw)
    client = h.OllamaModelClient(settings)
    client.chat("gemma4:e4b", [{"role": "system", "content": "s"}, {"role": "user", "content": "{}"}],
                h.TRANSLATION_FORMAT, settings.extract.num_ctx, settings.extract.translate_num_predict)
    assert sent[0]["truncate"] is False and sent[0]["keep_alive"] == 0 and sent[0]["budget_rule"] == "warn"


def test_translation_over_the_real_budget_is_invalid_and_fails_closed(setup):
    _, prompts, ctx = setup

    class Over(FakeClient):
        def chat(self, model, messages, format_schema, num_ctx, num_predict):
            content, m = super().chat(model, messages, format_schema, num_ctx, num_predict)
            if format_schema == h.TRANSLATION_FORMAT:
                m = {**m, "prompt_eval_count": num_ctx - num_predict + 1}
            return content, m

    _, run = h.run_arm(ctx(Over()), arm(**EN), prompts, LECTURE, windows(1), [0])
    assert not run["windows"][0]["valid"] and run["totals"]["translation_failed_windows"] == 1
    assert run["totals"]["prompt_overflow_calls"] == 2
    assert "prompt overflow" in run["translations"][0]["errors"][0][0]


# -- VRAM per phase ------------------------------------------------------------------------------------------------


def test_vram_peak_is_recorded_per_phase(setup, tmp_path):
    settings, prompts, _ = setup
    level = {"v": 1000}
    sampler = VramSampler(10.0, read=lambda: level["v"])  # the thread never fires; samples come from the client

    class Loaded(FakeClient):
        def chat(self, model, messages, format_schema, num_ctx, num_predict):
            if format_schema != h.SELF_TEST_FORMAT:
                level["v"] = 5000 if format_schema == h.TRANSLATION_FORMAT else 3000
                sampler._sample()
                level["v"] = 1000
            return super().chat(model, messages, format_schema, num_ctx, num_predict)

    c = h.RunContext(settings=settings, client=Loaded(), cache=h.ReplyCache(tmp_path / "cache"),
                     translations=TranslationCache(tmp_path / "translations"), lease=lambda p: __import__(
                         "contextlib").nullcontext(), sampler=sampler)
    _, run = h.run_arm(c, arm(**EN), prompts, LECTURE, windows(2), [0, 1])
    vram = run["cost"]["vram"]
    assert vram["peak_mib"] == 5000
    assert vram["phases"]["translation"]["peak_mib"] == 5000
    assert vram["phases"]["extraction"]["peak_mib"] == 3000
    assert vram["phases"]["extraction"]["peak_above_baseline_mib"] == 2000


# -- the draft-prompt check ----------------------------------------------------------------------------------------


def test_translate_check_refuses_gold_windows_and_leaves_the_stage_alone(setup, tmp_path):
    _, prompts, ctx = setup
    client = FakeClient()
    with pytest.raises(h.HarnessError, match="gold windows"):
        h.translation_check(ctx(client), "gemma4:e4b", prompts.translation, False, LECTURE, windows(6), [0, 1],
                            gold={1, 2, 4})
    assert client.chats == [] and client.probes == []
    report = h.translation_check(ctx(client), "gemma4:e4b", prompts.translation, False, LECTURE, windows(6),
                                 [0, 3, 5], gold={1, 2, 4})
    assert [w["english"] for w in report["windows"]] == [f"EN synthetic window {i} text" for i in (0, 3, 5)]
    assert report["windows"][0]["source_text"] == "synthetic window 0 text"
    assert report["prompt_frozen"] is False and report["truncate_self_test"]["refused"] is True
    assert stage_files(tmp_path) == []  # nothing stored
    assert client.unloaded[-1] == "gemma4:e4b"


def test_cli_run_fresh_flag(tmp_path, monkeypatch):
    from insightex.extract import cli

    seen = {}
    real = cli.make_context

    def spy(settings, client=None, fresh=False):
        seen["fresh"] = fresh
        return real(settings, client, fresh)

    monkeypatch.setattr(cli, "make_context", spy)
    monkeypatch.setattr(h, "run_arm", lambda *a, **k: (_ for _ in ()).throw(h.HarnessError("stop here")))
    wfile = tmp_path / "w.json"
    wfile.write_text(json.dumps({"windows": [{"id": 0, "start": 0.0, "end": 30.0, "text": "synthetic"}]}))
    tfile = tmp_path / "t.json"
    tfile.write_text("[0]")
    rc = cli.main(["run", "--arm", "C1-gemma4-e4b", "--lecture", LECTURE, "--targets", str(tfile), "--windows",
                   str(wfile), "--out", str(tmp_path / "out"), "--fresh"], client=FakeClient())
    assert rc == 1 and seen["fresh"] is True


def test_shipped_translation_prompt_has_its_pinned_sha256():
    shipped = load_settings().extract
    if shipped.translate_prompt_file is not None:
        p = h.load_prompts(load_settings(), arm(**EN)).translation
        assert p is not None and p.sha256 == shipped.translate_prompt_sha256


def test_shipped_context_block_has_its_pinned_sha256():
    shipped = load_settings().extract
    if shipped.context_block_file is not None:
        p = h.load_prompts(load_settings(), arm(context="previous")).context_block
        assert p is not None and p.sha256 == shipped.context_block_sha256
