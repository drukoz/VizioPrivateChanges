"""Google Cast telemetry opt-out over the Cast setup API.

The TV runs Google's "eureka" Cast setup service. Reads go over plain HTTP on
port 8008. The opt-out write goes over HTTPS on port 8443: on the owner's TV
(Cast firmware 1.68) a write on 8008 answers 403 and changes nothing, while the
same write on 8443 answers 200 and takes effect, with no token (checked on
2026-11-16). The 8443 certificate is self-signed, so certificate checks are
off, as in ``api.py``. No auth is needed for the calls used here.

This module reads the device's telemetry opt-in flags and tries to turn crash
and usage reporting off. It reports honestly whether the change took, and
never raises on a rejected write: only the read performed after the write
proves the result, because the device answers 200 OK even for fields it ignores.

This module is independent of the SmartCast client in ``api.py``: it uses
``http.client`` directly and defines its own injectable transport.
"""

from __future__ import annotations

import http.client
import json
import ssl
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import urlsplit

# The body of the opt-out write, confirmed on the owner's TV on 2026-11-16 (sent
# over HTTPS on port 8443). A 200 OK proves nothing (the device answers 200 even
# for fields it ignores), so the result is decided by the read that follows.
SET_OPT_IN_BODY = {"opt_in": {"crash": False, "stats": False}}

# Transport contract: a callable that performs one HTTP request and returns
# ``(http_status, text)``. Injecting it lets the tests run without a socket.
Transport = Callable[[str, str, Dict[str, str], Optional[str]], Tuple[int, str]]

_EUREKA_INFO_PATH = "/setup/eureka_info?params=opt_in,device_info"
_SET_EUREKA_INFO_PATH = "/setup/set_eureka_info"


def default_transport(timeout: float = 5.0) -> Transport:
    """Return a transport that uses ``http.client``: HTTPS for ``https://`` URLs,
    plain HTTP otherwise.

    HTTPS skips certificate checks, because the TV's certificate is
    self-signed. Host and port are taken from the URL passed in, matching the
    transport contract ``(method, url, headers, body) -> (status, text)``.
    """
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    def transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[str],
    ) -> Tuple[int, str]:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
        path = parts.path
        if parts.query:
            path = "{}?{}".format(path, parts.query)
        if parts.scheme == "https":
            conn = http.client.HTTPSConnection(
                host, port, timeout=timeout, context=ssl_ctx
            )  # type: http.client.HTTPConnection
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            text = resp.read().decode("utf-8", "replace")
            return (resp.status, text)
        finally:
            conn.close()

    return transport


@dataclass
class OptOutResult:
    """Outcome of an opt-out attempt, judged from the reads around the write."""

    before: Dict[str, bool]
    after: Dict[str, bool]
    posted_status: Optional[int]
    error: Optional[str] = None

    @property
    def changed(self) -> bool:
        """True when the after-read shows both flags off and that differs from before."""
        after_off = self.after.get("crash") is False and self.after.get("stats") is False
        before_off = self.before.get("crash") is False and self.before.get("stats") is False
        return after_off and not before_off

    @property
    def reporting_off(self) -> bool:
        """True when the read after the write shows crash and stats reporting both off."""
        return self.after.get("crash") is False and self.after.get("stats") is False

    def summary(self) -> str:
        """One-line human message describing the truth from the after-read.

        Never includes a device identifier.
        """
        before_off = self.before.get("crash") is False and self.before.get("stats") is False
        if before_off:
            return "crash/stats reporting already off"
        if self.changed:
            return "crash/stats reporting now off"
        state = "crash={} stats={}".format(
            "off" if self.after.get("crash") is False else "on",
            "off" if self.after.get("stats") is False else "on",
        )
        if self.error:
            return "Cast opt-out failed ({}); {}".format(self.error, state)
        if self.posted_status is not None and self.posted_status != 200:
            return "TV rejected the change (status {}); {}".format(self.posted_status, state)
        return "TV did not apply the change (status {}); {}".format(self.posted_status, state)


class CastClient:
    """Read Google Cast telemetry flags on port 8008; write the opt-out on port 8443."""

    def __init__(
        self,
        host: str,
        transport: Optional[Transport] = None,
        port: int = 8008,
        secure_port: int = 8443,
    ) -> None:
        self.host = host
        self.port = port
        self.secure_port = secure_port
        self.transport = transport if transport is not None else default_transport()

    def _url(self, path: str) -> str:
        return "http://{}:{}{}".format(self.host, self.port, path)

    def _secure_url(self, path: str) -> str:
        return "https://{}:{}{}".format(self.host, self.secure_port, path)

    def read_opt_in(self) -> Dict[str, bool]:
        """Return the device's ``opt_in`` dict, or ``{}`` if absent or unparseable."""
        url = self._url(_EUREKA_INFO_PATH)
        status, text = self.transport("GET", url, {}, None)
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return {}
        if not isinstance(data, dict):
            return {}
        opt_in = data.get("opt_in")
        if not isinstance(opt_in, dict):
            return {}
        return dict(opt_in)

    def opt_out(self) -> OptOutResult:
        """Read the flags, post the opt-out, then read again and judge the result."""
        before = self.read_opt_in()
        posted_status = None  # type: Optional[int]
        error = None  # type: Optional[str]
        try:
            url = self._secure_url(_SET_EUREKA_INFO_PATH)
            headers = {"Content-Type": "application/json"}
            posted_status, _ = self.transport(
                "POST", url, headers, json.dumps(SET_OPT_IN_BODY)
            )
        except (OSError, http.client.HTTPException) as exc:
            error = str(exc)
        after = self.read_opt_in()
        return OptOutResult(
            before=before,
            after=after,
            posted_status=posted_status,
            error=error,
        )
