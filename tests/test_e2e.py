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
        cast_factory = lambda host: CastClient(host, port=self.tv.cast_port)
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


if __name__ == "__main__":
    unittest.main()
