"""Tests for the dashboard page: static/index.html, app.css and app.js.

The server runs on 127.0.0.1 against the real static folder; nothing here
touches the TV or a Plex server. The JS helpers run under node only.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import subprocess
import threading
import unittest

import vizio_privacy.dashboard.server
from vizio_privacy.dashboard.model import ImageShape
from vizio_privacy.dashboard.server import make_server

STATIC = os.path.join(os.path.dirname(vizio_privacy.dashboard.server.__file__), "static")

FORBIDDEN = [
    r"=>",
    r"`",
    r"\blet\s",
    r"\bconst\s",
    r"\bclass\s",
    r"\bfetch\s*\(",
    r"\bPromise\b",
    r"\basync\b",
    r"\bawait\b",
    r"\.\.\.",
    r"\?\.",
    r"\?\?",
    r"\.includes\(",
    r"\.find\(",
    r"\.closest\(",
    r"Object\.assign",
    r"\binnerHTML\b",
    r"\.append\(",
    r"\.remove\(",
]


def _no_image(p, w, h):
    return None


class _AnyService:
    """Any object: no route under test (/, /static) calls the service."""

    def home(self):
        raise AssertionError("home() must not be called by the page tests")

    def run(self, action):
        raise AssertionError("run() must not be called by the page tests")


class PageFileTests(unittest.TestCase):
    def read_js(self):
        with open(os.path.join(STATIC, "app.js"), "r", encoding="utf-8") as handle:
            return handle.read()

    def test_files_exist(self) -> None:
        for name in ("index.html", "app.css", "app.js"):
            self.assertTrue(
                os.path.isfile(os.path.join(STATIC, name)),
                "missing %s" % name,
            )

    def test_app_js_is_es5(self) -> None:
        source = self.read_js()
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        source = re.sub(r"//[^\n]*", "", source)
        for pattern in FORBIDDEN:
            match = re.search(pattern, source)
            self.assertIsNone(
                match,
                "forbidden pattern %r matched: %r"
                % (pattern, match.group(0) if match else ""),
            )


class ServerServesPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = make_server(
            _AnyService(), _no_image, host="127.0.0.1", port=0
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_server_serves_the_page(self) -> None:
        status, headers, body = self.get("/")
        self.assertEqual(200, status)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        text = body.decode("utf-8")
        self.assertIn("/static/app.js", text)
        self.assertIn("/static/app.css", text)

        status, headers, _ = self.get("/static/app.js")
        self.assertEqual(200, status)
        self.assertTrue(headers["Content-Type"].startswith("application/javascript"))

        status, headers, _ = self.get("/static/app.css")
        self.assertEqual(200, status)
        self.assertTrue(headers["Content-Type"].startswith("text/css"))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class NodeTests(unittest.TestCase):
    def run_node(self, js):
        result = subprocess.run(
            ["node", "-e", js], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def script(self, body):
        app = os.path.join(STATIC, "app.js")
        return "var m = require(%s);\n%s\nconsole.log(JSON.stringify(out));" % (
            json.dumps(app),
            body,
        )

    def test_node_check(self) -> None:
        app = os.path.join(STATIC, "app.js")
        result = subprocess.run(
            ["node", "--check", app], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_shape_classes_match_model(self) -> None:
        data = self.run_node(
            self.script("var out = {shapes: m.SHAPE_CLASSES, dir: m.DIR};")
        )
        expected = [s.name.lower() for s in sorted(ImageShape, key=int)]
        self.assertEqual(expected, data["shapes"])
        self.assertEqual({"LEFT": 0, "RIGHT": 1, "UP": 2, "DOWN": 3}, data["dir"])

    def test_next_position(self) -> None:
        js = self.script(
            "var lengths = [3, 5, 2];\n"
            "var lastCol = [-1, -1, -1];\n"
            "var seq = [[[0,0],0],[[0,0],1],[[0,2],1],[[0,1],2],"
            "[[0,2],3],[[1,4],3],[[2,1],2],[[1,4],2]];\n"
            "var out = [];\n"
            "for (var i = 0; i < seq.length; i++) {\n"
            "  var p = {line: seq[i][0][0], col: seq[i][0][1]};\n"
            "  var r = m.nextPosition(lengths, p, lastCol, seq[i][1]);\n"
            "  out.push([r.line, r.col]);\n"
            "}\n"
            "out.push(lastCol);"
        )
        self.assertEqual(
            [[0, 0], [0, 1], [0, 2], [0, 1], [1, 2], [2, 1], [1, 4], [0, 2], [2, 4, 1]],
            self.run_node(js),
        )

    def test_scroll_for(self) -> None:
        js = self.script(
            "var out = [m.scrollFor(0, 20, 30, 100, 10), m.scrollFor(0, 80, 30, 100, 10),"
            " m.scrollFor(50, 30, 30, 100, 10), m.scrollFor(50, 5, 30, 100, 10)];"
        )
        self.assertEqual([0, 20, 20, 0], self.run_node(js))

    def test_find_tile(self) -> None:
        js = self.script(
            "var lines = [{title: 'x', tiles: [{id: 'a'}, {id: 'b'}]},"
            " {title: 'y', tiles: [{id: 'c'}]}];\n"
            "var out = [m.findTile(lines, 'c'), m.findTile(lines, 'zz')];"
        )
        self.assertEqual([{"line": 1, "col": 0}, None], self.run_node(js))

    def test_build_lines(self) -> None:
        js = self.script(
            "var home = {rows: [{title: 'CW', tiles: [{id: 't1'}]},"
            " {title: 'Empty', tiles: []}], apps: [{id: 'a1'}], notices: []};\n"
            "var full = m.buildLines(home);\n"
            "home.apps = [];\n"
            "var out = {full: full, appsEmpty: m.buildLines(home)};"
        )
        data = self.run_node(js)
        self.assertEqual(
            [
                {"title": "CW", "tiles": [{"id": "t1"}]},
                {"title": "Apps", "tiles": [{"id": "a1"}]},
            ],
            data["full"],
        )
        self.assertEqual([{"title": "CW", "tiles": [{"id": "t1"}]}], data["appsEmpty"])


if __name__ == "__main__":
    unittest.main()
