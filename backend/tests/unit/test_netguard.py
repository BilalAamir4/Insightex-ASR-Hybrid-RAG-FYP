import socket

import httpx
import pytest

from insightex.ingest import netguard
from insightex.ingest.errors import ErrorCode, IngestError


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "127.8.9.10", "10.1.2.3", "172.16.0.1", "172.31.255.255", "192.168.1.1",
     "169.254.169.254", "0.0.0.0", "100.64.0.1", "224.0.0.1", "255.255.255.255",
     "::1", "::", "fc00::1", "fd12:3456::1", "fe80::1", "ff02::1",
     "::ffff:127.0.0.1", "::ffff:10.0.0.1", "2002:7f00:0001::1", "192.0.2.1", "198.18.0.1"],
)
def test_non_public_addresses(ip):
    assert not netguard.is_public_ip(ip)


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "142.250.80.46", "172.32.0.1", "2606:4700:4700::1111"])
def test_public_addresses(ip):
    assert netguard.is_public_ip(ip)


def _resolver(table):
    def resolve(host, port):
        if host not in table:
            raise socket.gaierror("unknown host")
        return table[host]
    return resolve


def test_check_url_blocks_private_resolution():
    with pytest.raises(IngestError) as e:
        netguard.check_url("http://intranet.example/x.mp4", _resolver({"intranet.example": ["10.0.0.5"]}))
    assert e.value.code == ErrorCode.BLOCKED_ADDRESS


def test_check_url_blocks_if_any_address_private():
    r = _resolver({"mixed.example": ["93.184.216.34", "127.0.0.1"]})
    with pytest.raises(IngestError) as e:
        netguard.check_url("https://mixed.example/x.mp4", r)
    assert e.value.code == ErrorCode.BLOCKED_ADDRESS


@pytest.mark.parametrize("url", ["http://127.0.0.1/x.mp4", "http://[::1]:8080/x.mp4", "http://169.254.169.254/latest",
                                 "http://[::ffff:192.168.0.1]/x"])
def test_check_url_blocks_ip_literals(url):
    with pytest.raises(IngestError) as e:
        netguard.check_url(url, _resolver({}))
    assert e.value.code == ErrorCode.BLOCKED_ADDRESS


def test_check_url_dns_failure_is_network_error():
    with pytest.raises(IngestError) as e:
        netguard.check_url("https://nope.example/x.mp4", _resolver({}))
    assert e.value.code == ErrorCode.NETWORK_ERROR


def test_check_url_allows_public():
    netguard.check_url("https://cdn.example/x.mp4", _resolver({"cdn.example": ["93.184.216.34"]}))


def _client(handler):
    return netguard.make_client(transport=httpx.MockTransport(handler))


def test_redirect_to_private_address_blocked():
    def handler(request):
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://internal.example/secret.mp4"})
        raise AssertionError("must not connect to the internal host")

    r = _resolver({"public.example": ["93.184.216.34"], "internal.example": ["192.168.1.10"]})
    with _client(handler) as client, pytest.raises(IngestError) as e:
        with netguard.guarded_stream(client, "https://public.example/v.mp4", r):
            pass
    assert e.value.code == ErrorCode.BLOCKED_ADDRESS


def test_relative_redirect_to_ip_literal_blocked():
    def handler(request):
        return httpx.Response(301, headers={"location": "http://127.0.0.1:9000/v.mp4"})

    with _client(handler) as client, pytest.raises(IngestError) as e:
        with netguard.guarded_stream(client, "https://public.example/v.mp4", _resolver({"public.example": ["93.184.216.34"]})):
            pass
    assert e.value.code == ErrorCode.BLOCKED_ADDRESS


def test_redirect_to_other_scheme_rejected():
    def handler(request):
        return httpx.Response(302, headers={"location": "file:///etc/passwd"})

    with _client(handler) as client, pytest.raises(IngestError) as e:
        with netguard.guarded_stream(client, "https://public.example/v.mp4", _resolver({"public.example": ["93.184.216.34"]})):
            pass
    assert e.value.code == ErrorCode.UNSUPPORTED_URL


def test_public_redirect_chain_followed():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        if request.url.path == "/b":
            return httpx.Response(307, headers={"location": "https://cdn.example/c.mp4"})
        return httpx.Response(200, headers={"content-type": "video/mp4"}, content=b"x")

    r = _resolver({"public.example": ["93.184.216.34"], "cdn.example": ["93.184.216.35"]})
    with _client(handler) as client:
        with netguard.guarded_stream(client, "https://public.example/a", r) as resp:
            assert resp.status_code == 200
    assert seen == ["https://public.example/a", "https://public.example/b", "https://cdn.example/c.mp4"]


def test_redirect_loop_stops():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://public.example/loop"})

    with _client(handler) as client, pytest.raises(IngestError) as e:
        with netguard.guarded_stream(client, "https://public.example/loop", _resolver({"public.example": ["93.184.216.34"]})):
            pass
    assert e.value.code == ErrorCode.DOWNLOAD_FAILED
