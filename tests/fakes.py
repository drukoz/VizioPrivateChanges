"""Fake transport for the tests: no test ever opens a socket."""

from __future__ import annotations

import json
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
