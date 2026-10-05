import httpx
import pytest

from insightex.ingest import netguard
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.sources import direct
from insightex.ingest.sources.base import SourceMeta
from insightex.ingest.urls import parse_url

PUBLIC = {"videos.example": ["93.184.216.34"], "cdn.example": ["93.184.216.35"], "evil.example": ["10.0.0.1"]}


def resolver(host, port):
    return PUBLIC[host]


def client(handler):
    return netguard.make_client(transport=httpx.MockTransport(handler))


def serve(body=b"", headers=None, status=200):
    def handler(request):
        return httpx.Response(status, headers=headers or {}, content=body)
    return handler


def test_probe_reads_headers_only(settings):
    p = parse_url("https://videos.example/lectures/Week%203.mp4")
    meta = direct.probe(p, settings, client(serve(b"x" * 10, {"content-type": "video/mp4", "content-length": "10"})), resolver)
    assert meta.title == "Week 3" and meta.size_bytes == 10 and meta.ext == "mp4" and meta.duration_s is None


@pytest.mark.parametrize(
    "headers,url,code",
    [
        ({"content-type": "text/html; charset=utf-8"}, "https://videos.example/watch", ErrorCode.NOT_A_VIDEO),
        ({"content-type": "application/pdf"}, "https://videos.example/a.pdf", ErrorCode.NOT_A_VIDEO),
        ({"content-type": "application/octet-stream"}, "https://videos.example/a.zip", ErrorCode.NOT_A_VIDEO),
        ({"content-type": "application/vnd.apple.mpegurl"}, "https://videos.example/a.m3u8", ErrorCode.NOT_A_VIDEO),
        ({"content-type": "video/mp4", "content-length": str(5 * 1024**3)}, "https://videos.example/a.mp4",
         ErrorCode.TOO_LARGE),
    ],
)
def test_probe_rejections(settings, headers, url, code):
    with pytest.raises(IngestError) as e:
        direct.probe(parse_url(url), settings, client(serve(b"", headers)), resolver)
    assert e.value.code == code


def test_octet_stream_with_video_extension_accepted(settings):
    p = parse_url("https://videos.example/a.mkv")
    meta = direct.probe(p, settings, client(serve(b"", {"content-type": "application/octet-stream"})), resolver)
    assert meta.ext == "mkv"


def test_content_disposition_filename(settings):
    headers = {"content-type": "application/octet-stream", "content-disposition": 'attachment; filename="Lecture 5.mov"'}
    meta = direct.probe(parse_url("https://videos.example/dl?id=5"), settings, client(serve(b"", headers)), resolver)
    assert meta.title == "Lecture 5" and meta.ext == "mov"


@pytest.mark.parametrize("status,code", [(403, ErrorCode.PRIVATE_OR_LOGIN_REQUIRED), (404, ErrorCode.DOWNLOAD_FAILED),
                                         (500, ErrorCode.NETWORK_ERROR)])
def test_probe_http_status(settings, status, code):
    with pytest.raises(IngestError) as e:
        direct.probe(parse_url("https://videos.example/a.mp4"), settings, client(serve(b"", {}, status)), resolver)
    assert e.value.code == code


def test_probe_blocked_host(settings):
    with pytest.raises(IngestError) as e:
        direct.probe(parse_url("https://evil.example/a.mp4"), settings, client(serve()), resolver)
    assert e.value.code == ErrorCode.BLOCKED_ADDRESS


def test_probe_redirect_into_private_network(settings):
    def handler(request):
        if request.url.host == "videos.example":
            return httpx.Response(302, headers={"location": "https://evil.example/a.mp4"})
        raise AssertionError("connected to blocked host")

    with pytest.raises(IngestError) as e:
        direct.probe(parse_url("https://videos.example/a.mp4"), settings, client(handler), resolver)
    assert e.value.code == ErrorCode.BLOCKED_ADDRESS


def test_connect_error_is_network_error(settings):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(IngestError) as e:
        direct.probe(parse_url("https://videos.example/a.mp4"), settings, client(handler), resolver)
    assert e.value.code == ErrorCode.NETWORK_ERROR


def test_download_writes_file_and_reports_bytes(settings, tmp_path):
    body = b"v" * (3 * 1024 * 1024 + 7)
    calls = []
    p = parse_url("https://videos.example/a.webm")
    out = direct.download(p, tmp_path, settings, SourceMeta(), lambda r, t: calls.append((r, t)),
                          client(serve(body, {"content-type": "video/webm", "content-length": str(len(body))})), resolver)
    assert out == tmp_path / "source.webm" and out.read_bytes() == body
    assert calls[-1] == (len(body), len(body))
    assert not (tmp_path / "source.part").exists()


def test_download_cap_enforced_on_received_bytes(tmp_path):
    from insightex.ingest.settings import IngestSettings

    small = IngestSettings(lectures_dir=tmp_path, max_download_bytes=2 * 1024 * 1024)
    # No Content-Length: only the byte count can catch it.
    body = b"v" * (5 * 1024 * 1024)

    def handler(request):
        return httpx.Response(200, headers={"content-type": "video/mp4"}, stream=httpx.ByteStream(body))

    with pytest.raises(IngestError) as e:
        direct.download(parse_url("https://videos.example/a.mp4"), tmp_path, small, SourceMeta(), None, client(handler), resolver)
    assert e.value.code == ErrorCode.TOO_LARGE
    assert list(tmp_path.iterdir()) == []


def test_download_cap_enforced_on_content_length(tmp_path):
    from insightex.ingest.settings import IngestSettings

    small = IngestSettings(lectures_dir=tmp_path, max_download_bytes=100)
    with pytest.raises(IngestError) as e:
        direct.download(parse_url("https://videos.example/a.mp4"), tmp_path, small, SourceMeta(), None,
                        client(serve(b"", {"content-type": "video/mp4", "content-length": "101"})), resolver)
    assert e.value.code == ErrorCode.TOO_LARGE


def test_truncated_download_detected(settings, tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "video/mp4", "content-length": "1000"},
                              stream=httpx.ByteStream(b"x" * 10))

    with pytest.raises(IngestError) as e:
        direct.download(parse_url("https://videos.example/a.mp4"), tmp_path, settings, SourceMeta(), None, client(handler), resolver)
    assert e.value.code == ErrorCode.NETWORK_ERROR
    assert list(tmp_path.iterdir()) == []
