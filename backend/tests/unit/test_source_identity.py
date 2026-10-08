"""Source identity: YouTube parsing, workspace ids, streaming hash."""

from __future__ import annotations

import hashlib
import io

import pytest

from insightex.jobs.workspace import validate_workspace_id
from insightex.sources.identity import (
    HashingWriter,
    sha256_file,
    workspace_id_for_bytes,
    workspace_id_for_youtube,
    youtube_video_id,
)

VID = "dQw4w9WgXcQ"

CASES = [
    (f"https://www.youtube.com/watch?v={VID}", VID),
    (f"http://youtube.com/watch?v={VID}", VID),
    (f"youtube.com/watch?v={VID}", VID),
    (f"https://m.youtube.com/watch?v={VID}", VID),
    (f"https://music.youtube.com/watch?v={VID}&list=RDAMVM{VID}", VID),
    (f"https://youtu.be/{VID}", VID),
    (f"https://youtu.be/{VID}?t=42", VID),
    (f"https://www.youtu.be/{VID}", VID),
    (f"https://www.youtube.com/shorts/{VID}", VID),
    (f"https://www.youtube.com/embed/{VID}?autoplay=1", VID),
    (f"https://www.youtube.com/live/{VID}?feature=share", VID),
    (f"https://www.youtube.com/watch?list=PL123&v={VID}&index=3#t=10", VID),
    (f"  https://www.youtube.com/watch?v={VID}  ", VID),
    ("https://www.youtube.com/watch?v=short", None),
    ("https://www.youtube.com/watch?v=waytoolongvideoid123", None),
    ("https://www.youtube.com/watch?v=bad!chars!!", None),
    ("https://www.youtube.com/playlist?list=PLabcdefghijk", None),
    ("https://www.youtube.com/watch", None),
    ("https://www.youtube.com/", None),
    (f"https://vimeo.com/watch?v={VID}", None),
    (f"https://evil.example/youtu.be/{VID}", None),
    (f"https://youtube.com.evil.example/watch?v={VID}", None),
    (f"https://notyoutu.be/{VID}", None),
    ("", None),
    ("not a url", None),
]


@pytest.mark.parametrize("url,expected", CASES)
def test_youtube_video_id(url, expected):
    assert youtube_video_id(url) == expected


def test_workspace_ids_pass_the_validator():
    assert workspace_id_for_youtube(VID) == f"yt-{VID}"
    assert workspace_id_for_youtube("-_-_-_-_-_-") == "yt--_-_-_-_-_-"
    digest = hashlib.sha256(b"x").hexdigest()
    wid = workspace_id_for_bytes(digest)
    assert wid == f"sha256-{digest[:32]}"
    for w in (workspace_id_for_youtube(VID), wid):
        assert validate_workspace_id(w) == w


@pytest.mark.parametrize("bad", ["", "short", "a" * 12])
def test_bad_youtube_id_rejected(bad):
    with pytest.raises(ValueError):
        workspace_id_for_youtube(bad)


def test_bad_digest_rejected():
    with pytest.raises(ValueError):
        workspace_id_for_bytes("abc")


def test_hashing_writer_matches_sha256_file(tmp_path):
    data = bytes(range(256)) * 5000 + b"tail"
    path = tmp_path / "f.bin"
    with open(path, "wb") as f:
        w = HashingWriter(f, 4096)
        assert w.write(data[:10]) == 10
        w.write(data[10:])
        w.flush()
    assert w.bytes_written == len(data)
    assert w.hexdigest() == sha256_file(path, 1000) == hashlib.sha256(data).hexdigest()
    assert path.read_bytes() == data


def test_hashing_writer_chunks_large_writes():
    sink = io.BytesIO()
    w = HashingWriter(sink, 3)
    w.write(b"abcdefgh")
    assert sink.getvalue() == b"abcdefgh" and w.hexdigest() == hashlib.sha256(b"abcdefgh").hexdigest()
