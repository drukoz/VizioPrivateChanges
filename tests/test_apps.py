"""Tests for the dashboard app table in apps.py."""
from __future__ import annotations

import unittest

from vizio_privacy.apps import (
    APPS,
    DEFAULT_APPS,
    ICON,
    AppId,
    AppKind,
    get_app,
    parse_app_names,
)

VIZIO_HOME_MESSAGE = "http://127.0.0.1:12345/scfs/sctv/main.html"

# (id, title, kind, name_space, app_id, message, input_name, catalog_id, icon number)
TABLE = [
    (AppId.PLEX, "Plex", AppKind.LAUNCH, 2, "9", None, None, "40", 900000013),
    (AppId.NETFLIX, "Netflix", AppKind.LAUNCH, 3, "1", None, None, "34", 500000018),
    (AppId.YOUTUBE, "YouTube", AppKind.LAUNCH, 5, "1", None, None, "44", 500000006),
    (AppId.PRIME_VIDEO, "Prime Video", AppKind.LAUNCH, 3, "3", None, None, "33", 900000086),
    (AppId.DISNEY_PLUS, "Disney+", AppKind.LAUNCH, 2, "75", None, None, "76", 900000043),
    (AppId.HULU, "Hulu", AppKind.LAUNCH, 2, "3", None, None, "19", 500000015),
    (AppId.HBO_MAX, "HBO Max", AppKind.LAUNCH, 2, "128", None, None, "128", 900000299),
    (AppId.CRUNCHYROLL, "Crunchyroll", AppKind.LAUNCH, 2, "481", None, None, "2481", 900000694),
    (AppId.APPLE_TV_PLUS, "Apple TV+", AppKind.LAUNCH, 3, "4", None, None, "91", 900000049),
    (AppId.PARAMOUNT_PLUS, "Paramount+", AppKind.LAUNCH, 2, "37", None, None, "9", 500000049),
    (AppId.PEACOCK, "Peacock", AppKind.LAUNCH, 2, "88", None, None, "88", 900000062),
    (AppId.TUBI, "Tubi", AppKind.LAUNCH, 2, "61", None, None, "90", 900000036),
    (AppId.YOUTUBE_TV, "YouTube TV", AppKind.LAUNCH, 5, "3", None, None, "45", 900000019),
    (AppId.FIRE_TV_STICK, "Fire TV Stick", AppKind.INPUT,
     None, None, None, "HDMI-2", None, None),
    (AppId.VIZIO_HOME, "VIZIO Home", AppKind.LAUNCH,
     4, "1", VIZIO_HOME_MESSAGE, None, None, None),
]


class TableShapeTest(unittest.TestCase):
    def test_fifteen_entries_in_enum_order(self):
        self.assertEqual(len(APPS), 15)
        self.assertEqual([entry.id for entry in APPS], list(AppId))

    def test_no_repeated_ids(self):
        ids = [entry.id for entry in APPS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_launch_and_input_fields(self):
        for entry in APPS:
            with self.subTest(app=entry.id.name):
                if entry.kind == AppKind.LAUNCH:
                    self.assertIsNotNone(entry.name_space)
                    self.assertIsNotNone(entry.app_id)
                    self.assertIsNone(entry.input_name)
                else:
                    self.assertEqual(entry.kind, AppKind.INPUT)
                    self.assertIsNotNone(entry.input_name)
                    self.assertIsNone(entry.name_space)
                    self.assertIsNone(entry.app_id)
                    self.assertIsNone(entry.message)


class TableRowsTest(unittest.TestCase):
    def test_every_row(self):
        self.assertEqual(len(TABLE), len(APPS))
        for expected, entry in zip(TABLE, APPS):
            app_id, title, kind, ns, app_id_s, message, input_name, catalog_id, icon = expected
            with self.subTest(app=app_id.name):
                self.assertEqual(entry.id, app_id)
                self.assertEqual(entry.title, title)
                self.assertEqual(entry.kind, kind)
                self.assertEqual(entry.name_space, ns)
                self.assertEqual(entry.app_id, app_id_s)
                self.assertEqual(entry.message, message)
                self.assertEqual(entry.input_name, input_name)
                self.assertEqual(entry.catalog_id, catalog_id)
                self.assertEqual(
                    entry.icon_url, ICON.format(icon) if icon is not None else None
                )


class GetAppTest(unittest.TestCase):
    def test_prime_video_uses_resolved_values(self):
        entry = get_app(AppId.PRIME_VIDEO)
        self.assertEqual(entry.name_space, 3)
        self.assertEqual(entry.app_id, "3")

    def test_vizio_home_message(self):
        self.assertEqual(get_app(AppId.VIZIO_HOME).message, VIZIO_HOME_MESSAGE)


class DefaultAppsTest(unittest.TestCase):
    def test_default_apps(self):
        self.assertEqual(
            tuple(DEFAULT_APPS),
            (AppId.PLEX, AppId.NETFLIX, AppId.YOUTUBE, AppId.PRIME_VIDEO,
             AppId.DISNEY_PLUS, AppId.FIRE_TV_STICK, AppId.VIZIO_HOME),
        )


class ParseAppNamesTest(unittest.TestCase):
    def test_names_titles_case_spaces_and_repeats(self):
        self.assertEqual(
            parse_app_names(["Netflix", "prime_video", " DISNEY+ ", "netflix"]),
            [AppId.NETFLIX, AppId.PRIME_VIDEO, AppId.DISNEY_PLUS],
        )

    def test_input_and_home_by_title(self):
        self.assertEqual(
            parse_app_names(["Fire TV Stick", "vizio home"]),
            [AppId.FIRE_TV_STICK, AppId.VIZIO_HOME],
        )

    def test_unknown_name_raises(self):
        with self.assertRaises(ValueError) as caught:
            parse_app_names(["Netflix", "Spotify"])
        self.assertIn("Spotify", str(caught.exception))

    def test_empty_list(self):
        self.assertEqual(parse_app_names([]), [])


if __name__ == "__main__":
    unittest.main()
