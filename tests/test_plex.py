"""Tests for the Plex client against the scrubbed fixtures. No sockets."""

from __future__ import annotations

import unittest
from typing import Optional

from vizio_privacy.api import Response
from vizio_privacy.plex import (
    Library,
    LibraryType,
    PlexError,
    PlexItem,
    PlexItemType,
    PlexClient,
)
from tests.fake_pms import FakePMS

BASE_URL = "http://192.0.2.5:32400"
MACHINE = "0123456789abcdef0123456789abcdef01234567"


def make_client(token: Optional[str] = None) -> PlexClient:
    return PlexClient(BASE_URL, transport=FakePMS(), token=token)


class IdentityTests(unittest.TestCase):
    def test_identity(self) -> None:
        machine, version = make_client().identity()
        self.assertEqual(machine, MACHINE)
        self.assertEqual(version, "1.43.5.11079-b3b13e506")


class LibrariesTests(unittest.TestCase):
    def test_libraries(self) -> None:
        self.assertEqual(
            make_client().libraries(),
            [
                Library(1, "Movies", LibraryType.MOVIE),
                Library(3, "Anime", LibraryType.SHOW),
                Library(2, "TV Shows", LibraryType.SHOW),
                Library(4, "Music", LibraryType.MUSIC),
            ],
        )


class ContinueWatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.items = make_client().continue_watching()

    def test_three_items(self) -> None:
        self.assertEqual([item.rating_key for item in self.items], ["4617", "17346", "24339"])
        self.assertEqual(
            [item.type for item in self.items],
            [PlexItemType.EPISODE, PlexItemType.EPISODE, PlexItemType.MOVIE],
        )

    def test_episode_fields(self) -> None:
        item = self.items[0]
        self.assertEqual(item.title, "title 30")
        self.assertEqual(item.show_title, "grandparentTitle 31")
        self.assertEqual(item.season_index, 4)
        self.assertEqual(item.episode_index, 4)
        self.assertEqual(item.year, 2012)
        self.assertEqual(item.view_offset_ms, 540259)
        self.assertEqual(item.duration_ms, 702484)
        self.assertEqual(item.view_count, 0)
        self.assertEqual(item.library_section_id, 3)
        self.assertEqual(item.thumb, "/library/metadata/4617/thumb/1790131474")
        self.assertEqual(item.art, "/library/metadata/4516/art/1687580316")
        self.assertEqual(item.grandparent_thumb, "/library/metadata/4516/thumb/1687580316")

    def test_movie_fields(self) -> None:
        item = self.items[2]
        self.assertEqual(item.year, 1995)
        self.assertEqual(item.view_count, 1)
        self.assertIsNone(item.show_title)
        self.assertIsNone(item.season_index)


class SectionHubsTests(unittest.TestCase):
    def test_movie_hub_identifiers_in_order(self) -> None:
        hubs = make_client().section_hubs(1)
        self.assertEqual(len(hubs), 7)
        self.assertEqual(
            [hub.identifier for hub in hubs],
            [
                "movie.inprogress.1",
                "movie.recentlyreleased.1",
                "movie.recentlyadded.1",
                "movie.genre.1.297",
                "movie.by.actor.or.director.1.10149",
                "movie.topunwatched.1",
                "movie.recentlyviewed.1",
            ],
        )

    def test_hub_without_metadata_is_empty(self) -> None:
        hubs = {hub.identifier: hub for hub in make_client().section_hubs(1)}
        self.assertEqual(hubs["movie.by.actor.or.director.1.10149"].items, [])

    def test_recently_added_hub(self) -> None:
        hubs = {hub.identifier: hub for hub in make_client().section_hubs(1)}
        hub = hubs["movie.recentlyadded.1"]
        self.assertEqual(hub.title, "Recently Added in Movies")
        self.assertEqual([item.rating_key for item in hub.items], ["29124", "29141"])

    def test_show_hubs(self) -> None:
        hubs = {hub.identifier: hub for hub in make_client().section_hubs(2)}
        start = hubs["tv.startwatching.2"]
        self.assertEqual([item.rating_key for item in start.items], ["19258", "20979"])
        self.assertEqual([item.type for item in start.items], [PlexItemType.SHOW, PlexItemType.SHOW])
        added = hubs["tv.recentlyadded.2"]
        self.assertEqual([item.rating_key for item in added.items], ["34150", "33968"])
        self.assertEqual([item.type for item in added.items], [PlexItemType.SHOW, PlexItemType.SHOW])


class ItemTests(unittest.TestCase):
    def test_movie(self) -> None:
        item = make_client().item("24339")
        self.assertEqual(item.type, PlexItemType.MOVIE)
        self.assertEqual(item.year, 1995)

    def test_show(self) -> None:
        item = make_client().item("4516")
        self.assertEqual(item.type, PlexItemType.SHOW)
        self.assertEqual(item.year, 2010)

    def test_episode(self) -> None:
        item = make_client().item("4617")
        self.assertEqual(item.type, PlexItemType.EPISODE)
        self.assertEqual(item.parent_rating_key, "4613")
        self.assertEqual(item.grandparent_rating_key, "4516")

    def test_missing_item_raises(self) -> None:
        with self.assertRaises(PlexError) as caught:
            make_client().item("999")
        self.assertEqual(caught.exception.status, 404)


class NextEpisodeTests(unittest.TestCase):
    def test_partly_watched_show(self) -> None:
        episode = make_client().next_episode("4516")
        self.assertIsNotNone(episode)
        assert episode is not None
        self.assertEqual(episode.rating_key, "4617")
        self.assertEqual(episode.season_index, 4)
        self.assertEqual(episode.episode_index, 4)
        self.assertEqual(episode.view_offset_ms, 540259)

    def test_unstarted_show(self) -> None:
        episode = make_client().next_episode("19258")
        self.assertIsNotNone(episode)
        assert episode is not None
        self.assertEqual(episode.rating_key, "19260")
        self.assertEqual(episode.season_index, 1)
        self.assertEqual(episode.episode_index, 1)
        self.assertIsNone(episode.view_offset_ms)

    def test_movie_has_no_next_episode(self) -> None:
        self.assertIsNone(make_client().next_episode("24339"))


class PlayQueueTests(unittest.TestCase):
    def test_create_play_queue(self) -> None:
        pms = FakePMS()
        client = PlexClient(BASE_URL, transport=pms)
        self.assertEqual(client.create_play_queue(MACHINE, "4617"), 1616)
        self.assertEqual(len(pms.calls), 1)
        method, path, query, headers = pms.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/playQueues")
        self.assertIn("type=video", query)
        self.assertIn("own=1", query)
        self.assertIn(
            "uri=server%3A%2F%2F0123456789abcdef0123456789abcdef01234567"
            "%2Fcom.plexapp.plugins.library%2Flibrary%2Fmetadata%2F4617",
            query,
        )


class ImageUrlTests(unittest.TestCase):
    def test_image_url_without_token(self) -> None:
        client = PlexClient(BASE_URL + "/")
        self.assertEqual(
            client.image_url("/library/metadata/4617/thumb/1790131474", 384, 216),
            "http://192.0.2.5:32400/photo/:/transcode?width=384&height=216&minSize=1"
            "&upscale=1&url=%2Flibrary%2Fmetadata%2F4617%2Fthumb%2F1790131474",
        )

    def test_image_url_with_token(self) -> None:
        client = PlexClient(BASE_URL + "/", token="abc")
        self.assertEqual(
            client.image_url("/library/metadata/4617/thumb/1790131474", 384, 216),
            "http://192.0.2.5:32400/photo/:/transcode?width=384&height=216&minSize=1"
            "&upscale=1&url=%2Flibrary%2Fmetadata%2F4617%2Fthumb%2F1790131474"
            "&X-Plex-Token=abc",
        )


class HeadersTests(unittest.TestCase):
    def _exercise(self, client: PlexClient) -> None:
        client.identity()
        client.libraries()
        client.continue_watching()
        client.section_hubs(1)
        client.item("4617")
        client.next_episode("4516")
        client.create_play_queue(MACHINE, "4617")

    def test_headers_without_token(self) -> None:
        pms = FakePMS()
        self._exercise(PlexClient(BASE_URL, transport=pms))
        self.assertTrue(pms.calls)
        for method, path, query, headers in pms.calls:
            self.assertEqual(headers.get("Accept"), "application/json")
            self.assertEqual(headers.get("X-Plex-Client-Identifier"), "vizio-privacy-dashboard")
            self.assertEqual(headers.get("X-Plex-Product"), "Vizio Privacy Dashboard")
            self.assertEqual(headers.get("X-Plex-Version"), "1")
            self.assertNotIn("X-Plex-Token", headers)

    def test_headers_with_token(self) -> None:
        pms = FakePMS()
        self._exercise(PlexClient(BASE_URL, transport=pms, token="t0k"))
        self.assertTrue(pms.calls)
        for method, path, query, headers in pms.calls:
            self.assertEqual(headers.get("X-Plex-Token"), "t0k")


class BadAnswerTests(unittest.TestCase):
    def test_non_json_answer(self) -> None:
        def transport(method, url, headers, body):
            return Response(200, "<html>")

        client = PlexClient(BASE_URL, transport=transport)
        with self.assertRaises(PlexError) as caught:
            client.identity()
        self.assertEqual(caught.exception.detail, "response is not JSON")

    def test_error_status_keeps_detail(self) -> None:
        def transport(method, url, headers, body):
            return Response(500, "boom")

        client = PlexClient(BASE_URL, transport=transport)
        with self.assertRaises(PlexError) as caught:
            client.identity()
        self.assertEqual(caught.exception.status, 500)
        self.assertEqual(caught.exception.detail, "boom")


class PlexItemFromJsonTests(unittest.TestCase):
    def test_minimal_item(self) -> None:
        item = PlexItem.from_json({"ratingKey": "1", "type": "clip", "title": "x"})
        self.assertEqual(item.type, PlexItemType.OTHER)
        self.assertEqual(item.rating_key, "1")
        self.assertEqual(item.title, "x")
        self.assertEqual(item.view_count, 0)
        for field in (
            "show_title",
            "season_index",
            "episode_index",
            "year",
            "thumb",
            "art",
            "parent_thumb",
            "grandparent_thumb",
            "grandparent_art",
            "view_offset_ms",
            "duration_ms",
            "library_section_id",
            "parent_rating_key",
            "grandparent_rating_key",
        ):
            self.assertIsNone(getattr(item, field), field)


if __name__ == "__main__":
    unittest.main()
