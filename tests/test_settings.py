"""Tests for the settings walk, plan and harden. They never open a socket."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional

from vizio_privacy.api import SmartCastClient
from vizio_privacy.settings import ChangeOutcome, dump, harden, plan

from tests.fakes import FakeTV

M = "T_MENU_V1"
L = "T_LIST_V1"
V = "T_VALUE_V1"


def item(
    cname: str,
    name: str,
    type_: str,
    value: Any = None,
    elements: Optional[List[str]] = None,
    hashval: Optional[int] = None,
) -> Dict[str, Any]:
    obj = {"CNAME": cname, "NAME": name, "TYPE": type_}  # type: Dict[str, Any]
    if value is not None:
        obj["VALUE"] = value
    if elements is not None:
        obj["ELEMENTS"] = list(elements)
    if hashval is not None:
        obj["HASHVAL"] = hashval
    return obj


def tree() -> Dict[str, List[dict]]:
    return {
        "": [
            item("admin_and_privacy", "Admin & Privacy", M),
            item("system_information", "System Information", M),
            item("picture", "Picture", M),
            item("broken", "Broken", M),
        ],
        "admin_and_privacy": [
            item("viewing_data", "Viewing Data", L, "On", ["On", "Off"], 11),
            item("advertising", "Advertising", M),
            item("interest_based_ads", "Interest-Based Ads", L, "Off", ["On", "Off"], 12),
            item("ad_id", "Advertising ID", V, "SENTINEL-ID", None, 13),
        ],
        "admin_and_privacy/advertising": [
            item("limit_ad_tracking", "Limit Ad Tracking", L, "Off", ["On", "Off"], 21),
            item("recommendations", "Recommendations", L, "Enabled", ["Enabled", "Custom"], 22),
        ],
        "system_information": [
            item("serial_number", "Serial Number", V, "SENTINEL-SERIAL", None, 31),
        ],
        "picture": [
            item("downloads", "Downloads", L, "On", ["On", "Off"], 41),
            item("ad_volume", "AD Volume", L, "On", ["On", "Off"], 42),
        ],
    }


class SettingsWalkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tv = FakeTV(tree())
        self.client = SmartCastClient("tv", transport=self.tv, auth_token="t")

    def puts(self) -> List[Any]:
        out = []
        for method, path, body in self.tv.calls:
            if method == "PUT":
                out.append((path, json.loads(body) if body else None))
        return out

    def rows_by_cname(self, rows: List[Any]) -> Dict[str, Any]:
        found = {}
        for row in rows:
            found[row.cname] = row
        return found

    def test_dump_opens_submenus_skips_and_survives(self) -> None:
        pairs = dump(self.client)
        by_path = {}  # type: Dict[str, List[str]]
        for path, item_ in pairs:
            by_path.setdefault(path, []).append(item_.cname)
        self.assertEqual(
            sorted(by_path.get("admin_and_privacy/advertising", [])),
            ["limit_ad_tracking", "recommendations"],
        )
        self.assertIn("downloads", by_path.get("picture", []))
        getters = [path for method, path, _body in self.tv.calls if method == "GET"]
        self.assertIn("/menu_native/dynamic/tv_settings/broken", getters)
        for method, path, _body in self.tv.calls:
            self.assertNotIn("system_information", path)
        self.assertNotIn("serial_number", [i.cname for _p, i in pairs])

    def test_plan_rows(self) -> None:
        rows = plan(self.client)
        self.assertEqual(len(rows), 5)
        by = self.rows_by_cname(rows)
        self.assertEqual(
            sorted(by),
            [
                "ad_id",
                "interest_based_ads",
                "limit_ad_tracking",
                "recommendations",
                "viewing_data",
            ],
        )
        self.assertEqual(by["viewing_data"].outcome, ChangeOutcome.WOULD_CHANGE)
        self.assertEqual(by["viewing_data"].desired, "Off")
        self.assertEqual(by["interest_based_ads"].outcome, ChangeOutcome.ALREADY_PRIVATE)
        self.assertEqual(by["ad_id"].outcome, ChangeOutcome.NOT_A_LIST)
        self.assertIsNone(by["ad_id"].current)
        self.assertEqual(by["limit_ad_tracking"].outcome, ChangeOutcome.WOULD_CHANGE)
        self.assertEqual(by["limit_ad_tracking"].desired, "On")
        self.assertEqual(by["recommendations"].outcome, ChangeOutcome.UNRESOLVED)
        for row in rows:
            for value in (
                row.path,
                row.cname,
                row.name,
                row.why,
                row.current,
                row.desired,
                row.detail,
            ):
                self.assertNotIn("SENTINEL", str(value))

    def test_harden_dry_run_sends_no_put(self) -> None:
        rows = harden(self.client)
        self.assertEqual(self.puts(), [])
        self.assertEqual(len(rows), 5)

    def test_harden_apply_writes_and_reads_back(self) -> None:
        rows = harden(self.client, apply=True)
        self.assertEqual(
            self.puts(),
            [
                (
                    "/menu_native/dynamic/tv_settings/admin_and_privacy/viewing_data",
                    {"REQUEST": "MODIFY", "HASHVAL": 11, "VALUE": "Off"},
                ),
                (
                    "/menu_native/dynamic/tv_settings/admin_and_privacy/advertising"
                    "/limit_ad_tracking",
                    {"REQUEST": "MODIFY", "HASHVAL": 21, "VALUE": "On"},
                ),
            ],
        )
        by = self.rows_by_cname(rows)
        self.assertEqual(by["viewing_data"].outcome, ChangeOutcome.CHANGED)
        self.assertEqual(by["limit_ad_tracking"].outcome, ChangeOutcome.CHANGED)
        self.assertEqual(self.tv.menus["admin_and_privacy"][0]["VALUE"], "Off")
        self.assertEqual(self.tv.menus["admin_and_privacy/advertising"][0]["VALUE"], "On")

    def test_harden_apply_survives_a_refused_write(self) -> None:
        tv = FakeTV(tree(), refuse={"viewing_data"})
        client = SmartCastClient("tv", transport=tv, auth_token="t")
        rows = harden(client, apply=True)
        by = self.rows_by_cname(rows)
        self.assertEqual(by["viewing_data"].outcome, ChangeOutcome.FAILED)
        self.assertIn("INVALID_PARAMETER", by["viewing_data"].detail or "")
        self.assertEqual(by["limit_ad_tracking"].outcome, ChangeOutcome.CHANGED)


if __name__ == "__main__":
    unittest.main()
