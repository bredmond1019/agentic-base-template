#!/usr/bin/env python3
"""Fixture tests for regenerate_gemini.py — the only tool that WRITES a GEMINI.md.

Registered as `regenerate-gemini-tests`. This is a writer, not a checker, which is why it is
tested ahead of the non-gating checkers: a checker that regresses stops reporting, but a writer
that regresses destroys the Antigravity tail of every GEMINI.md it touches, silently, and the
`agent-docs` gate would then report the file as in-sync because the shared region still matches.

The load-bearing behaviour is `test_refuses_when_the_tail_marker_is_absent`. Without the marker
the tail cannot be located, and writing anyway would delete the surface-specific half — so the
script must refuse and leave the file untouched rather than produce a plausible-looking result.
"""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "regenerate_gemini.py"
_spec = importlib.util.spec_from_file_location("regenerate_gemini", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

BANNER = "> **GENERATED FILE — do not edit by hand.**\n> banner line\n"
TAIL = "## Fleet & Core Skills\n\nTAIL_SENTINEL\n"


class RegenerateGeminiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "AGENTS.md").write_text(
            "# AGENTS.md — probe\n\nShared line ALPHA.\n", encoding="utf-8"
        )
        (self.tmp / "GEMINI.md").write_text(
            "# GEMINI.md — probe\n\n" + BANNER + "\nStale line BETA.\n\n" + TAIL, encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def g(self):
        return (self.tmp / "GEMINI.md").read_text(encoding="utf-8")

    def test_regenerates_the_shared_region(self):
        self.assertEqual(mod.regenerate(self.tmp, quiet=True), 0)
        self.assertIn("ALPHA", self.g())
        self.assertNotIn("BETA", self.g())

    def test_preserves_the_tail_byte_for_byte(self):
        """The whole contract: the Antigravity half is never authored by this script."""
        mod.regenerate(self.tmp, quiet=True)
        self.assertIn("TAIL_SENTINEL", self.g())
        self.assertIn("## Fleet & Core Skills", self.g())

    def test_is_idempotent(self):
        mod.regenerate(self.tmp, quiet=True)
        once = self.g()
        mod.regenerate(self.tmp, quiet=True)
        self.assertEqual(once, self.g(), "a second run against an unchanged AGENTS.md must be a no-op")

    def test_check_mode_writes_nothing(self):
        before = self.g()
        mod.regenerate(self.tmp, check_only=True, quiet=True)
        self.assertEqual(before, self.g(), "--check must not write")

    def test_refuses_when_the_tail_marker_is_absent(self):
        """Refusing beats writing: without the marker the tail would be silently deleted."""
        (self.tmp / "GEMINI.md").write_text("no marker here\n", encoding="utf-8")
        rc = mod.regenerate(self.tmp, quiet=True)
        self.assertEqual(rc, 1, "must exit non-zero rather than guess")
        self.assertEqual(self.g(), "no marker here\n", "must leave the file untouched")

    def test_missing_agents_md_is_a_skip_not_a_crash(self):
        (self.tmp / "AGENTS.md").unlink()
        self.assertEqual(mod.regenerate(self.tmp, quiet=True), 0)

    def test_missing_gemini_md_is_a_skip_not_a_creation(self):
        """A repo with no GEMINI.md is not asking for one to be invented."""
        (self.tmp / "GEMINI.md").unlink()
        self.assertEqual(mod.regenerate(self.tmp, quiet=True), 0)
        self.assertFalse((self.tmp / "GEMINI.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
