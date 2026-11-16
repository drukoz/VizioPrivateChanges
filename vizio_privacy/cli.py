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
from typing import Callable, Dict, List, Optional, Tuple

from vizio_privacy import settings, targets, tokenstore
from vizio_privacy.api import ResultStatus, SmartCastClient, SmartCastError
from vizio_privacy.cast import CastClient
from vizio_privacy.pairing import DEFAULT_DEVICE_ID, begin_pair, finish_pair
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
    print(cast_factory(host).opt_out().summary())
    return 0


_COMMANDS = {
    "info": _cmd_info,
    "pair": _cmd_pair,
    "dump": _cmd_dump,
    "status": _cmd_status,
    "harden": _cmd_harden,
    "cast-optout": _cmd_cast_optout,
}


def main(
    argv: Optional[List[str]] = None,
    client_factory: Optional[Callable[..., SmartCastClient]] = None,
    cast_factory: Optional[Callable[..., CastClient]] = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
