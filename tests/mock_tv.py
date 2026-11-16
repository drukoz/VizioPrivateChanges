"""A local mock of the TV: the SmartCast (HTTPS) and Cast (HTTP) servers.

Part 1 of the end-to-end tests uses this to run the real command line, with
its real transports, over real sockets bound to ``127.0.0.1`` only. It is a
faithful-enough stand-in for the two servers the CLI talks to: the SmartCast
envelope, PIN pairing, the settings tree (dynamic and static), the settings
write with its ``HASHVAL`` guard, and the Cast ``eureka_info`` read/write.

Every request is recorded so a test can assert on what the client sent. The
identifier constants are deliberately loud, so a test can prove they never
reach an asserted output.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import ssl
import subprocess
import threading
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

PIN = "4321"
CHALLENGE_TYPE = 1
PAIRING_REQ_TOKEN = 98765
AUTH_TOKEN = "MOCK-AUTH-TOKEN"
SERIAL = "MOCK-SERIAL-SHOULD-NOT-PRINT"
TVAD = "MOCK-TVAD-SHOULD-NOT-PRINT"
MAC = "MOCK-MAC-SHOULD-NOT-PRINT"

MENU_ROOT = "/menu_native/dynamic/tv_settings"
STATIC_ROOT = "/menu_native/static/tv_settings"

EUREKA_INFO_PATH = "/setup/eureka_info"
SET_EUREKA_INFO_PATH = "/setup/set_eureka_info"


def make_certificate(directory: str) -> Tuple[str, str]:
    """A throwaway self-signed certificate; returns (cert path, key path)."""
    cert = os.path.join(directory, "cert.pem")
    key = os.path.join(directory, "key.pem")
    subprocess.run(
        [shutil.which("openssl") or "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", key, "-out", cert, "-days", "1", "-subj", "/CN=localhost"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return cert, key


def menu(cname: str, name: str) -> Dict[str, Any]:
    return {"CNAME": cname, "NAME": name, "TYPE": "T_MENU_V1"}


def choice(cname: str, name: str, elements: List[str]) -> Dict[str, Any]:
    return {"CNAME": cname, "NAME": name, "TYPE": "T_LIST_V1", "ELEMENTS": elements}


MENUS = {
    "": [menu("picture", "Picture"), menu("admin_and_privacy", "Admin & Privacy"), menu("system", "System")],
    "picture": [choice("picture_mode", "Picture Mode", ["Vivid", "Calibrated"])],
    "admin_and_privacy": [
        choice("viewing_data", "Viewing Data", ["On", "Off"]),
        menu("advertising", "Advertising"),
        menu("system_information", "System Information"),
    ],
    "admin_and_privacy/advertising": [
        choice("limit_ad_tracking", "Limit Ad Tracking", ["Off", "On"]),
        {"CNAME": "reset_advertising_id", "NAME": "Reset Advertising ID", "TYPE": "T_ACTION_V1"},
    ],
    "admin_and_privacy/system_information": [
        {"CNAME": "serial_number", "NAME": "Serial Number", "TYPE": "T_VALUE_V1", "VALUE": SERIAL},
    ],
    "system": [menu("broken", "Broken Menu")],
}

DEVICE_VALUE = {
    "MODEL_NAME": "D24f-J09",
    "API_VERSION": "3.3.3",
    "SC_INFO": "prod 59.47",
    "SETTINGS_ROOT": "tv_settings",
    "CAST_NAME": "Living Room",
    "INPUTS": ["CAST", "HDMI1"],
    "CAPABILITIES": {},
    "BINARIES": {"acr": "1", "s3logger": "1", "upnp": "1"},
    "SYSTEM_INFO": {"SERIAL_NUMBER": SERIAL, "TVAD_ID": TVAD},
}

PAIR_BODY = {
    "DEVICE_ID": "vizio-privacy",
    "CHALLENGE_TYPE": CHALLENGE_TYPE,
    "PAIRING_REQ_TOKEN": PAIRING_REQ_TOKEN,
    "RESPONSE_VALUE": PIN,
}

CAST_OPT_OUT_BODY = {"opt_in": {"crash": False, "stats": False}}


def _success(**extra: Any) -> Dict[str, Any]:
    payload = {"STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"}}  # type: Dict[str, Any]
    payload.update(extra)
    return payload


def _status(result: str, detail: str) -> Dict[str, Any]:
    return {"STATUS": {"RESULT": result, "DETAIL": detail}}


def _key(menu_path: str, cname: str) -> str:
    return menu_path + "/" + cname if menu_path else cname


class _QuietHandler(http.server.BaseHTTPRequestHandler):
    """Shared plumbing for both handler classes; keeps test output quiet."""

    def log_message(self, *args: Any) -> None:
        pass

    def _send(self, status: int, obj: dict) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else None


class SmartCastHandler(_QuietHandler):
    """The SmartCast server (HTTPS). Routes are checked top to bottom."""

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        self._route("GET")

    def do_PUT(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        self._route("PUT")

    def _route(self, method: str) -> None:
        tv = self.server.tv  # type: ignore[attr-defined]
        body = self._body() if method == "PUT" else None
        path = urllib.parse.urlsplit(self.path).path
        headers = {
            "AUTH": self.headers.get("AUTH"),
            "Content-Type": self.headers.get("Content-Type"),
        }
        tv.requests.append((method, path, headers, body))

        if method == "GET" and path == "/state/device/deviceinfo":
            return self._send(200, _success(ITEMS=[{"VALUE": DEVICE_VALUE}]))
        if method == "PUT" and path == "/pairing/start":
            return self._send(
                200,
                _success(ITEM={"CHALLENGE_TYPE": CHALLENGE_TYPE, "PAIRING_REQ_TOKEN": PAIRING_REQ_TOKEN}),
            )
        if method == "PUT" and path == "/pairing/pair":
            if body == PAIR_BODY:
                return self._send(200, _success(ITEM={"AUTH_TOKEN": AUTH_TOKEN}))
            return self._send(400, _status("PAIRING_DENIED", "Incorrect PIN"))
        if method == "PUT" and path == "/pairing/cancel":
            return self._send(200, _success())

        if path.startswith("/menu_native/"):
            if headers["AUTH"] != AUTH_TOKEN or not tv.token_valid:
                return self._send(403, _status("REQUIRES_PAIRING", "Pairing is required"))
            if method == "GET" and (path == MENU_ROOT or path.startswith(MENU_ROOT + "/")):
                return self._menu_get(tv, path[len(MENU_ROOT):].lstrip("/"), True)
            if method == "GET" and (path == STATIC_ROOT or path.startswith(STATIC_ROOT + "/")):
                return self._menu_get(tv, path[len(STATIC_ROOT):].lstrip("/"), False)
            if method == "PUT" and path.startswith(MENU_ROOT + "/"):
                return self._menu_put(tv, path[len(MENU_ROOT) + 1:], body)

        return self._send(200, _status("URI_NOT_FOUND", "No such path"))

    def _menu_get(self, tv: "MockTV", rel: str, dynamic: bool) -> None:
        if rel not in MENUS:
            return self._send(200, _status("URI_NOT_FOUND", "No such menu"))
        items = []  # type: List[Dict[str, Any]]
        for template in MENUS[rel]:
            if dynamic:
                item = {k: v for k, v in template.items() if k != "ELEMENTS"}
                stored = tv.values.get(_key(rel, str(template["CNAME"])))
                if stored is not None:
                    item["VALUE"] = stored[0]
                    item["HASHVAL"] = stored[1]
            else:
                item = {k: v for k, v in template.items() if k not in ("VALUE", "HASHVAL")}
            items.append(item)
        return self._send(200, _success(ITEMS=items))

    def _menu_put(self, tv: "MockTV", rel: str, body: Any) -> None:
        menu_path, _, cname = rel.rpartition("/")
        key = _key(menu_path, cname)
        if key not in tv.values:
            return self._send(200, _status("URI_NOT_FOUND", "No such item"))
        if tv.refuse_writes:
            return self._send(200, _status("INVALID_PARAMETER", "Refused"))
        sent = body if isinstance(body, dict) else {}
        if sent.get("HASHVAL") != tv.values[key][1]:
            return self._send(200, _status("INVALID_PARAMETER", "Stale HASHVAL"))
        if not tv.ignore_writes:
            tv.values[key] = [sent.get("VALUE"), tv.values[key][1] + 1]
        return self._send(200, _success())


class CastHandler(_QuietHandler):
    """The Google Cast setup server on plain HTTP (the TV's port 8008).

    Like the real TV, it answers reads and refuses every write with 403.
    """

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        tv = self.server.tv  # type: ignore[attr-defined]
        body = self._body()
        tv.cast_requests.append(("GET", self.path, body))
        path = urllib.parse.urlsplit(self.path).path
        if path == EUREKA_INFO_PATH:
            reply = {"opt_in": dict(tv.opt_in), "device_info": {"mac_address": MAC}}
            return self._send(200, reply)
        return self._send_empty(404)

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        tv = self.server.tv  # type: ignore[attr-defined]
        body = self._body()
        tv.cast_requests.append(("POST", self.path, body))
        return self._send_empty(403)


class CastSecureHandler(_QuietHandler):
    """The Google Cast setup server on HTTPS (the TV's port 8443).

    Only the opt-out write is modelled. The real TV answers it 200 with an
    empty body, and applies it.
    """

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        tv = self.server.tv  # type: ignore[attr-defined]
        body = self._body()
        tv.cast_secure_requests.append(("POST", self.path, body))
        path = urllib.parse.urlsplit(self.path).path
        if path != SET_EUREKA_INFO_PATH:
            return self._send_empty(404)
        if tv.cast_applies_writes and body == CAST_OPT_OUT_BODY:
            tv.opt_in.update(body["opt_in"])
        return self._send_empty(200)


class MockTV:
    """Both mock servers on 127.0.0.1, with the state the tests drive."""

    def __init__(self, cert: str, key: str) -> None:
        self.cert = cert
        self.key = key
        self.values = {
            "picture/picture_mode": ["Calibrated", 303],
            "admin_and_privacy/viewing_data": ["On", 101],
            "admin_and_privacy/advertising/limit_ad_tracking": ["Off", 202],
        }  # type: Dict[str, List[Any]]
        self.token_valid = True
        self.refuse_writes = False
        self.ignore_writes = False
        self.cast_applies_writes = True
        self.opt_in = {"crash": True, "opencast": False, "stats": True}  # type: Dict[str, bool]
        self.requests = []  # type: List[Tuple[str, str, Dict[str, Optional[str]], Any]]
        self.cast_requests = []  # type: List[Tuple[str, str, Any]]
        self.cast_secure_requests = []  # type: List[Tuple[str, str, Any]]
        self._smartcast = None  # type: Optional[http.server.ThreadingHTTPServer]
        self._cast = None  # type: Optional[http.server.ThreadingHTTPServer]
        self._cast_secure = None  # type: Optional[http.server.ThreadingHTTPServer]
        self.smartcast_port = 0
        self.cast_port = 0
        self.cast_secure_port = 0

    def start(self) -> None:
        self._smartcast = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SmartCastHandler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.cert, self.key)
        self._smartcast.socket = ctx.wrap_socket(self._smartcast.socket, server_side=True)
        self._cast = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CastHandler)
        self._cast_secure = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CastSecureHandler)
        self._cast_secure.socket = ctx.wrap_socket(self._cast_secure.socket, server_side=True)
        for server in (self._smartcast, self._cast, self._cast_secure):
            server.tv = self  # the handlers reach the MockTV as self.server.tv
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.smartcast_port = self._smartcast.server_address[1]
        self.cast_port = self._cast.server_address[1]
        self.cast_secure_port = self._cast_secure.server_address[1]

    def stop(self) -> None:
        for server in (self._smartcast, self._cast, self._cast_secure):
            server.shutdown()
            server.server_close()
