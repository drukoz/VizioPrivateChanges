"""Writes the home-screen golden file the Kotlin HomeBuilder test compares against (RUK M2-T3).

Run from the repository root: python3 android/scripts/golden/make_home_golden.py
It reads Plex only through tests/fake_pms.py (the captured fixtures); it never opens a socket.
Only the Plex rows and the notices are compared: the Fire TV app builds its own app row.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from tests.fake_pms import FakePMS  # noqa: E402
from vizio_privacy.dashboard.service import DashboardService  # noqa: E402
from vizio_privacy.plex import PlexClient  # noqa: E402

PLEX_URL = "http://127.0.0.1:32400"
OUT_FILE = os.path.join(ROOT, "android", "app", "src", "test", "resources", "home_golden", "home_rows.json")


def offline_transport(method: str, url: str, headers: Dict[str, str], body: Optional[str]) -> Any:
    raise OSError("connection refused")


def rows_and_notices(transport: Any) -> Dict[str, Any]:
    service = DashboardService(PlexClient(PLEX_URL, transport=transport), tv=None)  # type: ignore[arg-type]
    home = service.home().to_json()
    return {"rows": home["rows"], "notices": home["notices"]}


def golden() -> Dict[str, Any]:
    return {"online": rows_and_notices(FakePMS()), "offline": rows_and_notices(offline_transport)}


def render(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as handle:
        handle.write(render(golden()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
