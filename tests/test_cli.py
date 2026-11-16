"""Tests for the command line. They never open a socket and never read real input."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from typing import Any, Optional, Tuple
from unittest import mock

from vizio_privacy import tokenstore
from vizio_privacy.api import Response, SmartCastClient
from vizio_privacy.cast import OptOutResult
from vizio_privacy.cli import main

from tests.fakes import FakeTV, FakeTransport, ok
from tests.test_settings import V, item, tree

DEVICE_VALUE = {
    "MODEL_NAME": "D24f-J09",
    "API_VERSION": "3.3.3-2538.0001",
    "SC_INFO": "prod 59.47",
    "SETTINGS_ROOT": "tv_settings",
    "CAST_NAME": "D24f-J09 (1)",
    "INPUTS": ["CAST", "HDMI1", "HDMI2"],
    "CAPABILITIES": {"pv2": {"value": "1.0.0"}},
    "BINARIES": {"acr": "1.2.3", "s3logger": "2.0.1", "upnp": "0.9"},
    "SYSTEM_INFO": {"SERIAL_NUMBER": "SHOULD_NOT_APPEAR"},
}


def run_main(
    argv: list,
    client_factory: Optional[Any] = None,
    cast_factory: Optional[Any] = None,
) -> Tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv, client_factory=client_factory, cast_factory=cast_factory)
    return code, buffer.getvalue()


def smartcast_factory(responses: Any) -> Any:
    transport = FakeTransport(responses)

    def factory(host: str, auth_token: Optional[str] = None) -> SmartCastClient:
        return SmartCastClient(host, transport=transport, auth_token=auth_token)

    return factory


def tv_factory(tv: FakeTV) -> Any:
    def factory(host: str, auth_token: Optional[str] = None) -> SmartCastClient:
        return SmartCastClient(host, transport=tv, auth_token=auth_token)

    return factory


def device_info_response() -> Any:
    return ok([{"VALUE": DEVICE_VALUE}])


def pair_routes(method: str, url: str) -> Any:
    if url.endswith("/pairing/start"):
        return ok(None, ITEM={"CHALLENGE_TYPE": 4, "PAIRING_REQ_TOKEN": 7})
    if url.endswith("/pairing/pair"):
        return ok(None, ITEM={"AUTH_TOKEN": "SECRET_TOKEN"})
    raise AssertionError("unexpected request {} {}".format(method, url))


class FakeCast:
    def __init__(self) -> None:
        self.opt_out_calls = 0

    def opt_out(self) -> OptOutResult:
        self.opt_out_calls += 1
        return OptOutResult(
            before={"crash": True, "stats": True},
            after={"crash": False, "stats": False},
            posted_status=200,
        )


class BakingClient:
    """A client whose every call fails the way an unreachable TV does."""

    def get_device_info(self) -> Any:
        raise OSError(113, "No route to host")

    def get_items(self, path: str, auth: bool = True) -> Any:
        raise OSError(113, "No route to host")


class InfoTest(unittest.TestCase):
    def test_info_prints_model_and_telemetry_and_no_serial(self) -> None:
        code, out = run_main(
            ["--host", "127.0.0.1", "info"],
            client_factory=smartcast_factory([device_info_response()]),
        )
        self.assertEqual(code, 0)
        self.assertIn("D24f-J09", out)
        self.assertIn("acr", out)
        self.assertIn("s3logger", out)
        self.assertNotIn("upnp", out)
        self.assertNotIn("SHOULD_NOT_APPEAR", out)


class PairTest(unittest.TestCase):
    def test_pair_prompts_saves_token_and_never_prints_it(self) -> None:
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(
            os.environ, {"VIZIO_PRIVACY_HOME": home}
        ), mock.patch("builtins.input", return_value="1234") as prompt:
            code, out = run_main(
                ["--host", "127.0.0.1", "pair"],
                client_factory=smartcast_factory(pair_routes),
            )
            saved = tokenstore.load_token("127.0.0.1")
        self.assertEqual(code, 0)
        prompt.assert_called_once_with("Enter the 4-digit PIN shown on the TV: ")
        self.assertIn("Paired. Token saved to", out)
        self.assertNotIn("SECRET_TOKEN", out)
        self.assertIsNotNone(saved)
        self.assertEqual((saved or {}).get("auth_token"), "SECRET_TOKEN")


class StatusTest(unittest.TestCase):
    def test_status_prints_plan_rows(self) -> None:
        tv = FakeTV(tree())
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(
            os.environ, {"VIZIO_PRIVACY_HOME": home}
        ):
            tokenstore.save_token("127.0.0.1", "vizio-privacy", "TOK")
            code, out = run_main(
                ["--host", "127.0.0.1", "status"], client_factory=tv_factory(tv)
            )
        self.assertEqual(code, 0)
        self.assertIn(
            "WOULD_CHANGE  admin_and_privacy/viewing_data: On -> Off", out
        )
        self.assertIn(
            "WOULD_CHANGE  admin_and_privacy/advertising/limit_ad_tracking: Off -> On",
            out,
        )
        self.assertNotIn("SENTINEL", out)

    def test_status_without_a_saved_token_returns_2(self) -> None:
        def factory(host: str, auth_token: Optional[str] = None) -> Any:
            raise AssertionError("no client may be built before pairing")

        with tempfile.TemporaryDirectory() as home, mock.patch.dict(
            os.environ, {"VIZIO_PRIVACY_HOME": home}
        ):
            code, out = run_main(["--host", "127.0.0.1", "status"], client_factory=factory)
        self.assertEqual(code, 2)
        self.assertIn(
            "Not paired yet. Run: python3 -m vizio_privacy --host 127.0.0.1 pair", out
        )


class DumpTest(unittest.TestCase):
    def test_dump_hides_identifier_values(self) -> None:
        menus = tree()
        menus["admin_and_privacy"].append(
            item("tvad_id", "TVAD ID", V, "SHOULD_NOT_APPEAR", None, 99)
        )
        tv = FakeTV(menus)
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(
            os.environ, {"VIZIO_PRIVACY_HOME": home}
        ):
            tokenstore.save_token("127.0.0.1", "vizio-privacy", "TOK")
            code, out = run_main(
                ["--host", "127.0.0.1", "dump"], client_factory=tv_factory(tv)
            )
        self.assertEqual(code, 0)
        self.assertIn("admin_and_privacy/tvad_id = <hidden>  [VALUE]", out)
        self.assertNotIn("SHOULD_NOT_APPEAR", out)
        self.assertNotIn("SENTINEL", out)


class HardenTest(unittest.TestCase):
    def _tree_with_token(self, tv: FakeTV, argv: list) -> Tuple[int, str]:
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(
            os.environ, {"VIZIO_PRIVACY_HOME": home}
        ):
            tokenstore.save_token("127.0.0.1", "vizio-privacy", "TOK")
            return run_main(
                ["--host", "127.0.0.1"] + argv, client_factory=tv_factory(tv)
            )

    def test_harden_dry_run_prints_hint_and_sends_no_put(self) -> None:
        tv = FakeTV(tree())
        code, out = self._tree_with_token(tv, ["harden"])
        self.assertEqual(code, 0)
        self.assertIn("Dry run: nothing changed. Re-run with --apply to change these.", out)
        for method, _path, _body in tv.calls:
            self.assertNotEqual(method, "PUT")
        self.assertIn("WOULD_CHANGE", out)

    def test_harden_apply_prints_changed_rows_and_returns_0(self) -> None:
        tv = FakeTV(tree())
        code, out = self._tree_with_token(tv, ["harden", "--apply"])
        self.assertEqual(code, 0)
        self.assertIn("CHANGED  admin_and_privacy/viewing_data: Off -> Off", out)
        self.assertIn("CHANGED", out)
        self.assertNotIn("Dry run", out)

    def test_harden_apply_returns_1_when_a_row_failed(self) -> None:
        tv = FakeTV(tree(), refuse={"viewing_data"})
        code, out = self._tree_with_token(tv, ["harden", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("FAILED", out)


class CastOptOutTest(unittest.TestCase):
    def test_cast_optout_prints_the_summary(self) -> None:
        cast = FakeCast()
        code, out = run_main(["--host", "127.0.0.1", "cast-optout"], cast_factory=lambda host: cast)
        self.assertEqual(code, 0)
        self.assertEqual(cast.opt_out_calls, 1)
        self.assertIn("crash/stats reporting now off", out)


class GlobalFailureTest(unittest.TestCase):
    def test_missing_host_returns_2(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            code, out = run_main(["info"])
        self.assertEqual(code, 2)
        self.assertIn("--host is required (or set VIZIO_HOST)", out)

    def test_unreachable_tv_returns_1(self) -> None:
        code, out = run_main(
            ["--host", "192.0.2.5", "info"],
            client_factory=lambda host, auth_token=None: BakingClient(),
        )
        self.assertEqual(code, 1)
        self.assertIn("Cannot reach the TV at 192.0.2.5", out)
        self.assertIn("No route to host", out)

    def test_tv_error_is_reported_and_returns_1(self) -> None:
        refuse = [
            Response(
                403,
                '{"STATUS": {"RESULT": "REQUIRES_PAIRING", "DETAIL": "Pairing is required"}}',
            )
        ]
        code, out = run_main(
            ["--host", "127.0.0.1", "pair"],
            client_factory=smartcast_factory(refuse),
        )
        self.assertEqual(code, 1)
        self.assertIn("TV error: REQUIRES_PAIRING: Pairing is required", out)


if __name__ == "__main__":
    unittest.main()
