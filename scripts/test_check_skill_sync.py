#!/usr/bin/env python3
"""Regression tests for check_skill_sync.py's drift-tripwire logic.

Exercises hashing + manifest comparison against a synthetic repo layout, independent of the real
engine files, so the test doesn't churn every time sdlc-task.js/sdlc-flow.js are edited.

Run: python3 scripts/test_check_skill_sync.py
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "check_skill_sync.py"
_spec = importlib.util.spec_from_file_location("check_skill_sync", _MODULE_PATH)
check_skill_sync = importlib.util.module_from_spec(_spec)
sys.modules["check_skill_sync"] = check_skill_sync
_spec.loader.exec_module(check_skill_sync)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class DriftTripwire(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root / "engine.js", "line1\nline2\nANCHOR CONTENT\nline4\n")
        _write(self.root / "GUIDE.md", "guide\n")
        self.anchors = [("engine.js", "the-anchor", 3, 3, "GUIDE.md")]

    def tearDown(self) -> None:
        # Restore the module's MANIFEST_PATH global between tests; each test sets its own.
        pass

    def _manifest_path(self) -> Path:
        return self.root / "scripts" / "skill_sync_manifest.json"

    def test_first_run_with_no_manifest_fails(self) -> None:
        check_skill_sync.MANIFEST_PATH = self._manifest_path()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_skill_sync.run(self.root, self.anchors, update=False)
        self.assertEqual(code, 1)
        self.assertIn("no manifest entry", buf.getvalue())

    def test_update_then_verify_passes(self) -> None:
        check_skill_sync.MANIFEST_PATH = self._manifest_path()
        code = check_skill_sync.run(self.root, self.anchors, update=True)
        self.assertEqual(code, 0)
        self.assertTrue(self._manifest_path().exists())

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_skill_sync.run(self.root, self.anchors, update=False)
        self.assertEqual(code, 0)
        self.assertIn("OK", buf.getvalue())

    def test_engine_edit_after_stamp_fails(self) -> None:
        check_skill_sync.MANIFEST_PATH = self._manifest_path()
        check_skill_sync.run(self.root, self.anchors, update=True)

        # Mutate the anchored line — simulates an engine change that nobody re-verified the guide for.
        _write(self.root / "engine.js", "line1\nline2\nCHANGED CONTENT\nline4\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_skill_sync.run(self.root, self.anchors, update=False)
        self.assertEqual(code, 1)
        self.assertIn("engine content changed", buf.getvalue())

    def test_edit_outside_anchor_does_not_trip(self) -> None:
        check_skill_sync.MANIFEST_PATH = self._manifest_path()
        check_skill_sync.run(self.root, self.anchors, update=True)

        # Mutate a line OUTSIDE the anchored range — must not trip the tripwire.
        _write(self.root / "engine.js", "line1\nCHANGED\nANCHOR CONTENT\nline4\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_skill_sync.run(self.root, self.anchors, update=False)
        self.assertEqual(code, 0)

    def test_missing_engine_file_errors(self) -> None:
        check_skill_sync.MANIFEST_PATH = self._manifest_path()
        code = check_skill_sync.run(self.root, [("missing.js", "x", 1, 1, "GUIDE.md")], update=False)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
