"""Tests for the Google Cast opt-out client. They never open a socket."""

from __future__ import annotations

import json
import unittest
from typing import Dict, List, Optional, Tuple

from vizio_privacy.cast import SET_OPT_IN_BODY, CastClient


class FakeTransport:
    """A scripted transport: returns ``(status, text)`` in order and records calls."""

    def __init__(self, responses: List[Tuple[int, str]]) -> None:
        self._responses = list(responses)
        self.calls: List[Tuple[str, str, Dict[str, str], Optional[str]]] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[str],
    ) -> Tuple[int, str]:
        self.calls.append((method, url, headers, body))
        if self._responses:
            return self._responses.pop(0)
        return (200, "")

    def find(self, method: str) -> Optional[Tuple[str, str, Dict[str, str], Optional[str]]]:
        for call in self.calls:
            if call[0] == method:
                return call
        return None


def _eureka(opt_in: Optional[Dict[str, bool]]) -> str:
    payload = {"device_info": {"model": "D24f-J09"}}
    if opt_in is not None:
        payload["opt_in"] = opt_in
    return json.dumps(payload)


class ReadOptInTests(unittest.TestCase):
    def test_read_opt_in_returns_parsed_dict(self):
        transport = FakeTransport([(200, _eureka({"crash": True, "opencast": False, "stats": True}))])
        client = CastClient("192.0.2.10", transport=transport)
        self.assertEqual(
            client.read_opt_in(),
            {"crash": True, "opencast": False, "stats": True},
        )

    def test_read_opt_in_malformed_json_returns_empty(self):
        transport = FakeTransport([(200, "this is not json {")])
        client = CastClient("192.0.2.10", transport=transport)
        self.assertEqual(client.read_opt_in(), {})

    def test_read_opt_in_missing_opt_in_returns_empty(self):
        transport = FakeTransport([(200, json.dumps({"device_info": {}}))])
        client = CastClient("192.0.2.10", transport=transport)
        self.assertEqual(client.read_opt_in(), {})


class OptOutTests(unittest.TestCase):
    def test_opt_out_applied(self):
        transport = FakeTransport(
            [
                (200, _eureka({"crash": True, "stats": True})),  # before
                (200, "{}"),  # POST
                (200, _eureka({"crash": False, "stats": False})),  # after
            ]
        )
        client = CastClient("192.0.2.10", transport=transport)
        result = client.opt_out()
        self.assertTrue(result.changed)
        self.assertEqual(result.posted_status, 200)
        self.assertIn("now off", result.summary())

        post = transport.find("POST")
        self.assertIsNotNone(post)
        self.assertEqual(post[1], "https://192.0.2.10:8443/setup/set_eureka_info")
        self.assertEqual(json.loads(post[3]), SET_OPT_IN_BODY)
        gets = [call[1] for call in transport.calls if call[0] == "GET"]
        self.assertEqual(len(gets), 2)
        for url in gets:
            self.assertTrue(url.startswith("http://192.0.2.10:8008/setup/eureka_info"), url)
        self.assertTrue(result.reporting_off)

    def test_opt_out_uses_the_given_ports(self):
        transport = FakeTransport(
            [
                (200, _eureka({"crash": True, "stats": True})),  # before
                (200, ""),  # POST
                (200, _eureka({"crash": False, "stats": False})),  # after
            ]
        )
        client = CastClient("192.0.2.10", transport=transport, port=18008, secure_port=18443)
        client.opt_out()
        urls = [(call[0], call[1]) for call in transport.calls]
        self.assertEqual(
            urls,
            [
                ("GET", "http://192.0.2.10:18008/setup/eureka_info?params=opt_in,device_info"),
                ("POST", "https://192.0.2.10:18443/setup/set_eureka_info"),
                ("GET", "http://192.0.2.10:18008/setup/eureka_info?params=opt_in,device_info"),
            ],
        )

    def test_opt_out_rejected_404(self):
        transport = FakeTransport(
            [
                (200, _eureka({"crash": True, "stats": True})),  # before
                (404, "not found"),  # POST rejected
                (200, _eureka({"crash": True, "stats": True})),  # after unchanged
            ]
        )
        client = CastClient("192.0.2.10", transport=transport)
        result = client.opt_out()  # must not raise
        self.assertFalse(result.changed)
        self.assertFalse(result.reporting_off)
        self.assertEqual(result.posted_status, 404)
        summary = result.summary()
        self.assertIn("rejected", summary)
        self.assertIn("404", summary)

    def test_opt_out_200_but_not_applied(self):
        transport = FakeTransport(
            [
                (200, _eureka({"crash": True, "stats": True})),  # before
                (200, "{}"),  # POST accepted (means nothing)
                (200, _eureka({"crash": True, "stats": True})),  # after unchanged
            ]
        )
        client = CastClient("192.0.2.10", transport=transport)
        result = client.opt_out()
        self.assertFalse(result.changed)
        self.assertEqual(result.posted_status, 200)
        summary = result.summary()
        self.assertNotIn("now off", summary)
        self.assertIn("did not apply", summary)

    def test_opt_out_already_off(self):
        transport = FakeTransport(
            [
                (200, _eureka({"crash": False, "stats": False})),  # before
                (200, "{}"),  # POST
                (200, _eureka({"crash": False, "stats": False})),  # after
            ]
        )
        client = CastClient("192.0.2.10", transport=transport)
        result = client.opt_out()
        self.assertFalse(result.changed)
        self.assertTrue(result.reporting_off)
        self.assertIn("already off", result.summary())

    def test_reporting_off_is_false_when_the_after_read_failed(self):
        transport = FakeTransport(
            [
                (200, _eureka({"crash": True, "stats": True})),  # before
                (200, ""),  # POST
                (200, "not json"),  # after-read unparseable
            ]
        )
        result = CastClient("192.0.2.10", transport=transport).opt_out()
        self.assertEqual(result.after, {})
        self.assertFalse(result.reporting_off)


if __name__ == "__main__":
    unittest.main()
