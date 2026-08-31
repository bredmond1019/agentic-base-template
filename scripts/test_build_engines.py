#!/usr/bin/env python3
"""Fixture suite over scripts/build_engines.py -- the shared-library inliner.

Every case runs against synthetic engine/library text, never the real engines, so
this suite cannot be made to pass by editing the real ones and cannot damage them.

The load-bearing case is `test_drift_in_an_inlined_copy_is_detected`: the whole
mechanism is worthless if a hand-edit inside an engine's inlined region passes the
check. There is a matching non-vacuity case proving the checker reports OK on the
clean fixture, so a checker that always failed would not look like a pass here.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_engines", REPO_ROOT / "scripts/build_engines.py")
be = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(be)


LIB = """// header prose
// <<shared:GREET>>
const GREET = 'hello'
// <</shared:GREET>>

// <<shared:helper>>
function helper(x) {
  return x + 1
}
// <</shared:helper>>
"""

ENGINE_CLEAN = """const LOCAL = 1
// <<shared:GREET>>
const GREET = 'hello'
// <</shared:GREET>>
const AFTER = 2
// <<shared:helper>>
function helper(x) {
  return x + 1
}
// <</shared:helper>>
"""


def lib():
    return be.parse_regions(LIB, "lib")


class ParseRegionsTest(unittest.TestCase):
    def test_extracts_each_named_region(self):
        regions = lib()
        self.assertEqual(sorted(regions), ["GREET", "helper"])
        self.assertEqual(regions["GREET"][2], "const GREET = 'hello'")

    def test_unclosed_region_is_refused(self):
        with self.assertRaises(SystemExit):
            be.parse_regions("// <<shared:A>>\nconst A = 1\n", "fixture")

    def test_close_without_open_is_refused(self):
        with self.assertRaises(SystemExit):
            be.parse_regions("// <</shared:A>>\n", "fixture")

    def test_mismatched_marker_names_are_refused(self):
        with self.assertRaises(SystemExit):
            be.parse_regions("// <<shared:A>>\nx\n// <</shared:B>>\n", "fixture")

    def test_nested_region_is_refused(self):
        with self.assertRaises(SystemExit):
            be.parse_regions("// <<shared:A>>\n// <<shared:B>>\nx\n// <</shared:B>>\n", "fixture")

    def test_duplicate_region_in_one_file_is_refused(self):
        dup = "// <<shared:A>>\nx\n// <</shared:A>>\n// <<shared:A>>\nx\n// <</shared:A>>\n"
        with self.assertRaises(SystemExit):
            be.parse_regions(dup, "fixture")


class BuildTest(unittest.TestCase):
    def test_clean_engine_is_unchanged_by_a_rebuild(self):
        """Non-vacuity guard for the drift case below: a matching engine rebuilds to itself."""
        self.assertEqual(be.build(ENGINE_CLEAN, lib(), "engine"), ENGINE_CLEAN)

    def test_drift_in_an_inlined_copy_is_detected(self):
        """THE case this mechanism exists for -- a hand-edit inside an engine's inlined region
        must not survive a rebuild, which is how the gate reports it as drift."""
        drifted = ENGINE_CLEAN.replace("const GREET = 'hello'", "const GREET = 'HAND EDITED'")
        self.assertNotEqual(drifted, ENGINE_CLEAN)
        self.assertEqual(be.build(drifted, lib(), "engine"), ENGINE_CLEAN)

    def test_engine_local_code_outside_regions_is_never_touched(self):
        """The engines are mostly NOT shared. A build must leave every engine-local line alone."""
        built = be.build(ENGINE_CLEAN, lib(), "engine")
        self.assertIn("const LOCAL = 1", built)
        self.assertIn("const AFTER = 2", built)

    def test_region_position_is_preserved(self):
        """Position matters: `const` blocks are subject to TDZ, so a build that reordered or
        relocated a region could break the engine while still 'containing' every block."""
        built = be.build(ENGINE_CLEAN, lib(), "engine").split("\n")
        self.assertLess(built.index("const LOCAL = 1"), built.index("const GREET = 'hello'"))
        self.assertLess(built.index("const GREET = 'hello'"), built.index("const AFTER = 2"))

    def test_multi_line_region_replacement_does_not_corrupt_neighbours(self):
        shrunk = ENGINE_CLEAN.replace("function helper(x) {\n  return x + 1\n}", "function helper() {}")
        built = be.build(shrunk, lib(), "engine")
        self.assertEqual(built, ENGINE_CLEAN)

    def test_region_with_no_master_is_refused_rather_than_blanked(self):
        """A marker naming a block the library does not carry must ERROR. Silently emptying the
        region would delete working engine code."""
        orphan = ENGINE_CLEAN + "// <<shared:missing>>\nconst M = 1\n// <</shared:missing>>\n"
        with self.assertRaises(SystemExit):
            be.build(orphan, lib(), "engine")

    def test_engine_with_no_shared_regions_is_left_alone(self):
        plain = "const ONLY = 1\n"
        self.assertEqual(be.build(plain, lib(), "engine"), plain)


class RealArtifactsTest(unittest.TestCase):
    """Light structural assertions about the real files -- not a rebuild (the gated
    `engines-inlined` check does that), just the invariants a reader would assume."""

    def test_library_exists_and_declares_regions(self):
        regions = be.parse_regions(be.LIBRARY.read_text(), "shared.js")
        self.assertGreater(len(regions), 0)

    def test_both_engines_carry_the_same_shared_region_names(self):
        names = [sorted(be.parse_regions(e.read_text(), e.name)) for e in be.ENGINES]
        self.assertEqual(
            names[0],
            names[1],
            "both engines must mark the same shared blocks -- a block shared by only one engine "
            "is engine-local by definition and does not belong in the library",
        )

    def test_every_engine_region_has_a_master(self):
        library = set(be.parse_regions(be.LIBRARY.read_text(), "shared.js"))
        for engine in be.ENGINES:
            self.assertTrue(set(be.parse_regions(engine.read_text(), engine.name)) <= library)

    def test_no_master_is_orphaned(self):
        """An orphan master -- in the library, marked by no engine -- is the dangerous direction.
        The block looks authoritative while neither engine contains it, so an engine CALLING it
        throws at run time and `node --check` sees nothing wrong. This was created for real while
        landing the second extraction cut."""
        library = set(be.parse_regions(be.LIBRARY.read_text(), "shared.js"))
        marked: set[str] = set()
        for engine in be.ENGINES:
            marked |= set(be.parse_regions(engine.read_text(), engine.name))
        self.assertEqual(
            sorted(library - marked),
            [],
            "master block(s) present in shared.js but inlined by no engine",
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
