"""Checks the committed Android golden files match the current Python model.

Imports the golden-writing script by path and, for every name it produces,
asserts the committed file's text equals render(value). Fails when someone
changes the model without re-running the script.
"""

from __future__ import annotations

import importlib.util
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "android", "scripts", "golden", "make_contract_golden.py")


def _load_script():
    spec = importlib.util.spec_from_file_location("make_contract_golden", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AndroidGoldenTest(unittest.TestCase):
    def test_committed_files_match_model(self):
        script = _load_script()
        for name, value in script.golden_files().items():
            path = os.path.join(script.OUT_DIR, name)
            with self.subTest(name=name):
                self.assertTrue(os.path.exists(path), "missing golden file: %s" % path)
                with open(path, encoding="utf-8") as handle:
                    committed = handle.read()
                self.assertEqual(committed, script.render(value))


if __name__ == "__main__":
    unittest.main()
