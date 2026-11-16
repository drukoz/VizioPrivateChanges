"""Fake Plex Media Server transport: answers from tests/fixtures/plex/, never opens a socket."""

from __future__ import annotations

import os
import urllib.parse
from typing import Dict, List, Optional, Tuple

from vizio_privacy.api import Response

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "plex")

ROUTES = {
    ("GET", "/identity"): "identity.json",
    ("GET", "/library/sections"): "library_sections.json",
    ("GET", "/hubs/continueWatching"): "hubs_continue_watching.json",
    ("GET", "/hubs/sections/1"): "hubs_section_movie.json",
    ("GET", "/hubs/sections/2"): "hubs_section_show.json",
    ("GET", "/library/metadata/4617"): "metadata_episode.json",
    ("GET", "/library/metadata/24339"): "metadata_movie.json",
    ("GET", "/library/metadata/4516"): "metadata_show.json",
    ("POST", "/playQueues"): "play_queue_created.json",
}

# Paths whose answer is a different file once the query asks for includeOnDeck=1.
ON_DECK_ROUTES = {
    ("GET", "/library/metadata/4516"): "metadata_show_ondeck.json",
    ("GET", "/library/metadata/19258"): "metadata_show_unstarted_ondeck.json",
}


class FakePMS:
    """A transport that replays captured Plex answers; it is itself callable."""

    def __init__(self) -> None:
        self.calls = []  # type: List[Tuple[str, str, str, Dict[str, str]]]

    def __call__(
        self, method: str, url: str, headers: Dict[str, str], body: Optional[str]
    ) -> Response:
        parts = urllib.parse.urlsplit(url)
        path = parts.path
        query = parts.query
        self.calls.append((method.upper(), path, query, dict(headers)))
        key = (method.upper(), path)
        if "includeOnDeck=1" in query and key in ON_DECK_ROUTES:
            name = ON_DECK_ROUTES[key]
        elif key in ROUTES:
            name = ROUTES[key]
        else:
            return Response(404, "Not Found")
        with open(os.path.join(FIXTURE_DIR, name), "r", encoding="utf-8") as handle:
            return Response(200, handle.read())
