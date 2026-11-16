"""Tests for the dashboard contract in vizio_privacy.dashboard.model."""

import json
import unittest

from vizio_privacy.dashboard.model import (
    MAX_TARGET_LENGTH,
    Action,
    ActionKind,
    ActionResult,
    Home,
    ImageShape,
    Row,
    RowKind,
    Tile,
    image_path,
    parse_image_query,
)


def make_home():
    return Home(
        rows=[
            Row(
                id="continueWatching",
                title="Continue Watching",
                kind=RowKind.CONTINUE_WATCHING,
                tiles=[
                    Tile(
                        id="plex:4617",
                        title="Show name",
                        subtitle="S4 \u00b7 E4 \u00b7 Episode name",
                        image="/img?p=%2Flibrary%2Fmetadata%2F4617%2Fthumb%2F1790131474&w=384&h=216",
                        shape=ImageShape.WIDE,
                        progress=0.76913,
                        action=Action(ActionKind.PLAY_PLEX, "4617"),
                    )
                ],
            )
        ],
        apps=[
            Tile(
                id="app:1",
                title="Netflix",
                subtitle=None,
                image="/static/apps/1.png",
                shape=ImageShape.ICON,
                progress=None,
                action=Action(ActionKind.OPEN_APP, "1"),
            )
        ],
        notices=["Plex is not answering; showing apps only."],
    )


EXPECTED_HOME = {
    "version": 1,
    "rows": [
        {
            "id": "continueWatching",
            "title": "Continue Watching",
            "kind": 0,
            "tiles": [
                {
                    "id": "plex:4617",
                    "title": "Show name",
                    "subtitle": "S4 \u00b7 E4 \u00b7 Episode name",
                    "image": "/img?p=%2Flibrary%2Fmetadata%2F4617%2Fthumb%2F1790131474&w=384&h=216",
                    "shape": 1,
                    "progress": 0.769,
                    "action": {"kind": 0, "target": "4617"},
                }
            ],
        }
    ],
    "apps": [
        {
            "id": "app:1",
            "title": "Netflix",
            "subtitle": None,
            "image": "/static/apps/1.png",
            "shape": 2,
            "progress": None,
            "action": {"kind": 1, "target": "1"},
        }
    ],
    "notices": ["Plex is not answering; showing apps only."],
}


def make_tile(progress):
    return Tile(
        id="plex:1",
        title="T",
        subtitle=None,
        image=None,
        shape=ImageShape.WIDE,
        progress=progress,
        action=Action(ActionKind.PLAY_PLEX, "1"),
    )


class EnumsTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(RowKind.PLEX_HUB, 1)
        self.assertEqual(ActionKind.VIZIO_HOME, 3)
        self.assertEqual(ImageShape.ICON, 2)

    def test_members_exact(self):
        self.assertEqual(
            [(int(m), m.name) for m in RowKind],
            [(0, "CONTINUE_WATCHING"), (1, "PLEX_HUB")],
        )
        self.assertEqual(
            [(int(m), m.name) for m in ActionKind],
            [
                (0, "PLAY_PLEX"),
                (1, "OPEN_APP"),
                (2, "SWITCH_INPUT"),
                (3, "VIZIO_HOME"),
                (4, "AMAZON_HOME"),
            ],
        )
        self.assertEqual(
            [(int(m), m.name) for m in ImageShape],
            [(0, "POSTER"), (1, "WIDE"), (2, "ICON")],
        )


class HomeToJsonTest(unittest.TestCase):
    def test_matches_contract_example(self):
        self.assertEqual(make_home().to_json(), EXPECTED_HOME)

    def test_json_round_trip(self):
        data = json.loads(json.dumps(make_home().to_json()))
        self.assertEqual(data, EXPECTED_HOME)

    def test_enums_are_plain_ints(self):
        d = make_home().to_json()
        self.assertIs(type(d["rows"][0]["kind"]), int)
        self.assertIs(type(d["rows"][0]["tiles"][0]["shape"]), int)
        self.assertIs(type(d["rows"][0]["tiles"][0]["action"]["kind"]), int)

    def test_action_result_to_json(self):
        self.assertEqual(
            ActionResult(True, "Opening Netflix").to_json(),
            {"ok": True, "message": "Opening Netflix"},
        )


class ProgressTest(unittest.TestCase):
    def test_clamping(self):
        self.assertEqual(make_tile(1.7).to_json()["progress"], 1.0)
        self.assertEqual(make_tile(-0.2).to_json()["progress"], 0.0)
        self.assertIsNone(make_tile(None).to_json()["progress"])

    def test_rounding(self):
        self.assertEqual(make_tile(0.76913).to_json()["progress"], 0.769)


class ActionFromJsonTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(
            Action.from_json({"kind": 1, "target": "1"}),
            Action(ActionKind.OPEN_APP, "1"),
        )

    def test_bad_inputs(self):
        bad = [
            "x",
            {},
            {"kind": "1", "target": "1"},
            {"kind": True, "target": "1"},
            {"kind": 9, "target": "1"},
            {"kind": 0},
            {"kind": 0, "target": ""},
            {"kind": 0, "target": "   "},
            {"kind": 0, "target": 5},
            {"kind": 0, "target": "x" * (MAX_TARGET_LENGTH + 1)},
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Action.from_json(value)


class ImageQueryTest(unittest.TestCase):
    def test_image_path(self):
        self.assertEqual(
            image_path("/library/metadata/4617/thumb/1790131474", 384, 216),
            "/img?p=%2Flibrary%2Fmetadata%2F4617%2Fthumb%2F1790131474&w=384&h=216",
        )

    def test_parse_round_trip(self):
        path = "/library/metadata/4617/thumb/1790131474"
        query = image_path(path, 384, 216).split("?", 1)[1]
        self.assertEqual(parse_image_query(query), (path, 384, 216))

    def test_parse_bad_queries(self):
        bad = [
            "w=10&h=10",                              # no p
            "p=%2Flibrary%2Fa&p=%2Flibrary%2Fb&w=10&h=10",  # two p
            "p=%2Fphoto%2Fx&w=10&h=10",               # p not under /library/
            "p=%2Flibrary%2F..%2Fetc&w=10&h=10",      # p has ..
            "p=%2Flibrary%2Fx%3A%2F%2Fy&w=10&h=10",   # p has ://
            "p=%2Flibrary%2Fa&w=0&h=10",              # w below 1
            "p=%2Flibrary%2Fa&w=1921&h=10",           # w above 1920
            "p=%2Flibrary%2Fa&w=10&h=1081",           # h above 1080
            "p=%2Flibrary%2Fa&w=abc&h=10",            # w not a number
            "p=%2Flibrary%2Fa&w=-5&h=10",             # w has a sign
            "p=%2Flibrary%2Fa&h=10",                  # w missing
        ]
        for query in bad:
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    parse_image_query(query)


if __name__ == "__main__":
    unittest.main()
