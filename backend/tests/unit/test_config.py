import pytest

from insightex.core.config import ConfigError, load_config, repo_root
from insightex.ingest.settings import IngestSettings


def test_repo_default_config_loads(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIGHTEX_DATA", str(tmp_path))
    s = IngestSettings.from_config(load_config(repo_root() / "config"))
    assert s.lectures_dir == tmp_path / "lectures"
    assert (s.max_duration_s, s.max_download_bytes, s.keep_source) == (10800, 4 * 1024**3, False)
    assert s.drive_downloader in ("yt-dlp", "gdown")


def test_local_yaml_overrides_and_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_DATA", "/data/x")
    (tmp_path / "default.yaml").write_text(
        "paths:\n  lectures: ${MY_DATA}/lectures\ningest:\n  url:\n    max_duration_s: 100\n    keep_source: false\n"
    )
    (tmp_path / "local.yaml").write_text("ingest:\n  url:\n    keep_source: true\n")
    s = IngestSettings.from_config(load_config(tmp_path))
    assert str(s.lectures_dir) == "/data/x/lectures" and s.max_duration_s == 100 and s.keep_source is True


def test_unset_variable_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_UNSET", raising=False)
    (tmp_path / "default.yaml").write_text("paths:\n  lectures: ${NOPE_UNSET}/lectures\n")
    with pytest.raises(ConfigError, match="NOPE_UNSET"):
        IngestSettings.from_config(load_config(tmp_path))


def test_bad_drive_downloader_rejected(tmp_path):
    with pytest.raises(ValueError):
        IngestSettings(lectures_dir=tmp_path, drive_downloader="wget")
