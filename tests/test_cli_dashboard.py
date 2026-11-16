"""Tests for the dashboard command line. They open no socket.

``lan_address``, ``make_server``, ``_server_answers`` and ``time.sleep`` are
patched, and the TV is a ``FakeRemoteTV``; no test binds a port or reaches the
network.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

from vizio_privacy import tokenstore
from vizio_privacy.api import Response, SmartCastClient
from vizio_privacy.apps import AppId, DEFAULT_APPS
from vizio_privacy.cli import main
from vizio_privacy.dashboard.service import DashboardService
from vizio_privacy.plex_discovery import ServerInfo

from tests.fakes import FakeRemoteTV


def run_main(argv: List[str], client_factory: Optional[Any] = None) -> Tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv, client_factory=client_factory)
    return code, buffer.getvalue()


def tv_factory(tv: FakeRemoteTV) -> Any:
    def factory(host: str, auth_token: Optional[str] = None) -> SmartCastClient:
        return SmartCastClient(host, transport=tv, auth_token=auth_token)

    return factory


class FakeServer:
    """A stand-in for DashboardServer: serve_forever stops, server_close records."""

    def __init__(self) -> None:
        self.server_address = ("0.0.0.0", 8790)  # type: Tuple[str, int]
        self.serve_forever_calls = 0
        self.server_close_calls = 0

    def serve_forever(self) -> None:
        self.serve_forever_calls += 1
        raise KeyboardInterrupt()

    def server_close(self) -> None:
        self.server_close_calls += 1


class NoSwitchTV(FakeRemoteTV):
    """Answers every PUT with success and never records an app, so /app/current stays None."""

    def _put(self, path: str, body: Optional[str]) -> Response:
        return Response(200, json.dumps({"STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"}}))


@contextlib.contextmanager
def token_home(plex_url: Optional[str] = None, pop_plex: bool = False) -> Any:
    """A temporary token store, paired for 127.0.0.1; optionally set/clear VIZIO_PLEX_URL."""
    with tempfile.TemporaryDirectory() as home:
        env = {"VIZIO_PRIVACY_HOME": home}  # type: Dict[str, str]
        if plex_url is not None:
            env["VIZIO_PLEX_URL"] = plex_url
        with mock.patch.dict(os.environ, env):
            if pop_plex:
                os.environ.pop("VIZIO_PLEX_URL", None)
            tokenstore.save_token("127.0.0.1", "vizio-privacy", "TOK")
            yield


def capture_server(captured: List[Tuple[Any, str, int, FakeServer]]) -> Any:
    def make_server(service: Any, image_source: Any, host: str = "0.0.0.0",
                    port: int = 8790, static_dir: Optional[str] = None) -> FakeServer:
        server = FakeServer()
        captured.append((service, host, port, server))
        return server

    return make_server


class ServeTokenTest(unittest.TestCase):
    def test_serve_without_a_saved_token_returns_2_with_the_pair_hint(self) -> None:
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(
            os.environ, {"VIZIO_PRIVACY_HOME": home}
        ):
            def factory(host: str, auth_token: Optional[str] = None) -> Any:
                raise AssertionError("no client may be built before pairing")

            code, out = run_main(
                ["--host", "127.0.0.1", "dashboard", "serve"], client_factory=factory
            )
        self.assertEqual(code, 2)
        self.assertIn(
            "Not paired yet. Run: python3 -m vizio_privacy --host 127.0.0.1 pair", out
        )


class ServeWithPlexUrlTest(unittest.TestCase):
    def test_serve_with_plex_url_builds_service_and_stops_cleanly(self) -> None:
        tv = FakeRemoteTV()
        captured = []  # type: List[Tuple[Any, str, int, FakeServer]]
        with token_home():
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli.make_server", side_effect=capture_server(captured)):
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "serve",
                     "--plex", "http://127.0.0.1:32400"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 0)
        self.assertEqual(len(captured), 1)
        service, host, port, server = captured[0]
        self.assertEqual(host, "0.0.0.0")
        self.assertEqual(port, 8790)
        self.assertIsInstance(service, DashboardService)
        self.assertEqual(service.plex.base_url, "http://127.0.0.1:32400")
        self.assertEqual(service.apps, DEFAULT_APPS)
        self.assertIn("http://192.168.1.45:8790/", out)
        self.assertEqual(server.server_close_calls, 1)
        self.assertNotIn("TOK", out)


class ServeAppsTest(unittest.TestCase):
    def test_serve_apps_plex_youtube(self) -> None:
        tv = FakeRemoteTV()
        captured = []  # type: List[Tuple[Any, str, int, FakeServer]]
        with token_home():
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli.make_server", side_effect=capture_server(captured)):
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "serve",
                     "--plex", "http://127.0.0.1:32400", "--apps", "Plex, YouTube"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 0)
        service = captured[0][0]
        self.assertEqual(service.apps, (AppId.PLEX, AppId.YOUTUBE))

    def test_serve_unknown_app_returns_2_and_builds_no_server(self) -> None:
        tv = FakeRemoteTV()
        make_server = mock.MagicMock()
        with token_home():
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli.make_server", make_server):
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "serve",
                     "--plex", "http://127.0.0.1:32400", "--apps", "Nope"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 2)
        self.assertIn("unknown app: Nope", out)
        make_server.assert_not_called()


class ServePlexResolutionTest(unittest.TestCase):
    def test_serve_uses_env_plex_url_and_does_not_discover(self) -> None:
        tv = FakeRemoteTV()
        captured = []  # type: List[Tuple[Any, str, int, FakeServer]]
        with token_home(plex_url="http://127.0.0.1:32401"):
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli.make_server", side_effect=capture_server(captured)), \
                    mock.patch("vizio_privacy.cli.plex_discovery.discover") as discover:
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "serve"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 0)
        self.assertEqual(captured[0][0].plex.base_url, "http://127.0.0.1:32401")
        discover.assert_not_called()

    def test_serve_discovers_first_server_when_nothing_given(self) -> None:
        tv = FakeRemoteTV()
        captured = []  # type: List[Tuple[Any, str, int, FakeServer]]
        servers = [ServerInfo("127.0.0.1", 32400, "pms", "abc", "1.0")]
        with token_home(pop_plex=True):
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli.make_server", side_effect=capture_server(captured)), \
                    mock.patch("vizio_privacy.cli.plex_discovery.discover", return_value=servers) as discover:
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "serve"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 0)
        self.assertEqual(captured[0][0].plex.base_url, "http://127.0.0.1:32400")
        discover.assert_called_once()

    def test_serve_no_plex_found_returns_1_and_builds_no_server(self) -> None:
        tv = FakeRemoteTV()
        make_server = mock.MagicMock()
        with token_home(pop_plex=True):
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli.make_server", make_server), \
                    mock.patch("vizio_privacy.cli.plex_discovery.discover", return_value=[]):
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "serve"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 1)
        self.assertIn("No Plex server answered", out)
        make_server.assert_not_called()


class OpenTest(unittest.TestCase):
    def test_open_shows_dashboard_on_the_tv(self) -> None:
        tv = FakeRemoteTV()
        with token_home():
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli._server_answers", return_value=True):
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "open"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 0)
        self.assertEqual(
            tv.app,
            {"MESSAGE": "http://192.168.1.45:8790/", "NAME_SPACE": 4, "APP_ID": "1"},
        )
        self.assertIn("The TV is showing the dashboard", out)

    def test_open_launches_with_namespace_app_id_and_url(self) -> None:
        tv = FakeRemoteTV()
        with token_home():
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli._server_answers", return_value=True):
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "open",
                     "--namespace", "2", "--app-id", "3", "--url", "http://127.0.0.1:9/"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 0)
        launch = [body for method, path, body in tv.calls if method == "PUT" and path == "/app/launch"]
        self.assertEqual(len(launch), 1)
        value = json.loads(launch[0])["VALUE"]
        self.assertEqual(value["NAME_SPACE"], 2)
        self.assertEqual(value["APP_ID"], "3")
        self.assertEqual(value["MESSAGE"], "http://127.0.0.1:9/")

    def test_open_when_server_not_answering_sends_no_put(self) -> None:
        tv = FakeRemoteTV()
        with token_home():
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli._server_answers", return_value=False):
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "open"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 1)
        self.assertIn("not answering", out)
        self.assertNotIn("PUT", [method for method, _path, _body in tv.calls])

    def test_open_refused_launch_is_a_tv_error(self) -> None:
        tv = FakeRemoteTV(refuse_launch=True)
        with token_home():
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli._server_answers", return_value=True):
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "open"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 1)
        self.assertIn("TV error", out)

    def test_open_when_the_tv_does_not_switch_reports_and_retries_five_times(self) -> None:
        tv = NoSwitchTV()
        with token_home():
            with mock.patch("vizio_privacy.cli.lan_address", return_value="192.168.1.45"), \
                    mock.patch("vizio_privacy.cli._server_answers", return_value=True), \
                    mock.patch("vizio_privacy.cli.time.sleep") as sleep:
                code, out = run_main(
                    ["--host", "127.0.0.1", "dashboard", "open"],
                    client_factory=tv_factory(tv),
                )
        self.assertEqual(code, 1)
        self.assertIn("did not switch", out)
        self.assertEqual(sleep.call_count, 5)


if __name__ == "__main__":
    unittest.main()
