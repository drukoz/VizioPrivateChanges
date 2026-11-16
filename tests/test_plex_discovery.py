"""Tests for plex_discovery.py. No test opens a real socket."""
from __future__ import annotations

import os
import socket
import unittest
from typing import Any, List, Tuple

from vizio_privacy.plex_discovery import (
    GDM_ADDRESS,
    GDM_MESSAGE,
    ServerInfo,
    discover,
    parse_gdm_reply,
)

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "plex", "gdm_reply.txt"
)
MACHINE = b"0123456789abcdef0123456789abcdef01234567"
OTHER_MACHINE = b"ffffffffffffffffffffffffffffffffffffffff"


def fixture() -> bytes:
    with open(FIXTURE_PATH, "rb") as handle:
        return handle.read()


class FakeSocket:
    """Stands in for a UDP socket: replays queued datagrams, then times out."""

    def __init__(self, replies: List[Tuple[bytes, Tuple[str, int]]]) -> None:
        self.replies = list(replies)
        self.sent = []  # type: List[Tuple[bytes, Any]]
        self.timeouts = []  # type: List[float]
        self.closed = False

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)

    def setsockopt(self, *args: Any) -> None:
        pass

    def sendto(self, data: bytes, address: Tuple[str, int]) -> None:
        self.sent.append((data, address))

    def recvfrom(self, bufsize: int) -> Tuple[bytes, Tuple[str, int]]:
        if not self.replies:
            raise socket.timeout
        return self.replies.pop(0)

    def close(self) -> None:
        self.closed = True


class BrokenSocket(FakeSocket):
    """A fake whose sendto raises OSError, as if the host has no route."""

    def sendto(self, data: bytes, address: Tuple[str, int]) -> None:
        super(BrokenSocket, self).sendto(data, address)
        raise OSError("no route")


class ParseGdmReplyTest(unittest.TestCase):
    def test_fixture(self):
        info = parse_gdm_reply(fixture(), "192.0.2.10")
        self.assertEqual(
            info,
            ServerInfo(
                address="192.0.2.10",
                port=32400,
                name="plexserver",
                machine_identifier=MACHINE.decode(),
                version="1.43.5.11079-b3b13e506",
            ),
        )
        self.assertEqual(info.base_url, "http://192.0.2.10:32400")

    def test_media_player_is_rejected(self):
        data = fixture().replace(b"plex/media-server", b"plex/media-player")
        self.assertIsNone(parse_gdm_reply(data, "192.0.2.10"))

    def test_port_line_missing(self):
        data = fixture().replace(b"Port: 32400\r\n", b"")
        self.assertIsNone(parse_gdm_reply(data, "192.0.2.10"))

    def test_port_not_digits(self):
        data = fixture().replace(b"Port: 32400", b"Port: abc")
        self.assertIsNone(parse_gdm_reply(data, "192.0.2.10"))

    def test_resource_identifier_missing(self):
        data = fixture().replace(b"Resource-Identifier: " + MACHINE + b"\r\n", b"")
        self.assertIsNone(parse_gdm_reply(data, "192.0.2.10"))

    def test_not_utf8(self):
        self.assertIsNone(parse_gdm_reply(b"\xff\xfe", "192.0.2.10"))

    def test_lower_case_keys(self):
        info = parse_gdm_reply(fixture().lower(), "192.0.2.10")
        self.assertEqual(
            info,
            ServerInfo(
                address="192.0.2.10",
                port=32400,
                name="plexserver",
                machine_identifier=MACHINE.decode(),
                version="1.43.5.11079-b3b13e506",
            ),
        )


class DiscoverTest(unittest.TestCase):
    def test_two_servers_deduped_in_order(self):
        other = fixture().replace(MACHINE, OTHER_MACHINE)
        fake = FakeSocket(
            [
                (fixture(), ("192.0.2.10", 32414)),
                (fixture(), ("192.0.2.10", 32414)),
                (other, ("192.0.2.11", 32414)),
            ]
        )
        servers = discover(timeout=0.2, socket_factory=lambda: fake)
        self.assertEqual([s.address for s in servers], ["192.0.2.10", "192.0.2.11"])
        self.assertEqual(servers[1].machine_identifier, OTHER_MACHINE.decode())
        self.assertEqual(fake.sent, [(GDM_MESSAGE, GDM_ADDRESS)])
        self.assertTrue(fake.closed)

    def test_no_replies(self):
        fake = FakeSocket([])
        self.assertEqual(discover(timeout=0.2, socket_factory=lambda: fake), [])
        self.assertTrue(fake.closed)

    def test_sendto_os_error_returns_empty(self):
        fake = BrokenSocket([])
        self.assertEqual(discover(timeout=0.2, socket_factory=lambda: fake), [])
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
