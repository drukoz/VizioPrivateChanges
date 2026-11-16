"""Fake transport for the tests: no test ever opens a socket."""

from __future__ import annotations

import json
from collections import namedtuple
from typing import Any, Callable, Dict, List, Optional, Union

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
