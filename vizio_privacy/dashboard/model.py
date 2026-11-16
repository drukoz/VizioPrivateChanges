"""The JSON the dashboard server sends to the TV page and accepts back.

Contract: docs/dashboard/plan.md, section "Contract: page <-> server".
Enums are integers on the wire; text appears only in labels.
"""

from __future__ import annotations

import enum
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class RowKind(enum.IntEnum):
    CONTINUE_WATCHING = 0
    PLEX_HUB = 1


class ActionKind(enum.IntEnum):
    PLAY_PLEX = 0
    OPEN_APP = 1
    SWITCH_INPUT = 2
    VIZIO_HOME = 3
    AMAZON_HOME = 4


class ImageShape(enum.IntEnum):
    POSTER = 0   # 2:3
    WIDE = 1     # 16:9
    ICON = 2     # app tile


CONTRACT_VERSION = 1
MAX_TARGET_LENGTH = 200


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    target: str

    def to_json(self) -> Dict[str, Any]:
        return {"kind": int(self.kind), "target": self.target}

    @classmethod
    def from_json(cls, value: Any) -> "Action":
        if not isinstance(value, dict):
            raise ValueError("action must be a dict, got %s" % type(value).__name__)
        if "kind" not in value:
            raise ValueError("action is missing 'kind'")
        kind = value["kind"]
        if isinstance(kind, bool) or not isinstance(kind, int):
            raise ValueError("action 'kind' must be an int, got %r" % (kind,))
        try:
            action_kind = ActionKind(kind)
        except ValueError:
            raise ValueError("action 'kind' is not an ActionKind value: %r" % (kind,))
        if "target" not in value:
            raise ValueError("action is missing 'target'")
        target = value["target"]
        if not isinstance(target, str):
            raise ValueError("action 'target' must be a str, got %r" % (target,))
        if not target.strip():
            raise ValueError("action 'target' is empty after strip()")
        if len(target) > MAX_TARGET_LENGTH:
            raise ValueError(
                "action 'target' is longer than %d characters" % MAX_TARGET_LENGTH
            )
        return cls(action_kind, target)


@dataclass
class Tile:
    id: str
    title: str
    subtitle: Optional[str]
    image: Optional[str]
    shape: ImageShape
    progress: Optional[float]
    action: Action

    def to_json(self) -> Dict[str, Any]:
        progress = self.progress
        if progress is not None:
            progress = round(max(0.0, min(1.0, progress)), 3)
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "image": self.image,
            "shape": int(self.shape),
            "progress": progress,
            "action": self.action.to_json(),
        }


@dataclass
class Row:
    id: str
    title: str
    kind: RowKind
    tiles: List[Tile]

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": int(self.kind),
            "tiles": [tile.to_json() for tile in self.tiles],
        }


@dataclass
class Home:
    rows: List[Row]
    apps: List[Tile]
    notices: List[str] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        return {
            "version": CONTRACT_VERSION,
            "rows": [row.to_json() for row in self.rows],
            "apps": [tile.to_json() for tile in self.apps],
            "notices": list(self.notices),
        }


@dataclass
class ActionResult:
    ok: bool
    message: str

    def to_json(self) -> Dict[str, Any]:
        return {"ok": self.ok, "message": self.message}


def image_path(plex_path: str, width: int, height: int) -> str:
    return "/img?p=" + urllib.parse.quote(plex_path, safe="") + "&w=%d&h=%d" % (
        width,
        height,
    )


def parse_image_query(query: str) -> Tuple[str, int, int]:
    """Validate the query string of GET /img (without the leading '?')."""
    params = urllib.parse.parse_qs(query)

    p_values = params.get("p")
    if p_values is None or len(p_values) != 1:
        raise ValueError("'p' must be present exactly once")
    p = p_values[0]
    if not p.startswith("/library/"):
        raise ValueError("'p' must start with /library/")
    if ".." in p:
        raise ValueError("'p' must not contain ..")
    if "://" in p:
        raise ValueError("'p' must not contain ://")

    w = _parse_side(params, "w", 1920)
    h = _parse_side(params, "h", 1080)
    return p, w, h


def _parse_side(params: Dict[str, List[str]], name: str, maximum: int) -> int:
    values = params.get(name)
    if values is None or len(values) != 1:
        raise ValueError("'%s' must be present exactly once" % name)
    raw = values[0]
    if not (raw.isascii() and raw.isdigit()):
        raise ValueError("'%s' must be digits only, got %r" % (name, raw))
    number = int(raw)
    if number < 1 or number > maximum:
        raise ValueError("'%s' must be from 1 to %d, got %d" % (name, maximum, number))
    return number
