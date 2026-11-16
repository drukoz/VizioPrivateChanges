"""A fake Plex Media Server over real HTTP on ``127.0.0.1``, answering through ``FakePMS``.

``tests/test_e2e_dashboard.py`` points ``dashboard serve --plex`` at ``base_url``, so
the dashboard server's real Plex transport opens real sockets to this server. Plex
paths are answered by ``FakePMS`` from ``tests/fixtures/plex/``; the transcoder
answers with ``IMAGE_BYTES``, so no test needs a real picture.
"""

from __future__ import annotations

import http.server
import threading
from typing import Any, List, Optional, Tuple

from tests.fake_pms import FakePMS

IMAGE_BYTES = b"\xff\xd8\xff\xe0fake-jpeg"

TRANSCODE_PREFIX = "/photo/:/transcode"


class _FakePlexHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method: str) -> None:
        fake = self.server.fake  # type: ignore[attr-defined]
        fake.requests.append((method, self.path))
        body = None  # type: Optional[str]
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            body = raw.decode("utf-8") if raw else None
        if self.path.startswith(TRANSCODE_PREFIX):
            return self._send(200, "image/jpeg", IMAGE_BYTES)
        response = fake.pms(method, "http://127.0.0.1" + self.path, dict(self.headers), body)
        text = response.body if response.body is not None else ""
        return self._send(response.status, "application/json", text.encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        self._route("GET")

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        self._route("POST")


class FakePlexHTTP:
    """A Plex server on an ephemeral 127.0.0.1 port; records every request path."""

    def __init__(self) -> None:
        self.pms = FakePMS()
        self.requests = []  # type: List[Tuple[str, str]]
        self.port = 0
        self._server = None  # type: Optional[http.server.ThreadingHTTPServer]

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:{}".format(self.port)

    def start(self) -> None:
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakePlexHandler)
        self._server.fake = self  # the handler reaches the fake as self.server.fake
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.port = self._server.server_address[1]

    def stop(self) -> None:
        server = self._server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        self._server = None
