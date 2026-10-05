import hashlib

import pytest

from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.urls import parse_url

VID = "dQw4w9WgXcQ"
DRIVE = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}",
        f"http://www.youtube.com/watch?v={VID}&t=42s",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=abc123&t=10",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/embed/{VID}?start=5",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/live/{VID}",
        f"https://www.youtube.com/live/{VID}?si=ns4N9Ce4tC9Yoc39",
        f"https://m.youtube.com/live/{VID}?feature=share",
        f"https://youtu.be/{VID}?si=dovXyEMYwxqczXa_",
        f"https://www.youtube.com/watch?v={VID}&list=PLxyz123&index=3",
        f"https://www.youtube.com/watch?list=PLxyz123&v={VID}",
        f"  https://WWW.YouTube.com/watch?v={VID}  ",
        f"youtube.com/watch?v={VID}",
        f"youtu.be/{VID}",
    ],
)
def test_youtube_shapes(url):
    p = parse_url(url)
    assert p.source_type == "youtube"
    assert p.canonical_id == f"yt:{VID}"
    assert p.lecture_id == f"yt_{VID}"
    assert p.normalized_url == f"https://www.youtube.com/watch?v={VID}"
    assert p.external_timestamp_url_template == f"https://www.youtube.com/watch?v={VID}&t={{t}}s"
    assert p.source_url == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/playlist?list=PLxyz123",
        "https://www.youtube.com/watch?list=PLxyz123",
        "https://www.youtube.com/embed/videoseries?list=PLxyz123",
    ],
)
def test_playlist_only_rejected(url):
    with pytest.raises(IngestError) as e:
        parse_url(url)
    assert e.value.code == ErrorCode.PLAYLIST_NOT_SUPPORTED


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/@somechannel",
        "https://www.youtube.com/channel/UC123",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ/../x",
        "https://youtu.be/",
        "https://www.youtube.com/live",
        "https://www.youtube.com/live/",
        "https://www.youtube.com/live/short",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_bad_youtube_rejected(url):
    with pytest.raises(IngestError) as e:
        parse_url(url)
    assert e.value.code == ErrorCode.UNSUPPORTED_URL


@pytest.mark.parametrize(
    "url",
    [
        f"https://drive.google.com/file/d/{DRIVE}/view",
        f"https://drive.google.com/file/d/{DRIVE}/view?usp=sharing",
        f"https://drive.google.com/file/d/{DRIVE}/preview",
        f"https://drive.google.com/file/d/{DRIVE}/edit",
        f"https://drive.google.com/file/d/{DRIVE}",
        f"https://drive.google.com/open?id={DRIVE}",
        f"https://drive.google.com/uc?id={DRIVE}&export=download",
        f"https://drive.google.com/uc?export=download&id={DRIVE}",
    ],
)
def test_drive_shapes(url):
    p = parse_url(url)
    assert p.source_type == "gdrive"
    assert p.canonical_id == f"gdrive:{DRIVE}"
    assert p.lecture_id == f"gdrive_{DRIVE}"
    assert p.normalized_url == f"https://drive.google.com/file/d/{DRIVE}/view"
    assert p.external_timestamp_url_template is None


@pytest.mark.parametrize(
    "url",
    [
        "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456",
        "https://drive.google.com/file/d/short/view",
        "https://drive.google.com/file/d/{}/copy".format(DRIVE),
        "https://drive.google.com/",
        "https://docs.google.com/document/d/abc/edit",
        "https://classroom.google.com/c/123",
        "https://canvas.instructure.com/courses/1/files/2",
        "https://moodle.example.edu/mod/resource/view.php?id=5",
    ],
)
def test_bad_google_and_lms_rejected(url):
    with pytest.raises(IngestError) as e:
        parse_url(url)
    assert e.value.code == ErrorCode.UNSUPPORTED_URL


def test_direct_url_canonical_id_and_normalization():
    a = parse_url("HTTPS://Example.COM:443/videos/Lecture%201.mp4?b=2&a=1#frag")
    b = parse_url("https://example.com/videos/Lecture%201.mp4?a=1&b=2")
    assert a.source_type == b.source_type == "direct"
    assert a.normalized_url == b.normalized_url == "https://example.com/videos/Lecture%201.mp4?a=1&b=2"
    digest = hashlib.sha256(a.normalized_url.encode()).hexdigest()[:16]
    assert a.canonical_id == f"url:{digest}"
    assert a.lecture_id == f"url_{digest}"
    assert a.external_timestamp_url_template is None
    # The URL used for fetching stays as pasted.
    assert a.source_url == "HTTPS://Example.COM:443/videos/Lecture%201.mp4?b=2&a=1#frag"


def test_direct_url_keeps_non_default_port():
    assert parse_url("http://example.com:8080/a.mp4").normalized_url == "http://example.com:8080/a.mp4"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/a.mp4",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:video/mp4;base64,AAAA",
        "mailto:a@b.com",
        "",
        "   ",
        "not a url",
        "hello",
        "https://",
        "https:///a.mp4",
        "https://exa mple.com/a.mp4",
        "https://user:pass@example.com/a.mp4",
        "https://example.com:99999/a.mp4",
        "https://example.com/" + "a" * 3000,
        "https://example.com/a\n.mp4",
    ],
)
def test_garbage_and_schemes_rejected(url):
    with pytest.raises(IngestError) as e:
        parse_url(url)
    assert e.value.code == ErrorCode.UNSUPPORTED_URL


def test_non_string_rejected():
    with pytest.raises(IngestError):
        parse_url(None)  # type: ignore[arg-type]
