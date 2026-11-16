"""The apps the dashboard can put on its bottom row, and how to open each one.

Launch values come from VIZIO's public catalog (app_availability_prod.json, read
2026-11-16) for this TV: chip MT5583, firmware 3.710.30.5. The Fire TV Stick is
not an app: it is opened by switching the TV's input to HDMI-2.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


class AppId(enum.IntEnum):
    PLEX = 0
    NETFLIX = 1
    YOUTUBE = 2
    PRIME_VIDEO = 3
    DISNEY_PLUS = 4
    HULU = 5
    HBO_MAX = 6
    CRUNCHYROLL = 7
    APPLE_TV_PLUS = 8
    PARAMOUNT_PLUS = 9
    PEACOCK = 10
    TUBI = 11
    YOUTUBE_TV = 12
    FIRE_TV_STICK = 13
    VIZIO_HOME = 14


class AppKind(enum.IntEnum):
    LAUNCH = 0   # opened with PUT /app/launch
    INPUT = 1    # opened by switching the TV's input


@dataclass(frozen=True)
class AppEntry:
    id: AppId
    title: str                         # the tile's label
    kind: AppKind
    name_space: Optional[int] = None   # LAUNCH only
    app_id: Optional[str] = None       # LAUNCH only
    message: Optional[str] = None      # LAUNCH only
    input_name: Optional[str] = None   # INPUT only, e.g. "HDMI-2"
    catalog_id: Optional[str] = None   # VIZIO catalog id
    icon_url: Optional[str] = None     # VIZIO catalog icon


ICON = "https://image-api-prod.smartcasttv.com/api/brandimage/{}/app-row-square?from=csapp"

APPS: Tuple[AppEntry, ...] = (
    AppEntry(AppId.PLEX, "Plex", AppKind.LAUNCH,
             name_space=2, app_id="9",
             catalog_id="40", icon_url=ICON.format(900000013)),
    AppEntry(AppId.NETFLIX, "Netflix", AppKind.LAUNCH,
             name_space=3, app_id="1",
             catalog_id="34", icon_url=ICON.format(500000018)),
    AppEntry(AppId.YOUTUBE, "YouTube", AppKind.LAUNCH,
             name_space=5, app_id="1",
             catalog_id="44", icon_url=ICON.format(500000006)),
    AppEntry(AppId.PRIME_VIDEO, "Prime Video", AppKind.LAUNCH,
             name_space=3, app_id="3",
             catalog_id="33", icon_url=ICON.format(900000086)),
    AppEntry(AppId.DISNEY_PLUS, "Disney+", AppKind.LAUNCH,
             name_space=2, app_id="75",
             catalog_id="76", icon_url=ICON.format(900000043)),
    AppEntry(AppId.HULU, "Hulu", AppKind.LAUNCH,
             name_space=2, app_id="3",
             catalog_id="19", icon_url=ICON.format(500000015)),
    AppEntry(AppId.HBO_MAX, "HBO Max", AppKind.LAUNCH,
             name_space=2, app_id="128",
             catalog_id="128", icon_url=ICON.format(900000299)),
    AppEntry(AppId.CRUNCHYROLL, "Crunchyroll", AppKind.LAUNCH,
             name_space=2, app_id="481",
             catalog_id="2481", icon_url=ICON.format(900000694)),
    AppEntry(AppId.APPLE_TV_PLUS, "Apple TV+", AppKind.LAUNCH,
             name_space=3, app_id="4",
             catalog_id="91", icon_url=ICON.format(900000049)),
    AppEntry(AppId.PARAMOUNT_PLUS, "Paramount+", AppKind.LAUNCH,
             name_space=2, app_id="37",
             catalog_id="9", icon_url=ICON.format(500000049)),
    AppEntry(AppId.PEACOCK, "Peacock", AppKind.LAUNCH,
             name_space=2, app_id="88",
             catalog_id="88", icon_url=ICON.format(900000062)),
    AppEntry(AppId.TUBI, "Tubi", AppKind.LAUNCH,
             name_space=2, app_id="61",
             catalog_id="90", icon_url=ICON.format(900000036)),
    AppEntry(AppId.YOUTUBE_TV, "YouTube TV", AppKind.LAUNCH,
             name_space=5, app_id="3",
             catalog_id="45", icon_url=ICON.format(900000019)),
    AppEntry(AppId.FIRE_TV_STICK, "Fire TV Stick", AppKind.INPUT,
             input_name="HDMI-2"),
    AppEntry(AppId.VIZIO_HOME, "VIZIO Home", AppKind.LAUNCH,
             name_space=4, app_id="1",
             message="http://127.0.0.1:12345/scfs/sctv/main.html"),
)

DEFAULT_APPS = (AppId.PLEX, AppId.NETFLIX, AppId.YOUTUBE, AppId.PRIME_VIDEO,
                AppId.DISNEY_PLUS, AppId.FIRE_TV_STICK, AppId.VIZIO_HOME)  # type: Tuple[AppId, ...]

_BY_ID: Dict[AppId, AppEntry] = {entry.id: entry for entry in APPS}

# Lower-case enum member name or title -> app id, for parse_app_names.
_BY_NAME: Dict[str, AppId] = {
    key: entry.id
    for entry in APPS
    for key in (entry.id.name.lower(), entry.title.lower())
}


def get_app(app_id: AppId) -> AppEntry:
    """The entry with that id. KeyError if the table has none (it always does)."""
    return _BY_ID[app_id]


def parse_app_names(names: List[str]) -> List[AppId]:
    """App ids named by the owner's words: enum member names or titles,
    case-insensitive, spaces stripped. Keeps the order given, drops repeats.
    An unknown name raises ValueError naming the first unknown one."""
    picked: List[AppId] = []
    for name in names:
        app_id = _BY_NAME.get(name.strip().lower())
        if app_id is None:
            raise ValueError("unknown app: {}".format(name))
        if app_id not in picked:
            picked.append(app_id)
    return picked
