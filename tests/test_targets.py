"""Tests for the privacy matching rules in targets.py."""
from __future__ import annotations

import types
import unittest

from vizio_privacy import targets as t


def it(cname, name, elements=(), value=None):
    return types.SimpleNamespace(cname=cname, name=name, elements=list(elements), value=value)


class WordsTest(unittest.TestCase):
    def test_words(self):
        self.assertEqual(t.words("Limit Ad Tracking"), ["limit", "ad", "tracking"])
        self.assertEqual(t.words("admin_and_privacy"), ["admin", "and", "privacy"])
        self.assertEqual(t.words(None), [])


class MatchesTest(unittest.TestCase):
    def test_matches_tracking_items(self):
        for item in [
            it("viewing_data", "Viewing Data"),
            it("smart_interactivity", "Smart Interactivity"),
            it("interest_based_ads", "Interest-Based Ads"),
            it("limit_ad_tracking", "Limit Ad Tracking"),
            it("do_not_track", "Do Not Track"),
            it("acr", "ACR"),
            it("personalized_recommendations", "Personalized Recommendations"),
        ]:
            self.assertIsNotNone(t.matches(item), item.cname)

    def test_matches_reason(self):
        self.assertEqual(
            t.matches(it("limit_ad_tracking", "Limit Ad Tracking")), "ad tracking"
        )

    def test_no_match(self):
        for item in [
            it("downloads", "Downloads"),
            it("advanced_picture", "Advanced Picture"),
            it("admin_and_privacy", "Admin & Privacy"),
            it("ad_volume", "AD Volume"),
            it("audio_track", "Audio Track"),
            it("tvad_id", "TVAD ID"),
            it("picture_mode", "Picture Mode"),
        ]:
            self.assertIsNone(t.matches(item), item.cname)


class PrivateValueTest(unittest.TestCase):
    def test_private_value(self):
        self.assertEqual(
            t.private_value(it("viewing_data", "Viewing Data", ["On", "Off"])), "Off"
        )
        self.assertEqual(
            t.private_value(it("limit_ad_tracking", "Limit Ad Tracking", ["On", "Off"])),
            "On",
        )
        self.assertEqual(
            t.private_value(it("do_not_track", "Do Not Track", ["Off", "On"])), "On"
        )
        self.assertEqual(
            t.private_value(
                it("personalized_recommendations", "Personalized Recommendations", ["Normal", "Off"])
            ),
            "Off",
        )
        self.assertEqual(
            t.private_value(it("interest_based_ads", "Interest-Based Ads", ["Enabled", "Disabled"])),
            "Disabled",
        )
        self.assertIsNone(
            t.private_value(it("recommendations", "Recommendations", ["Enabled", "Custom"]))
        )
        self.assertIsNone(
            t.private_value(it("limit_ad_tracking", "Limit Ad Tracking", ["Limited", "Unlimited"]))
        )


class ProtectiveTest(unittest.TestCase):
    def test_protective_true(self):
        for item in [
            it("limit_ad_tracking", "Limit Ad Tracking"),
            it("do_not_track", "Do Not Track"),
            it("dont_track", "Don't Track"),
            it("opt_out_interest_ads", "Opt Out of Interest-Based Ads"),
        ]:
            self.assertTrue(t.is_protective(item), item.cname)

    def test_protective_false(self):
        for item in [
            it("viewing_data", "Viewing Data"),
            it("interest_based_ads", "Interest-Based Ads"),
        ]:
            self.assertFalse(t.is_protective(item), item.cname)


class IdentifierTest(unittest.TestCase):
    def test_identifier_true(self):
        for item in [
            it("serial_number", "Serial Number"),
            it("tvad_id", "TVAD ID"),
            it("mac_address", "MAC Address"),
            it("advertising_id", "Advertising ID"),
        ]:
            self.assertTrue(t.is_identifier(item), item.cname)

    def test_identifier_false(self):
        for item in [
            it("viewing_data", "Viewing Data"),
            it("ad_volume", "AD Volume"),
        ]:
            self.assertFalse(t.is_identifier(item), item.cname)


class DisplayValueTest(unittest.TestCase):
    def test_display_value(self):
        self.assertEqual(
            t.display_value(it("serial_number", "Serial Number", value="SHOULD_NOT_APPEAR")),
            "<hidden>",
        )
        self.assertEqual(
            t.display_value(it("picture_mode", "Picture Mode", value="Calibrated")),
            "Calibrated",
        )


class SkipMenuTest(unittest.TestCase):
    def test_skip_menu_true(self):
        for item in [
            it("system_information", "System Information"),
            it("channels", "Channels"),
        ]:
            self.assertTrue(t.skip_menu(item), item.cname)

    def test_skip_menu_false(self):
        for item in [
            it("admin_and_privacy", "Admin & Privacy"),
            it("reset_and_admin", "Reset & Admin"),
            it("advertising", "Advertising"),
            it("picture", "Picture"),
        ]:
            self.assertFalse(t.skip_menu(item), item.cname)


if __name__ == "__main__":
    unittest.main()
