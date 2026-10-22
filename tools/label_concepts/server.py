"""`serve`: a small standard-library HTTP server for the labelling page, bound to 127.0.0.1 only.

GET  /                 the page (static/index.html, static/app.js)
GET  /api/session      lecture, labeller, the labeller's windows (text, times, shared flag) and their saved labels
PUT  /api/window/<i>   save one window's labels; validated with extraction_schema.check_window_record, 400 with the
                       error list if invalid; the labels file is rewritten atomically (temp file + os.replace)
GET  /video.mp4        the workspace's normalised video, with HTTP Range support so the browser can seek

The relabelling pass (ADR-0048 Amendment 5) has its own page and endpoints: see make_relabel_handler.
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

import relabel
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


def send_video(h: BaseHTTPRequestHandler, video: Path) -> None:
    """Stream the video with HTTP Range support, so the browser can seek."""
    size = video.stat().st_size
    rng = h.headers.get("Range")
    start, end, status = 0, size - 1, HTTPStatus.OK
    if rng:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
        if not m or (not m.group(1) and not m.group(2)):
            h.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            h.send_header("Content-Range", f"bytes */{size}")
            h.end_headers()
            return
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:  # suffix range: the last N bytes
            start = max(0, size - int(m.group(2)))
        if start >= size or start > end:
            h.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            h.send_header("Content-Range", f"bytes */{size}")
            h.end_headers()
            return
        status = HTTPStatus.PARTIAL_CONTENT
    h.send_response(status)
    h.send_header("Content-Type", "video/mp4")
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(end - start + 1))
    if status == HTTPStatus.PARTIAL_CONTENT:
        h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    h.end_headers()
    try:
        with video.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(CHUNK, left))
                if not chunk:
                    break
                h.wfile.write(chunk)
                left -= len(chunk)
    except (BrokenPipeError, ConnectionResetError):
        pass  # the browser cancels range requests while seeking


class JsonHandler(BaseHTTPRequestHandler):
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

    def _body(self) -> Any:
        """The request's JSON body; raises ValueError if it is not JSON."""
        try:
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"null")
        except UnicodeDecodeError as e:
            raise ValueError(str(e)) from e


def make_handler(*, session: dict[str, Any], rows: dict[int, dict[str, Any]], store: LabelStore, video: Path):
    class Handler(JsonHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/app.js":
                self._send(200, (STATIC / "app.js").read_bytes(), "text/javascript; charset=utf-8")
            elif path == "/api/session":
                self._json(200, {**session, "labels": store.document()["windows"]})
            elif path == "/video.mp4":
                send_video(self, video)
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


# -- relabelling pass (ADR-0048 Amendment 5; relabel.py) -------------------------------------------------------------


class RelabelStore:
    """The relabelling state file next to its frozen base gold; every accepted change is written atomically."""

    def __init__(self, state_path: Path, base_path: Path, lecture_id: str):
        self.state_path, self.lock = state_path, threading.Lock()
        self.state, self.base = relabel.load(state_path, base_path, lecture_id)

    def view(self) -> dict[str, Any]:
        recs = relabel.derived(self.state, self.base)
        return {"summary": relabel.summary(self.state, self.base),
                "windows": {w["window_index"]: {"reviewed": w["reviewed"], "concepts": w["concepts"],
                                                "added": w.get("added", []), "v2": recs[w["window_index"]]}
                            for w in self.state["windows"]}}

    def update(self, window_index: int, body: Any) -> list[str]:
        with self.lock:
            errors = relabel.update_window(self.state, self.base, window_index, body)
            if not errors:
                relabel.write_atomic(self.state_path, self.state)
            return errors


def make_relabel_handler(*, session: dict[str, Any], store: RelabelStore, video: Path):
    """GET /, /relabel.js, /api/relabel (windows with text, the frozen v1 record, the decisions and the derived v2
    record, plus a summary); PUT /api/relabel/window/<i> with {"reviewed", "concepts", "added"}; GET /video.mp4."""
    base = {r["window"]["window_index"]: r for r in store.base["windows"]}

    class Handler(JsonHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/relabel.html"):
                self._send(200, (STATIC / "relabel.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/relabel.js":
                self._send(200, (STATIC / "relabel.js").read_bytes(), "text/javascript; charset=utf-8")
            elif path == "/api/relabel":
                with store.lock:
                    view = store.view()
                windows = [{**w, "v1": base[w["window_index"]], **view["windows"][w["window_index"]]}
                           for w in session["windows"]]
                self._json(200, {**session, "windows": windows, "summary": view["summary"]})
            elif path == "/video.mp4":
                send_video(self, video)
            else:
                self._json(404, {"error": "not found"})

        def do_PUT(self) -> None:
            m = re.fullmatch(r"/api/relabel/window/(\d+)", self.path)
            if not m or int(m.group(1)) not in base:
                self._json(404, {"errors": ["no such gold window"]})
                return
            try:
                body = self._body()
            except ValueError:
                self._json(400, {"errors": ["body is not JSON"]})
                return
            errors = store.update(int(m.group(1)), body)
            if errors:
                self._json(400, {"errors": errors})
                return
            with store.lock:
                view = store.view()
            self._json(200, {"ok": True, "window": view["windows"][int(m.group(1))], "summary": view["summary"]})

    return Handler


def serve_relabel(*, port: int, session: dict[str, Any], store: RelabelStore, video: Path) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_relabel_handler(session=session, store=store, video=video))
    print(f"relabelling {session['lecture_id']} ({session['pass']}): http://127.0.0.1:{port}/  (Ctrl+C to stop)")
    print(f"decisions and the change log are saved to {store.state_path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
