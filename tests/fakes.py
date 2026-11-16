"""Fake transport for the tests: no test ever opens a socket."""

from __future__ import annotations

import copy
import json
import os
import urllib.parse
from collections import namedtuple
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from vizio_privacy.api import Response

Call = namedtuple("Call", ["method", "url", "headers", "body"])


class FakeTransport:
    """A callable transport that replays queued responses or routes by request."""

    def __init__(
        self,
        responses: Optional[Union[List[Response], Callable[[str, str], Response]]] = None,
    ) -> None:
        self.responses = responses if responses is not None else []
        self.calls = []  # type: List[Call]

    def __call__(
        self, method: str, url: str, headers: Dict[str, str], body: Optional[str]
    ) -> Response:
        self.calls.append(Call(method, url, dict(headers), body))
        if callable(self.responses):
            return self.responses(method, url)  # type: ignore[operator]
        queued = self.responses
        if not queued:
            raise AssertionError("FakeTransport has no queued response for {} {}".format(method, url))
        if len(queued) == 1:
            return queued[0]
        return queued.pop(0)


def envelope(items: Optional[List[Dict[str, Any]]] = None, **extra: Any) -> str:
    """Build a SUCCESS envelope body, optionally with ITEMS."""
    payload = {"STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"}}  # type: Dict[str, Any]
    payload.update(extra)
    if items is not None:
        payload["ITEMS"] = items
    import json

    return json.dumps(payload)


def ok(items: Optional[List[Dict[str, Any]]] = None, **extra: Any) -> Response:
    return Response(200, envelope(items, **extra))


MENU_PREFIX = "/menu_native/dynamic/tv_settings"
STATIC_PREFIX = "/menu_native/static/tv_settings"


def _status(result: str, detail: str) -> Response:
    return Response(200, json.dumps({"STATUS": {"RESULT": result, "DETAIL": detail}}))


class FakeTV:
    """A fake SmartCast settings tree; it is itself a transport and never opens a socket."""

    def __init__(
        self,
        menus: Dict[str, List[dict]],
        refuse: Optional[Set[str]] = None,
        dynamic_elements: bool = True,
        static_menus: Optional[Dict[str, List[dict]]] = None,
    ) -> None:
        self.menus = menus
        self.refuse = refuse if refuse is not None else set()
        # A real TV leaves ELEMENTS out of its dynamic answers; False copies that.
        self.dynamic_elements = dynamic_elements
        # Static answers: by default each menu's items without VALUE and HASHVAL.
        self.static_menus = static_menus
        self.calls = []  # type: List[Tuple[str, str, Optional[str]]]

    def _static(self, rel: str) -> Response:
        if self.static_menus is not None:
            items = self.static_menus.get(rel)
        elif rel in self.menus:
            items = [
                {k: v for k, v in it.items() if k not in ("VALUE", "HASHVAL")}
                for it in self.menus[rel]
            ]
        else:
            items = None
        if items is None:
            return _status("URI_NOT_FOUND", "not found")
        return Response(
            200,
            json.dumps({"STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"}, "ITEMS": items}),
        )

    def __call__(
        self, method: str, url: str, headers: Dict[str, str], body: Optional[str]
    ) -> Response:
        path = urllib.parse.urlsplit(url).path
        self.calls.append((method, path, body))
        if path == STATIC_PREFIX or path.startswith(STATIC_PREFIX + "/"):
            if method.upper() != "GET":
                return _status("URI_NOT_FOUND", "not found")
            return self._static(path[len(STATIC_PREFIX):].lstrip("/"))
        rel = path[len(MENU_PREFIX):].lstrip("/")
        if method.upper() == "GET":
            if rel in self.menus:
                items = self.menus[rel]
                if not self.dynamic_elements:
                    items = [{k: v for k, v in it.items() if k != "ELEMENTS"} for it in items]
                return Response(
                    200,
                    json.dumps(
                        {
                            "STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"},
                            "ITEMS": items,
                        }
                    ),
                )
            return _status("URI_NOT_FOUND", "not found")
        menu, _, cname = rel.rpartition("/")
        req = json.loads(body) if body is not None else {}
        items = self.menus.get(menu)
        if items is None:
            return _status("URI_NOT_FOUND", "not found")
        item = None
        for candidate in items:
            if candidate.get("CNAME") == cname:
                item = candidate
                break
        if item is None:
            return _status("URI_NOT_FOUND", "not found")
        if cname in self.refuse:
            return _status("INVALID_PARAMETER", "refused")
        if req.get("HASHVAL") != item.get("HASHVAL"):
            return _status("INVALID_PARAMETER", "refused")
        item["VALUE"] = req.get("VALUE")
        item["HASHVAL"] = item["HASHVAL"] + 1
        return _status("SUCCESS", "Success")


TV_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "tv")


def load_tv_fixture(name: str) -> dict:
    """Read tests/fixtures/tv/<name> and return the whole {http_status, body} dict."""
    with open(os.path.join(TV_FIXTURES, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


POWER_PATH = "/state/device/power_mode"
APP_CURRENT_PATH = "/app/current"
APP_LAUNCH_PATH = "/app/launch"
KEY_COMMAND_PATH = "/key_command/"
DEVICES_PREFIX = "/menu_native/dynamic/tv_settings/devices"
CURRENT_INPUT_PATH = DEVICES_PREFIX + "/current_input"
NAME_INPUT_PATH = DEVICES_PREFIX + "/name_input"


class FakeRemoteTV:
    """A fake TV for the dashboard control calls; a transport that never opens a socket."""

    def __init__(self, power: int = 0, app: Optional[dict] = None, refuse_launch: bool = False) -> None:
        self.power = power
        self.app = app
        self.refuse_launch = refuse_launch
        self.input_value = "SMARTCAST"
        self.input_hash = 2023834057
        self.keys = []  # type: List[Tuple[int, int]]
        self.calls = []  # type: List[Tuple[str, str, Optional[str]]]

    def _body(self, name: str) -> Dict[str, Any]:
        return copy.deepcopy(load_tv_fixture(name)["body"])

    def __call__(
        self, method: str, url: str, headers: Dict[str, str], body: Optional[str]
    ) -> Response:
        path = urllib.parse.urlsplit(url).path
        self.calls.append((method, path, body))
        verb = method.upper()
        if verb == "GET":
            return self._get(path)
        if verb == "PUT":
            return self._put(path, body)
        return _status("URI_NOT_FOUND", "not found")

    def _get(self, path: str) -> Response:
        if path == POWER_PATH:
            body = self._body("power_mode_standby.json")
            body["ITEMS"][0]["VALUE"] = self.power
            return _json(body)
        if path == APP_CURRENT_PATH:
            body = self._body("app_current_standby.json")
            body["ITEM"]["VALUE"] = self.app
            return _json(body)
        if path == CURRENT_INPUT_PATH:
            body = self._body("current_input_smartcast.json")
            body["ITEMS"][0]["VALUE"] = self.input_value
            body["ITEMS"][0]["HASHVAL"] = self.input_hash
            return _json(body)
        if path == NAME_INPUT_PATH:
            return _json(self._body("name_input.json"))
        return _status("URI_NOT_FOUND", "not found")

    def _put(self, path: str, body: Optional[str]) -> Response:
        req = json.loads(body) if body is not None else {}
        if path == APP_LAUNCH_PATH:
            if self.refuse_launch:
                return _status("INVALID_PARAMETER", "refused")
            self.app = req.get("VALUE")
            return _status("SUCCESS", "Success")
        if path == KEY_COMMAND_PATH:
            for key in req.get("KEYLIST", []):
                self.keys.append((key.get("CODESET"), key.get("CODE")))
            return _status("SUCCESS", "Success")
        if path == CURRENT_INPUT_PATH:
            if req.get("HASHVAL") != self.input_hash:
                return _status("INVALID_PARAMETER", "refused")
            self.input_value = req.get("VALUE")
            self.input_hash = self.input_hash + 1
            return _status("SUCCESS", "Success")
        return _status("URI_NOT_FOUND", "not found")


def _json(body: Dict[str, Any]) -> Response:
    return Response(200, json.dumps(body))
