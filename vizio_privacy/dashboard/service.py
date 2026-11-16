"""Builds the dashboard home screen from Plex and the app table, and runs actions.

Rows: Continue Watching first, then the Plex hub rows in HUB_ORDER, at most
MAX_ROWS in all. The app row comes from apps.py. A Plex that does not answer
leaves the apps alone with one notice; a TV that does not answer gives ok: false.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from vizio_privacy.api import AppConfig, SmartCastClient, SmartCastError
from vizio_privacy.apps import DEFAULT_APPS, AppId, AppKind, get_app
from vizio_privacy.dashboard.model import (
    Action,
    ActionKind,
    ActionResult,
    Home,
    ImageShape,
    Row,
    RowKind,
    Tile,
    image_path,
)
from vizio_privacy.plex import (
    Hub,
    Library,
    LibraryType,
    PlexClient,
    PlexError,
    PlexItem,
    PlexItemType,
)

HUB_ORDER = (
    "movie.recentlyadded",
    "tv.recentlyadded",
    "tv.startwatching",
    "movie.topunwatched",
    "tv.moreingenre",
    "movie.genre",
    "tv.rediscover",
    "tv.toprated",
)  # type: Tuple[str, ...]

MAX_ROWS = 8
WIDE_SIZE = (384, 216)
POSTER_SIZE = (240, 360)
PLEX_OFFLINE_NOTICE = "Plex is not answering; showing apps only."

SEP = " \u00b7 "


def _titles(item: PlexItem) -> Tuple[str, Optional[str]]:
    """The tile's title and subtitle for one Plex item."""
    if item.type is PlexItemType.MOVIE:
        year = str(item.year) if item.year is not None else None
        return item.title, year
    if item.type is PlexItemType.EPISODE:
        title = item.show_title if item.show_title is not None else item.title
        if item.season_index is not None and item.episode_index is not None:
            subtitle = "S%d \u00b7 E%d \u00b7 %s" % (
                item.season_index,
                item.episode_index,
                item.title,
            )
        else:
            subtitle = item.title
        return title, subtitle
    return item.title, None


def _image(item: PlexItem, shape: ImageShape) -> Optional[str]:
    """The tile's image URL, or None when Plex has no servable picture for it."""
    if shape is ImageShape.WIDE:
        if item.type is PlexItemType.EPISODE:
            path = item.thumb if item.thumb else item.grandparent_art
        else:
            path = item.art
        width, height = WIDE_SIZE
    else:
        if item.type is PlexItemType.EPISODE:
            path = item.grandparent_thumb if item.grandparent_thumb else item.thumb
        else:
            path = item.thumb
        width, height = POSTER_SIZE
    if path is None or not path.startswith("/library/"):
        return None
    return image_path(path, width, height)


def plex_tile(item: PlexItem, shape: ImageShape) -> Tile:
    """The tile for one Plex item: an episode shows under its show's name."""
    title, subtitle = _titles(item)
    progress = None
    if item.view_offset_ms is not None and item.duration_ms is not None:
        if item.duration_ms > 0:
            progress = item.view_offset_ms / item.duration_ms
    return Tile(
        id="plex:" + item.rating_key,
        title=title,
        subtitle=subtitle,
        image=_image(item, shape),
        shape=shape,
        progress=progress,
        action=Action(ActionKind.PLAY_PLEX, item.rating_key),
    )


def app_tile(app_id: AppId) -> Tile:
    """The tile for one app; its action opens the app, the input, or VIZIO Home."""
    entry = get_app(app_id)
    if app_id is AppId.VIZIO_HOME:
        kind = ActionKind.VIZIO_HOME
    elif entry.kind is AppKind.INPUT:
        kind = ActionKind.SWITCH_INPUT
    else:
        kind = ActionKind.OPEN_APP
    return Tile(
        id="app:%d" % int(app_id),
        title=entry.title,
        subtitle=None,
        image="/static/apps/%d.png" % int(app_id),
        shape=ImageShape.ICON,
        progress=None,
        action=Action(kind, str(int(app_id))),
    )


def _hub_rank(identifier: str) -> Optional[int]:
    """The index of the prefix from HUB_ORDER the hub matches, None for no match."""
    for rank, prefix in enumerate(HUB_ORDER):
        if identifier == prefix or identifier.startswith(prefix + "."):
            return rank
    return None


def _hub_title(hub: Hub, library: Library) -> str:
    """The hub's title, with the library's name added when it does not name it."""
    if library.title.lower() in hub.title.lower():
        return hub.title
    return hub.title + SEP + library.title


def _require_digits(target: str) -> str:
    if not (target.isascii() and target.isdigit()):
        raise ValueError("action target must be digits only, got %r" % (target,))
    return target


class DashboardService:
    def __init__(
        self,
        plex: PlexClient,
        tv: SmartCastClient,
        apps: Sequence[AppId] = DEFAULT_APPS,
        play: Optional[Callable[[str], ActionResult]] = None,
    ) -> None:
        self.plex = plex
        self.tv = tv
        self.apps = tuple(apps)  # type: Tuple[AppId, ...]
        self.play = play

    def home(self) -> Home:
        notices = []  # type: List[str]
        try:
            rows = self._plex_rows()
        except (PlexError, OSError):
            rows = []
            notices.append(PLEX_OFFLINE_NOTICE)
        apps = [app_tile(app_id) for app_id in self.apps]
        return Home(rows=rows[:MAX_ROWS], apps=apps, notices=notices)

    def _plex_rows(self) -> List[Row]:
        """The Plex rows; PlexError or OSError from the first two calls propagates."""
        rows = []  # type: List[Row]
        items = self.plex.continue_watching(20)
        if items:
            rows.append(
                Row(
                    id="continueWatching",
                    title="Continue Watching",
                    kind=RowKind.CONTINUE_WATCHING,
                    tiles=[plex_tile(item, ImageShape.WIDE) for item in items],
                )
            )
        candidates = []  # type: List[Tuple[int, int, Row]]
        for position, library in enumerate(self.plex.libraries()):
            if library.type not in (LibraryType.MOVIE, LibraryType.SHOW):
                continue
            try:
                hubs = self.plex.section_hubs(library.section_id, 20)
            except (PlexError, OSError):
                continue
            for hub in hubs:
                rank = _hub_rank(hub.identifier)
                if rank is None or not hub.items:
                    continue
                row = Row(
                    id="hub:" + hub.identifier,
                    title=_hub_title(hub, library),
                    kind=RowKind.PLEX_HUB,
                    tiles=[plex_tile(item, ImageShape.POSTER) for item in hub.items],
                )
                candidates.append((rank, position, row))
        candidates.sort(key=lambda entry: (entry[0], entry[1]))
        rows.extend(entry[2] for entry in candidates)
        return rows

    def run(self, action: Action) -> ActionResult:
        """Opens an app, switches to an input, opens VIZIO Home, or plays a Plex item."""
        kind = action.kind
        target = action.target
        if kind is ActionKind.PLAY_PLEX:
            _require_digits(target)
            if self.play is not None:
                return self.play(target)
            return self._open(AppId.PLEX)
        _require_digits(target)
        app_id = AppId(int(target))
        if app_id not in self.apps:
            raise ValueError("app %d is not in the dashboard's app row" % int(app_id))
        if kind is not app_tile(app_id).action.kind:
            raise ValueError(
                "app %d is opened with action kind %d, not %d"
                % (int(app_id), int(app_tile(app_id).action.kind), int(kind))
            )
        return self._open(app_id)

    def _open(self, app_id: AppId) -> ActionResult:
        entry = get_app(app_id)
        try:
            if entry.kind is AppKind.INPUT:
                self.tv.set_input(entry.input_name)
            else:
                self.tv.launch_app(AppConfig(entry.name_space, entry.app_id, entry.message))
        except (SmartCastError, OSError) as error:
            return ActionResult(False, "The TV did not respond: " + str(error))
        if entry.kind is AppKind.INPUT:
            return ActionResult(True, "Switching to " + entry.title)
        return ActionResult(True, "Opening " + entry.title)
