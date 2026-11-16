"""VIZIO SmartCast local API client: transport, response envelope and enums."""

from __future__ import annotations

import enum
import http.client
import json
import ssl
import urllib.parse
from collections import namedtuple
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

Response = namedtuple("Response", ["status", "body"])


class ResultStatus(enum.IntEnum):
    SUCCESS = 0
    REQUIRES_PAIRING = 1
    INVALID_PARAMETER = 2
    URI_NOT_FOUND = 3
    UNKNOWN = 4

    @classmethod
    def from_text(cls, text: Optional[str]) -> "ResultStatus":
        if text is None:
            return cls.UNKNOWN
        mapped = {
            "SUCCESS": cls.SUCCESS,
            "REQUIRES_PAIRING": cls.REQUIRES_PAIRING,
            "INVALID_PARAMETER": cls.INVALID_PARAMETER,
            "URI_NOT_FOUND": cls.URI_NOT_FOUND,
        }
        return mapped.get(text.upper().strip(), cls.UNKNOWN)


class ItemType(enum.IntEnum):
    MENU = 0
    LIST = 1
    SLIDER = 2
    VALUE = 3
    LIST_X = 4
    UNKNOWN = 5

    @classmethod
    def from_text(cls, text: Optional[str]) -> "ItemType":
        if text is None:
            return cls.UNKNOWN
        mapped = {
            "T_MENU_V1": cls.MENU,
            "T_LIST_V1": cls.LIST,
            "T_VALUE_ABS_V1": cls.SLIDER,
            "T_VALUE_V1": cls.VALUE,
            "T_LIST_X_V1": cls.LIST_X,
        }
        return mapped.get(text.upper().strip(), cls.UNKNOWN)


def _ci_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Case-insensitive dictionary lookup."""
    if not isinstance(d, dict):
        return default
    lowered = {str(k).lower(): v for k, v in d.items()}
    return lowered.get(key.lower(), default)


class SmartCastError(Exception):
    def __init__(self, result: ResultStatus, detail: str = "") -> None:
        self.result = result
        self.detail = detail
        super().__init__("{}: {}".format(result.name, detail))


def default_transport(timeout: float = 5.0) -> Callable[..., Response]:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    def transport(method: str, url: str, headers: Dict[str, str], body: Optional[str]) -> Response:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
        target = parts.path + ("?" + parts.query if parts.query else "")
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ssl_ctx)
        try:
            conn.request(method, target, body=body, headers=headers)
            resp = conn.getresponse()
            return Response(resp.status, resp.read().decode("utf-8"))
        finally:
            conn.close()

    return transport


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Item:
    cname: str = ""
    name: Optional[str] = None
    type: ItemType = ItemType.UNKNOWN
    value: Any = None
    hashval: Optional[int] = None
    elements: List[str] = field(default_factory=list)
    minimum: Optional[int] = None
    maximum: Optional[int] = None
    center: Optional[int] = None

    @classmethod
    def from_json(cls, obj: Dict[str, Any]) -> "Item":
        elements = _ci_get(obj, "ELEMENTS", [])
        if not isinstance(elements, list):
            elements = []
        return cls(
            cname=str(_ci_get(obj, "CNAME", "") or ""),
            name=_ci_get(obj, "NAME"),
            type=ItemType.from_text(_ci_get(obj, "TYPE")),
            value=_ci_get(obj, "VALUE"),
            hashval=_as_int(_ci_get(obj, "HASHVAL")),
            elements=[str(e) for e in elements],
            minimum=_as_int(_ci_get(obj, "MINIMUM")),
            maximum=_as_int(_ci_get(obj, "MAXIMUM")),
            center=_as_int(_ci_get(obj, "CENTER")),
        )


@dataclass
class DeviceInfo:
    model_name: Optional[str] = None
    api_version: Optional[str] = None
    sc_info: Optional[str] = None
    settings_root: Optional[str] = None
    cast_name: Optional[str] = None
    inputs: List[str] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    binaries: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: Dict[str, Any]) -> "DeviceInfo":
        inputs = _ci_get(value, "INPUTS", [])
        if not isinstance(inputs, list):
            inputs = []
        capabilities = _ci_get(value, "CAPABILITIES", {})
        if not isinstance(capabilities, dict):
            capabilities = {}
        binaries = _ci_get(value, "BINARIES", {})
        if not isinstance(binaries, dict):
            binaries = {}
        return cls(
            model_name=_ci_get(value, "MODEL_NAME"),
            api_version=_ci_get(value, "API_VERSION"),
            sc_info=_ci_get(value, "SC_INFO"),
            settings_root=_ci_get(value, "SETTINGS_ROOT"),
            cast_name=_ci_get(value, "CAST_NAME"),
            inputs=[str(i) for i in inputs],
            capabilities={str(k): v for k, v in capabilities.items()},
            binaries={str(k): str(v) for k, v in binaries.items()},
        )


class PowerState(enum.IntEnum):
    STANDBY = 0
    ON = 1
    UNKNOWN = 2


class RemoteKey(enum.IntEnum):
    DOWN = 0
    LEFT = 1
    OK = 2
    RIGHT = 3
    UP = 4
    BACK = 5
    HOME = 6
    EXIT = 7


# (CODESET, CODE) for each key, from pyvizio const.py DEVICE_CONFIGS["tv"].key_codes.
KEY_CODES = {
    RemoteKey.DOWN: (3, 0),
    RemoteKey.LEFT: (3, 1),
    RemoteKey.OK: (3, 2),
    RemoteKey.RIGHT: (3, 7),
    RemoteKey.UP: (3, 8),
    RemoteKey.BACK: (4, 0),
    RemoteKey.HOME: (4, 15),
    RemoteKey.EXIT: (9, 0),
}  # type: Dict[RemoteKey, Tuple[int, int]]


@dataclass(frozen=True)
class AppConfig:
    name_space: int
    app_id: str
    message: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return {"MESSAGE": self.message, "NAME_SPACE": self.name_space, "APP_ID": self.app_id}

    @classmethod
    def from_json(cls, value: Any) -> Optional["AppConfig"]:
        """None unless value is a dict holding NAME_SPACE and APP_ID (keys read case-insensitively)."""
        if not isinstance(value, dict):
            return None
        name_space = _as_int(_ci_get(value, "NAME_SPACE"))
        app_id = _ci_get(value, "APP_ID")
        if name_space is None or app_id is None:
            return None
        message = _ci_get(value, "MESSAGE")
        return cls(
            name_space=name_space,
            app_id=str(app_id),
            message=None if message is None else str(message),
        )


@dataclass
class InputState:
    name: str      # current_input VALUE, e.g. "SMARTCAST" or "HDMI-2"
    hashval: int


@dataclass
class InputInfo:
    cname: str     # "hdmi2"
    name: str      # "HDMI-2": the value set_input takes
    label: str     # VALUE.NAME, e.g. "Fire TV Stick"; NAME when VALUE.NAME is missing


class SmartCastClient:
    def __init__(
        self,
        host: str,
        transport: Optional[Callable] = None,
        auth_token: Optional[str] = None,
        port: int = 7345,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.transport = transport if transport is not None else default_transport()

    def _request(
        self, method: str, path: str, body: Optional[dict] = None, auth: bool = False
    ) -> Dict[str, Any]:
        url = "https://{}:{}{}".format(self.host, self.port, path)
        headers = {}  # type: Dict[str, str]
        if method.upper() == "PUT":
            headers["Content-Type"] = "application/json"
        if auth and self.auth_token:
            headers["AUTH"] = self.auth_token
        text = json.dumps(body) if body is not None else None
        response = self.transport(method.upper(), url, headers, text)
        raw = response.body if response.body is not None else ""
        try:
            parsed = json.loads(raw) if raw.strip() else None
        except ValueError:
            parsed = None
        if not isinstance(parsed, dict):
            raise SmartCastError(
                ResultStatus.UNKNOWN, "HTTP {}: response is not JSON".format(response.status)
            )
        status = _ci_get(parsed, "STATUS", {})
        if not isinstance(status, dict):
            status = {}
        result = ResultStatus.from_text(_ci_get(status, "RESULT"))
        if result is not ResultStatus.SUCCESS:
            detail = _ci_get(status, "DETAIL", "")
            raise SmartCastError(result, str(detail) if detail is not None else "")
        return parsed

    def get(self, path: str, auth: bool = False) -> Dict[str, Any]:
        return self._request("GET", path, auth=auth)

    def put(self, path: str, body: dict, auth: bool = False) -> Dict[str, Any]:
        return self._request("PUT", path, body=body, auth=auth)

    def get_device_info(self) -> DeviceInfo:
        envelope = self.get("/state/device/deviceinfo", auth=False)
        items = _ci_get(envelope, "ITEMS", [])
        if not isinstance(items, list) or not items:
            return DeviceInfo()
        first = _ci_get(items[0], "VALUE", {})
        if not isinstance(first, dict):
            return DeviceInfo()
        return DeviceInfo.from_value(first)

    def get_items(self, path: str, auth: bool = True) -> List[Item]:
        envelope = self.get(path, auth=auth)
        items = _ci_get(envelope, "ITEMS", [])
        if not isinstance(items, list):
            return []
        return [Item.from_json(item) for item in items if isinstance(item, dict)]

    def power_state(self) -> PowerState:
        envelope = self.get("/state/device/power_mode", auth=True)
        items = _ci_get(envelope, "ITEMS", [])
        if not isinstance(items, list) or not items:
            return PowerState.UNKNOWN
        value = _as_int(_ci_get(items[0], "VALUE"))
        if value == 0:
            return PowerState.STANDBY
        if value == 1:
            return PowerState.ON
        return PowerState.UNKNOWN

    def current_app(self) -> Optional[AppConfig]:
        envelope = self.get("/app/current", auth=True)
        item = _ci_get(envelope, "ITEM")
        value = _ci_get(item, "VALUE") if isinstance(item, dict) else None
        return AppConfig.from_json(value)

    def launch_app(self, config: AppConfig) -> None:
        self.put("/app/launch", {"VALUE": config.to_json()}, auth=True)

    def press_key(self, key: RemoteKey) -> None:
        codeset, code = KEY_CODES[key]
        body = {"KEYLIST": [{"CODESET": codeset, "CODE": code, "ACTION": "KEYPRESS"}]}
        self.put("/key_command/", body, auth=True)

    def current_input(self) -> InputState:
        envelope = self.get(
            "/menu_native/dynamic/tv_settings/devices/current_input", auth=True
        )
        items = _ci_get(envelope, "ITEMS", [])
        if not isinstance(items, list) or not items:
            raise SmartCastError(ResultStatus.UNKNOWN, "no current input")
        value = _ci_get(items[0], "VALUE")
        hashval = _as_int(_ci_get(items[0], "HASHVAL"))
        if value is None or hashval is None:
            raise SmartCastError(ResultStatus.UNKNOWN, "no current input")
        return InputState(name=str(value), hashval=hashval)

    def list_inputs(self) -> List[InputInfo]:
        envelope = self.get(
            "/menu_native/dynamic/tv_settings/devices/name_input", auth=True
        )
        items = _ci_get(envelope, "ITEMS", [])
        if not isinstance(items, list):
            return []
        result = []  # type: List[InputInfo]
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(_ci_get(item, "TYPE", "")).upper().strip() != "T_DEVICE_V1":
                continue
            name = str(_ci_get(item, "NAME", "") or "")
            value = _ci_get(item, "VALUE")
            label = _ci_get(value, "NAME") if isinstance(value, dict) else None
            label = str(label) if label is not None else name
            result.append(
                InputInfo(cname=str(_ci_get(item, "CNAME", "") or ""), name=name, label=label)
            )
        return result

    def set_input(self, name: str) -> None:
        current = self.current_input()
        body = {"REQUEST": "MODIFY", "VALUE": name, "HASHVAL": current.hashval}
        self.put(
            "/menu_native/dynamic/tv_settings/devices/current_input", body, auth=True
        )
