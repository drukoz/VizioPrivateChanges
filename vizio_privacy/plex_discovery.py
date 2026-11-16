"""Find Plex Media Servers on the local network with Plex's GDM broadcast."""
from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

GDM_ADDRESS = ("239.0.0.250", 32414)
GDM_MESSAGE = b"M-SEARCH * HTTP/1.1\r\n\r\n"


@dataclass(frozen=True)
class ServerInfo:
    address: str
    port: int
    name: str
    machine_identifier: str
    version: str

    @property
    def base_url(self) -> str:
        return "http://{}:{}".format(self.address, self.port)


def parse_gdm_reply(data: bytes, address: str) -> Optional[ServerInfo]:
    """Turn one GDM reply datagram into a ServerInfo, or None if it is not one."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    headers = {}  # type: Dict[str, str]
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()
    if headers.get("content-type") != "plex/media-server":
        return None
    port = headers.get("port", "")
    if not port.isdigit():
        return None
    if "resource-identifier" not in headers:
        return None
    return ServerInfo(
        address=address,
        port=int(port),
        name=headers.get("name", ""),
        machine_identifier=headers["resource-identifier"],
        version=headers.get("version", ""),
    )


def _make_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    return sock


def discover(
    timeout: float = 2.0, socket_factory: Optional[Callable[[], Any]] = None
) -> List[ServerInfo]:
    """Send one GDM query and collect the servers that answer, first seen first."""
    sock = socket_factory() if socket_factory is not None else _make_socket()
    try:
        sock.settimeout(0.25)
        try:
            sock.sendto(GDM_MESSAGE, GDM_ADDRESS)
        except OSError:
            return []
        servers = []  # type: List[ServerInfo]
        seen = set()  # type: set
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            info = parse_gdm_reply(data, addr[0])
            if info is None or info.machine_identifier in seen:
                continue
            seen.add(info.machine_identifier)
            servers.append(info)
        return servers
    finally:
        sock.close()
