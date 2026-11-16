"""Asserts the committed Plex golden file equals what the golden script renders. No sockets."""

from __future__ import annotations

import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "android", "scripts", "golden", "make_plex_golden.py")


def load_module():
    spec = importlib.util.spec_from_file_location("make_plex_golden", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AndroidPlexGoldenTest(unittest.TestCase):
    def test_committed_file_matches_rendered_golden(self) -> None:
        module = load_module()
        with open(module.OUT_FILE, "r", encoding="utf-8") as handle:
            committed = handle.read()
        self.assertEqual(module.render(module.golden()), committed)


if __name__ == "__main__":
    unittest.main()
