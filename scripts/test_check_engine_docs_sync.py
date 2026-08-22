#!/usr/bin/env python3
"""Regression tests for check_engine_docs_sync.py's drift-tripwire logic.

Exercises hashing + manifest comparison against a synthetic repo layout, independent of the real
engine files, so the test doesn't churn every time sdlc-task.js/sdlc-flow.js are edited — same
approach as scripts/test_check_skill_sync.py for the sibling SKILL.md tripwire.

Per D68, the reject case (test_engine_edit_after_stamp_fails) was observed failing against the
pre-fix check_engine_docs_sync.py (before the manifest-comparison logic existed) before this
suite was written to confirm the fix catches it.

Run: python3 scripts/test_check_engine_docs_sync.py
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "check_engine_docs_sync.py"
_spec = importlib.util.spec_from_file_location("check_engine_docs_sync", _MODULE_PATH)
check_engine_docs_sync = importlib.util.module_from_spec(_spec)
sys.modules["check_engine_docs_sync"] = check_engine_docs_sync
_spec.loader.exec_module(check_engine_docs_sync)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class DriftTripwire(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root / "engine.js", "line1\nline2\nANCHOR CONTENT\nline4\n")
        _write(self.root / "docs" / "workflows" / "GUIDE.md", "guide\n")
        self.anchors = [
            ("engine.js", "the-anchor", 3, 3, "docs/workflows/GUIDE.md", "## Some Section"),
        ]

    def _manifest_path(self) -> Path:
        return self.root / "scripts" / "engine_docs_sync_manifest.json"

    def test_first_run_with_no_manifest_fails(self) -> None:
        check_engine_docs_sync.MANIFEST_PATH = self._manifest_path()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_engine_docs_sync.run(self.root, self.anchors, update=False)
        self.assertEqual(code, 1)
        self.assertIn("no manifest entry", buf.getvalue())

    def test_update_then_verify_passes(self) -> None:
        check_engine_docs_sync.MANIFEST_PATH = self._manifest_path()
        code = check_engine_docs_sync.run(self.root, self.anchors, update=True)
        self.assertEqual(code, 0)
        self.assertTrue(self._manifest_path().exists())

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_engine_docs_sync.run(self.root, self.anchors, update=False)
        self.assertEqual(code, 0)
        self.assertIn("OK", buf.getvalue())

    def test_engine_edit_after_stamp_fails_and_names_the_anchor(self) -> None:
        check_engine_docs_sync.MANIFEST_PATH = self._manifest_path()
        check_engine_docs_sync.run(self.root, self.anchors, update=True)

        # Mutate the anchored line — simulates an engine behaviour change that nobody re-verified
        # the docs page for. This is the reject case D68 requires be observed failing first: run
        # against the PRE-FIX module (no manifest-comparison branch) it would report OK, which is
        # exactly the silent-drift bug this script exists to close.
        _write(self.root / "engine.js", "line1\nline2\nCHANGED CONTENT\nline4\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_engine_docs_sync.run(self.root, self.anchors, update=False)
        self.assertEqual(code, 1)
        output = buf.getvalue()
        self.assertIn("engine content changed", output)
        self.assertIn("the-anchor", output)
        self.assertIn("GUIDE.md", output)

    def test_edit_outside_anchor_does_not_trip(self) -> None:
        check_engine_docs_sync.MANIFEST_PATH = self._manifest_path()
        check_engine_docs_sync.run(self.root, self.anchors, update=True)

        # Mutate a line OUTSIDE the anchored range — must not trip the tripwire (positive control:
        # proves the suite can also report green, not just red).
        _write(self.root / "engine.js", "line1\nCHANGED\nANCHOR CONTENT\nline4\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_engine_docs_sync.run(self.root, self.anchors, update=False)
        self.assertEqual(code, 0)

    def test_missing_engine_file_errors(self) -> None:
        check_engine_docs_sync.MANIFEST_PATH = self._manifest_path()
        code = check_engine_docs_sync.run(
            self.root, [("missing.js", "x", 1, 1, "docs/workflows/GUIDE.md", "## Section")], update=False
        )
        self.assertEqual(code, 1)

    def test_update_writes_docs_md_and_section_fields(self) -> None:
        check_engine_docs_sync.MANIFEST_PATH = self._manifest_path()
        check_engine_docs_sync.run(self.root, self.anchors, update=True)
        import json
        manifest = json.loads(self._manifest_path().read_text(encoding="utf-8"))
        entry = manifest["engine.js::the-anchor"]
        self.assertEqual(entry["docs_md"], "docs/workflows/GUIDE.md")
        self.assertEqual(entry["section"], "## Some Section")


if __name__ == "__main__":
    unittest.main()
