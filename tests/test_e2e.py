"""End-to-end tests: the real CLI over real HTTP(S) against a mock TV.

These run ``vizio_privacy.cli.main`` with its real ``default_transport``
sockets against ``tests/mock_tv.py`` on ``127.0.0.1`` only. The factories
change nothing but the port, so the real HTTPS/HTTP code paths are exercised.
Part 1 covers ``info``, ``pair`` and ``status``.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import socket
import stat
import tempfile
import unittest
from typing import Any, Optional, Tuple
from unittest import mock

from vizio_privacy import tokenstore
from vizio_privacy.api import SmartCastClient
from vizio_privacy.cast import CastClient
from vizio_privacy.cli import main

from tests.mock_tv import (
    AUTH_TOKEN,
    MAC,
    PAIR_BODY,
    PIN,
    SERIAL,
    TVAD,
    MockTV,
    make_certificate,
)


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@unittest.skipUnless(shutil.which("openssl"), "openssl makes the mock TV's certificate")
class EndToEndTest(unittest.TestCase):
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
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        patcher = mock.patch.dict(os.environ, {"VIZIO_PRIVACY_HOME": home.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(
        self, *args: str, pin: str = "", port: Optional[int] = None
    ) -> Tuple[int, str]:
        smartcast_port = self.tv.smartcast_port if port is None else port
        client_factory = lambda host, auth_token=None: SmartCastClient(
            host, auth_token=auth_token, port=smartcast_port
        )
        cast_factory = lambda host: CastClient(
            host, port=self.tv.cast_port, secure_port=self.tv.cast_secure_port
        )
        buffer = io.StringIO()
        with mock.patch("builtins.input", return_value=pin), contextlib.redirect_stdout(buffer):
            code = main(
                ["--host", "127.0.0.1", *args],
                client_factory=client_factory,
                cast_factory=cast_factory,
            )
        return code, buffer.getvalue()

    def pair(self) -> None:
        code, _out = self.run_cli("pair", pin=PIN)
        self.assertEqual(code, 0)

    def test_info_over_https(self) -> None:
        code, out = self.run_cli("info")
        self.assertEqual(code, 0)
        for line in (
            "model: D24f-J09",
            "api version: 3.3.3",
            "sc_info: prod 59.47",
            "cast name: Living Room",
            "inputs: 2",
            "telemetry components: acr, s3logger",
        ):
            self.assertIn(line, out)
        self.assertNotIn(SERIAL, out)
        self.assertNotIn(TVAD, out)

    def test_status_before_pairing_says_not_paired(self) -> None:
        code, out = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn(
            "Not paired yet. Run: python3 -m vizio_privacy --host 127.0.0.1 pair", out
        )
        for _method, path, _headers, _body in self.tv.requests:
            self.assertFalse(path.startswith("/menu_native/"))

    def test_pair_saves_an_owner_only_token(self) -> None:
        code, out = self.run_cli("pair", pin=PIN)
        self.assertEqual(code, 0)
        self.assertIn("Paired. Token saved to", out)
        self.assertNotIn(AUTH_TOKEN, out)
        path = tokenstore.token_path("127.0.0.1")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)
        self.assertEqual(tokenstore.load_token("127.0.0.1")["auth_token"], AUTH_TOKEN)
        bodies = [
            body
            for method, req_path, _headers, body in self.tv.requests
            if method == "PUT" and req_path == "/pairing/pair"
        ]
        self.assertEqual(bodies, [PAIR_BODY])

    def test_pair_with_a_wrong_pin_saves_nothing(self) -> None:
        code, out = self.run_cli("pair", pin="0000")
        self.assertEqual(code, 1)
        self.assertIn("TV error: UNKNOWN: Incorrect PIN", out)
        self.assertFalse(os.path.exists(tokenstore.token_path("127.0.0.1")))

    def test_rejected_token_prints_the_pair_hint(self) -> None:
        self.pair()
        self.tv.token_valid = False
        code, out = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertIn("TV error: REQUIRES_PAIRING: Pairing is required", out)
        self.assertIn(
            "The TV no longer accepts the saved pairing. "
            "Run: python3 -m vizio_privacy --host 127.0.0.1 pair",
            out,
        )

    def test_unreachable_tv(self) -> None:
        code, out = self.run_cli("info", port=closed_port())
        self.assertEqual(code, 1)
        self.assertIn("Cannot reach the TV at 127.0.0.1", out)

    def test_dump_reads_the_tree_and_never_opens_system_information(self) -> None:
        self.pair()
        code, out = self.run_cli("dump")
        self.assertEqual(code, 0)
        for line in (
            "picture/picture_mode = Calibrated  [LIST]",
            "admin_and_privacy/viewing_data = On  [LIST]",
            "admin_and_privacy/advertising/limit_ad_tracking = Off  [LIST]",
            "Could not read menu system/broken: URI_NOT_FOUND: No such menu",
        ):
            self.assertIn(line, out)
        for _method, path, _headers, _body in self.tv.requests:
            self.assertNotIn("system_information", path)
        self.assertNotIn(SERIAL, out)

    def test_harden_dry_run_plans_and_writes_nothing(self) -> None:
        self.pair()
        code, out = self.run_cli("harden")
        self.assertEqual(code, 0)
        for line in (
            "WOULD_CHANGE  admin_and_privacy/viewing_data: On -> Off"
            "  (Viewing Data: ACR / Inscape content recognition)",
            "WOULD_CHANGE  admin_and_privacy/advertising/limit_ad_tracking:"
            " Off -> On  (ad tracking)",
            "NOT_A_LIST  admin_and_privacy/advertising/reset_advertising_id:"
            " - -> -  (advertising)",
            "Could not read menu system/broken: URI_NOT_FOUND: No such menu",
            "WOULD_CHANGE: 2, NOT_A_LIST: 1",
            "Dry run: nothing changed. Re-run with --apply to change these.",
        ):
            self.assertIn(line, out)
        get_paths = [
            path
            for method, path, _headers, _body in self.tv.requests
            if method == "GET"
        ]
        for method, path, _headers, _body in self.tv.requests:
            if method == "PUT":
                self.assertFalse(path.startswith("/menu_native/"))
        self.assertIn("/menu_native/static/tv_settings/admin_and_privacy", get_paths)
        self.assertIn(
            "/menu_native/static/tv_settings/admin_and_privacy/advertising", get_paths
        )
        self.assertEqual(
            self.tv.values,
            {
                "picture/picture_mode": ["Calibrated", 303],
                "admin_and_privacy/viewing_data": ["On", 101],
                "admin_and_privacy/advertising/limit_ad_tracking": ["Off", 202],
            },
        )

    def test_harden_apply_changes_both_and_reads_back(self) -> None:
        self.pair()
        code, out = self.run_cli("harden", "--apply")
        self.assertEqual(code, 0)
        for line in (
            "CHANGED  admin_and_privacy/viewing_data: On -> Off"
            "  (Viewing Data: ACR / Inscape content recognition)",
            "CHANGED  admin_and_privacy/advertising/limit_ad_tracking:"
            " Off -> On  (ad tracking)",
            "NOT_A_LIST  admin_and_privacy/advertising/reset_advertising_id:"
            " - -> -  (advertising)",
            "Could not read menu system/broken: URI_NOT_FOUND: No such menu",
            "CHANGED: 2, NOT_A_LIST: 1",
        ):
            self.assertIn(line, out)
        self.assertNotIn("Dry run", out)
        self.assertEqual(
            self.tv.values,
            {
                "picture/picture_mode": ["Calibrated", 303],
                "admin_and_privacy/viewing_data": ["Off", 102],
                "admin_and_privacy/advertising/limit_ad_tracking": ["On", 203],
            },
        )
        headers = {"AUTH": AUTH_TOKEN, "Content-Type": "application/json"}
        native_puts = [
            (method, path, hdrs, body)
            for method, path, hdrs, body in self.tv.requests
            if method == "PUT" and path.startswith("/menu_native/")
        ]
        self.assertEqual(
            native_puts,
            [
                (
                    "PUT",
                    "/menu_native/dynamic/tv_settings/admin_and_privacy/viewing_data",
                    headers,
                    {"REQUEST": "MODIFY", "HASHVAL": 101, "VALUE": "Off"},
                ),
                (
                    "PUT",
                    "/menu_native/dynamic/tv_settings/admin_and_privacy/advertising"
                    "/limit_ad_tracking",
                    headers,
                    {"REQUEST": "MODIFY", "HASHVAL": 202, "VALUE": "On"},
                ),
            ],
        )

    def native_put_count(self) -> int:
        return sum(
            1
            for method, path, _headers, _body in self.tv.requests
            if method == "PUT" and path.startswith("/menu_native/")
        )

    def test_second_apply_finds_everything_private(self) -> None:
        self.pair()
        first, _out = self.run_cli("harden", "--apply")
        self.assertEqual(first, 0)
        puts_before = self.native_put_count()
        code, out = self.run_cli("harden", "--apply")
        self.assertEqual(code, 0)
        for line in (
            "ALREADY_PRIVATE  admin_and_privacy/viewing_data: Off -> Off"
            "  (Viewing Data: ACR / Inscape content recognition)",
            "ALREADY_PRIVATE  admin_and_privacy/advertising/limit_ad_tracking:"
            " On -> On  (ad tracking)",
            "ALREADY_PRIVATE: 2, NOT_A_LIST: 1",
        ):
            self.assertIn(line, out)
        self.assertEqual(self.native_put_count(), puts_before)

    def test_refused_write_is_reported_and_exits_1(self) -> None:
        self.pair()
        self.tv.refuse_writes = True
        code, out = self.run_cli("harden", "--apply")
        self.assertEqual(code, 1)
        for line in (
            "FAILED  admin_and_privacy/viewing_data: On -> Off"
            "  (Viewing Data: ACR / Inscape content recognition)",
            "  INVALID_PARAMETER: Refused",
            "FAILED  admin_and_privacy/advertising/limit_ad_tracking:"
            " Off -> On  (ad tracking)",
            "  INVALID_PARAMETER: Refused",
            "NOT_A_LIST: 1, FAILED: 2",
        ):
            self.assertIn(line, out)
        self.assertEqual(
            self.tv.values,
            {
                "picture/picture_mode": ["Calibrated", 303],
                "admin_and_privacy/viewing_data": ["On", 101],
                "admin_and_privacy/advertising/limit_ad_tracking": ["Off", 202],
            },
        )

    def test_ignored_write_is_reported_and_exits_1(self) -> None:
        self.pair()
        self.tv.ignore_writes = True
        code, out = self.run_cli("harden", "--apply")
        self.assertEqual(code, 1)
        for line in (
            "FAILED  admin_and_privacy/viewing_data: On -> Off"
            "  (Viewing Data: ACR / Inscape content recognition)",
            "  TV still reports On",
            "FAILED  admin_and_privacy/advertising/limit_ad_tracking:"
            " Off -> On  (ad tracking)",
            "  TV still reports Off",
            "NOT_A_LIST: 1, FAILED: 2",
        ):
            self.assertIn(line, out)
        self.assertEqual(
            self.tv.values,
            {
                "picture/picture_mode": ["Calibrated", 303],
                "admin_and_privacy/viewing_data": ["On", 101],
                "admin_and_privacy/advertising/limit_ad_tracking": ["Off", 202],
            },
        )

    def test_cast_optout_turns_reporting_off(self) -> None:
        code, out = self.run_cli("cast-optout")
        self.assertEqual(code, 0)
        self.assertIn("crash/stats reporting now off", out)
        self.assertEqual(self.tv.opt_in, {"crash": False, "opencast": False, "stats": False})
        self.assertEqual(
            self.tv.cast_secure_requests,
            [("POST", "/setup/set_eureka_info", {"opt_in": {"crash": False, "stats": False}})],
        )
        plain_posts = [method for method, _path, _body in self.tv.cast_requests if method == "POST"]
        self.assertEqual(plain_posts, [])
        self.assertNotIn(MAC, out)

    def test_cast_optout_reports_an_ignored_write(self) -> None:
        self.tv.cast_applies_writes = False
        code, out = self.run_cli("cast-optout")
        self.assertEqual(code, 1)
        self.assertIn("TV did not apply the change (status 200); crash=on stats=on", out)
        self.assertEqual(self.tv.opt_in, {"crash": True, "opencast": False, "stats": True})


if __name__ == "__main__":
    unittest.main()
