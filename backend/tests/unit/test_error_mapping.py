import httpx
import pytest
import requests
from gdown.exceptions import DownloadError as GdownDownloadError
from gdown.exceptions import FileURLRetrievalError
from yt_dlp.utils import DownloadError, ExtractorError, GeoRestrictedError

from insightex.ingest import netguard
from insightex.ingest.errors import DEFAULT_MESSAGES, ErrorCode, IngestError
from insightex.ingest.sources.gdrive import map_gdown_error
from insightex.ingest.sources.ytdlp import map_ytdlp_error

E = ErrorCode


def test_every_code_has_a_message():
    assert set(DEFAULT_MESSAGES) == set(ErrorCode)
    assert len(ErrorCode) == 17
    err = IngestError("TOO_LONG")
    assert err.code is E.TOO_LONG and err.to_dict() == {"code": "TOO_LONG", "message": DEFAULT_MESSAGES[E.TOO_LONG]}


def test_unknown_code_rejected():
    with pytest.raises(ValueError):
        IngestError("SOMETHING_ELSE")


def _dl(msg, inner=None):
    return DownloadError(f"ERROR: [youtube] abc: {msg}", (type(inner), inner, None) if inner else None)


@pytest.mark.parametrize(
    "msg,code",
    [
        ("Private video. Sign in if you've been granted access to this video", E.PRIVATE_OR_LOGIN_REQUIRED),
        ("Join this channel to get access to members-only content like this video", E.PRIVATE_OR_LOGIN_REQUIRED),
        ("Sign in to confirm your age. This video may be inappropriate for some users.", E.AGE_RESTRICTED),
        ("Video unavailable. The uploader has not made this video available in your country", E.GEO_BLOCKED),
        ("This live event will begin in 3 hours.", E.LIVE_NOT_SUPPORTED),
        ("Premieres in 2 days", E.LIVE_NOT_SUPPORTED),
        ("This video is DRM protected", E.UNSUPPORTED_URL),
        ("Sign in to confirm you’re not a bot. Use --cookies-from-browser", E.DOWNLOAD_FAILED),
        ("Video unavailable. This video has been removed by the uploader", E.DOWNLOAD_FAILED),
        ("Unable to download webpage: <urlopen error [Errno -3] Temporary failure in name resolution>", E.NETWORK_ERROR),
        ("Unable to download API page: The read operation timed out", E.NETWORK_ERROR),
        ("Requested format is not available", E.DOWNLOAD_FAILED),
        ("Unsupported URL: https://example.com", E.UNSUPPORTED_URL),
        ("something nobody anticipated", E.DOWNLOAD_FAILED),
    ],
)
def test_ytdlp_youtube_messages(msg, code):
    err = map_ytdlp_error(_dl(msg), [], "youtube")
    assert err.code == code
    assert "Traceback" not in err.message and "ERROR:" not in err.message


def test_ytdlp_geo_exception_type():
    assert map_ytdlp_error(_dl("blocked", GeoRestrictedError("nope")), [], "youtube").code == E.GEO_BLOCKED
    assert map_ytdlp_error(GeoRestrictedError("nope"), [], "youtube").code == E.GEO_BLOCKED


def test_ytdlp_uses_logged_warnings():
    err = map_ytdlp_error(ExtractorError("no formats"), ["[youtube] abc: This video is DRM protected"], "youtube")
    assert err.code == E.UNSUPPORTED_URL


@pytest.mark.parametrize(
    "msg,code",
    [
        ("Unable to download JSON metadata: HTTP Error 403: Forbidden", E.DRIVE_NOT_SHARED),
        ("Unable to download JSON metadata: HTTP Error 404: Not Found", E.DRIVE_NOT_SHARED),
        ("Too many users have viewed or downloaded this file recently", E.DRIVE_QUOTA_EXCEEDED),
        ("Download quota exceeded for this file", E.DRIVE_QUOTA_EXCEEDED),
        ("<urlopen error timed out>", E.NETWORK_ERROR),
    ],
)
def test_ytdlp_drive_messages(msg, code):
    assert map_ytdlp_error(DownloadError(f"ERROR: [GoogleDrive] x: {msg}"), [], "gdrive").code == code


def test_ytdlp_403_on_youtube_is_not_drive_error():
    assert map_ytdlp_error(DownloadError("ERROR: HTTP Error 403: Forbidden"), [], "youtube").code == E.DOWNLOAD_FAILED


@pytest.mark.parametrize(
    "exc,code",
    [
        (FileURLRetrievalError("Too many users have viewed or downloaded this file recently."), E.DRIVE_QUOTA_EXCEEDED),
        (FileURLRetrievalError("Cannot retrieve the public link of the file. You may need to change the permission"),
         E.DRIVE_NOT_SHARED),
        (requests.ConnectionError("conn refused"), E.NETWORK_ERROR),
        (requests.Timeout("slow"), E.NETWORK_ERROR),
        (GdownDownloadError("response body ended early"), E.DOWNLOAD_FAILED),
        (RuntimeError("weird"), E.DOWNLOAD_FAILED),
    ],
)
def test_gdown_mapping(exc, code):
    assert map_gdown_error(exc).code == code


def test_gdown_http_status():
    resp = requests.Response()
    resp.status_code = 403
    assert map_gdown_error(requests.HTTPError(response=resp)).code == E.DRIVE_NOT_SHARED
    resp.status_code = 429
    assert map_gdown_error(requests.HTTPError(response=resp)).code == E.DRIVE_QUOTA_EXCEEDED


_REQ = httpx.Request("GET", "https://example.com/v.mp4")


@pytest.mark.parametrize(
    "exc,code",
    [
        (httpx.ConnectError("refused", request=_REQ), E.NETWORK_ERROR),
        (httpx.ReadTimeout("slow", request=_REQ), E.NETWORK_ERROR),
        (httpx.RemoteProtocolError("peer closed", request=_REQ), E.NETWORK_ERROR),
        (httpx.HTTPStatusError("403", request=_REQ, response=httpx.Response(403, request=_REQ)),
         E.PRIVATE_OR_LOGIN_REQUIRED),
        (httpx.HTTPStatusError("404", request=_REQ, response=httpx.Response(404, request=_REQ)), E.DOWNLOAD_FAILED),
        (httpx.HTTPStatusError("503", request=_REQ, response=httpx.Response(503, request=_REQ)), E.NETWORK_ERROR),
        (httpx.UnsupportedProtocol("ftp", request=_REQ), E.UNSUPPORTED_URL),
    ],
)
def test_httpx_mapping(exc, code):
    assert netguard.map_httpx_error(exc).code == code
