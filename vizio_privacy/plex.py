"""Plex Media Server client: continue watching, library rows, items, play queues, images."""

from __future__ import annotations

import enum
import http.client
import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from vizio_privacy.api import Response, _as_int


class PlexItemType(enum.IntEnum):
    MOVIE = 0  # Plex "movie"
    EPISODE = 1  # "episode"
    SHOW = 2  # "show"
    SEASON = 3  # "season"
    OTHER = 4  # anything else

    @classmethod
    def from_text(cls, text: Optional[str]) -> "PlexItemType":
        if text is None:
            return cls.OTHER
        mapped = {
            "movie": cls.MOVIE,
            "episode": cls.EPISODE,
            "show": cls.SHOW,
            "season": cls.SEASON,
        }
        return mapped.get(text.lower().strip(), cls.OTHER)


class LibraryType(enum.IntEnum):
    MOVIE = 0  # "movie"
    SHOW = 1  # "show"
    MUSIC = 2  # "artist"
    PHOTO = 3  # "photo"
    OTHER = 4

    @classmethod
    def from_text(cls, text: Optional[str]) -> "LibraryType":
        if text is None:
            return cls.OTHER
        mapped = {
            "movie": cls.MOVIE,
            "show": cls.SHOW,
            "artist": cls.MUSIC,
            "photo": cls.PHOTO,
        }
        return mapped.get(text.lower().strip(), cls.OTHER)


@dataclass
class PlexItem:
    rating_key: str
    type: PlexItemType
    title: str
    show_title: Optional[str]  # grandparentTitle
    season_index: Optional[int]  # parentIndex
    episode_index: Optional[int]  # index
    year: Optional[int]
    thumb: Optional[str]
    art: Optional[str]
    parent_thumb: Optional[str]  # parentThumb
    grandparent_thumb: Optional[str]  # grandparentThumb
    grandparent_art: Optional[str]  # grandparentArt
    view_offset_ms: Optional[int]  # viewOffset
    duration_ms: Optional[int]  # duration
    view_count: int  # viewCount, 0 when missing
    library_section_id: Optional[int]  # librarySectionID
    parent_rating_key: Optional[str]  # parentRatingKey
    grandparent_rating_key: Optional[str]  # grandparentRatingKey

    @classmethod
    def from_json(cls, obj: Dict[str, Any]) -> "PlexItem":
        def text(key: str) -> Optional[str]:
            value = obj.get(key)
            return None if value is None else str(value)

        view_count = _as_int(obj.get("viewCount"))
        return cls(
            rating_key=text("ratingKey") or "",
            type=PlexItemType.from_text(obj.get("type")),
            title=text("title") or "",
            show_title=text("grandparentTitle"),
            season_index=_as_int(obj.get("parentIndex")),
            episode_index=_as_int(obj.get("index")),
            year=_as_int(obj.get("year")),
            thumb=text("thumb"),
            art=text("art"),
            parent_thumb=text("parentThumb"),
            grandparent_thumb=text("grandparentThumb"),
            grandparent_art=text("grandparentArt"),
            view_offset_ms=_as_int(obj.get("viewOffset")),
            duration_ms=_as_int(obj.get("duration")),
            view_count=view_count if view_count is not None else 0,
            library_section_id=_as_int(obj.get("librarySectionID")),
            parent_rating_key=text("parentRatingKey"),
            grandparent_rating_key=text("grandparentRatingKey"),
        )


@dataclass
class Hub:
    identifier: str  # hubIdentifier
    title: str
    items: List[PlexItem]


@dataclass
class Library:
    section_id: int  # int(key)
    title: str
    type: LibraryType


class PlexError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__("{}: {}".format(status, detail))


def default_transport(timeout: float = 8.0) -> Callable[..., Response]:
    def transport(method: str, url: str, headers: Dict[str, str], body: Optional[str]) -> Response:
        parts = urllib.parse.urlsplit(url)
        conn = http.client.HTTPConnection(parts.hostname or "", parts.port or 80, timeout=timeout)
        target = parts.path + ("?" + parts.query if parts.query else "")
        try:
            conn.request(method, target, body=body, headers=headers)
            resp = conn.getresponse()
            return Response(resp.status, resp.read().decode("utf-8", "replace"))
        finally:
            conn.close()

    return transport


def _dict_list(container: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = container.get(key)
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


class PlexClient:
    def __init__(
        self,
        base_url: str,
        transport: Optional[Callable] = None,
        token: Optional[str] = None,
        client_id: str = "vizio-privacy-dashboard",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client_id = client_id
        self.transport = transport if transport is not None else default_transport()

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Product": "Vizio Privacy Dashboard",
            "X-Plex-Version": "1",
        }
        if self.token:
            headers["X-Plex-Token"] = self.token
        return headers

    def _request(
        self, method: str, path: str, body: Optional[str] = None
    ) -> Dict[str, Any]:
        url = self.base_url + path
        response = self.transport(method, url, self._headers(), body)
        raw = response.body if response.body is not None else ""
        if not 200 <= response.status <= 299:
            raise PlexError(response.status, raw[:200])
        try:
            parsed = json.loads(raw) if raw.strip() else None
        except ValueError:
            parsed = None
        if not isinstance(parsed, dict):
            raise PlexError(response.status, "response is not JSON")
        return parsed

    def _container(self, method: str, path: str, body: Optional[str] = None) -> Dict[str, Any]:
        parsed = self._request(method, path, body=body)
        container = parsed.get("MediaContainer")
        return container if isinstance(container, dict) else {}

    def identity(self) -> Tuple[str, str]:
        container = self._container("GET", "/identity")
        machine = container.get("machineIdentifier")
        version = container.get("version")
        machine_text = str(machine) if machine is not None else ""
        version_text = str(version) if version is not None else ""
        return (machine_text, version_text)

    def libraries(self) -> List[Library]:
        container = self._container("GET", "/library/sections")
        libraries = []  # type: List[Library]
        for directory in _dict_list(container, "Directory"):
            section_id = _as_int(directory.get("key"))
            if section_id is None:
                continue
            libraries.append(
                Library(
                    section_id=section_id,
                    title=str(directory.get("title") or ""),
                    type=LibraryType.from_text(directory.get("type")),
                )
            )
        return libraries

    def continue_watching(self, count: int = 20) -> List[PlexItem]:
        container = self._container("GET", "/hubs/continueWatching?count={}".format(count))
        hubs = _dict_list(container, "Hub")
        if not hubs:
            return []
        return [PlexItem.from_json(entry) for entry in _dict_list(hubs[0], "Metadata")]

    def section_hubs(self, section_id: int, count: int = 20) -> List[Hub]:
        container = self._container("GET", "/hubs/sections/{}?count={}".format(section_id, count))
        hubs = []  # type: List[Hub]
        for hub in _dict_list(container, "Hub"):
            hubs.append(
                Hub(
                    identifier=str(hub.get("hubIdentifier") or ""),
                    title=str(hub.get("title") or ""),
                    items=[PlexItem.from_json(entry) for entry in _dict_list(hub, "Metadata")],
                )
            )
        return hubs

    def item(self, rating_key: str) -> PlexItem:
        container = self._container("GET", "/library/metadata/{}".format(rating_key))
        metadata = _dict_list(container, "Metadata")
        if not metadata:
            raise PlexError(404, "no such item")
        return PlexItem.from_json(metadata[0])

    def next_episode(self, rating_key: str) -> Optional[PlexItem]:
        container = self._container(
            "GET", "/library/metadata/{}?includeOnDeck=1".format(rating_key)
        )
        metadata = _dict_list(container, "Metadata")
        if not metadata:
            return None
        on_deck = metadata[0].get("OnDeck")
        if not isinstance(on_deck, dict):
            return None
        nested = on_deck.get("Metadata")
        if isinstance(nested, list):
            if not nested or not isinstance(nested[0], dict):
                return None
            return PlexItem.from_json(nested[0])
        if isinstance(nested, dict):
            return PlexItem.from_json(nested)
        return None

    def create_play_queue(self, machine_identifier: str, rating_key: str) -> int:
        uri = "server://{}/com.plexapp.plugins.library/library/metadata/{}".format(
            machine_identifier, rating_key
        )
        query = (
            "type=video&shuffle=0&repeat=0&continuous=0&own=1&includeChapters=1&uri="
            + urllib.parse.quote(uri, safe="")
        )
        container = self._container("POST", "/playQueues?" + query, body=None)
        queue_id = _as_int(container.get("playQueueID"))
        if queue_id is None:
            raise PlexError(200, "no playQueueID")
        return queue_id

    def image_url(self, path: str, width: int, height: int) -> str:
        url = "{}/photo/:/transcode?width={}&height={}&minSize=1&upscale=1&url={}".format(
            self.base_url, width, height, urllib.parse.quote(path, safe="")
        )
        if self.token:
            url += "&X-Plex-Token={}".format(self.token)
        return url
