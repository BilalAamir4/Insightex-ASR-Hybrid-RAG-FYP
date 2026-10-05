"""SSRF guard for direct URLs: resolve the host, refuse non-public addresses, re-check after every redirect.

Known gap: the address is checked here and then httpx resolves the name again to connect. A DNS
rebinding server could answer differently the second time. Pinning the IP would break TLS SNI and
certificate checks, so the gap is documented rather than closed.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from urllib.parse import urljoin, urlsplit

import httpx

from insightex.ingest.errors import ErrorCode, IngestError

log = logging.getLogger(__name__)

MAX_REDIRECTS = 10
USER_AGENT = "Insightex/0.1 (lecture ingestion)"
TIMEOUT = httpx.Timeout(connect=15.0, read=60.0, write=60.0, pool=15.0)

# Spelled out to match the spec; is_global below also catches CGNAT, reserved, documentation etc.
BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8", "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "169.254.0.0/16", "100.64.0.0/10", "224.0.0.0/4", "240.0.0.0/4",
        "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
    )
)

Resolver = Callable[[str, int], list[str]]


def is_public_ip(ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    addr = ipaddress.ip_address(ip) if isinstance(ip, str) else ip
    if isinstance(addr, ipaddress.IPv6Address):
        # ::ffff:127.0.0.1 and friends are judged by the embedded IPv4 address.
        mapped = addr.ipv4_mapped or addr.sixtofour
        if mapped is not None:
            return is_public_ip(mapped)
        if addr.teredo is not None:
            return False
    if any(addr in net for net in BLOCKED_NETWORKS if net.version == addr.version):
        return False
    return addr.is_global and not addr.is_multicast


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def check_url(url: str, resolver: Resolver = system_resolver) -> None:
    """Raise BLOCKED_ADDRESS unless url is http(s) and every address its host resolves to is public."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise IngestError(ErrorCode.UNSUPPORTED_URL, "Only http and https links are supported.")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise IngestError(ErrorCode.UNSUPPORTED_URL)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addrs = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addrs = resolver(host, port)
        except (socket.gaierror, UnicodeError, OSError) as exc:
            log.warning("DNS resolution failed for %s: %r", host, exc)
            raise IngestError(
                ErrorCode.NETWORK_ERROR, "We couldn't find that website. Check the link and try again."
            ) from exc
    if not addrs:
        raise IngestError(ErrorCode.NETWORK_ERROR, "We couldn't find that website. Check the link and try again.")
    blocked = [a for a in addrs if not is_public_ip(a.split("%", 1)[0])]
    if blocked:
        log.warning("blocked non-public address for %s: %s", host, blocked)
        raise IngestError(ErrorCode.BLOCKED_ADDRESS)


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    # trust_env=False: no proxy or netrc credentials from the environment.
    return httpx.Client(
        follow_redirects=False,
        timeout=TIMEOUT,
        # identity: the byte cap and Content-Length comparison count bytes as sent on the wire.
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
        trust_env=False,
        transport=transport,
    )


@contextmanager
def guarded_stream(
    client: httpx.Client,
    url: str,
    resolver: Resolver = system_resolver,
    method: str = "GET",
) -> Iterator[httpx.Response]:
    """Stream url, following up to MAX_REDIRECTS redirects by hand, checking each hop's address."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        check_url(current, resolver)
        request = client.build_request(method, current)
        response = client.send(request, stream=True)
        if response.is_redirect:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise IngestError(ErrorCode.DOWNLOAD_FAILED, "The server sent a broken redirect.")
            current = urljoin(current, location)
            continue
        try:
            yield response
        finally:
            response.close()
        return
    raise IngestError(ErrorCode.DOWNLOAD_FAILED, "The link redirects too many times.")


def map_httpx_error(exc: Exception) -> IngestError:
    """httpx failure -> IngestError. The raw exception is logged by the caller, never shown."""
    if isinstance(exc, IngestError):
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        return map_http_status(exc.response.status_code)
    if isinstance(exc, httpx.TimeoutException):
        return IngestError(ErrorCode.NETWORK_ERROR, "The video's server took too long to respond. Try again later.")
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError, httpx.ProxyError)):
        return IngestError(ErrorCode.NETWORK_ERROR)
    if isinstance(exc, (httpx.InvalidURL, httpx.UnsupportedProtocol)):
        return IngestError(ErrorCode.UNSUPPORTED_URL)
    return IngestError(ErrorCode.DOWNLOAD_FAILED)


def map_http_status(status: int) -> IngestError:
    if status in (401, 403):
        return IngestError(ErrorCode.PRIVATE_OR_LOGIN_REQUIRED, "The server refused access to this video. It may need a sign-in.")
    if status in (404, 410):
        return IngestError(ErrorCode.DOWNLOAD_FAILED, "The video wasn't found at that link.")
    if status == 451:
        return IngestError(ErrorCode.GEO_BLOCKED)
    if status >= 500:
        return IngestError(ErrorCode.NETWORK_ERROR, "The video's server had an error. Try again later.")
    return IngestError(ErrorCode.DOWNLOAD_FAILED)
