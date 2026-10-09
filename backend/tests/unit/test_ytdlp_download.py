"""Real yt-dlp download path (progress hook, byte cap, output naming) against a loopback HTTP server.

No internet: yt-dlp's generic extractor fetches a synthetic clip from 127.0.0.1.
"""

import functools
import http.server
import threading

import pytest

from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources import ytdlp


@pytest.fixture
def server(media):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(media["h264_aac_mp4"].parent))
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_download_with_progress(server, tmp_path, media):
    settings = IngestSettings()
    calls = []
    out = ytdlp.download(f"{server}/h264_aac.mp4", tmp_path, settings, "direct", "b", lambda r, t: calls.append((r, t)),
                         merge_mp4=False)
    assert out.parent == tmp_path and out.name == "source.mp4"
    assert out.read_bytes() == media["h264_aac_mp4"].read_bytes()
    assert calls and calls[-1][0] == out.stat().st_size


def test_byte_cap_aborts_download(server, tmp_path):
    settings = IngestSettings(max_download_bytes=1000)
    with pytest.raises(IngestError) as e:
        ytdlp.download(f"{server}/h264_aac.mp4", tmp_path, settings, "direct", "b", None, merge_mp4=False)
    assert e.value.code == ErrorCode.TOO_LARGE


def test_missing_file_maps_to_error(server, tmp_path):
    settings = IngestSettings()
    with pytest.raises(IngestError) as e:
        ytdlp.download(f"{server}/nope.mp4", tmp_path, settings, "direct", "b", None, merge_mp4=False)
    assert e.value.code in (ErrorCode.DOWNLOAD_FAILED, ErrorCode.UNSUPPORTED_URL)


class _NoLengthHandler(http.server.BaseHTTPRequestHandler):
    """Close-delimited body with no Content-Length: yt-dlp can't pre-check the size, so only the hook can."""

    body = b""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a):
        pass


def test_byte_cap_enforced_by_hook_without_content_length(tmp_path, media):
    _NoLengthHandler.body = media["h264_aac_mp4"].read_bytes()
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _NoLengthHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        settings = IngestSettings(max_download_bytes=1000)
        with pytest.raises(IngestError) as e:
            ytdlp.download(f"http://127.0.0.1:{httpd.server_address[1]}/clip.mp4", tmp_path, settings, "direct", "b",
                           None, merge_mp4=False)
        assert e.value.code == ErrorCode.TOO_LARGE
    finally:
        httpd.shutdown()
