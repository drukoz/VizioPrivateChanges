"""The dashboard HTTP server: the page's files, /api/home, /api/action and /img.

Contract: docs/dashboard/plan.md, section "Contract: page <-> server".
The service is any object with home() -> Home and run(action) -> ActionResult;
this module never imports dashboard/service.py.
"""

from __future__ import annotations

import http.client
import http.server
import json
import logging
import os
import urllib.parse
from typing import Any, Callable, Dict, Optional, Tuple

from vizio_privacy.dashboard.model import Action, parse_image_query
from vizio_privacy.plex import PlexClient

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 4096
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
}

# (p, w, h) -> (content type, body), or None when the artwork is not available.
ImageSource = Callable[[str, int, int], Optional[Tuple[str, bytes]]]

_JSON = "application/json; charset=utf-8"
_NO_STORE = "no-store"

logger = logging.getLogger(__name__)


def http_fetch(url: str, timeout: float = 8.0) -> Tuple[int, str, bytes]:
    """GET over http.client; returns (status, Content-Type header or "", body bytes)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            parts.netloc, timeout=timeout
        )
    else:
        conn = http.client.HTTPConnection(parts.netloc, timeout=timeout)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    try:
        conn.request("GET", target, headers={"Accept": "*/*"})
        response = conn.getresponse()
        body = response.read()
        return response.status, response.getheader("Content-Type") or "", body
    finally:
        conn.close()


def plex_image_source(
    plex: PlexClient,
    fetch: Callable[[str], Tuple[int, str, bytes]] = http_fetch,
) -> ImageSource:
    """An ImageSource that fetches artwork from Plex through its own binary fetch.

    p is untrusted: it is handed to plex.image_url, which percent-encodes all of
    it as one value of the transcoder's url parameter and adds the token itself.
    """

    def source(p: str, w: int, h: int) -> Optional[Tuple[str, bytes]]:
        try:
            status, content_type, body = fetch(plex.image_url(p, w, h))
        except OSError:
            return None
        if status != 200:
            return None
        return (content_type or "image/jpeg", body)

    return source


class DashboardServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: Tuple[str, int],
        service: Any,
        image_source: ImageSource,
        static_dir: str = STATIC_DIR,
    ) -> None:
        super().__init__(address, DashboardHandler)
        self.service = service
        self.image_source = image_source
        self.static_dir = static_dir


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info(fmt, *args)

    # -- responses ---------------------------------------------------------

    def _respond(
        self,
        status: int,
        body: bytes,
        content_type: str,
        cache_control: Optional[str] = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._respond(status, body, _JSON, _NO_STORE)

    def _send_fail(self, status: int, message: str) -> None:
        self._send_json(status, {"ok": False, "message": message})

    def _fail_internal(self) -> None:
        logger.exception("dashboard request failed")
        try:
            self._send_fail(500, "internal error")
        except OSError:
            pass

    # -- GET ---------------------------------------------------------------

    def do_GET(self) -> None:
        parts = urllib.parse.urlsplit(self.path)
        try:
            if parts.path == "/":
                self._serve_index()
            elif parts.path == "/api/home":
                self._serve_home()
            elif parts.path == "/img":
                self._serve_image(parts.query)
            elif parts.path.startswith("/static/"):
                self._serve_static(parts.path[len("/static/"):])
            else:
                self._send_fail(404, "not found")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self._fail_internal()

    def _serve_index(self) -> None:
        index = os.path.join(self.server.static_dir, "index.html")
        if not os.path.isfile(index):
            self._send_fail(404, "not found")
            return
        with open(index, "rb") as handle:
            body = handle.read()
        self._respond(200, body, CONTENT_TYPES[".html"])

    def _serve_home(self) -> None:
        try:
            home = self.server.service.home()
        except (BrokenPipeError, ConnectionResetError):
            raise
        except Exception:
            self._fail_internal()
            return
        self._send_json(200, home.to_json())

    def _serve_static(self, raw_rel: str) -> None:
        rel = urllib.parse.unquote(raw_rel)
        if not os.path.isdir(self.server.static_dir):
            self._send_fail(404, "not found")
            return
        root = os.path.realpath(self.server.static_dir) + os.sep
        resolved = os.path.realpath(os.path.join(self.server.static_dir, rel))
        if (
            not rel
            or rel.startswith("/")
            or "\\" in rel
            or any(part == ".." for part in rel.split("/"))
            or not resolved.startswith(root)
            or not os.path.isfile(resolved)
            or os.path.splitext(rel)[1].lower() not in CONTENT_TYPES
        ):
            self._send_fail(404, "not found")
            return
        with open(resolved, "rb") as handle:
            body = handle.read()
        self._respond(
            200, body, CONTENT_TYPES[os.path.splitext(rel)[1].lower()]
        )

    def _serve_image(self, query: str) -> None:
        try:
            p, w, h = parse_image_query(query)
        except ValueError:
            self._send_fail(400, "bad image query")
            return
        result = self.server.image_source(p, w, h)
        if result is None:
            self._send_fail(502, "image not available")
            return
        content_type, body = result
        self._respond(200, body, content_type, "max-age=86400")

    # -- POST --------------------------------------------------------------

    def do_POST(self) -> None:
        parts = urllib.parse.urlsplit(self.path)
        if parts.path != "/api/action":
            self._send_fail(404, "not found")
            return
        try:
            self._handle_action()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self._fail_internal()

    def _handle_action(self) -> None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or not raw_length.isdigit():
            self._send_fail(411, "Content-Length required")
            return
        length = int(raw_length)
        if length > MAX_BODY:
            self._send_fail(413, "body too large")
            return
        try:
            raw = self.rfile.read(length) if length else b""
        except OSError:
            return
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            self._send_fail(400, "body must be UTF-8 JSON")
            return
        try:
            action = Action.from_json(data)
        except ValueError as exc:
            self._send_fail(400, str(exc))
            return
        try:
            result = self.server.service.run(action)
        except ValueError as exc:
            self._send_fail(400, str(exc))
            return
        except Exception:
            self._fail_internal()
            return
        self._send_json(200 if result.ok else 502, result.to_json())


def make_server(
    service: Any,
    image_source: ImageSource,
    host: str = "0.0.0.0",
    port: int = 8790,
    static_dir: Optional[str] = None,
) -> DashboardServer:
    directory = STATIC_DIR if static_dir is None else static_dir
    return DashboardServer((host, port), service, image_source, directory)
