"""Tests for the Fire TV package commands.

They pass a fake ADB runner to the command line and a fake ``run`` to
``subprocess_runner``; nothing here calls ``subprocess`` for real, so no test
can contact the stick.
"""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Tuple
from unittest import mock

from vizio_privacy import firetv
from vizio_privacy.cli import main
from vizio_privacy.firetv import (
    DISABLE_PLAN,
    NEVER_DISABLE,
    PROTECTED,
    AdbResult,
    ChangeOutcome,
    PackageGroup,
    PackageState,
    subprocess_runner,
)

DEVICE = "192.0.2.1:5555"

B1_METRICS = "com.amazon.client.metrics.api"
B1_ADS = "com.amazon.kso.blackbird"
B2_METRICS = "com.amazon.spiderpork"
B2_UPDATES = "com.amazon.tv.forcedotaupdater.v2"
PROTECTED_ONE = "com.amazon.client.metrics"
NEVER_ONE = "com.amazon.vizzini"


class FakeAdb:
    """A callable stand-in for an AdbRunner. It records every argument list."""

    def __init__(
        self,
        installed: Iterable[str] = (),
        disabled: Iterable[str] = (),
        protected: Iterable[str] = (),
        stubborn: Iterable[str] = (),
        offline: bool = False,
    ) -> None:
        self.installed = set(installed)
        self.disabled = set(disabled) & self.installed
        self.protected = set(protected)
        # in stubborn: disable-user prints success but the package stays enabled
        self.stubborn = set(stubborn)
        self.offline = offline
        self.calls: List[List[str]] = []

    def __call__(self, args: List[str]) -> AdbResult:
        self.calls.append(list(args))
        if args == ["get-state"]:
            if self.offline:
                return AdbResult(1, "error: device offline\n")
            return AdbResult(0, "device\n")
        if args[:4] == ["shell", "pm", "list", "packages"]:
            if args[4:] == []:
                names = self.installed
            elif args[4:] == ["-d"]:
                names = self.installed & self.disabled
            else:
                raise AssertionError("unexpected pm list: %r" % (args,))
            return AdbResult(0, "".join("package:%s\n" % name for name in sorted(names)))
        if args[:5] == ["shell", "pm", "disable-user", "--user", "0"]:
            pkg = args[5]
            if pkg in self.protected:
                return AdbResult(
                    255,
                    "Error: java.lang.SecurityException: "
                    + firetv.PROTECTED_MESSAGE
                    + "\n",
                )
            if pkg not in self.installed:
                return AdbResult(255, "Error: unknown package: %s\n" % pkg)
            if pkg not in self.stubborn:
                self.disabled.add(pkg)
            return AdbResult(0, "Package %s new state: disabled-user\n" % pkg)
        if args[:3] == ["shell", "pm", "enable"]:
            pkg = args[3]
            if pkg not in self.installed:
                return AdbResult(255, "Error: unknown package: %s\n" % pkg)
            self.disabled.discard(pkg)
            return AdbResult(0, "Package %s new state: enabled\n" % pkg)
        raise AssertionError("unexpected adb args: %r" % (args,))

    def pm_calls(self) -> List[List[str]]:
        return [call for call in self.calls if call[:2] == ["shell", "pm"]]

    def disable_calls(self) -> List[List[str]]:
        return [call for call in self.calls if call[:3] == ["shell", "pm", "disable-user"]]

    def enable_calls(self) -> List[List[str]]:
        return [call for call in self.calls if call[:3] == ["shell", "pm", "enable"]]


def run_firetv(argv: List[str], runner: Any) -> Tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(
            ["firetv", "--device", DEVICE] + argv,
            firetv_runner_factory=lambda args: runner,
        )
    return code, buffer.getvalue()


def all_enabled() -> Dict[str, PackageState]:
    states = {planned.package: PackageState.ENABLED for planned in DISABLE_PLAN}
    states.update({pkg: PackageState.ENABLED for pkg in PROTECTED})
    return states


class PlanDataTests(unittest.TestCase):
    EXPECTED = [
        ("com.amazon.client.metrics.api", 0, 1),
        ("com.amazon.metrics.api", 0, 1),
        ("com.amazon.tv.fw.metrics", 0, 1),
        ("com.amazon.wirelessmetrics.service", 0, 1),
        ("com.amazon.perfcollection", 0, 1),
        ("com.amazon.dp.logger", 0, 1),
        ("com.amazon.ceviche", 0, 1),
        ("com.amazon.tv.developer.dataservice", 0, 1),
        ("com.amazon.wifilocker", 0, 1),
        ("com.amazon.kso.blackbird", 1, 1),
        ("com.amazon.sneakpeek", 1, 1),
        ("com.amazon.hybridadidservice", 1, 1),
        ("com.amazon.hedwig", 1, 1),
        ("com.amazon.tv.easyupgrade", 1, 1),
        ("com.amazon.device.sale.service", 1, 1),
        ("com.amazon.shoptv.client", 1, 1),
        ("com.amazon.shoptv.firetv.client", 1, 1),
        ("com.amazon.tv.website_launcher", 1, 1),
        ("com.amazon.bueller.photos", 1, 1),
        ("com.amazon.neo.minerva.logcat", 0, 2),
        ("com.amazon.spiderpork", 0, 2),
        ("com.amazon.privacypassservice", 1, 2),
        ("com.amazon.media.recommendations", 1, 2),
        ("com.amazon.systemnotices", 1, 2),
        ("com.amazon.videoads.app", 1, 2),
        ("com.amazon.tv.forcedotaupdater.v2", 2, 2),
    ]

    def test_plan_is_the_spec_table_in_order(self) -> None:
        self.assertEqual(
            [(p.package, int(p.group), p.batch) for p in DISABLE_PLAN], self.EXPECTED
        )

    def test_protected_list_is_exact(self) -> None:
        self.assertEqual(
            PROTECTED,
            (
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
            ),
        )

    def test_never_disable_list_is_exact(self) -> None:
        self.assertEqual(
            NEVER_DISABLE,
            (
                "com.amazon.vizzini",
                "com.amazon.device.messaging",
                "com.amazon.firebat",
                "com.amazon.tv.support",
                "com.amazon.tv.launcher",
                "com.rukoz.tvhome",
            ),
        )

    def test_the_three_lists_share_no_package(self) -> None:
        plan = {planned.package for planned in DISABLE_PLAN}
        self.assertEqual(plan & set(PROTECTED), set())
        self.assertEqual(plan & set(NEVER_DISABLE), set())
        self.assertEqual(set(PROTECTED) & set(NEVER_DISABLE), set())

    def test_enums_have_the_spec_numbers(self) -> None:
        self.assertEqual(
            [int(v) for v in (PackageGroup.TELEMETRY, PackageGroup.ADS, PackageGroup.UPDATES)],
            [0, 1, 2],
        )
        self.assertEqual(
            [
                int(v)
                for v in (
                    PackageState.NOT_INSTALLED,
                    PackageState.ENABLED,
                    PackageState.DISABLED,
                )
            ],
            [0, 1, 2],
        )
        self.assertEqual(
            [int(v) for v in (ChangeOutcome.CHANGED, ChangeOutcome.PROTECTED, ChangeOutcome.FAILED)],
            [0, 1, 2],
        )


class PlanFunctionTests(unittest.TestCase):
    def test_batch_one_is_plan_order(self) -> None:
        chosen = firetv.packages_to_disable(all_enabled(), 1, None)
        expected = [p for p in DISABLE_PLAN if p.batch == 1]
        self.assertEqual(chosen, expected)
        self.assertEqual(len(chosen), 19)

    def test_batch_two_adds_the_second_batch(self) -> None:
        chosen = firetv.packages_to_disable(all_enabled(), 2, None)
        self.assertEqual(chosen, list(DISABLE_PLAN))
        self.assertEqual(len(chosen), 26)

    def test_skips_disabled_and_missing(self) -> None:
        states = all_enabled()
        states[B1_METRICS] = PackageState.NOT_INSTALLED
        states[B1_ADS] = PackageState.DISABLED
        chosen = [p.package for p in firetv.packages_to_disable(states, 1, None)]
        self.assertNotIn(B1_METRICS, chosen)
        self.assertNotIn(B1_ADS, chosen)
        self.assertEqual(len(chosen), 17)

    def test_only_an_enabled_package(self) -> None:
        self.assertEqual(firetv.packages_to_disable(all_enabled(), 1, B1_METRICS), [DISABLE_PLAN[0]])

    def test_only_a_disabled_or_missing_package_is_empty(self) -> None:
        states = all_enabled()
        states[B1_METRICS] = PackageState.DISABLED
        self.assertEqual(firetv.packages_to_disable(states, 1, B1_METRICS), [])
        states[B1_METRICS] = PackageState.NOT_INSTALLED
        self.assertEqual(firetv.packages_to_disable(states, 1, B1_METRICS), [])

    def test_only_refuses_never_disable(self) -> None:
        with self.assertRaises(ValueError) as caught:
            firetv.packages_to_disable(all_enabled(), 1, NEVER_ONE)
        self.assertIn("never", str(caught.exception))

    def test_only_refuses_protected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            firetv.packages_to_disable(all_enabled(), 1, PROTECTED_ONE)
        self.assertIn("protected", str(caught.exception))

    def test_only_refuses_unknown(self) -> None:
        with self.assertRaises(ValueError) as caught:
            firetv.packages_to_disable(all_enabled(), 1, "com.example.unknown")
        self.assertIn("com.example.unknown", str(caught.exception))

    def test_enable_list_is_the_disabled_plan_packages_in_order(self) -> None:
        states = all_enabled()
        states[B2_METRICS] = PackageState.DISABLED
        states[B1_ADS] = PackageState.DISABLED
        chosen = [p.package for p in firetv.packages_to_enable(states, None)]
        self.assertEqual(chosen, [B1_ADS, B2_METRICS])

    def test_enable_only(self) -> None:
        states = all_enabled()
        b2 = [p for p in DISABLE_PLAN if p.package == B2_METRICS][0]
        self.assertEqual(firetv.packages_to_enable(states, B2_METRICS), [])
        states[B2_METRICS] = PackageState.DISABLED
        self.assertEqual(firetv.packages_to_enable(states, B2_METRICS), [b2])
        with self.assertRaises(ValueError):
            firetv.packages_to_enable(states, NEVER_ONE)


class SubprocessRunnerTests(unittest.TestCase):
    class RecordingRun:
        def __init__(self, stdout: str = "", stderr: str = "", code: int = 0) -> None:
            self.calls: List[Tuple[List[str], Dict[str, Any]]] = []
            self.stdout = stdout
            self.stderr = stderr
            self.code = code

        def __call__(self, argv: List[str], **kwargs: Any) -> Any:
            self.calls.append((list(argv), kwargs))
            return SimpleNamespace(returncode=self.code, stdout=self.stdout, stderr=self.stderr)

    def test_argv_and_env(self) -> None:
        run = self.RecordingRun(stdout="package:x\n")
        runner = subprocess_runner(
            DEVICE, adb_home="/Users/tester/.vizio-privacy/adb", run=run
        )
        result = runner(["shell", "pm", "list", "packages"])
        argv, kwargs = run.calls[0]
        self.assertEqual(argv, ["adb", "-s", DEVICE, "shell", "pm", "list", "packages"])
        self.assertEqual(kwargs["env"]["HOME"], "/Users/tester/.vizio-privacy/adb")
        self.assertEqual(kwargs["env"]["ANDROID_ADB_SERVER_PORT"], "5038")
        self.assertIs(kwargs["capture_output"], True)
        self.assertIs(kwargs["text"], True)
        self.assertEqual(result, AdbResult(0, "package:x\n"))

    def test_stdout_and_stderr_are_joined(self) -> None:
        run = self.RecordingRun(stdout="a\n", stderr="b\n", code=255)
        runner = subprocess_runner(DEVICE, adb="adb", run=run)
        result = runner(["get-state"])
        self.assertEqual(result, AdbResult(255, "a\nb\n"))

    def test_home_is_untouched_without_adb_home(self) -> None:
        run = self.RecordingRun()
        runner = subprocess_runner(DEVICE, run=run)
        runner(["get-state"])
        _, kwargs = run.calls[0]
        self.assertEqual(kwargs["env"].get("HOME"), os.environ.get("HOME"))

    def test_custom_port_and_adb_path(self) -> None:
        run = self.RecordingRun()
        runner = subprocess_runner(DEVICE, adb="/opt/adb", server_port=6000, run=run)
        runner(["get-state"])
        argv, kwargs = run.calls[0]
        self.assertEqual(argv[0], "/opt/adb")
        self.assertEqual(kwargs["env"]["ANDROID_ADB_SERVER_PORT"], "6000")

    def test_refuses_uninstall_clear_and_bare_disable(self) -> None:
        run = self.RecordingRun()
        runner = subprocess_runner(DEVICE, run=run)
        for bad in (
            ["shell", "pm", "uninstall", "x"],
            ["shell", "pm", "clear", "x"],
            ["shell", "pm", "disable", "x"],
        ):
            with self.assertRaises(ValueError):
                runner(bad)
        self.assertEqual(run.calls, [])

    def test_allows_disable_user(self) -> None:
        run = self.RecordingRun()
        runner = subprocess_runner(DEVICE, run=run)
        runner(["shell", "pm", "disable-user", "--user", "0", "x"])
        self.assertEqual(len(run.calls), 1)


class StatusCliTests(unittest.TestCase):
    def test_status_lists_plan_and_protected_with_states(self) -> None:
        fake = FakeAdb(
            installed=[B1_METRICS, B1_ADS, B2_METRICS, PROTECTED_ONE],
            disabled=[B2_METRICS],
        )
        code, out = run_firetv(["status"], fake)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Fire TV " + DEVICE)
        self.assertIn("  enabled  %s  (telemetry, batch 1)" % B1_METRICS, lines)
        self.assertIn("  enabled  %s  (ads, batch 1)" % B1_ADS, lines)
        self.assertIn("  disabled  %s  (telemetry, batch 2)" % B2_METRICS, lines)
        self.assertIn("  not installed  %s  (updates, batch 2)" % B2_UPDATES, lines)
        self.assertIn("Protected (Fire OS refuses to disable): ", lines)
        self.assertIn("  enabled  %s" % PROTECTED_ONE, lines)
        for planned in DISABLE_PLAN:
            self.assertIn(planned.package, out)
        for pkg in PROTECTED:
            self.assertIn(pkg, out)
        self.assertEqual(fake.disable_calls(), [])
        self.assertEqual(fake.enable_calls(), [])


class HardenCliTests(unittest.TestCase):
    def test_dry_run_changes_nothing(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS, B1_ADS, B2_METRICS])
        code, out = run_firetv(["harden"], fake)
        self.assertEqual(code, 0)
        self.assertIn("Would disable 2 package(s):", out)
        self.assertIn("Dry run: nothing changed. Add --apply to disable them.", out)
        self.assertEqual(fake.disable_calls(), [])
        self.assertEqual(fake.disabled, set())

    def test_dry_run_with_nothing_to_do(self) -> None:
        fake = FakeAdb(installed=[])
        code, out = run_firetv(["harden"], fake)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to disable.", out)
        self.assertEqual(fake.disable_calls(), [])

    def test_apply_disables_batch_one_with_read_back(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS, B1_ADS, B2_METRICS])
        code, out = run_firetv(["harden", "--apply"], fake)
        self.assertEqual(code, 0)
        self.assertIn("disabled  %s" % B1_METRICS, out)
        self.assertIn("disabled  %s" % B1_ADS, out)
        self.assertNotIn(B2_METRICS, out)
        self.assertEqual(fake.disabled, {B1_METRICS, B1_ADS})
        disables = fake.disable_calls()
        self.assertEqual(
            [call[5] for call in disables], [B1_METRICS, B1_ADS]
        )
        for index, call in enumerate(fake.calls):
            if call in disables:
                self.assertEqual(fake.calls[index + 1], ["shell", "pm", "list", "packages", "-d"])

    def test_apply_batch_two_includes_the_second_batch(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS, B2_METRICS, B2_UPDATES])
        code, out = run_firetv(["harden", "--apply", "--batch", "2"], fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.disabled, {B1_METRICS, B2_METRICS, B2_UPDATES})

    def test_apply_protected_package(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS], protected={B1_METRICS})
        code, out = run_firetv(["harden", "--apply"], fake)
        self.assertEqual(code, 0)
        self.assertIn("protected %s" % B1_METRICS, out)
        self.assertEqual(fake.disabled, set())

    def test_apply_that_does_not_take_is_failed_and_returns_1(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS], stubborn={B1_METRICS})
        code, out = run_firetv(["harden", "--apply"], fake)
        self.assertEqual(code, 1)
        self.assertIn("FAILED    %s: " % B1_METRICS, out)
        self.assertEqual(fake.disabled, set())

    def test_package_outside_the_plan_returns_2_and_changes_nothing(self) -> None:
        for pkg in (NEVER_ONE, PROTECTED_ONE, "com.example.unknown"):
            fake = FakeAdb(installed=[B1_METRICS])
            code, out = run_firetv(["harden", "--apply", "--package", pkg], fake)
            self.assertEqual(code, 2, pkg)
            self.assertIn(pkg, out)
            self.assertEqual(fake.disable_calls(), [], pkg)
            self.assertEqual(fake.disabled, set(), pkg)

    def test_package_applies_one(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS, B1_ADS])
        code, out = run_firetv(["harden", "--apply", "--package", B1_ADS], fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.disabled, {B1_ADS})
        self.assertEqual([call[5] for call in fake.disable_calls()], [B1_ADS])


class UndoCliTests(unittest.TestCase):
    def test_dry_run_changes_nothing(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS, B1_ADS], disabled=[B1_METRICS])
        code, out = run_firetv(["undo"], fake)
        self.assertEqual(code, 0)
        self.assertIn("Would enable 1 package(s):", out)
        self.assertIn("Dry run: nothing changed. Add --apply to enable them.", out)
        self.assertEqual(fake.enable_calls(), [])
        self.assertEqual(fake.disabled, {B1_METRICS})

    def test_apply_enables_only_disabled_plan_packages(self) -> None:
        fake = FakeAdb(
            installed=[B1_METRICS, B1_ADS, B2_METRICS, PROTECTED_ONE],
            disabled=[B1_METRICS, B2_METRICS],
        )
        code, out = run_firetv(["undo", "--apply"], fake)
        self.assertEqual(code, 0)
        self.assertIn("enabled  %s" % B1_METRICS, out)
        self.assertIn("enabled  %s" % B2_METRICS, out)
        self.assertEqual(fake.disabled, set())
        self.assertEqual([call[3] for call in fake.enable_calls()], [B1_METRICS, B2_METRICS])

    def test_package_outside_the_plan_returns_2(self) -> None:
        for pkg in (NEVER_ONE, PROTECTED_ONE, "com.example.unknown"):
            fake = FakeAdb(installed=[B1_METRICS], disabled=[B1_METRICS])
            code, out = run_firetv(["undo", "--apply", "--package", pkg], fake)
            self.assertEqual(code, 2, pkg)
            self.assertEqual(fake.enable_calls(), [], pkg)

    def test_dry_run_with_nothing_to_do(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS])
        code, out = run_firetv(["undo"], fake)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to enable.", out)
        self.assertEqual(fake.enable_calls(), [])


class ConnectionTests(unittest.TestCase):
    def test_not_connected_returns_1_and_sends_no_pm_call(self) -> None:
        fake = FakeAdb(installed=[B1_METRICS], offline=True)
        code, out = run_firetv(["harden", "--apply"], fake)
        self.assertEqual(code, 1)
        self.assertIn("Not connected to %s. Run: adb connect %s" % (DEVICE, DEVICE), out)
        self.assertEqual(fake.pm_calls(), [])


class DeviceArgumentTests(unittest.TestCase):
    def test_no_device_returns_2_without_running_anything(self) -> None:
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stdout(buffer):
                code = main(["firetv", "status"])
        self.assertEqual(code, 2)
        self.assertEqual(buffer.getvalue(), "--device is required (or set FIRETV_DEVICE)\n")

    def test_device_comes_from_the_environment(self) -> None:
        seen: Dict[str, str] = {}

        def factory(args: Any) -> FakeAdb:
            seen["device"] = args.device
            return FakeAdb(installed=[B1_METRICS])

        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"FIRETV_DEVICE": DEVICE}, clear=True):
            with contextlib.redirect_stdout(buffer):
                code = main(["firetv", "status"], firetv_runner_factory=factory)
        self.assertEqual(code, 0)
        self.assertEqual(seen["device"], DEVICE)
        self.assertIn("Fire TV " + DEVICE, buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
