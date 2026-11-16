"""End-to-end tests for the dashboard: the real CLI over real sockets on 127.0.0.1.

These run ``vizio_privacy.cli.main`` with its real transports against
``tests/mock_tv.py`` (the TV) and ``tests/fake_plex_http.py`` (Plex), both bound to
``127.0.0.1`` only. ``dashboard serve`` runs in-process on a thread with ``--port 0``,
so every test uses a real dashboard server on an ephemeral port; ``dashboard open``
runs in-process too and drives the mock TV. The page (``static/``, T8) does not
exist yet, so no test asks for ``GET /``.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

from vizio_privacy import cli as cli_module
from vizio_privacy.api import SmartCastClient
from vizio_privacy.apps import DEFAULT_APPS
from vizio_privacy.cli import main
from vizio_privacy.dashboard.server import make_server
from vizio_privacy.dashboard.service import PLEX_OFFLINE_NOTICE, DashboardService
from vizio_privacy.plex import PlexClient

from tests.fake_plex_http import IMAGE_BYTES, FakePlexHTTP
from tests.fake_pms import FakePMS
from tests.mock_tv import AUTH_TOKEN, PIN, MockTV, make_certificate

CURRENT_INPUT_PATH = "/menu_native/dynamic/tv_settings/devices/current_input"
APP_TILE_IDS = ["app:0", "app:1", "app:2", "app:3", "app:4", "app:13", "app:14"]


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@unittest.skipUnless(shutil.which("openssl"), "openssl makes the mock TV's certificate")
class DashboardEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._cert_dir = tempfile.TemporaryDirectory()
        cls.cert, cls.key = make_certificate(cls._cert_dir.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._cert_dir.cleanup()

    def setUp(self) -> None:
        self.tv = MockTV(self.cert, self.key)
        self.tv.start()
        self.addCleanup(self.tv.stop)
        self.plex = FakePlexHTTP()
        self.plex.start()
        self.addCleanup(self.plex.stop)
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        env = mock.patch.dict(os.environ, {"VIZIO_PRIVACY_HOME": home.name})
        env.start()
        self.addCleanup(env.stop)
        # Both the serve thread and the main thread print here.
        self.out = io.StringIO()
        stdout = mock.patch("sys.stdout", self.out)
        stdout.start()
        self.addCleanup(stdout.stop)
        with mock.patch("builtins.input", return_value=PIN):
            self.assertEqual(self.run_cli("pair"), 0)

    # -- running the command line ------------------------------------------

    def client_factory(self, host: str, auth_token: Optional[str] = None) -> SmartCastClient:
        return SmartCastClient(host, auth_token=auth_token, port=self.tv.smartcast_port)

    def run_cli(self, *args: str) -> int:
        return main(["--host", "127.0.0.1", *args], client_factory=self.client_factory)

    def start_serve(self, plex_url: str, *extra: str) -> int:
        """Run ``dashboard serve`` in-process on a thread; return its real port."""
        ready = threading.Event()
        servers = []  # type: List[Any]
        codes = []  # type: List[int]

        def watch_make_server(*args: Any, **kwargs: Any) -> Any:
            server = make_server(*args, **kwargs)
            servers.append(server)
            ready.set()
            return server

        def serve() -> None:
            codes.append(
                main(
                    [
                        "--host", "127.0.0.1", "dashboard", "serve",
                        "--plex", plex_url, "--bind", "127.0.0.1", "--port", "0", *extra,
                    ],
                    client_factory=self.client_factory,
                )
            )

        patcher = mock.patch.object(cli_module, "make_server", watch_make_server)
        patcher.start()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.addCleanup(self._stop_serve, thread, servers, codes, patcher)
        self.assertTrue(ready.wait(10.0), "dashboard serve never built its server")
        return servers[0].server_address[1]

    def _stop_serve(self, thread: threading.Thread, servers: List[Any],
                    codes: List[int], patcher: Any) -> None:
        if servers:
            servers[0].shutdown()
        thread.join(10.0)
        self.assertFalse(thread.is_alive(), "the serve thread did not stop")
        self.assertEqual(codes, [0], "dashboard serve did not exit 0")
        patcher.stop()

    # -- talking HTTP to the dashboard server ------------------------------

    def get(self, port: int, path: str) -> Tuple[int, str, bytes]:
        request = urllib.request.Request("http://127.0.0.1:{}{}".format(port, path))
        try:
            with urllib.request.urlopen(request, timeout=10.0) as response:
                return response.status, response.headers.get("Content-Type") or "", response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.headers.get("Content-Type") or "", error.read()

    def post_json(self, port: int, path: str, obj: Any) -> Tuple[int, Any]:
        request = urllib.request.Request(
            "http://127.0.0.1:{}{}".format(port, path),
            data=json.dumps(obj).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10.0) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read().decode("utf-8"))

    def get_home(self, port: int) -> Dict[str, Any]:
        status, content_type, body = self.get(port, "/api/home")
        self.assertEqual(status, 200)
        self.assertTrue(content_type.startswith("application/json"), content_type)
        return json.loads(body.decode("utf-8"))

    # -- the home JSON ------------------------------------------------------

    def test_home_matches_the_service_built_from_the_same_fixtures(self) -> None:
        port = self.start_serve(self.plex.base_url)
        status, content_type, body = self.get(port, "/api/home")
        self.assertEqual(status, 200)
        self.assertTrue(content_type.startswith("application/json"), content_type)
        payload = json.loads(body.decode("utf-8"))
        service = DashboardService(
            PlexClient("http://plex.invalid", transport=FakePMS()), None, apps=DEFAULT_APPS
        )
        self.assertEqual(payload, json.loads(json.dumps(service.home().to_json())))

        self.assertEqual(payload["version"], 1)
        rows = payload["rows"]
        self.assertEqual(rows[0]["id"], "continueWatching")
        self.assertEqual(rows[0]["kind"], 0)
        for row in rows[1:]:
            self.assertEqual(row["kind"], 1)
        self.assertLessEqual(len(rows), 8)
        for row in rows:
            for tile in row["tiles"]:
                self.assertEqual(tile["action"]["kind"], 0, tile["id"])
                target = tile["action"]["target"]
                self.assertTrue(target.isascii() and target.isdigit(), tile["id"])
                # None is allowed by the contract: Plex has no servable picture for it.
                self.assertTrue(
                    tile["image"] is None or tile["image"].startswith("/img?p="), tile["id"]
                )
        self.assertEqual([tile["id"] for tile in payload["apps"]], APP_TILE_IDS)
        self.assertEqual(payload["notices"], [])
        seen = [(method, path) for method, path in self.plex.requests]
        self.assertTrue(
            any(method == "GET" and path.startswith("/hubs/continueWatching?")
                for method, path in seen),
            seen,
        )
        self.assertIn(("GET", "/library/sections"), seen)

    def test_apps_option_sets_the_app_row(self) -> None:
        port = self.start_serve(self.plex.base_url, "--apps", "Plex,YouTube")
        payload = self.get_home(port)
        self.assertEqual([tile["id"] for tile in payload["apps"]], ["app:0", "app:2"])

    def test_plex_down_shows_apps_and_a_notice(self) -> None:
        port = self.start_serve("http://127.0.0.1:{}".format(closed_port()))
        payload = self.get_home(port)
        self.assertEqual(payload["rows"], [])
        self.assertEqual([tile["id"] for tile in payload["apps"]], APP_TILE_IDS)
        self.assertEqual(payload["notices"], [PLEX_OFFLINE_NOTICE])

    # -- the artwork proxy --------------------------------------------------

    def test_artwork_is_fetched_from_plex(self) -> None:
        port = self.start_serve(self.plex.base_url)
        rows = self.get_home(port)["rows"]
        image = rows[0]["tiles"][0]["image"]
        self.assertTrue(image.startswith("/img?p="), image)
        p = urllib.parse.parse_qs(urllib.parse.urlsplit(image).query)["p"][0]

        status, content_type, body = self.get(port, image)
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(body, IMAGE_BYTES)

        method, path = self.plex.requests[-1]
        self.assertEqual(method, "GET")
        self.assertTrue(path.startswith("/photo/:/transcode?"), path)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        self.assertEqual(query["url"], [p])
        self.assertNotIn("X-Plex-Token", query)

    def test_artwork_path_cannot_add_plex_parameters(self) -> None:
        port = self.start_serve(self.plex.base_url)
        smuggled = "/library/x?X-Plex-Token=evil&width=9"
        status, _content_type, body = self.get(
            port, "/img?p=" + urllib.parse.quote(smuggled, safe="") + "&w=10&h=10"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, IMAGE_BYTES)
        method, path = self.plex.requests[-1]
        self.assertEqual(method, "GET")
        self.assertTrue(path.startswith("/photo/:/transcode?"), path)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        self.assertEqual(query["url"], [smuggled])
        self.assertEqual(query["width"], ["10"])
        self.assertNotIn("X-Plex-Token", query)

    # -- actions ------------------------------------------------------------

    def test_actions_reach_the_tv(self) -> None:
        port = self.start_serve(self.plex.base_url)

        status, payload = self.post_json(port, "/api/action", {"kind": 1, "target": "1"})
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "message": "Opening Netflix"})
        self.assertEqual(self.tv.launches[-1], {"MESSAGE": None, "NAME_SPACE": 3, "APP_ID": "1"})

        status, payload = self.post_json(port, "/api/action", {"kind": 0, "target": "4617"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "Opening Plex")
        self.assertEqual(self.tv.launches[-1]["NAME_SPACE"], 2)
        self.assertEqual(self.tv.launches[-1]["APP_ID"], "9")

        status, payload = self.post_json(port, "/api/action", {"kind": 3, "target": "14"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            self.tv.launches[-1],
            {"MESSAGE": "http://127.0.0.1:12345/scfs/sctv/main.html",
             "NAME_SPACE": 4, "APP_ID": "1"},
        )

        status, payload = self.post_json(port, "/api/action", {"kind": 2, "target": "13"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "Switching to Fire TV Stick")
        self.assertEqual(self.tv.current_input[0], "HDMI-2")
        self.assertIn(
            ("PUT", CURRENT_INPUT_PATH, {"AUTH": AUTH_TOKEN, "Content-Type": "application/json"},
             {"REQUEST": "MODIFY", "VALUE": "HDMI-2", "HASHVAL": 2023834057}),
            self.tv.requests,
        )

        for method, path, headers, _body in self.tv.requests:
            if path in ("/app/current", "/app/launch", CURRENT_INPUT_PATH):
                self.assertEqual(headers["AUTH"], AUTH_TOKEN, (method, path))

    def test_bad_actions_are_400_and_touch_nothing(self) -> None:
        port = self.start_serve(self.plex.base_url)
        for action in (
            {"kind": 9, "target": "1"},
            {"kind": 1},
            {"kind": 1, "target": "5"},
        ):
            status, payload = self.post_json(port, "/api/action", action)
            self.assertEqual(status, 400, action)
            self.assertFalse(payload["ok"], action)
        self.assertEqual(self.tv.launches, [])

    def test_tv_error_on_an_action_is_502(self) -> None:
        port = self.start_serve(self.plex.base_url)
        self.tv.token_valid = False
        status, payload = self.post_json(port, "/api/action", {"kind": 1, "target": "1"})
        self.assertEqual(status, 502)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["message"].startswith("The TV did not respond"), payload)

    # -- dashboard open -----------------------------------------------------

    def test_open_shows_the_dashboard(self) -> None:
        port = self.start_serve(self.plex.base_url)
        self.assertEqual(self.run_cli("dashboard", "open", "--port", str(port)), 0)
        url = "http://127.0.0.1:{}/".format(port)
        self.assertIn("The TV is showing the dashboard ({}).".format(url), self.out.getvalue())
        self.assertEqual(
            self.tv.launches, [{"MESSAGE": url, "NAME_SPACE": 4, "APP_ID": "1"}]
        )

    def test_open_namespace_option_is_sent(self) -> None:
        port = self.start_serve(self.plex.base_url)
        code = self.run_cli("dashboard", "open", "--port", str(port), "--namespace", "2")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.tv.launches), 1)
        self.assertEqual(self.tv.launches[0]["NAME_SPACE"], 2)

    def test_open_reports_when_the_tv_does_not_switch(self) -> None:
        port = self.start_serve(self.plex.base_url)
        self.tv.launch_switches = False
        with mock.patch("vizio_privacy.cli.time.sleep", lambda _seconds: None):
            code = self.run_cli("dashboard", "open", "--port", str(port))
        self.assertEqual(code, 1)
        self.assertIn(
            "It reports: NAME_SPACE 345 APP_ID 707 MESSAGE dtv-system://power",
            self.out.getvalue(),
        )
        self.assertEqual(len(self.tv.launches), 1)
        self.assertEqual(
            5, sum(1 for method, path, _h, _b in self.tv.requests
                   if method == "GET" and path == "/app/current")
        )

    def test_open_without_a_server_launches_nothing(self) -> None:
        url = "http://127.0.0.1:{}/".format(closed_port())
        code = self.run_cli("dashboard", "open", "--url", url)
        self.assertEqual(code, 1)
        self.assertIn("The dashboard server is not answering at", self.out.getvalue())
        self.assertEqual(self.tv.launches, [])
        for _method, path, _headers, _body in self.tv.requests:
            self.assertNotEqual(path, "/app/launch")


if __name__ == "__main__":
    unittest.main()
