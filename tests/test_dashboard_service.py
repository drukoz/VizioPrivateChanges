"""Tests for vizio_privacy.dashboard.service: rows, app tiles and actions.

Every test uses FakePMS or FakeRemoteTV; none opens a socket.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional, Tuple

from vizio_privacy.api import SmartCastClient
from vizio_privacy.apps import AppId
from vizio_privacy.dashboard.model import (
    Action,
    ActionKind,
    ActionResult,
    ImageShape,
    image_path,
)
from vizio_privacy.dashboard.service import (
    MAX_ROWS,
    PLEX_OFFLINE_NOTICE,
    DashboardService,
    app_tile,
    plex_tile,
)
from vizio_privacy.plex import PlexClient, PlexItem, PlexItemType
from tests.fake_pms import FakePMS
from tests.fakes import FakeRemoteTV

PLEX_URL = "http://plex.test:32400"
TV_HOST = "tv.test"


class DeadTransport:
    """A Plex transport that fails every call, as an unplugged server does."""

    def __call__(self, method: str, url: str, headers: Dict[str, str], body: Any) -> Any:
        raise OSError("connection refused")


def make_plex(transport: Any = None) -> PlexClient:
    return PlexClient(PLEX_URL, transport=transport if transport is not None else FakePMS())


def make_service(
    plex: Optional[PlexClient] = None,
    tv_transport: Optional[FakeRemoteTV] = None,
    apps: Optional[List[AppId]] = None,
    play: Any = None,
) -> Tuple[DashboardService, FakeRemoteTV]:
    tv = tv_transport if tv_transport is not None else FakeRemoteTV(power=1)
    kwargs = {}  # type: Dict[str, Any]
    if apps is not None:
        kwargs["apps"] = apps
    if play is not None:
        kwargs["play"] = play
    service = DashboardService(
        plex if plex is not None else make_plex(),
        SmartCastClient(TV_HOST, transport=tv, auth_token="tok"),
        **kwargs
    )
    return service, tv


def item(**fields: Any) -> PlexItem:
    """A PlexItem with empty defaults; fields override."""
    base = dict(
        rating_key="1",
        type=PlexItemType.OTHER,
        title="t",
        show_title=None,
        season_index=None,
        episode_index=None,
        year=None,
        thumb=None,
        art=None,
        parent_thumb=None,
        grandparent_thumb=None,
        grandparent_art=None,
        view_offset_ms=None,
        duration_ms=None,
        view_count=0,
        library_section_id=None,
        parent_rating_key=None,
        grandparent_rating_key=None,
    )  # type: Dict[str, Any]
    base.update(fields)
    return PlexItem(**base)


class HomeRowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service, self.tv = make_service()
        self.home = self.service.home()

    def row(self, row_id: str) -> Any:
        for row in self.home.rows:
            if row.id == row_id:
                return row
        raise AssertionError("no row with id " + row_id)

    def test_row_ids_in_order(self) -> None:
        self.assertEqual(
            [row.id for row in self.home.rows],
            [
                "continueWatching",
                "hub:movie.recentlyadded.1",
                "hub:tv.recentlyadded.2",
                "hub:tv.startwatching.2",
                "hub:movie.topunwatched.1",
                "hub:tv.moreingenre.2",
                "hub:movie.genre.1.297",
                "hub:tv.rediscover.2",
            ],
        )
        self.assertEqual(self.home.notices, [])
        self.assertEqual(len(self.home.rows), MAX_ROWS)

    def test_row_titles(self) -> None:
        self.assertEqual(
            self.row("hub:tv.startwatching.2").title, "Start Watching \u00b7 TV Shows"
        )
        self.assertEqual(
            self.row("hub:movie.recentlyadded.1").title, "Recently Added in Movies"
        )

    def test_first_continue_watching_tile(self) -> None:
        self.assertEqual(
            self.home.rows[0].tiles[0].to_json(),
            {
                "id": "plex:4617",
                "title": "grandparentTitle 31",
                "subtitle": "S4 \u00b7 E4 \u00b7 title 30",
                "shape": 1,
                "progress": 0.769,
                "image": image_path("/library/metadata/4617/thumb/1790131474", 384, 216),
                "action": {"kind": 0, "target": "4617"},
            },
        )

    def test_movie_tile_in_continue_watching(self) -> None:
        tile = self.home.rows[0].tiles[2]
        self.assertEqual(tile.title, "title 75")
        self.assertEqual(tile.subtitle, "1995")
        self.assertEqual(
            tile.image, image_path("/library/metadata/24339/art/1787303570", 384, 216)
        )

    def test_start_watching_show_without_thumb(self) -> None:
        tiles = {tile.id: tile for tile in self.row("hub:tv.startwatching.2").tiles}
        show = tiles["plex:20979"]
        self.assertIsNone(show.image)
        self.assertIsNone(show.subtitle)

    def test_row_kinds_and_shapes(self) -> None:
        self.assertEqual(int(self.home.rows[0].kind), 0)
        self.assertEqual(int(self.home.rows[1].kind), 1)
        self.assertEqual(int(self.home.rows[0].tiles[0].shape), int(ImageShape.WIDE))
        self.assertEqual(int(self.home.rows[1].tiles[0].shape), int(ImageShape.POSTER))

    def test_plex_offline_gives_apps_and_notice(self) -> None:
        service, _ = make_service(plex=make_plex(DeadTransport()))
        home = service.home()
        self.assertEqual(home.rows, [])
        self.assertEqual(home.notices, [PLEX_OFFLINE_NOTICE])
        self.assertEqual(
            [tile.id for tile in home.apps],
            ["app:0", "app:1", "app:2", "app:3", "app:4", "app:13", "app:14"],
        )


class PlexTileTests(unittest.TestCase):
    def test_thumb_outside_library_gives_no_image(self) -> None:
        show = item(type=PlexItemType.SHOW, title="T", thumb="/http/media/cover.jpg")
        tile = plex_tile(show, ImageShape.POSTER)
        self.assertIsNone(tile.image)
        self.assertEqual(tile.id, "plex:1")
        self.assertEqual(tile.action, Action(ActionKind.PLAY_PLEX, "1"))

    def test_episode_uses_grandparent_thumb_for_poster(self) -> None:
        episode = item(
            type=PlexItemType.EPISODE,
            title="E",
            show_title="S",
            season_index=1,
            episode_index=2,
            thumb="/library/metadata/9/thumb/1",
            grandparent_thumb="/library/metadata/8/thumb/1",
        )
        tile = plex_tile(episode, ImageShape.POSTER)
        self.assertEqual(
            tile.image, image_path("/library/metadata/8/thumb/1", 240, 360)
        )
        self.assertEqual(tile.subtitle, "S1 \u00b7 E2 \u00b7 E")

    def test_progress_needs_both_numbers(self) -> None:
        running = item(
            type=PlexItemType.MOVIE, title="M", view_offset_ms=500, duration_ms=1000
        )
        zero = item(type=PlexItemType.MOVIE, title="M", view_offset_ms=500, duration_ms=0)
        self.assertEqual(plex_tile(running, ImageShape.WIDE).progress, 0.5)
        self.assertIsNone(plex_tile(zero, ImageShape.WIDE).progress)


class AppTileTests(unittest.TestCase):
    def test_netflix_tile(self) -> None:
        self.assertEqual(
            app_tile(AppId.NETFLIX).to_json(),
            {
                "id": "app:1",
                "title": "Netflix",
                "subtitle": None,
                "image": "/static/apps/1.png",
                "shape": 2,
                "progress": None,
                "action": {"kind": 1, "target": "1"},
            },
        )

    def test_fire_tv_stick_is_a_switch_input(self) -> None:
        action = app_tile(AppId.FIRE_TV_STICK).action
        self.assertEqual(int(action.kind), int(ActionKind.SWITCH_INPUT))
        self.assertEqual(action.target, "13")

    def test_vizio_home_action(self) -> None:
        action = app_tile(AppId.VIZIO_HOME).action
        self.assertEqual(int(action.kind), int(ActionKind.VIZIO_HOME))
        self.assertEqual(action.target, "14")

    def test_home_apps_follow_the_apps_list(self) -> None:
        service, _ = make_service(apps=[AppId.NETFLIX, AppId.PLEX])
        home = service.home()
        self.assertEqual([tile.id for tile in home.apps], ["app:1", "app:0"])


class RunActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service, self.tv = make_service()

    def test_open_netflix(self) -> None:
        result = self.service.run(Action(ActionKind.OPEN_APP, "1"))
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Opening Netflix")
        self.assertEqual(
            self.tv.app, {"MESSAGE": None, "NAME_SPACE": 3, "APP_ID": "1"}
        )

    def test_switch_input_to_fire_tv_stick(self) -> None:
        result = self.service.run(Action(ActionKind.SWITCH_INPUT, "13"))
        self.assertTrue(result.ok)
        self.assertEqual(self.tv.input_value, "HDMI-2")
        self.assertEqual(result.message, "Switching to Fire TV Stick")

    def test_vizio_home_launch(self) -> None:
        result = self.service.run(Action(ActionKind.VIZIO_HOME, "14"))
        self.assertTrue(result.ok)
        self.assertEqual(
            self.tv.app,
            {
                "MESSAGE": "http://127.0.0.1:12345/scfs/sctv/main.html",
                "NAME_SPACE": 4,
                "APP_ID": "1",
            },
        )

    def test_bad_targets_raise_value_error(self) -> None:
        for kind, target in [
            (ActionKind.OPEN_APP, "13"),  # kind mismatch: it is an input
            (ActionKind.OPEN_APP, "99"),  # not an AppId
            (ActionKind.OPEN_APP, "abc"),  # not digits
            (ActionKind.PLAY_PLEX, "12a"),  # not digits
        ]:
            with self.subTest(kind=int(kind), target=target):
                with self.assertRaises(ValueError):
                    self.service.run(Action(kind, target))

    def test_app_not_in_apps_list_raises_value_error(self) -> None:
        service, _ = make_service(apps=[AppId.NETFLIX])
        with self.assertRaises(ValueError):
            service.run(Action(ActionKind.OPEN_APP, "2"))

    def test_play_plex_without_play_opens_the_plex_app(self) -> None:
        result = self.service.run(Action(ActionKind.PLAY_PLEX, "4617"))
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Opening Plex")
        self.assertEqual(
            self.tv.app, {"MESSAGE": None, "NAME_SPACE": 2, "APP_ID": "9"}
        )

    def test_play_plex_uses_the_play_callable(self) -> None:
        seen = []  # type: List[str]

        def play(target: str) -> ActionResult:
            seen.append(target)
            return ActionResult(True, "Playing 4617")

        service, tv = make_service(play=play)
        result = service.run(Action(ActionKind.PLAY_PLEX, "4617"))
        self.assertEqual(seen, ["4617"])
        self.assertEqual(result, ActionResult(True, "Playing 4617"))
        self.assertIsNone(tv.app)

    def test_tv_refusing_the_launch_returns_not_ok(self) -> None:
        service, _ = make_service(tv_transport=FakeRemoteTV(power=1, refuse_launch=True))
        result = service.run(Action(ActionKind.OPEN_APP, "1"))
        self.assertFalse(result.ok)
        self.assertTrue(result.message.startswith("The TV did not respond: "))


if __name__ == "__main__":
    unittest.main()
