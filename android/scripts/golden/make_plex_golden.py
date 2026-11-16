"""Writes the Plex client golden file the Kotlin tests compare against (RUK M2-T2).

Run from the repository root: python3 android/scripts/golden/make_plex_golden.py
It reads Plex only through tests/fake_pms.py (the captured fixtures); it never opens a socket.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from typing import Any, Dict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from tests.fake_pms import FakePMS  # noqa: E402
from vizio_privacy.plex import PlexClient, PlexError  # noqa: E402

PLEX_URL = "http://127.0.0.1:32400"
OUT_FILE = os.path.join(ROOT, "android", "app", "src", "test", "resources", "plex_golden", "plex_client.json")


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {key: plain(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)  # IntEnum -> its number
    return value


def golden() -> Dict[str, Any]:
    plex = PlexClient(PLEX_URL, transport=FakePMS())
    machine, version = plex.identity()
    out = {
        "identity": {"machine_identifier": machine, "version": version},
        "libraries": plain(plex.libraries()),
        "continue_watching": plain(plex.continue_watching(20)),
        "section_hubs_1": plain(plex.section_hubs(1, 20)),
        "section_hubs_2": plain(plex.section_hubs(2, 20)),
        "item_4617": plain(plex.item("4617")),
        "item_24339": plain(plex.item("24339")),
        "item_4516": plain(plex.item("4516")),
        "next_episode_4516": plain(plex.next_episode("4516")),
        "next_episode_19258": plain(plex.next_episode("19258")),
        "next_episode_4617": plain(plex.next_episode("4617")),
        "image_url": plex.image_url("/library/metadata/1/thumb/2?x=a b", 240, 360),
    }  # type: Dict[str, Any]
    try:
        plex.item("999")
        out["item_999_status"] = None
    except PlexError as error:
        out["item_999_status"] = error.status
    return out


def render(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as handle:
        handle.write(render(golden()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
