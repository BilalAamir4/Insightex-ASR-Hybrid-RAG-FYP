"""Shared fixtures. Media fixtures are synthetic clips generated with ffmpeg at test time (none committed)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from insightex.core.config import clear_settings_cache
from insightex.ingest.settings import IngestSettings


@pytest.fixture(autouse=True)
def isolated_settings(request, monkeypatch, tmp_path, tmp_path_factory):
    """Every test sees default settings plus paths.data_dir=tmp_path, whatever the shell exports.

    Clears INSIGHTEX_DATA, OLLAMA_BASE_URL, INSIGHTEX_CONFIG and INSIGHTEX__* and points INSIGHTEX_CONFIG
    at a throwaway file, so config/local.yaml and ~/insightex-data are never read or written.
    Opt out with @pytest.mark.real_env (tests that need the real environment).
    """
    if request.node.get_closest_marker("real_env"):
        yield
        return
    for name in list(os.environ):
        if name.upper().startswith("INSIGHTEX__") or name in ("INSIGHTEX_DATA", "OLLAMA_BASE_URL", "INSIGHTEX_CONFIG"):
            monkeypatch.delenv(name)
    cfg = tmp_path_factory.mktemp("cfg") / "test_config.yaml"  # outside tmp_path: tests list its contents
    cfg.write_text(f"paths:\n  data_dir: {tmp_path}\n")
    monkeypatch.setenv("INSIGHTEX_CONFIG", str(cfg))
    clear_settings_cache()
    yield
    clear_settings_cache()


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


_SRC_V = ["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=12"]
_SRC_A = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=12"]


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("media")
    clips = {
        # Already H.264 (yuv420p) + AAC in mp4: should remux.
        "h264_aac_mp4": (d / "h264_aac.mp4", [*_SRC_V, *_SRC_A, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                              "-c:a", "aac", "-shortest"]),
        # Phone-style HEVC in MKV (OBS-style container) with variable frame rate: should transcode.
        "hevc_vfr_mkv": (d / "hevc_vfr.mkv", [*_SRC_V, *_SRC_A, "-vf", "select='not(mod(n\\,3))+lt(n\\,10)'",
                                              "-fps_mode", "vfr", "-c:v", "libx265", "-x265-params", "log-level=error",
                                              "-c:a", "libopus", "-shortest"]),
        # H.264 + AAC in mp4 but taller than 1080 (and odd width): transcode to scale down.
        "tall_h264_mp4": (d / "tall.mp4", ["-f", "lavfi", "-i", "testsrc2=size=322x1200:rate=10:duration=1",
                                           "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264",
                                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]),
        "video_only_mp4": (d / "video_only.mp4", [*_SRC_V, "-c:v", "libx264", "-pix_fmt", "yuv420p"]),
        "audio_only_m4a": (d / "audio_only.m4a", [*_SRC_A, "-c:a", "aac"]),
    }
    out = {}
    for key, (path, args) in clips.items():
        _ffmpeg(*args, str(path))
        out[key] = path
    garbage = d / "garbage.mp4"
    garbage.write_bytes(os.urandom(64 * 1024))
    out["garbage"] = garbage
    return out


@pytest.fixture
def settings(tmp_path) -> IngestSettings:
    return IngestSettings()


@pytest.fixture
def allow_loopback(monkeypatch):
    """Let the SSRF guard accept 127.0.0.1, for the duration of one test only.

    There is deliberately no config flag or environment variable for this in production code.
    """
    from insightex.ingest import netguard

    real = netguard.is_public_ip
    monkeypatch.setattr(netguard, "is_public_ip", lambda ip: str(ip) == "127.0.0.1" or real(ip))


@pytest.fixture
def serve_bytes(allow_loopback):
    """serve_bytes(body) -> a local HTTP server that answers every GET with `body` as video/mp4; no internet involved."""
    import http.server
    import threading

    servers = []

    def start(body: bytes):
        hits: list[str] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                if self.path.split("?")[0] != "/lecture.mp4":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return type("LocalServer", (), {"url": f"http://127.0.0.1:{server.server_address[1]}/lecture.mp4",
                                        "hits": hits, "size": len(body)})

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def video_server(media, serve_bytes):
    """The synthetic H.264/AAC clip served at /lecture.mp4."""
    return serve_bytes(media["h264_aac_mp4"].read_bytes())
