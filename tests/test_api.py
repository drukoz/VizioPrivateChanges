"""Tests for the SmartCast client, envelope and enums. No sockets."""

from __future__ import annotations

import dataclasses
import json
import unittest
from typing import Any, Dict, Optional

from vizio_privacy.api import (
    DeviceInfo,
    Item,
    ItemType,
    ResultStatus,
    Response,
    SmartCastClient,
    SmartCastError,
    default_transport,
)
from tests.fakes import FakeTransport, ok

SUCCESS_ENVELOPE = {
    "STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"},
    "URI": "/menu_native/dynamic/tv_settings/devices",
    "ITEMS": [
        {
            "CNAME": "viewing_data",
            "NAME": "Viewing Data",
            "TYPE": "T_LIST_V1",
            "VALUE": "On",
            "HASHVAL": 1234567890,
            "ELEMENTS": ["On", "Off"],
        }
    ],
}

LIST_ITEM_JSON = {
    "CNAME": "viewing_data",
    "NAME": "Viewing Data",
    "TYPE": "T_LIST_V1",
    "VALUE": "On",
    "HASHVAL": 1234567890,
    "ELEMENTS": ["On", "Off"],
}

SLIDER_ITEM_JSON = {
    "CNAME": "brightness",
    "NAME": "Brightness",
    "TYPE": "T_VALUE_ABS_V1",
    "VALUE": 10,
    "HASHVAL": 55,
    "MINIMUM": 0,
    "MAXIMUM": 100,
    "CENTER": 50,
}

DEVICE_VALUE = {
    "MODEL_NAME": "D24f-J09",
    "API_VERSION": "3.3.3-2538.0001",
    "SC_INFO": "prod 59.47",
    "SETTINGS_ROOT": "tv_settings",
    "CAST_NAME": "D24f-J09 (1)",
    "INPUTS": ["CAST", "HDMI1", "HDMI2"],
    "CAPABILITIES": {"pv2": {"value": "1.0.0"}, "airplay": {"value": "1.0.0"}},
    "BINARIES": {"acr": "1.2.3", "s3logger": "2.0.1"},
    "SYSTEM_INFO": {
        "SERIAL_NUMBER": "REDACTED",
        "TVAD_ID": "REDACTED",
        "MAC_ADDRESS": "REDACTED",
    },
}


def client_with(responses: Any, token: Optional[str] = "tok") -> SmartCastClient:
    transport = FakeTransport(responses)
    return SmartCastClient("192.0.2.10", transport=transport, auth_token=token)


class EnumTests(unittest.TestCase):
    def test_result_status_values(self) -> None:
        self.assertEqual(0, ResultStatus.SUCCESS.value)
        self.assertEqual(1, ResultStatus.REQUIRES_PAIRING.value)
        self.assertEqual(2, ResultStatus.INVALID_PARAMETER.value)
        self.assertEqual(3, ResultStatus.URI_NOT_FOUND.value)
        self.assertEqual(4, ResultStatus.UNKNOWN.value)
        self.assertTrue(issubclass(ResultStatus, int))

    def test_result_status_from_text(self) -> None:
        self.assertEqual(ResultStatus.SUCCESS, ResultStatus.from_text("SUCCESS"))
        self.assertEqual(ResultStatus.SUCCESS, ResultStatus.from_text("success"))
        self.assertEqual(
            ResultStatus.REQUIRES_PAIRING, ResultStatus.from_text("Requires_Pairing")
        )
        self.assertEqual(
            ResultStatus.INVALID_PARAMETER, ResultStatus.from_text("invalid_parameter")
        )
        self.assertEqual(ResultStatus.URI_NOT_FOUND, ResultStatus.from_text("uri_not_found"))
        self.assertEqual(ResultStatus.UNKNOWN, ResultStatus.from_text("WHAT"))
        self.assertEqual(ResultStatus.UNKNOWN, ResultStatus.from_text(None))

    def test_item_type_values(self) -> None:
        self.assertEqual(0, ItemType.MENU.value)
        self.assertEqual(1, ItemType.LIST.value)
        self.assertEqual(2, ItemType.SLIDER.value)
        self.assertEqual(3, ItemType.VALUE.value)
        self.assertEqual(4, ItemType.LIST_X.value)
        self.assertEqual(5, ItemType.UNKNOWN.value)
        self.assertTrue(issubclass(ItemType, int))

    def test_item_type_from_text(self) -> None:
        self.assertEqual(ItemType.MENU, ItemType.from_text("T_MENU_V1"))
        self.assertEqual(ItemType.LIST, ItemType.from_text("t_list_v1"))
        self.assertEqual(ItemType.SLIDER, ItemType.from_text("T_VALUE_ABS_V1"))
        self.assertEqual(ItemType.VALUE, ItemType.from_text("T_Value_V1"))
        self.assertEqual(ItemType.LIST_X, ItemType.from_text("T_LIST_X_V1"))
        self.assertEqual(ItemType.UNKNOWN, ItemType.from_text("T_ACTION_V1"))
        self.assertEqual(ItemType.UNKNOWN, ItemType.from_text(None))


class ItemTests(unittest.TestCase):
    def test_list_item(self) -> None:
        item = Item.from_json(LIST_ITEM_JSON)
        self.assertEqual("viewing_data", item.cname)
        self.assertEqual("Viewing Data", item.name)
        self.assertEqual(ItemType.LIST, item.type)
        self.assertEqual("On", item.value)
        self.assertEqual(1234567890, item.hashval)
        self.assertEqual(["On", "Off"], item.elements)
        self.assertIsNone(item.minimum)

    def test_slider_item(self) -> None:
        item = Item.from_json(SLIDER_ITEM_JSON)
        self.assertEqual(ItemType.SLIDER, item.type)
        self.assertEqual(10, item.value)
        self.assertEqual(0, item.minimum)
        self.assertEqual(100, item.maximum)
        self.assertEqual(50, item.center)
        self.assertEqual([], item.elements)

    def test_case_insensitive_keys(self) -> None:
        item = Item.from_json(
            {"cname": "x", "name": "X", "type": "t_list_v1", "value": "On", "hashval": 7}
        )
        self.assertEqual("x", item.cname)
        self.assertEqual(ItemType.LIST, item.type)
        self.assertEqual(7, item.hashval)


class ClientEnvelopeTests(unittest.TestCase):
    def test_success_parses_items(self) -> None:
        client = client_with([Response(200, json.dumps(SUCCESS_ENVELOPE))])
        items = client.get_items("/menu_native/dynamic/tv_settings/devices")
        self.assertEqual(1, len(items))
        self.assertEqual("viewing_data", items[0].cname)
        self.assertEqual(ItemType.LIST, items[0].type)

    def test_success_without_items_is_empty_list(self) -> None:
        body = json.dumps({"STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"}})
        client = client_with([Response(200, body)])
        self.assertEqual([], client.get_items("/menu_native/dynamic/tv_settings/devices"))

    def test_lowercase_envelope_keys(self) -> None:
        body = json.dumps(
            {
                "status": {"result": "success", "detail": "Success"},
                "items": [LIST_ITEM_JSON],
            }
        )
        client = client_with([Response(200, body)])
        items = client.get_items("/menu_native/dynamic/tv_settings/devices")
        self.assertEqual(1, len(items))
        self.assertEqual("viewing_data", items[0].cname)

    def test_403_requires_pairing_raises(self) -> None:
        body = json.dumps(
            {"STATUS": {"RESULT": "REQUIRES_PAIRING", "DETAIL": "Pairing is required"}}
        )
        client = client_with([Response(403, body)])
        with self.assertRaises(SmartCastError) as caught:
            client.get_items("/menu_native/dynamic/tv_settings")
        self.assertEqual(ResultStatus.REQUIRES_PAIRING, caught.exception.result)
        self.assertEqual("Pairing is required", caught.exception.detail)
        self.assertIn("REQUIRES_PAIRING", str(caught.exception))

    def test_unknown_result_and_missing_status(self) -> None:
        client = client_with([Response(200, json.dumps({"URI": "/x"}))])
        with self.assertRaises(SmartCastError) as caught:
            client.get("/menu_native/dynamic/tv_settings")
        self.assertEqual(ResultStatus.UNKNOWN, caught.exception.result)

    def test_non_json_body_raises_unknown(self) -> None:
        client = client_with([Response(502, "<html>Bad Gateway</html>")])
        with self.assertRaises(SmartCastError) as caught:
            client.get("/state/device/deviceinfo")
        self.assertEqual(ResultStatus.UNKNOWN, caught.exception.result)
        self.assertIn("HTTP 502", str(caught.exception))

    def test_empty_body_raises_unknown(self) -> None:
        client = client_with([Response(200, "")])
        with self.assertRaises(SmartCastError) as caught:
            client.get("/state/device/deviceinfo")
        self.assertEqual(ResultStatus.UNKNOWN, caught.exception.result)


class ClientRequestTests(unittest.TestCase):
    def test_get_device_info(self) -> None:
        client = client_with([ok([{"CNAME": "deviceinfo", "VALUE": DEVICE_VALUE}])])
        info = client.get_device_info()
        self.assertIsInstance(info, DeviceInfo)
        self.assertEqual("D24f-J09", info.model_name)
        self.assertEqual("3.3.3-2538.0001", info.api_version)
        self.assertEqual("prod 59.47", info.sc_info)
        self.assertEqual("tv_settings", info.settings_root)
        self.assertEqual("D24f-J09 (1)", info.cast_name)
        self.assertEqual(["CAST", "HDMI1", "HDMI2"], info.inputs)
        self.assertIn("pv2", info.capabilities)
        self.assertEqual("1.2.3", info.binaries["acr"])
        self.assertEqual("2.0.1", info.binaries["s3logger"])
        call = client.transport.calls[0]  # type: ignore[union-attr]
        self.assertEqual("GET", call.method)
        self.assertEqual("https://192.0.2.10:7345/state/device/deviceinfo", call.url)
        self.assertNotIn("AUTH", call.headers)

    def test_device_info_has_no_identifiers(self) -> None:
        field_names = [f.name for f in dataclasses.fields(DeviceInfo)]
        for forbidden in ("serial_number", "mac", "mac_address", "tvad_id", "esn", "uma_client_id"):
            self.assertNotIn(forbidden, field_names)
        info = DeviceInfo.from_value(DEVICE_VALUE)
        text = repr(info)
        for forbidden in ("REDACTED", "SERIAL", "TVAD", "MAC"):
            self.assertNotIn(forbidden, text)

    def test_put_sends_auth_header_and_body(self) -> None:
        client = client_with([ok()])
        body = {"REQUEST": "MODIFY", "HASHVAL": 55, "VALUE": "Off"}
        client.put("/menu_native/dynamic/tv_settings/devices/viewing_data", body, auth=True)
        call = client.transport.calls[0]  # type: ignore[union-attr]
        self.assertEqual("PUT", call.method)
        self.assertEqual("tok", call.headers.get("AUTH"))
        self.assertEqual("application/json", call.headers.get("Content-Type"))
        self.assertEqual(body, json.loads(call.body or ""))

    def test_get_without_auth_sends_no_auth_header(self) -> None:
        client = client_with([ok()])
        client.get("/state/device/deviceinfo")
        call = client.transport.calls[0]  # type: ignore[union-attr]
        self.assertNotIn("AUTH", call.headers)

    def test_get_with_auth_sends_auth_header(self) -> None:
        client = client_with([ok()])
        client.get("/menu_native/dynamic/tv_settings", auth=True)
        call = client.transport.calls[0]  # type: ignore[union-attr]
        self.assertEqual("tok", call.headers.get("AUTH"))

    def test_default_transport_sends_path_and_closes(self) -> None:
        recorded = {}  # type: Dict[str, Any]

        class StubConnection:
            closed = False

            def __init__(self, host: str, port: int, timeout: Any = None, context: Any = None) -> None:
                recorded["host"] = host
                recorded["port"] = port
                recorded["timeout"] = timeout
                recorded["context"] = context

            def request(self, method: str, target: str, body: Any = None, headers: Any = None) -> None:
                recorded["method"] = method
                recorded["target"] = target
                recorded["body"] = body
                recorded["headers"] = headers

            def getresponse(self) -> Any:
                class Resp:
                    status = 200

                    @staticmethod
                    def read() -> bytes:
                        return b'{"STATUS":{"RESULT":"SUCCESS","DETAIL":"Success"}}'

                return Resp()

            def close(self) -> None:
                StubConnection.closed = True

        import http.client as http_client

        from vizio_privacy import api

        original = http_client.HTTPSConnection
        http_client.HTTPSConnection = StubConnection  # type: ignore[misc]
        try:
            transport = default_transport(timeout=5.0)
            response = transport("GET", "https://192.0.2.10:7345/state/device/deviceinfo?x=1", {}, None)
        finally:
            http_client.HTTPSConnection = original  # type: ignore[misc]
        self.assertEqual("192.0.2.10", recorded["host"])
        self.assertEqual(7345, recorded["port"])
        self.assertEqual(5.0, recorded["timeout"])
        self.assertEqual("GET", recorded["method"])
        self.assertEqual("/state/device/deviceinfo?x=1", recorded["target"])
        self.assertEqual(200, response.status)
        self.assertIn("SUCCESS", response.body)
        self.assertTrue(StubConnection.closed)


if __name__ == "__main__":
    unittest.main()
