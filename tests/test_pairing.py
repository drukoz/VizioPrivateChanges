"""Tests for PIN pairing and the auth-token store. No sockets."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from typing import Any, Dict
from unittest import mock

from vizio_privacy.api import Response, SmartCastClient, SmartCastError
from vizio_privacy import tokenstore
from vizio_privacy.pairing import PairStart, begin_pair, cancel_pair, finish_pair
from tests.fakes import FakeTransport, ok

START_ITEM = {"CHALLENGE_TYPE": 1, "PAIRING_REQ_TOKEN": 987654321}
PAIR_ITEM = {"AUTH_TOKEN": "TOKEN-ABC"}


def client_for(responses: Any) -> SmartCastClient:
    return SmartCastClient("192.0.2.10", transport=FakeTransport(responses))


def body_of(client: SmartCastClient, index: int = 0) -> Dict[str, Any]:
    transport = client.transport  # type: FakeTransport
    return json.loads(transport.calls[index].body or "")


class BeginPairTests(unittest.TestCase):
    def test_reads_challenge_type_and_token(self) -> None:
        client = client_for([ok(ITEM=START_ITEM)])
        started = begin_pair(client)
        self.assertIsInstance(started, PairStart)
        self.assertEqual(1, started.challenge_type)
        self.assertEqual(987654321, started.pairing_token)
        self.assertIsInstance(started.challenge_type, int)
        self.assertIsInstance(started.pairing_token, int)

    def test_put_path_and_body(self) -> None:
        client = client_for([ok(ITEM=START_ITEM)])
        begin_pair(client)
        call = client.transport.calls[0]  # type: ignore[union-attr]
        self.assertEqual("PUT", call.method)
        self.assertEqual("https://192.0.2.10:7345/pairing/start", call.url)
        self.assertNotIn("AUTH", call.headers)
        body = body_of(client)
        self.assertEqual("vizio-privacy", body["DEVICE_ID"])
        self.assertEqual("Vizio Privacy", body["DEVICE_NAME"])

    def test_given_device_id_and_name_are_sent(self) -> None:
        client = client_for([ok(ITEM=START_ITEM)])
        begin_pair(client, device_id="my-id", device_name="My Name")
        body = body_of(client)
        self.assertEqual("my-id", body["DEVICE_ID"])
        self.assertEqual("My Name", body["DEVICE_NAME"])

    def test_lowercase_answer_keys(self) -> None:
        client = client_for([ok(item={"challenge_type": "2", "pairing_req_token": "77"})])
        started = begin_pair(client)
        self.assertEqual(2, started.challenge_type)
        self.assertEqual(77, started.pairing_token)

    def test_missing_item_raises(self) -> None:
        client = client_for([ok()])
        with self.assertRaises(SmartCastError):
            begin_pair(client)


class FinishPairTests(unittest.TestCase):
    def test_returns_auth_token(self) -> None:
        client = client_for([ok(ITEM=PAIR_ITEM)])
        self.assertEqual("TOKEN-ABC", finish_pair(client, 1, 987654321, "4912"))

    def test_put_path_and_body_types(self) -> None:
        client = client_for([ok(ITEM=PAIR_ITEM)])
        finish_pair(client, 1, 987654321, "4912", device_id="my-id")
        call = client.transport.calls[0]  # type: ignore[union-attr]
        self.assertEqual("PUT", call.method)
        self.assertEqual("https://192.0.2.10:7345/pairing/pair", call.url)
        self.assertNotIn("AUTH", call.headers)
        body = body_of(client)
        self.assertEqual("my-id", body["DEVICE_ID"])
        self.assertEqual(1, body["CHALLENGE_TYPE"])
        self.assertEqual(987654321, body["PAIRING_REQ_TOKEN"])
        self.assertEqual("4912", body["RESPONSE_VALUE"])
        self.assertIsInstance(body["CHALLENGE_TYPE"], int)
        self.assertIsInstance(body["PAIRING_REQ_TOKEN"], int)
        self.assertIsInstance(body["RESPONSE_VALUE"], str)

    def test_numeric_strings_are_coerced_to_ints(self) -> None:
        client = client_for([ok(ITEM=PAIR_ITEM)])
        finish_pair(client, "3", "42", 4912)
        body = body_of(client)
        self.assertEqual(3, body["CHALLENGE_TYPE"])
        self.assertEqual(42, body["PAIRING_REQ_TOKEN"])
        self.assertEqual("4912", body["RESPONSE_VALUE"])

    def test_lowercase_answer_keys(self) -> None:
        client = client_for([ok(item={"auth_token": "lower-token"})])
        self.assertEqual("lower-token", finish_pair(client, 1, 2, "0000"))

    def test_missing_auth_token_raises(self) -> None:
        client = client_for([ok(ITEM={"CNAME": "pair"})])
        with self.assertRaises(SmartCastError):
            finish_pair(client, 1, 2, "0000")

    def test_tv_error_propagates(self) -> None:
        body = json.dumps({"STATUS": {"RESULT": "INVALID_PARAMETER", "DETAIL": "bad PIN"}})
        client = client_for([Response(200, body)])
        with self.assertRaises(SmartCastError):
            finish_pair(client, 1, 2, "0000")


class CancelPairTests(unittest.TestCase):
    def test_put_path_and_body(self) -> None:
        client = client_for([ok()])
        self.assertIsNone(cancel_pair(client))
        call = client.transport.calls[0]  # type: ignore[union-attr]
        self.assertEqual("PUT", call.method)
        self.assertEqual("https://192.0.2.10:7345/pairing/cancel", call.url)
        body = body_of(client)
        self.assertEqual("vizio-privacy", body["DEVICE_ID"])
        self.assertEqual("Vizio Privacy", body["DEVICE_NAME"])

    def test_swallows_smartcast_error(self) -> None:
        body = json.dumps({"STATUS": {"RESULT": "INVALID_PARAMETER", "DETAIL": "no pairing"}})
        client = client_for([Response(200, body)])
        self.assertIsNone(cancel_pair(client))


class TokenStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        patcher = mock.patch.dict(os.environ, {"VIZIO_PRIVACY_HOME": self.home.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_token_path_honors_env_home_and_stays_outside_repo(self) -> None:
        path = tokenstore.token_path("192.0.2.10")
        self.assertEqual(
            os.path.join(self.home.name, ".vizio-privacy", "192.0.2.10.json"), path
        )
        self.assertTrue(path.startswith(self.home.name))
        self.assertNotIn(os.path.abspath("."), path)

    def test_save_then_load_round_trip(self) -> None:
        path = tokenstore.save_token("192.0.2.10", "dev-1", "TOKEN-ABC")
        loaded = tokenstore.load_token("192.0.2.10")
        self.assertEqual(
            {"host": "192.0.2.10", "device_id": "dev-1", "auth_token": "TOKEN-ABC"}, loaded
        )
        with open(path, "r", encoding="utf-8") as handle:
            self.assertEqual("TOKEN-ABC", json.load(handle)["auth_token"])

    def test_file_and_directory_modes(self) -> None:
        path = tokenstore.save_token("192.0.2.10", "dev-1", "TOKEN-ABC")
        self.assertEqual(0o600, stat.S_IMODE(os.stat(path).st_mode))
        self.assertEqual(0o700, stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode))

    def test_save_overwrites(self) -> None:
        tokenstore.save_token("192.0.2.10", "dev-1", "OLD")
        tokenstore.save_token("192.0.2.10", "dev-1", "NEW")
        self.assertEqual("NEW", tokenstore.load_token("192.0.2.10")["auth_token"])

    def test_load_token_missing_returns_none(self) -> None:
        self.assertIsNone(tokenstore.load_token("198.51.100.7"))

    def test_one_file_per_host(self) -> None:
        tokenstore.save_token("192.0.2.10", "dev-1", "TOKEN-A")
        tokenstore.save_token("192.0.2.11", "dev-1", "TOKEN-B")
        self.assertEqual("TOKEN-A", tokenstore.load_token("192.0.2.10")["auth_token"])
        self.assertEqual("TOKEN-B", tokenstore.load_token("192.0.2.11")["auth_token"])

    def test_save_does_not_write_inside_repo(self) -> None:
        before = set(os.listdir("."))
        tokenstore.save_token("192.0.2.10", "dev-1", "TOKEN-ABC")
        self.assertEqual(before, set(os.listdir(".")))


if __name__ == "__main__":
    unittest.main()
