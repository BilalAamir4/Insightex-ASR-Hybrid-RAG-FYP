from pathlib import Path

import pytest
import yaml

from insightex.core.config import (
    ConfigError,
    clear_settings_cache,
    get_settings,
    load_settings,
    load_settings_with_sources,
    render_effective,
    repo_root,
)
from insightex.ingest.settings import IngestSettings

DEFAULT = repo_root() / "config" / "default.yaml"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """No INSIGHTEX*/OLLAMA_BASE_URL from the shell, and an empty local file instead of the real config/local.yaml."""
    import os

    for name in list(os.environ):
        if name.upper().startswith("INSIGHTEX__") or name in ("INSIGHTEX_DATA", "OLLAMA_BASE_URL"):
            monkeypatch.delenv(name)
    empty = tmp_path / "empty_local.yaml"
    empty.write_text("")
    monkeypatch.setenv("INSIGHTEX_CONFIG", str(empty))
    clear_settings_cache()
    yield
    clear_settings_cache()


def _local(monkeypatch, tmp_path, text: str) -> Path:
    f = tmp_path / "local.yaml"
    f.write_text(text)
    monkeypatch.setenv("INSIGHTEX_CONFIG", str(f))
    return f


def test_defaults_match_default_yaml():
    s = load_settings()
    raw = yaml.safe_load(DEFAULT.read_text())
    assert s.api.port == raw["api"]["port"] == 8000
    assert s.api.host == "127.0.0.1"
    assert s.ingest.url.max_duration_s == raw["ingest"]["url"]["max_duration_s"]
    assert s.ollama.model == "qwen3.5:latest" and s.ollama.num_ctx == 8192 and s.ollama.think is False


def test_ingest_settings_dataclass_defaults_match_yaml():
    from_yaml = IngestSettings.from_settings(load_settings())
    assert from_yaml == IngestSettings(lectures_dir=from_yaml.lectures_dir)


def test_visual_disabled_by_default():
    assert load_settings().visual.enabled is False


def test_local_file_overrides_default(monkeypatch, tmp_path):
    _local(monkeypatch, tmp_path, "api:\n  port: 9001\ningest:\n  url:\n    keep_source: true\n")
    s = load_settings()
    assert s.api.port == 9001 and s.ingest.url.keep_source is True and s.api.host == "127.0.0.1"


def test_missing_config_env_file_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIGHTEX_CONFIG", str(tmp_path / "nope.yaml"))
    with pytest.raises(ConfigError, match="INSIGHTEX_CONFIG.*nope.yaml"):
        load_settings()


def test_env_overrides_file_and_is_type_converted(monkeypatch, tmp_path):
    _local(monkeypatch, tmp_path, "api:\n  port: 9001\n")
    monkeypatch.setenv("INSIGHTEX__API__PORT", "8123")
    monkeypatch.setenv("insightex__visual__enabled", "true")
    s = load_settings()
    assert s.api.port == 8123 and s.visual.enabled is True


def test_unknown_yaml_key_raises(monkeypatch, tmp_path):
    f = _local(monkeypatch, tmp_path, "api:\n  prot: 1\n")
    with pytest.raises(ConfigError, match=r"api\.prot.*file .*local\.yaml") as e:
        load_settings()
    assert str(f) in str(e.value)


def test_unknown_env_key_raises(monkeypatch):
    monkeypatch.setenv("INSIGHTEX__API__PROT", "1")
    with pytest.raises(ConfigError, match=r"api\.prot.*env INSIGHTEX__API__PROT"):
        load_settings()


def test_wrong_type_names_dotted_key(monkeypatch):
    monkeypatch.setenv("INSIGHTEX__INGEST__URL__MAX_DURATION_S", "soon")
    with pytest.raises(ConfigError, match=r"ingest\.url\.max_duration_s"):
        load_settings()


def test_alias_env_var_works(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIGHTEX_DATA", str(tmp_path / "d"))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example:1234")
    s = load_settings()
    assert s.paths.data_dir == tmp_path / "d" and s.paths.lectures_dir == tmp_path / "d" / "lectures"
    assert s.ollama.base_url == "http://example:1234"


def test_alias_and_canonical_conflict_raises(monkeypatch):
    monkeypatch.setenv("INSIGHTEX_DATA", "/a")
    monkeypatch.setenv("INSIGHTEX__PATHS__DATA_DIR", "/b")
    with pytest.raises(ConfigError, match="INSIGHTEX_DATA.*INSIGHTEX__PATHS__DATA_DIR"):
        load_settings()


def test_alias_and_canonical_same_value_ok(monkeypatch):
    monkeypatch.setenv("INSIGHTEX_DATA", "/a")
    monkeypatch.setenv("INSIGHTEX__PATHS__DATA_DIR", "/a")
    assert load_settings().paths.data_dir == Path("/a")


def test_tilde_and_env_expansion(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MY_ROOT", "/r")
    assert load_settings().paths.data_dir == tmp_path / "insightex-data"
    monkeypatch.setenv("INSIGHTEX__PATHS__DATA_DIR", "$MY_ROOT/x")
    assert load_settings().paths.data_dir == Path("/r/x")
    assert not (tmp_path / "insightex-data").exists()  # loading never creates directories


def test_explicit_overrides_beat_env(monkeypatch):
    monkeypatch.setenv("INSIGHTEX__API__PORT", "8123")
    assert load_settings({"api": {"port": 7000}}).api.port == 7000


def test_settings_are_frozen():
    with pytest.raises(Exception):
        load_settings().api.port = 1


def test_get_settings_cached_and_clearable(monkeypatch):
    first = get_settings()
    monkeypatch.setenv("INSIGHTEX__API__PORT", "8124")
    assert get_settings() is first and first.api.port == 8000
    clear_settings_cache()
    assert get_settings().api.port == 8124


def test_render_marks_sources(monkeypatch, tmp_path):
    f = _local(monkeypatch, tmp_path, "api:\n  host: 127.0.0.1\n")
    monkeypatch.setenv("INSIGHTEX_DATA", str(tmp_path))
    s, origins = load_settings_with_sources()
    out = render_effective(s, origins)
    assert "port: 8000  # default" in out
    assert f"host: 127.0.0.1  # file {f}" in out
    assert "data_dir:" in out and "# env INSIGHTEX_DATA" in out
