"""Tests for the dashboard HTTP server in vizio_privacy.dashboard.server.

The server runs on 127.0.0.1 with a temporary static folder and a fake service;
nothing here touches the TV or a Plex server.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
import urllib.parse

from vizio_privacy.dashboard.model import (
    Action,
    ActionKind,
    ActionResult,
    Home,
    ImageShape,
    Row,
    RowKind,
    Tile,
)
from vizio_privacy.dashboard.server import make_server, plex_image_source
from vizio_privacy.plex import PlexClient


class FakeService:
    def __init__(self) -> None:
        self.actions = []

    def home(self) -> Home:
        return Home(
            rows=[
                Row(
                    id="continueWatching",
                    title="Continue Watching",
                    kind=RowKind.CONTINUE_WATCHING,
                    tiles=[
                        Tile(
                            id="plex:1",
                            title="Show name",
                            subtitle="S1 \u00b7 E1 \u00b7 Episode name",
                            image="/img?p=%2Flibrary%2Fmetadata%2F1%2Fthumb%2F2&w=10&h=20",
                            shape=ImageShape.WIDE,
                            progress=0.5,
                            action=Action(ActionKind.PLAY_PLEX, "1"),
                        )
                    ],
                )
            ],
            apps=[
                Tile(
                    id="app:1",
                    title="Netflix",
                    subtitle=None,
                    image="/static/apps/1.png",
                    shape=ImageShape.ICON,
                    progress=None,
                    action=Action(ActionKind.OPEN_APP, "1"),
                )
            ],
            notices=[],
        )

    def run(self, action: Action) -> ActionResult:
        self.actions.append(action)
        if action.target == "bad":
            raise ValueError("unknown target %r" % (action.target,))
        if action.target == "boom":
            raise RuntimeError("boom")
        if action.target == "fail":
            return ActionResult(False, "TV off")
        return ActionResult(True, "Opening")


class RecordingSource:
    def __init__(self, result=None) -> None:
        self.result = result
        self.calls = []

    def __call__(self, p, w, h):
        self.calls.append((p, w, h))
        return self.result


class RecordingFetch:
    def __init__(self, status=200, content_type="image/png", body=b"jpeg", error=None):
        self.status = status
        self.content_type = content_type
        self.body = body
        self.error = error
        self.url = None

    def __call__(self, url):
        self.url = url
        if self.error is not None:
            raise self.error
        return self.status, self.content_type, self.body


class ServerTestCase(unittest.TestCase):
    source_result = ("image/jpeg", b"\xff\xd8\xff\x00\x80")

    def setUp(self) -> None:
        self.service = FakeService()
        self.source = RecordingSource(self.source_result)
        self.root = tempfile.mkdtemp()
        self.static = os.path.join(self.root, "static")
        os.mkdir(self.static)
        self.write_static("index.html", b"<html>dashboard</html>")
        self.write_static("app.js", b"console.log(1);")
        self.write_static("notes.py", b"# never served")
        with open(os.path.join(self.root, "secret.txt"), "wb") as handle:
            handle.write(b"secret")
        self.server = make_server(
            self.service,
            self.source,
            host="127.0.0.1",
            port=0,
            static_dir=self.static,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.root)

    def write_static(self, name: str, body: bytes) -> None:
        with open(os.path.join(self.static, name), "wb") as handle:
            handle.write(body)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            payload = response.read()
            return response.status, dict(response.getheaders()), payload
        finally:
            conn.close()

    def post_action(self, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        return self.request(
            "POST",
            "/api/action",
            body=body,
            headers={"Content-Type": "application/json"},
        )

    def raw_post(self, headers_block: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
            sock.sendall(
                b"POST /api/action HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                + headers_block
                + b"\r\n"
            )
            return sock.recv(4096)

    def status_line(self, response: bytes) -> str:
        return response.split(b"\r\n", 1)[0].decode("latin-1")


class ApiHomeTests(ServerTestCase):
    def test_get_api_home(self) -> None:
        status, headers, payload = self.request("GET", "/api/home")
        self.assertEqual(200, status)
        self.assertEqual(FakeService().home().to_json(), json.loads(payload))
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertEqual(str(len(payload)), headers["Content-Length"])

    def test_get_api_home_after_service_boom(self) -> None:
        self.post_action(json.dumps({"kind": 0, "target": "boom"}))
        status, _, _ = self.request("GET", "/api/home")
        self.assertEqual(200, status)


class ActionTests(ServerTestCase):
    def test_open_app_is_ok(self) -> None:
        status, headers, payload = self.post_action('{"kind": 1, "target": "1"}')
        self.assertEqual(200, status)
        self.assertEqual({"ok": True, "message": "Opening"}, json.loads(payload))
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertEqual([Action(ActionKind.OPEN_APP, "1")], self.service.actions)

    def test_bad_bodies_are_400(self) -> None:
        for body in (
            '{"kind": "1", "target": "1"}',
            '{"kind": 9, "target": "1"}',
            '{"kind": 1}',
            "not json",
            '{"kind": 1, "target": "bad"}',
        ):
            with self.subTest(body=body):
                status, headers, payload = self.post_action(body)
                self.assertEqual(400, status)
                self.assertFalse(json.loads(payload)["ok"])
                self.assertTrue(headers["Content-Type"].startswith("application/json"))
                self.assertEqual("no-store", headers["Cache-Control"])

    def test_failed_action_is_502(self) -> None:
        status, _, payload = self.post_action('{"kind": 1, "target": "fail"}')
        self.assertEqual(502, status)
        self.assertEqual({"ok": False, "message": "TV off"}, json.loads(payload))

    def test_service_crash_is_500_and_server_survives(self) -> None:
        status, headers, payload = self.post_action('{"kind": 1, "target": "boom"}')
        self.assertEqual(500, status)
        self.assertEqual({"ok": False, "message": "internal error"}, json.loads(payload))
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        status, _, _ = self.request("GET", "/api/home")
        self.assertEqual(200, status)

    def test_body_over_max_body_is_413(self) -> None:
        status, headers, payload = self.post_action('{"kind": 1, "target": "' + "x" * 5000 + '"}')
        self.assertEqual(413, status)
        self.assertFalse(json.loads(payload)["ok"])
        self.assertEqual([], self.service.actions)

    def test_missing_content_length_is_411(self) -> None:
        first = self.status_line(self.raw_post(b"Connection: close\r\n"))
        self.assertIn("411", first)

    def test_non_numeric_content_length_is_411(self) -> None:
        first = self.status_line(
            self.raw_post(b"Content-Length: abc\r\nConnection: close\r\n")
        )
        self.assertIn("411", first)

    def test_non_ascii_digit_content_length_is_411(self) -> None:
        first = self.status_line(
            self.raw_post(b"Content-Length: \xb2\r\nConnection: close\r\n")
        )
        self.assertIn("411", first)


class ImageTests(ServerTestCase):
    def test_img_serves_the_artwork(self) -> None:
        status, headers, payload = self.request(
            "GET", "/img?p=%2Flibrary%2Fmetadata%2F1%2Fthumb%2F2&w=10&h=20"
        )
        self.assertEqual(200, status)
        self.assertEqual(b"\xff\xd8\xff\x00\x80", payload)
        self.assertEqual("image/jpeg", headers["Content-Type"])
        self.assertEqual("max-age=86400", headers["Cache-Control"])
        self.assertEqual([("/library/metadata/1/thumb/2", 10, 20)], self.source.calls)

    def test_img_bad_queries_are_400(self) -> None:
        for query in ("p=%2Fetc%2Fpasswd&w=10&h=10", "w=0", "p=%2Flibrary%2F1"):
            with self.subTest(query=query):
                status, headers, payload = self.request("GET", "/img?" + query)
                self.assertEqual(400, status)
                self.assertFalse(json.loads(payload)["ok"])
                self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual([], self.source.calls)

    def test_img_without_artwork_is_502(self) -> None:
        self.source.result = None
        status, headers, payload = self.request(
            "GET", "/img?p=%2Flibrary%2Fmetadata%2F1%2Fthumb%2F2&w=10&h=20"
        )
        self.assertEqual(502, status)
        self.assertFalse(json.loads(payload)["ok"])
        self.assertTrue(headers["Content-Type"].startswith("application/json"))


class StaticTests(ServerTestCase):
    def test_index(self) -> None:
        status, headers, payload = self.request("GET", "/")
        self.assertEqual(200, status)
        self.assertEqual(b"<html>dashboard</html>", payload)
        self.assertEqual("text/html; charset=utf-8", headers["Content-Type"])

    def test_static_js(self) -> None:
        status, headers, payload = self.request("GET", "/static/app.js")
        self.assertEqual(200, status)
        self.assertEqual(b"console.log(1);", payload)
        self.assertEqual("application/javascript; charset=utf-8", headers["Content-Type"])

    def test_404_for_unserved_paths(self) -> None:
        for path in (
            "/static/notes.py",
            "/static/missing.css",
            "/static/..%2Fsecret.txt",
            "/static/%2Fetc%2Fpasswd",
            "/static/app%00.js",
            "/static/",
            "/nope",
        ):
            with self.subTest(path=path):
                status, headers, payload = self.request("GET", path)
                self.assertEqual(404, status)
                self.assertFalse(json.loads(payload)["ok"])
                self.assertTrue(headers["Content-Type"].startswith("application/json"))
                self.assertEqual("no-store", headers["Cache-Control"])

    def test_post_to_a_unknown_path_is_404(self) -> None:
        status, _, payload = self.request("POST", "/nope", body=b"{}")
        self.assertEqual(404, status)
        self.assertFalse(json.loads(payload)["ok"])

    def test_missing_index_is_404(self) -> None:
        os.remove(os.path.join(self.static, "index.html"))
        status, _, _ = self.request("GET", "/")
        self.assertEqual(404, status)


class PlexImageSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plex = PlexClient("http://plex.test:32400", token="real")
        self.p = "/library/x?X-Plex-Token=evil"

    def test_untrusted_p_cannot_add_a_parameter(self) -> None:
        fetch = RecordingFetch()
        source = plex_image_source(self.plex, fetch=fetch)
        self.assertEqual(("image/png", b"jpeg"), source(self.p, 10, 20))
        parts = urllib.parse.urlsplit(fetch.url)
        self.assertEqual("/photo/:/transcode", parts.path)
        query = urllib.parse.parse_qs(parts.query)
        self.assertEqual([self.p], query["url"])
        self.assertEqual(["real"], query["X-Plex-Token"])
        self.assertEqual(["10"], query["width"])
        self.assertEqual(["20"], query["height"])

    def test_other_status_is_none(self) -> None:
        source = plex_image_source(self.plex, fetch=RecordingFetch(status=404))
        self.assertIsNone(source(self.p, 10, 20))

    def test_os_error_is_none(self) -> None:
        source = plex_image_source(self.plex, fetch=RecordingFetch(error=OSError("down")))
        self.assertIsNone(source(self.p, 10, 20))

    def test_empty_content_type_becomes_jpeg(self) -> None:
        source = plex_image_source(self.plex, fetch=RecordingFetch(content_type=""))
        self.assertEqual(("image/jpeg", b"jpeg"), source(self.p, 10, 20))


if __name__ == "__main__":
    unittest.main()
