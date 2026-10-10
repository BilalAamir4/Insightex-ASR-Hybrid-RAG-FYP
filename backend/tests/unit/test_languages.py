"""Lecture language config (ADR-0040): validation, the committed list against the installed faster-whisper."""

from __future__ import annotations

import os

import pytest

from insightex.asr.languages import (
    LanguageConfigError,
    languages_for,
    load_languages,
    parse_languages,
    require_language,
    supported_whisper_codes,
)
from insightex.core.config import get_settings, load_settings
from insightex.ingest.errors import ErrorCode, IngestError

CODES = frozenset({"ur", "en", "hi", "fr"})
HINDI = {"id": "hindi", "label": "Hindi", "whisper_language": "ur", "tier": "tested", "evidence": "ADR-0039"}
ENGLISH = {"id": "english", "label": "English", "whisper_language": "en", "tier": "untested"}


def parse(*entries):
    return parse_languages({"languages": list(entries)}, CODES)


def test_valid_config_parses():
    langs = parse(HINDI, ENGLISH)
    assert langs.get("hindi").whisper_language == "ur" and langs.get("english").tier == "untested"
    assert langs.get("nope") is None


def test_duplicate_id_is_rejected():
    with pytest.raises(LanguageConfigError, match="duplicate id 'english'"):
        parse(HINDI, ENGLISH, {**ENGLISH, "label": "English again"})


def test_unsupported_whisper_code_is_rejected():
    with pytest.raises(LanguageConfigError, match="'xx' is not supported by the installed faster-whisper"):
        parse(HINDI, {**ENGLISH, "whisper_language": "xx"})


def test_tested_entry_without_evidence_is_rejected():
    with pytest.raises(LanguageConfigError, match="tested language needs 'evidence'"):
        parse({k: v for k, v in HINDI.items() if k != "evidence"})


def test_untested_entry_with_evidence_and_bad_tier_are_rejected():
    with pytest.raises(LanguageConfigError) as exc:
        parse({**ENGLISH, "evidence": "ADR-0001"}, {**ENGLISH, "id": "eng2", "tier": "maybe"})
    assert "must not have 'evidence'" in str(exc.value) and "tier must be one of" in str(exc.value)


def test_every_problem_is_listed_at_once():
    with pytest.raises(LanguageConfigError) as exc:
        parse({**HINDI, "evidence": None}, {**ENGLISH, "whisper_language": "zz"})
    assert str(exc.value).count("\n  ") == 2


def test_empty_or_malformed_file_is_rejected(tmp_path):
    with pytest.raises(LanguageConfigError, match="non-empty 'languages:' list"):
        parse_languages({"languages": []}, CODES)
    bad = tmp_path / "bad.yaml"
    bad.write_text("languages: [\n", encoding="utf-8")
    with pytest.raises(LanguageConfigError, match="cannot read language config"):
        load_languages(bad, CODES)


def test_tier_move_needs_only_a_config_edit(tmp_path):
    path = tmp_path / "langs.yaml"
    path.write_text(
        "languages:\n"
        "  - {id: hindi, label: Hindi, whisper_language: ur, tier: tested, evidence: ADR-0039}\n"
        "  - {id: english, label: English, whisper_language: en, tier: tested, evidence: ADR-9999}\n",
        encoding="utf-8",
    )
    assert load_languages(path, CODES).get("english").tier == "tested"


# -- the committed config/languages.yaml ---------------------------------------------------------------


@pytest.fixture(scope="module")
def committed():
    return load_languages(load_settings().asr.languages_file)


def test_committed_config_is_valid_and_hindi_is_the_only_tested_entry(committed):
    tested = [e for e in committed.entries if e.tier == "tested"]
    assert [(e.id, e.whisper_language, e.evidence) for e in tested] == [("hindi", "ur", "ADR-0039")]
    assert tested[0].label == "Hindi (including Hindi-English mixed)"


def test_hindi_appears_exactly_once(committed):
    assert [e.id for e in committed.entries if "hindi" in e.id or "hindi" in e.label.lower()] == ["hindi"]
    assert all(e.whisper_language != "hi" for e in committed.entries)


def test_committed_list_matches_the_installed_faster_whisper(committed):
    """Regenerate with tools/gen_languages after a faster-whisper upgrade if this fails."""
    untested = [e.whisper_language for e in committed.entries if e.tier == "untested"]
    assert len(untested) == len(set(untested))
    assert set(untested) == supported_whisper_codes() - {"hi"}


def test_well_known_entries(committed):
    assert committed.get("english").whisper_language == "en" and committed.get("english").tier == "untested"
    assert committed.get("urdu").whisper_language == "ur" and committed.get("urdu").tier == "untested"


def test_grouped_order(committed):
    groups = committed.grouped()
    assert [g["tier"] for g in groups] == ["tested", "untested"]
    assert groups[1]["label"] == "Not tested — transcription quality unknown"
    labels = [lang["label"] for lang in groups[1]["languages"]]
    assert labels == sorted(labels, key=str.casefold) and len(labels) == 99


# -- request-time validation ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_language_is_missing(value):
    with pytest.raises(IngestError) as exc:
        require_language(get_settings(), value)
    assert exc.value.code == ErrorCode.MISSING_LANGUAGE


@pytest.mark.parametrize("value", ["klingon", "Hindi", 5, ["hindi"]])
def test_unknown_language_is_unknown_and_names_the_value(value):
    with pytest.raises(IngestError) as exc:
        require_language(get_settings(), value)
    assert exc.value.code == ErrorCode.UNKNOWN_LANGUAGE
    if isinstance(value, str):
        assert value in exc.value.message


# -- live reload: strict at startup, last valid list kept afterwards ------------------------------------------

GOOD = (
    "languages:\n"
    "  - {id: hindi, label: Hindi, whisper_language: ur, tier: tested, evidence: ADR-0039}\n"
    "  - {id: english, label: English, whisper_language: en, tier: untested}\n"
)


def _write(path, text, step):
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(1_000_000_000 * step, 1_000_000_000 * step))  # distinct mtimes whatever the clock resolution


def _settings(path):
    return load_settings({"asr": {"languages_file": str(path)}})


def test_invalid_file_at_startup_raises(tmp_path):
    path = tmp_path / "langs.yaml"
    _write(path, GOOD.replace("whisper_language: en", "whisper_language: zz"), 1)
    with pytest.raises(LanguageConfigError, match="'zz' is not supported"):
        languages_for(_settings(path))
    missing = tmp_path / "nope.yaml"
    with pytest.raises(LanguageConfigError, match="cannot read language config"):
        languages_for(_settings(missing))


@pytest.mark.parametrize(("bad", "reason"), [
    (GOOD.replace("whisper_language: en", "whisper_language: zz"), "'zz' is not supported by the installed faster-whisper"),
    (GOOD.replace(", evidence: ADR-0039", ""), "a tested language needs 'evidence'"),
    (GOOD + "  - {id: english, label: Again, whisper_language: fr, tier: untested}\n", "duplicate id 'english'"),
    ("languages: [\n", "cannot read language config"),
])
def test_invalid_reload_keeps_the_last_valid_list_and_logs_the_reason_once(tmp_path, caplog, bad, reason):
    path = tmp_path / "langs.yaml"
    _write(path, GOOD, 1)
    settings = _settings(path)
    good = languages_for(settings)
    assert good.get("english").tier == "untested"

    _write(path, bad, 2)
    with caplog.at_level("ERROR", logger="insightex.asr.languages"):
        assert languages_for(settings) is good
        assert languages_for(settings) is good  # asked again: still served, not logged again
    records = [r for r in caplog.records if r.name == "insightex.asr.languages"]
    assert len(records) == 1 and reason in records[0].getMessage() and str(path) in records[0].getMessage()
    assert "still serving the last valid list" in records[0].getMessage()


def test_deleted_file_keeps_the_last_valid_list(tmp_path, caplog):
    path = tmp_path / "langs.yaml"
    _write(path, GOOD, 1)
    settings = _settings(path)
    good = languages_for(settings)
    path.unlink()
    with caplog.at_level("ERROR", logger="insightex.asr.languages"):
        assert languages_for(settings) is good
    assert "cannot read language config" in caplog.text


def test_a_later_valid_edit_replaces_the_list_and_a_new_bad_edit_is_logged_again(tmp_path, caplog):
    path = tmp_path / "langs.yaml"
    _write(path, GOOD, 1)
    settings = _settings(path)
    languages_for(settings)
    _write(path, "languages: [\n", 2)
    with caplog.at_level("ERROR", logger="insightex.asr.languages"):
        languages_for(settings)
    promoted = GOOD.replace("tier: untested}", "tier: tested, evidence: ADR-9999}")
    _write(path, promoted, 3)
    assert languages_for(settings).get("english").tier == "tested"  # recovered
    caplog.clear()
    _write(path, "languages: [\n", 4)
    with caplog.at_level("ERROR", logger="insightex.asr.languages"):
        assert languages_for(settings).get("english").tier == "tested"  # the promoted list, not the first one
    assert caplog.text.count("still serving the last valid list") == 1


def test_api_keeps_answering_after_a_bad_edit(tmp_path):
    from fastapi.testclient import TestClient

    from insightex.api.app import create_app

    path = tmp_path / "langs.yaml"
    _write(path, GOOD, 1)
    with TestClient(create_app(_settings(path))) as client:
        before = client.get("/api/languages").json()
        _write(path, GOOD.replace("whisper_language: en", "whisper_language: zz"), 2)
        r = client.get("/api/languages")
        assert r.status_code == 200 and r.json() == before
        _write(path, GOOD.replace("English", "Inglis"), 3)
        assert [lang["label"] for lang in client.get("/api/languages").json()["groups"][1]["languages"]] == ["Inglis"]
