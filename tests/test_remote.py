"""Tests for the dashboard control calls (power, app, keys, inputs). No sockets."""

from __future__ import annotations

import json
import unittest
from typing import Dict, List, Optional, Tuple

from vizio_privacy.api import (
    AppConfig,
    InputInfo,
    InputState,
    KEY_CODES,
    PowerState,
    RemoteKey,
    Response,
    ResultStatus,
    SmartCastClient,
    SmartCastError,
)
from tests.fakes import FakeRemoteTV, FakeTransport, load_tv_fixture

TOKEN = "test-token"
HOST = "192.0.2.1"
STANDBY_APP = {"APP_ID": "707", "NAME_SPACE": 345, "MESSAGE": "dtv-system://power"}


def make_client(tv) -> SmartCastClient:
    return SmartCastClient(HOST, transport=tv, auth_token=TOKEN)


class PowerStateTests(unittest.TestCase):
    def test_standby_by_default(self) -> None:
        self.assertEqual(make_client(FakeRemoteTV()).power_state(), PowerState.STANDBY)

    def test_on(self) -> None:
        self.assertEqual(make_client(FakeRemoteTV(power=1)).power_state(), PowerState.ON)

    def test_unknown_when_value_missing(self) -> None:
        body = {
            "STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"},
            "ITEMS": [{"CNAME": "power_mode", "TYPE": "T_VALUE_V1"}],
        }
        transport = FakeTransport([Response(200, json.dumps(body))])
        self.assertEqual(make_client(transport).power_state(), PowerState.UNKNOWN)

    def test_uses_auth(self) -> None:
        seen = []  # type: List[Dict[str, str]]

        def transport(method, url, headers, body):
            seen.append(dict(headers))
            return FakeRemoteTV()(method, url, headers, body)

        make_client(transport).power_state()
        self.assertEqual(seen[0].get("AUTH"), TOKEN)


class CurrentAppTests(unittest.TestCase):
    def test_standby_app(self) -> None:
        client = make_client(FakeRemoteTV(app=dict(STANDBY_APP)))
        self.assertEqual(client.current_app(), AppConfig(345, "707", "dtv-system://power"))

    def test_none_when_value_null(self) -> None:
        self.assertIsNone(make_client(FakeRemoteTV()).current_app())

    def test_none_when_item_missing(self) -> None:
        body = {"STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"}, "URI": "/app/current"}
        transport = FakeTransport([Response(200, json.dumps(body))])
        self.assertIsNone(make_client(transport).current_app())


class AppConfigTests(unittest.TestCase):
    def test_from_json_case_insensitive(self) -> None:
        self.assertEqual(
            AppConfig.from_json({"app_id": "1", "name_space": 4, "message": None}),
            AppConfig(4, "1", None),
        )

    def test_from_json_not_a_dict(self) -> None:
        self.assertIsNone(AppConfig.from_json("x"))

    def test_from_json_missing_name_space(self) -> None:
        self.assertIsNone(AppConfig.from_json({"APP_ID": "1"}))


class LaunchAppTests(unittest.TestCase):
    def test_launch_builds_body_and_updates_app(self) -> None:
        tv = FakeRemoteTV()
        seen = []  # type: List[Tuple[str, str, Dict[str, str], Optional[str]]]

        def transport(method, url, headers, body):
            seen.append((method, url, dict(headers), body))
            return tv(method, url, headers, body)

        client = SmartCastClient(HOST, transport=transport, auth_token=TOKEN)
        config = AppConfig(2, "9", "http://192.0.2.1:8790/")
        client.launch_app(config)

        self.assertEqual(len(tv.calls), 1)
        method, url, headers, body = seen[0]
        self.assertEqual(method, "PUT")
        self.assertTrue(url.endswith("/app/launch"))
        self.assertEqual(headers.get("AUTH"), TOKEN)
        self.assertEqual(
            json.loads(body),
            {"VALUE": {"MESSAGE": "http://192.0.2.1:8790/", "NAME_SPACE": 2, "APP_ID": "9"}},
        )
        self.assertEqual(client.current_app(), config)

    def test_launch_with_null_message(self) -> None:
        tv = FakeRemoteTV()
        make_client(tv).launch_app(AppConfig(2, "9", None))
        _method, _path, body = tv.calls[0]
        self.assertEqual(
            json.loads(body),
            {"VALUE": {"MESSAGE": None, "NAME_SPACE": 2, "APP_ID": "9"}},
        )

    def test_refused_launch_raises(self) -> None:
        client = make_client(FakeRemoteTV(refuse_launch=True))
        with self.assertRaises(SmartCastError) as ctx:
            client.launch_app(AppConfig(2, "9", "http://192.0.2.1:8790/"))
        self.assertEqual(ctx.exception.result, ResultStatus.INVALID_PARAMETER)


class PressKeyTests(unittest.TestCase):
    def test_every_key(self) -> None:
        for key in RemoteKey:
            with self.subTest(key=key.name):
                tv = FakeRemoteTV()
                make_client(tv).press_key(key)
                self.assertEqual(tv.keys, [KEY_CODES[key]])
                _method, path, body = tv.calls[0]
                self.assertEqual(path, "/key_command/")
                entry = json.loads(body)["KEYLIST"][0]
                self.assertEqual(entry["CODESET"], KEY_CODES[key][0])
                self.assertEqual(entry["CODE"], KEY_CODES[key][1])
                self.assertEqual(entry["ACTION"], "KEYPRESS")


class InputTests(unittest.TestCase):
    def test_current_input(self) -> None:
        self.assertEqual(
            make_client(FakeRemoteTV()).current_input(),
            InputState("SMARTCAST", 2023834057),
        )

    def test_current_input_unknown(self) -> None:
        body = {"STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"}, "ITEMS": []}
        transport = FakeTransport([Response(200, json.dumps(body))])
        with self.assertRaises(SmartCastError) as ctx:
            make_client(transport).current_input()
        self.assertEqual(ctx.exception.result, ResultStatus.UNKNOWN)

    def test_list_inputs(self) -> None:
        inputs = make_client(FakeRemoteTV()).list_inputs()
        self.assertEqual([i.cname for i in inputs], ["cast", "hdmi1", "hdmi2", "comp", "tuner"])
        by_cname = {i.cname: i for i in inputs}
        self.assertEqual(by_cname["hdmi2"], InputInfo("hdmi2", "HDMI-2", "Fire TV Stick"))
        self.assertEqual(by_cname["cast"], InputInfo("cast", "CAST", "SMARTCAST"))

    def test_set_input(self) -> None:
        tv = FakeRemoteTV()
        make_client(tv).set_input("HDMI-2")
        puts = [c for c in tv.calls if c[0] == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertEqual(puts[0][1], "/menu_native/dynamic/tv_settings/devices/current_input")
        self.assertEqual(
            json.loads(puts[0][2]),
            {"REQUEST": "MODIFY", "VALUE": "HDMI-2", "HASHVAL": 2023834057},
        )
        self.assertEqual(make_client(tv).current_input().name, "HDMI-2")

    def test_set_input_stale_hash(self) -> None:
        fixture = load_tv_fixture("current_input_smartcast.json")
        transport = FakeTransport(
            [
                Response(fixture["http_status"], json.dumps(fixture["body"])),
                Response(200, json.dumps({"STATUS": {"RESULT": "INVALID_PARAMETER", "DETAIL": "refused"}})),
            ]
        )
        with self.assertRaises(SmartCastError) as ctx:
            make_client(transport).set_input("HDMI-2")
        self.assertEqual(ctx.exception.result, ResultStatus.INVALID_PARAMETER)


if __name__ == "__main__":
    unittest.main()
