import pytest

from insightex.core.ids import lecture_dir, lecture_id_from_canonical, validate_lecture_id


def test_canonical_to_lecture_id():
    assert lecture_id_from_canonical("yt:dQw4w9WgXcQ") == "yt_dQw4w9WgXcQ"
    assert lecture_id_from_canonical("gdrive:1AbC-_x") == "gdrive_1AbC-_x"
    assert lecture_id_from_canonical("url:0123456789abcdef") == "url_0123456789abcdef"


@pytest.mark.parametrize(
    "bad",
    ["yt:../../etc", "yt:a/b", "yt:", "foo:abc", "yt:a.b", "yt:a b", "url:" + "a" * 65, "yt:abc\x00"],
)
def test_bad_canonical_rejected(bad):
    with pytest.raises(ValueError):
        lecture_id_from_canonical(bad)


@pytest.mark.parametrize(
    "bad",
    ["..", ".", "../yt_abc", "yt_abc/..", "yt_../x", "/etc/passwd", "yt_abc/def", "yt_a.b", "yt_",
     "YT_abc", "x_abc", "yt_abc\n", "yt_abc\x00", "", "yt_" + "a" * 65, "yt_%2e%2e", "yt_abc\\..\\x"],
)
def test_lecture_id_traversal_rejected(bad, tmp_path):
    with pytest.raises(ValueError):
        validate_lecture_id(bad)
    with pytest.raises(ValueError):
        lecture_dir(tmp_path, bad)


def test_lecture_dir_inside_root(tmp_path):
    assert lecture_dir(tmp_path, "yt_dQw4w9WgXcQ") == (tmp_path / "yt_dQw4w9WgXcQ").resolve()


def test_lecture_dir_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "yt_evil").symlink_to(tmp_path)
    with pytest.raises(ValueError):
        lecture_dir(root, "yt_evil")
