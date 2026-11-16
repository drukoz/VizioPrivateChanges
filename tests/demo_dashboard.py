"""A stdlib launcher that runs the whole dashboard locally against the mock TV.

Run it from the repository root with macOS's own Python:

    /usr/bin/python3 -m tests.demo_dashboard [--port 8765] [--plex-down]

It brings up the same stand-ins the end-to-end tests use -- the mock TV
(``tests/mock_tv.py``) and the fake Plex (``tests/fake_plex_http.py``), both on
``127.0.0.1`` only -- pairs once into a throwaway privacy home, prints the
dashboard URL, then runs ``dashboard serve`` until Ctrl-C or SIGTERM.

A daemon thread watches the mock TV and prints, one line each (flushed):

    TV launch: {"APP_ID": "1", "MESSAGE": null, "NAME_SPACE": 3}
    TV input: HDMI-2

for every launch the page puts on the TV and every change of the TV's input.

Nothing here touches the real TV (192.168.1.130) or the real Plex
(192.168.1.196): every socket binds to ``127.0.0.1``. Standard library only,
Python 3.9 compatible. The file name has no ``test`` in it so the unittest
discovery in ``tests/`` does not pick it up.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import tempfile
import threading
from types import FrameType
from typing import Any, Callable, List, Optional
from unittest import mock

from vizio_privacy.api import SmartCastClient
from vizio_privacy.cli import main

from tests.fake_plex_http import FakePlexHTTP
from tests.mock_tv import PIN, MockTV, make_certificate

DEFAULT_PORT = 8765
WATCH_INTERVAL = 0.5


def closed_port() -> int:
    """A port nothing listens on: bind to 0, read it back, release it."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def watch_tv(tv: MockTV, stop: threading.Event) -> None:
    """Print one line per new TV launch and per change of the TV's input."""
    seen_launches = 0
    last_input = tv.current_input[0]
    while not stop.is_set():
        launches = tv.launches  # type: List[Any]
        while seen_launches < len(launches):
            print(
                "TV launch: " + json.dumps(launches[seen_launches], sort_keys=True),
                flush=True,
            )
            seen_launches += 1
        current = tv.current_input[0]
        if current != last_input:
            print("TV input: {}".format(current), flush=True)
            last_input = current
        stop.wait(WATCH_INTERVAL)


def _terminate(_signum: int, _frame: Optional[FrameType]) -> None:
    """Turn SIGTERM into a clean exit so serve_forever unwinds and stops."""
    raise SystemExit(0)


def run(port: int, plex_down: bool) -> int:
    cert_dir = tempfile.TemporaryDirectory()
    home_dir = tempfile.TemporaryDirectory()
    cert, key = make_certificate(cert_dir.name)

    tv = MockTV(cert, key)
    tv.start()
    plex = None  # type: Optional[FakePlexHTTP]
    if not plex_down:
        plex = FakePlexHTTP()
        plex.start()

    os.environ["VIZIO_PRIVACY_HOME"] = home_dir.name
    factory = (
        lambda host, auth_token=None: SmartCastClient(
            host, auth_token=auth_token, port=tv.smartcast_port
        )
    )  # type: Callable[..., SmartCastClient]

    try:
        with mock.patch("builtins.input", return_value=PIN):
            main(["--host", "127.0.0.1", "pair"], client_factory=factory)

        if plex is not None:
            plex_url = plex.base_url
        else:
            plex_url = "http://127.0.0.1:{}".format(closed_port())

        stop = threading.Event()
        watcher = threading.Thread(target=watch_tv, args=(tv, stop), daemon=True)
        watcher.start()

        print("Dashboard: http://127.0.0.1:{}/".format(port), flush=True)

        signal.signal(signal.SIGTERM, _terminate)
        return main(
            [
                "--host", "127.0.0.1", "dashboard", "serve",
                "--plex", plex_url, "--bind", "127.0.0.1", "--port", str(port),
            ],
            client_factory=factory,
        )
    finally:
        stop.set()
        tv.stop()
        if plex is not None:
            plex.stop()
        cert_dir.cleanup()
        home_dir.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m tests.demo_dashboard",
        description="Run the dashboard on 127.0.0.1 against the mock TV and fake Plex.",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help="the dashboard server's port (default %(default)s)",
    )
    parser.add_argument(
        "--plex-down", action="store_true",
        help="point the dashboard at a closed port so Plex is offline",
    )
    return parser


def main_cli(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return run(port=args.port, plex_down=args.plex_down)


if __name__ == "__main__":
    sys.exit(main_cli())
