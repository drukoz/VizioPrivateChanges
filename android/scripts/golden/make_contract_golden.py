"""Writes the contract golden files the Kotlin tests compare against (RUK M2-T1).

Run from the repository root: python3 android/scripts/golden/make_contract_golden.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from vizio_privacy.dashboard.model import (  # noqa: E402
    Action, ActionKind, ActionResult, Home, ImageShape, Row, RowKind, Tile, image_path,
)

OUT_DIR = os.path.join(ROOT, "android", "app", "src", "test", "resources", "contract")

IMAGE_CASES = [
    ("/library/metadata/4617/thumb/1700000000", 384, 216),
    ("/library/metadata/2/thumb/1?x=a b&c=ü*~", 240, 360),
    ("/library/metadata/9/art/1+2", 1920, 1080),
]


def golden_home() -> Home:
    return Home(
        rows=[
            Row("continueWatching", "Continue Watching", RowKind.CONTINUE_WATCHING, [
                Tile("plex:4617", "Show A", "S1 · E2 · Episode B",
                     image_path(IMAGE_CASES[0][0], 384, 216), ImageShape.WIDE, 0.33333,
                     Action(ActionKind.PLAY_PLEX, "4617")),
                Tile("plex:24339", "Movie C", "2024", None, ImageShape.WIDE, 1.25,
                     Action(ActionKind.PLAY_PLEX, "24339")),
                Tile("plex:1", "Movie D", None, None, ImageShape.WIDE, -0.2,
                     Action(ActionKind.PLAY_PLEX, "1")),
            ]),
            Row("hub:movie.recentlyadded.1", "Recently Added Movies", RowKind.PLEX_HUB, [
                Tile("plex:2", "Movie E", None, image_path(IMAGE_CASES[1][0], 240, 360),
                     ImageShape.POSTER, None, Action(ActionKind.PLAY_PLEX, "2")),
            ]),
        ],
        apps=[
            Tile("app:com.netflix.ninja", "Netflix", None, "/appicon?pkg=com.netflix.ninja",
                 ImageShape.ICON, None, Action(ActionKind.OPEN_APP, "com.netflix.ninja")),
            Tile("app:amazon-home", "Amazon Home", None, None, ImageShape.ICON, None,
                 Action(ActionKind.AMAZON_HOME, "com.amazon.tv.launcher")),
        ],
        notices=["Plex is not answering; showing apps only."],
    )


def golden_files() -> Dict[str, Any]:
    return {
        "home.json": golden_home().to_json(),
        "action_results.json": [ActionResult(True, "Opening Netflix").to_json(),
                                ActionResult(False, "Plex is not installed").to_json()],
        "image_paths.json": [{"p": p, "w": w, "h": h, "path": image_path(p, w, h)}
                             for (p, w, h) in IMAGE_CASES],
    }


def render(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, value in golden_files().items():
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as handle:
            handle.write(render(value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
