"""The command line: ``python3 -m vizio_privacy <command>``.

The commands wire the API, pairing, token store, settings and Cast modules
together; they open no socket of their own. Clients are built only through
``client_factory`` and ``cast_factory``, so the tests pass fakes.

Redaction is a hard rule: the auth token and the TV's identifiers never
reach stdout. Setting values are printed only through
``targets.display_value``, which hides identifiers.
"""

from __future__ import annotations

import argparse
import http.client
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from vizio_privacy import firetv, plex_discovery, settings, targets, tokenstore
from vizio_privacy.api import (
    AppConfig,
    ResultStatus,
    SmartCastClient,
    SmartCastError,
)
from vizio_privacy.apps import DEFAULT_APPS, parse_app_names
from vizio_privacy.cast import CastClient
from vizio_privacy.dashboard.server import make_server, plex_image_source
from vizio_privacy.dashboard.service import DashboardService
from vizio_privacy.pairing import DEFAULT_DEVICE_ID, begin_pair, finish_pair
from vizio_privacy.plex import PlexClient
from vizio_privacy.settings import ChangeOutcome, HardenRow, WalkError

NO_MATCHES = "No tracking or ad settings were found in the menus that were read."

TELEMETRY_BINARIES = (
    "acr",
    "collectd",
    "errorcollector",
    "eventanalyzer",
    "recommendationd",
    "s3logger",
    "watchfree-helper",
)


def lan_address(tv_host: str) -> str:
    """The Mac's own address on the route to the TV. A UDP connect sends no packet."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((tv_host, 7345))
        return sock.getsockname()[0]
    finally:
        sock.close()


def _server_answers(url: str, timeout: float = 3.0) -> bool:
    """True when anything answers HTTP at url (a 404 counts: the page may not exist yet)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except urllib.error.HTTPError as err:
        err.close()
        return True
    except (OSError, ValueError):
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m vizio_privacy",
        description="Turn off tracking and ads on a Vizio SmartCast TV.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("VIZIO_HOST"),
        help="the TV's address (or set VIZIO_HOST)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="show device info and which telemetry components are present")
    sub.add_parser("pair", help="pair with the on-screen PIN and save the auth token")
    sub.add_parser("dump", help="print the settings tree")
    sub.add_parser("status", help="show the privacy status of the tracked settings")
    harden = sub.add_parser("harden", help="plan privacy changes (a dry run unless --apply)")
    harden.add_argument("--apply", action="store_true", help="write the changes to the TV")
    sub.add_parser("cast-optout", help="opt the TV's Google Cast out of telemetry")

    dashboard = sub.add_parser("dashboard", help="the home screen dashboard")
    dsub = dashboard.add_subparsers(dest="dashboard_command", required=True)
    dserve = dsub.add_parser("serve", help="run the dashboard server on this Mac")
    dserve.add_argument(
        "--plex",
        default=os.environ.get("VIZIO_PLEX_URL"),
        help="the Plex server's URL, for example http://192.168.1.196:32400; "
        "found on the network when not given",
    )
    dserve.add_argument(
        "--bind", default="0.0.0.0", help="the address to listen on (default 0.0.0.0)"
    )
    dserve.add_argument(
        "--port", type=int, default=8790, help="the port to listen on (default 8790)"
    )
    dserve.add_argument(
        "--apps",
        default=None,
        help='comma-separated apps for the bottom row, for example "Plex,Netflix,YouTube"',
    )
    dopen = dsub.add_parser("open", help="show the dashboard on the TV")
    dopen.add_argument(
        "--port", type=int, default=8790, help="the dashboard server's port (default 8790)"
    )
    dopen.add_argument(
        "--url",
        default=None,
        help="the dashboard URL (default: http://<this Mac on the route to the TV>:<port>/)",
    )
    dopen.add_argument(
        "--namespace", type=int, default=4, help="the NAME_SPACE to launch (default 4)"
    )
    dopen.add_argument(
        "--app-id", default="1", help='the APP_ID to launch (default "1")'
    )

    firetvp = sub.add_parser(
        "firetv",
        help="the Fire TV Stick's Amazon packages (status, harden, undo) over ADB",
    )
    firetvp.add_argument(
        "--device",
        default=os.environ.get("FIRETV_DEVICE"),
        help="the stick's address, for example 192.168.1.60:5555 (or set FIRETV_DEVICE)",
    )
    firetvp.add_argument("--adb", default="adb", help="the adb executable (default adb)")
    firetvp.add_argument(
        "--adb-home",
        default=os.environ.get("VIZIO_ADB_HOME"),
        help="HOME for adb, so it uses the key that trusts the stick (or set VIZIO_ADB_HOME)",
    )
    firetvp.add_argument(
        "--adb-port", type=int, default=5038, help="the adb server port (default 5038)"
    )
    fsub = firetvp.add_subparsers(dest="firetv_command", required=True)
    fsub.add_parser(
        "status", help="list the plan's packages and the protected ones with their state"
    )
    fhard = fsub.add_parser(
        "harden", help="plan package changes (a dry run unless --apply)"
    )
    fhard.add_argument("--apply", action="store_true", help="disable the packages on the stick")
    fhard.add_argument(
        "--batch",
        type=int,
        choices=[1, 2],
        default=1,
        help="batch 1 is proved on this stick; batch 2 is reported safe for Fire TV (default 1)",
    )
    fhard.add_argument("--package", default=None, help="only this package (it must be in the plan)")
    fundo = fsub.add_parser("undo", help="re-enable disabled packages")
    fundo.add_argument("--apply", action="store_true", help="enable the packages on the stick")
    fundo.add_argument("--package", default=None, help="only this package (it must be in the plan)")
    return parser


def _label(path: str, cname: str) -> str:
    return path + "/" + cname if path else cname


def _row_line(row: HardenRow) -> str:
    current = "-" if row.current is None else str(row.current)
    desired = "-" if row.desired is None else str(row.desired)
    line = "{}  {}: {} -> {}  ({})".format(
        row.outcome.name, _label(row.path, row.cname), current, desired, row.why
    )
    if row.detail:
        line += "\n  " + str(row.detail)
    return line


def _outcome_counts(rows: List[HardenRow]) -> str:
    counts = {}  # type: Dict[ChangeOutcome, int]
    for row in rows:
        counts[row.outcome] = counts.get(row.outcome, 0) + 1
    return ", ".join(
        "{}: {}".format(outcome.name, counts[outcome]) for outcome in sorted(counts)
    )


def _print_errors(errors: List[WalkError]) -> None:
    for path, detail in errors:
        print("Could not read menu {}: {}".format(path, detail))


def _client_with_token(
    host: str, client_factory: Callable[..., SmartCastClient]
) -> Tuple[Optional[SmartCastClient], Optional[int]]:
    """The paired client for ``host``, or ``(None, 2)`` with the pair hint."""
    token = tokenstore.load_token(host)
    if token is not None:
        return client_factory(host, auth_token=token["auth_token"]), None
    print("Not paired yet. Run: python3 -m vizio_privacy --host {} pair".format(host))
    return None, 2


def _cmd_info(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    info = client_factory(host).get_device_info()
    print("model: {}".format(info.model_name))
    print("api version: {}".format(info.api_version))
    print("sc_info: {}".format(info.sc_info))
    print("cast name: {}".format(info.cast_name))
    print("inputs: {}".format(len(info.inputs)))
    present = sorted(key for key in info.binaries if key in TELEMETRY_BINARIES)
    print("telemetry components: {}".format(", ".join(present) if present else "none"))
    return 0


def _cmd_pair(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    client = client_factory(host)
    start = begin_pair(client)
    pin = input("Enter the 4-digit PIN shown on the TV: ")
    auth_token = finish_pair(client, start.challenge_type, start.pairing_token, pin)
    path = tokenstore.save_token(host, DEFAULT_DEVICE_ID, auth_token)
    print("Paired. Token saved to {}.".format(path))
    return 0


def _cmd_dump(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    client, exit_code = _client_with_token(host, client_factory)
    if client is None:
        return exit_code if exit_code is not None else 2
    errors = []  # type: List[WalkError]
    for path, item in settings.dump(client, errors=errors):
        print(
            "{} = {}  [{}]".format(
                _label(path, item.cname), targets.display_value(item), item.type.name
            )
        )
    _print_errors(errors)
    return 0


def _cmd_status(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    client, exit_code = _client_with_token(host, client_factory)
    if client is None:
        return exit_code if exit_code is not None else 2
    errors = []  # type: List[WalkError]
    rows = settings.plan(client, errors=errors)
    for row in rows:
        print(_row_line(row))
    if not rows:
        print(NO_MATCHES)
    _print_errors(errors)
    return 0


def _cmd_harden(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    client, exit_code = _client_with_token(host, client_factory)
    if client is None:
        return exit_code if exit_code is not None else 2
    errors = []  # type: List[WalkError]
    rows = settings.harden(client, apply=args.apply, errors=errors)
    for row in rows:
        print(_row_line(row))
    _print_errors(errors)
    if not rows:
        print(NO_MATCHES)
        return 0
    print(_outcome_counts(rows))
    if not args.apply:
        print("Dry run: nothing changed. Re-run with --apply to change these.")
    return 1 if any(row.outcome is ChangeOutcome.FAILED for row in rows) else 0


def _cmd_cast_optout(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    result = cast_factory(host).opt_out()
    print(result.summary())
    return 0 if result.reporting_off else 1


def _dashboard_serve(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    client, exit_code = _client_with_token(host, client_factory)
    if client is None:
        return exit_code if exit_code is not None else 2
    if args.apps:
        try:
            apps = parse_app_names(args.apps.split(","))
        except ValueError as err:
            print(str(err))
            return 2
    else:
        apps = DEFAULT_APPS
    if args.plex:
        url = args.plex
    else:
        servers = plex_discovery.discover()
        if not servers:
            print(
                "No Plex server answered on the network. "
                "Pass --plex http://<address>:32400 or set VIZIO_PLEX_URL."
            )
            return 1
        url = servers[0].base_url
    plex = PlexClient(url)
    service = DashboardService(plex, client, apps=apps)
    server = make_server(service, plex_image_source(plex), host=args.bind, port=args.port)
    lan = lan_address(host)
    port = server.server_address[1]
    print("Dashboard: http://{}:{}/  (Plex: {})".format(lan, port, url))
    print(
        "Show it on the TV with: "
        "python3 -m vizio_privacy --host {} dashboard open".format(host)
    )
    print("Stop with Ctrl-C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("Dashboard stopped.")
    return 0


def _dashboard_open(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    client, exit_code = _client_with_token(host, client_factory)
    if client is None:
        return exit_code if exit_code is not None else 2
    url = args.url or "http://{}:{}/".format(lan_address(host), args.port)
    if not _server_answers(url):
        print(
            "The dashboard server is not answering at {}. Start it with: "
            "python3 -m vizio_privacy --host {} dashboard serve".format(url, host)
        )
        return 1
    client.launch_app(AppConfig(name_space=args.namespace, app_id=args.app_id, message=url))
    current = None  # type: Optional[AppConfig]
    for _ in range(5):
        current = client.current_app()
        if current is not None and current.message == url:
            print("The TV is showing the dashboard ({}).".format(url))
            return 0
        time.sleep(1.0)
    ns = "-" if current is None else current.name_space
    app_id = "-" if current is None else current.app_id
    message = "-" if current is None else current.message
    print(
        "The TV accepted the launch but did not switch to the dashboard. "
        "It reports: NAME_SPACE {} APP_ID {} MESSAGE {}".format(ns, app_id, message)
    )
    return 1


def _cmd_dashboard(
    host: str,
    args: argparse.Namespace,
    client_factory: Callable[..., SmartCastClient],
    cast_factory: Callable[..., CastClient],
) -> int:
    if args.dashboard_command == "serve":
        return _dashboard_serve(host, args, client_factory, cast_factory)
    return _dashboard_open(host, args, client_factory, cast_factory)


_COMMANDS = {
    "info": _cmd_info,
    "pair": _cmd_pair,
    "dump": _cmd_dump,
    "status": _cmd_status,
    "harden": _cmd_harden,
    "cast-optout": _cmd_cast_optout,
    "dashboard": _cmd_dashboard,
}


def main(
    argv: Optional[List[str]] = None,
    client_factory: Optional[Callable[..., SmartCastClient]] = None,
    cast_factory: Optional[Callable[..., CastClient]] = None,
    firetv_runner_factory: Optional[Callable[[argparse.Namespace], Any]] = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "firetv":
        return firetv.run_command(args, firetv_runner_factory)
    if client_factory is None:
        client_factory = lambda host, auth_token=None: SmartCastClient(
            host, auth_token=auth_token
        )
    if cast_factory is None:
        cast_factory = lambda host: CastClient(host)
    host = args.host
    if not host:
        print("--host is required (or set VIZIO_HOST)")
        return 2
    command = _COMMANDS[args.command]
    try:
        return command(host, args, client_factory, cast_factory)
    except SmartCastError as err:
        print("TV error: {}".format(err))
        if err.result is ResultStatus.REQUIRES_PAIRING and args.command != "pair":
            print(
                "The TV no longer accepts the saved pairing. "
                "Run: python3 -m vizio_privacy --host {} pair".format(host)
            )
        return 1
    except (OSError, http.client.HTTPException) as err:
        print("Cannot reach the TV at {}: {}".format(host, err))
        return 1
