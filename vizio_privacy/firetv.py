"""The Fire TV Stick's Amazon tracking and ad packages, over ADB.

``status`` lists the plan's packages and their state on the stick, ``harden``
disables them with ``pm disable-user --user 0`` and ``undo`` re-enables them
with ``pm enable``. Everything is a dry run unless ``--apply``; a change is
applied one package at a time and every change is followed by a read-back
(``pm list packages -d``). ADB's exit codes are not trusted: the outcome of
each package comes from the read-back and the output text.

All ADB traffic goes through an ``AdbRunner`` callable, so the tests pass a
fake and never run ``adb``; the real runner also refuses ``pm uninstall``,
``pm clear`` and a bare ``pm disable`` before anything is run.
"""

from __future__ import annotations

import argparse
import enum
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


class PackageGroup(enum.IntEnum):
    TELEMETRY = 0
    ADS = 1
    UPDATES = 2


class PackageState(enum.IntEnum):
    NOT_INSTALLED = 0
    ENABLED = 1
    DISABLED = 2


class ChangeOutcome(enum.IntEnum):
    CHANGED = 0
    PROTECTED = 1
    FAILED = 2


@dataclass(frozen=True)
class PlannedPackage:
    package: str
    group: PackageGroup
    batch: int


@dataclass
class AdbResult:
    code: int
    out: str  # stdout and stderr together


AdbRunner = Callable[[List[str]], AdbResult]

PROTECTED_MESSAGE = "Cannot disable a protected package"

# batch 1: applied on this exact model and build for 10+ days by the owner.
# batch 2: reported safe for Fire TV in general, not tested on this stick.
DISABLE_PLAN: Tuple[PlannedPackage, ...] = (
    PlannedPackage("com.amazon.client.metrics.api", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.metrics.api", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.tv.fw.metrics", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.wirelessmetrics.service", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.perfcollection", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.dp.logger", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.ceviche", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.tv.developer.dataservice", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.wifilocker", PackageGroup.TELEMETRY, 1),
    PlannedPackage("com.amazon.kso.blackbird", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.sneakpeek", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.hybridadidservice", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.hedwig", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.tv.easyupgrade", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.device.sale.service", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.shoptv.client", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.shoptv.firetv.client", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.tv.website_launcher", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.bueller.photos", PackageGroup.ADS, 1),
    PlannedPackage("com.amazon.neo.minerva.logcat", PackageGroup.TELEMETRY, 2),
    PlannedPackage("com.amazon.spiderpork", PackageGroup.TELEMETRY, 2),
    PlannedPackage("com.amazon.privacypassservice", PackageGroup.ADS, 2),
    PlannedPackage("com.amazon.media.recommendations", PackageGroup.ADS, 2),
    PlannedPackage("com.amazon.systemnotices", PackageGroup.ADS, 2),
    PlannedPackage("com.amazon.videoads.app", PackageGroup.ADS, 2),
    PlannedPackage("com.amazon.tv.forcedotaupdater.v2", PackageGroup.UPDATES, 2),
)

# Fire OS 6 refuses to disable these; status shows them, no disable is sent.
PROTECTED: Tuple[str, ...] = (
    "com.amazon.client.metrics",
    "com.amazon.device.metrics",
    "com.amazon.device.crashmanager",
    "com.amazon.device.logmanager",
    "com.amazon.minerva.client.api",
    "com.amazon.diode",
    "com.fireos.usagestats.proxy",
    "com.amazon.tv.csapp",
    "com.amazon.tv.oobe",
    "com.amazon.tcomm",
    "com.amazon.ftvads.deeplinking",
    "com.amazon.device.software.ota",
    "com.amazon.device.software.ota.override",
    "com.amazon.device.rdmapplication",
    "com.amazon.securitysyncclient",
    "com.amazon.whisperlink.core.android",
)

# Disabling these breaks the stick, the remote, Prime Video or our app.
NEVER_DISABLE: Tuple[str, ...] = (
    "com.amazon.vizzini",
    "com.amazon.device.messaging",
    "com.amazon.firebat",
    "com.amazon.tv.support",
    "com.amazon.tv.launcher",
    "com.rukoz.tvhome",
)


def _refusal(args: List[str]) -> Optional[str]:
    """Why these adb arguments must never be run, or None when they are safe."""
    if "uninstall" in args:
        return "refusing to uninstall a package: " + " ".join(args)
    if "clear" in args:
        return "refusing to clear a package's data: " + " ".join(args)
    for index, arg in enumerate(args):
        if arg == "disable" and (index + 1 >= len(args) or args[index + 1] != "--user"):
            return "refusing pm disable; the only disable allowed is pm disable-user --user 0: " + " ".join(args)
    return None


def subprocess_runner(
    device: str,
    adb: str = "adb",
    adb_home: Optional[str] = None,
    server_port: int = 5038,
    timeout: float = 30.0,
    run: Callable[..., Any] = subprocess.run,
) -> AdbRunner:
    """The real runner: ``adb -s <device>`` plus the arguments the caller gives.

    The stick trusts the key under ``--adb-home``, so HOME is set to it, and
    the tool keeps to its own adb server port.
    """

    def runner(args: List[str]) -> AdbResult:
        refusal = _refusal(list(args))
        if refusal is not None:
            raise ValueError(refusal)
        env = dict(os.environ)
        env["ANDROID_ADB_SERVER_PORT"] = str(server_port)
        if adb_home:
            env["HOME"] = adb_home
        result = run(
            [adb, "-s", device] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return AdbResult(result.returncode, result.stdout + result.stderr)

    return runner


def connected(run: AdbRunner) -> bool:
    return run(["get-state"]).out.strip() == "device"


def _package_list(run: AdbRunner, extra: List[str]) -> set:
    result = run(["shell", "pm", "list", "packages"] + extra)
    names = set()
    for line in result.out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            names.add(line[len("package:"):])
    return names


def read_states(run: AdbRunner) -> Dict[str, PackageState]:
    installed = _package_list(run, [])
    disabled = _package_list(run, ["-d"])
    states: Dict[str, PackageState] = {}
    for planned in DISABLE_PLAN:
        pkg = planned.package
        if pkg not in installed:
            states[pkg] = PackageState.NOT_INSTALLED
        elif pkg in disabled:
            states[pkg] = PackageState.DISABLED
        else:
            states[pkg] = PackageState.ENABLED
    for pkg in PROTECTED:
        if pkg not in installed:
            states[pkg] = PackageState.NOT_INSTALLED
        elif pkg in disabled:
            states[pkg] = PackageState.DISABLED
        else:
            states[pkg] = PackageState.ENABLED
    return states


def _plan_package(package: str) -> PlannedPackage:
    for planned in DISABLE_PLAN:
        if planned.package == package:
            return planned
    if package in NEVER_DISABLE:
        raise ValueError(
            "{} must never be disabled: it breaks the stick, the remote, "
            "Prime Video or our app".format(package)
        )
    if package in PROTECTED:
        raise ValueError("{} is protected: Fire OS refuses to disable it".format(package))
    raise ValueError("{} is not a package this tool manages".format(package))


def packages_to_disable(
    states: Dict[str, PackageState], batch: int, only: Optional[str]
) -> List[PlannedPackage]:
    if only is not None:
        planned = _plan_package(only)
        if states.get(planned.package) == PackageState.ENABLED:
            return [planned]
        return []
    return [
        planned
        for planned in DISABLE_PLAN
        if planned.batch <= batch and states.get(planned.package) == PackageState.ENABLED
    ]


def packages_to_enable(
    states: Dict[str, PackageState], only: Optional[str]
) -> List[PlannedPackage]:
    if only is not None:
        planned = _plan_package(only)
        if states.get(planned.package) == PackageState.DISABLED:
            return [planned]
        return []
    return [
        planned
        for planned in DISABLE_PLAN
        if states.get(planned.package) == PackageState.DISABLED
    ]


def disable(
    run: AdbRunner, packages: List[PlannedPackage]
) -> List[Tuple[str, ChangeOutcome, str]]:
    results: List[Tuple[str, ChangeOutcome, str]] = []
    for planned in packages:
        pkg = planned.package
        outcome = run(["shell", "pm", "disable-user", "--user", "0", pkg])
        now_disabled = pkg in _package_list(run, ["-d"])
        if now_disabled:
            results.append((pkg, ChangeOutcome.CHANGED, ""))
        elif PROTECTED_MESSAGE in outcome.out:
            results.append((pkg, ChangeOutcome.PROTECTED, ""))
        else:
            first = outcome.out.splitlines()[0] if outcome.out.strip() else "no output"
            results.append((pkg, ChangeOutcome.FAILED, first))
    return results


def enable(
    run: AdbRunner, packages: List[PlannedPackage]
) -> List[Tuple[str, ChangeOutcome, str]]:
    results: List[Tuple[str, ChangeOutcome, str]] = []
    for planned in packages:
        pkg = planned.package
        outcome = run(["shell", "pm", "enable", pkg])
        if pkg not in _package_list(run, ["-d"]):
            results.append((pkg, ChangeOutcome.CHANGED, ""))
        else:
            first = outcome.out.splitlines()[0] if outcome.out.strip() else "no output"
            results.append((pkg, ChangeOutcome.FAILED, first))
    return results


def _state_text(state: PackageState) -> str:
    return state.name.lower().replace("_", " ")


def _group_text(group: PackageGroup) -> str:
    return group.name.lower().replace("_", " ")


def _plan_line(planned: PlannedPackage, state: PackageState) -> str:
    return "  {}  {}  ({}, batch {})".format(
        _state_text(state), planned.package, _group_text(planned.group), planned.batch
    )


def _status(device: str, states: Dict[str, PackageState]) -> int:
    print("Fire TV {}".format(device))
    for planned in DISABLE_PLAN:
        print(_plan_line(planned, states.get(planned.package, PackageState.NOT_INSTALLED)))
    print("Protected (Fire OS refuses to disable): ")
    for pkg in PROTECTED:
        print("  {}  {}".format(_state_text(states.get(pkg, PackageState.NOT_INSTALLED)), pkg))
    return 0


def _change(
    run: AdbRunner,
    states: Dict[str, PackageState],
    args: argparse.Namespace,
    verb: str,
    changed_word: str,
) -> int:
    try:
        if verb == "disable":
            packages = packages_to_disable(states, args.batch, args.package)
        else:
            packages = packages_to_enable(states, args.package)
    except ValueError as err:
        print(err)
        return 2
    if not args.apply:
        if not packages:
            print("Nothing to {}.".format(verb))
            return 0
        print("Would {} {} package(s):".format(verb, len(packages)))
        for planned in packages:
            print(_plan_line(planned, states.get(planned.package, PackageState.NOT_INSTALLED)))
        print("Dry run: nothing changed. Add --apply to {} them.".format(verb))
        return 0
    # One package at a time, each line printed (and flushed) as soon as its
    # read-back is in, so an adb error part-way still shows what changed.
    change = disable if verb == "disable" else enable
    failed = 0
    for planned in packages:
        for pkg, outcome, detail in change(run, [planned]):
            if outcome == ChangeOutcome.CHANGED:
                print("{}  {}".format(changed_word, pkg), flush=True)
            elif outcome == ChangeOutcome.PROTECTED:
                print("protected {}".format(pkg), flush=True)
            else:
                failed += 1
                print("FAILED    {}: {}".format(pkg, detail), flush=True)
    return 1 if failed else 0


def run_command(
    args: argparse.Namespace,
    runner_factory: Optional[Callable[[argparse.Namespace], AdbRunner]] = None,
) -> int:
    device = getattr(args, "device", None)
    if not device:
        print("--device is required (or set FIRETV_DEVICE)")
        return 2
    if runner_factory is not None:
        run = runner_factory(args)
    else:
        run = subprocess_runner(device, args.adb, args.adb_home, args.adb_port)
    if not connected(run):
        print("Not connected to {}. Run: adb connect {}".format(device, device))
        return 1
    states = read_states(run)
    command = args.firetv_command
    if command == "status":
        return _status(device, states)
    if command == "harden":
        return _change(run, states, args, "disable", "disabled")
    return _change(run, states, args, "enable", "enabled")
