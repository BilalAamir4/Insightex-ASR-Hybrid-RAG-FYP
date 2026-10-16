"""`serve`: a small standard-library HTTP server for the labelling page, bound to 127.0.0.1 only.

GET  /                 the page (static/index.html, static/app.js)
GET  /api/session      lecture, labeller, the labeller's windows (text, times, shared flag) and their saved labels
PUT  /api/window/<i>   save one window's labels; validated with extraction_schema.check_window_record, 400 with the
                       error list if invalid; the labels file is rewritten atomically (temp file + os.replace)
GET  /video.mp4        the workspace's normalised video, with HTTP Range support so the browser can seek
"""

from __future__ import annotations

import json
import os
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from extraction_schema import RELATION_TYPES, check_window_record

STATIC = Path(__file__).with_name("static")
CHUNK = 1 << 20  # bytes per write when streaming video


class LabelStore:
    """One labeller's labels file: an extraction document (schema v1) with the windows in labelling order."""

    def __init__(self, path: Path, lecture_id: str, labeller: str, manifest_sha256: str, rows: list[dict[str, Any]],
                 earlier_manifest_sha256: frozenset[str] = frozenset()):
        """earlier_manifest_sha256: manifests this one was amended from; a file made against one of them is loaded and
        written back with the current sha256 on the next save."""
        self.path, self.lecture_id, self.labeller = path, lecture_id, labeller
        self.manifest_sha256 = manifest_sha256
        self.order = {r["window_index"]: r["order"] for r in rows}
        self.lock = threading.Lock()
        self.records: dict[int, dict[str, Any]] = {}
        if path.is_file():
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("sample_manifest_sha256") not in {manifest_sha256, *earlier_manifest_sha256}:
                raise SystemExit(f"{path} was made against another sample manifest; move it away first")
            self.records = {r["window"]["window_index"]: r for r in doc["windows"]}

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "lecture_id": self.lecture_id,
            "producer": {"kind": "human", "name": self.labeller},
            "sample_manifest_sha256": self.manifest_sha256,
            "windows": [self.records[i] for i in sorted(self.records, key=lambda i: self.order.get(i, 1 << 30))],
        }

    def save(self, record: dict[str, Any]) -> None:
        with self.lock:
            self.records[record["window"]["window_index"]] = record
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.document(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)


def make_handler(*, session: dict[str, Any], rows: dict[int, dict[str, Any]], store: LabelStore, video: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "label_concepts/1"

        def log_message(self, fmt: str, *args: Any) -> None:  # keep the console quiet apart from errors
            if args and str(args[1]).startswith(("4", "5")):
                super().log_message(fmt, *args)

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj: Any) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/app.js":
                self._send(200, (STATIC / "app.js").read_bytes(), "text/javascript; charset=utf-8")
            elif path == "/api/session":
                self._json(200, {**session, "labels": store.document()["windows"]})
            elif path == "/video.mp4":
                self._video()
            else:
                self._json(404, {"error": "not found"})

        def do_PUT(self) -> None:
            m = re.fullmatch(r"/api/window/(\d+)", self.path)
            if not m or int(m.group(1)) not in rows:
                self._json(404, {"errors": ["no such window in this labeller's sample"]})
                return
            row = rows[int(m.group(1))]
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"null")
            except (ValueError, UnicodeDecodeError):
                self._json(400, {"errors": ["body is not JSON"]})
                return
            if not isinstance(body, dict):
                self._json(400, {"errors": ["body must be an object"]})
                return
            record = {"window": {"lecture_id": store.lecture_id, "window_index": row["window_index"],
                                 "start_s": row["start_s"], "end_s": row["end_s"]}, **body}
            errors = check_window_record(record, "window")
            if errors:
                self._json(400, {"errors": errors})
                return
            store.save(record)
            self._json(200, {"ok": True})

        def _video(self) -> None:
            size = video.stat().st_size
            rng = self.headers.get("Range")
            start, end, status = 0, size - 1, HTTPStatus.OK
            if rng:
                m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
                if not m or (not m.group(1) and not m.group(2)):
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                else:  # suffix range: the last N bytes
                    start = max(0, size - int(m.group(2)))
                if start >= size or start > end:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = HTTPStatus.PARTIAL_CONTENT
            self.send_response(status)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with video.open("rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = f.read(min(CHUNK, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser cancels range requests while seeking

    return Handler


def serve(*, port: int, session: dict[str, Any], rows: list[dict[str, Any]], store: LabelStore, video: Path) -> None:
    handler = make_handler(session={**session, "relation_types": list(RELATION_TYPES)},
                           rows={r["window_index"]: r for r in rows}, store=store, video=video)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"labelling {session['lecture_id']} as {store.labeller}: http://127.0.0.1:{port}/  (Ctrl+C to stop)")
    print(f"labels are saved to {store.path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
