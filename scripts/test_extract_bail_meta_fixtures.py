#!/usr/bin/env python3
"""Regression pin for scripts/extract_bail_meta_fixtures.py (close-out coverage gap fill for
BT.ticket.work-assertion-cannot-express-a-correct-empty-intersection task 5).

The extraction script is inherently a one-shot recovery tool over REAL fleet history (the HQ
brain's bail-classification retro plus each named repo's own git log) -- it has no fixture-root
parameter to redirect at synthetic data, so this suite exercises the real script against real
data (read-only) rather than inventing a synthetic classification file that would test a
different code path than the one that actually runs. What it pins, never re-implementing the
script's own recovery logic:

  1. DETERMINISM -- running the script twice produces byte-identical stdout counts and
     byte-identical fixture files. This is the property the block's own acceptance criteria
     claimed but never pinned as an automated, repeatable check.
  2. SCHEMA VALIDITY -- every fixture file written under scripts/fixtures/bail_meta/work_assertion/
     satisfies .claude/workflows/meta.schema.json's required fields for a kind:bail record.
  3. ACCOUNTING -- the script's own "recovered: N unrecoverable: M" line accounts for every
     work-assertion-shaped record the classification file names (found via the same
     case-insensitive substring the script itself uses, never hand-picked).

Run: python3 scripts/test_extract_bail_meta_fixtures.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "extract_bail_meta_fixtures.py"
SCHEMA_PATH = REPO_ROOT / ".claude" / "workflows" / "meta.schema.json"
OUT_DIR = REPO_ROOT / "scripts" / "fixtures" / "bail_meta" / "work_assertion"
HQ_ROOT = REPO_ROOT.parent
CLASSIFICATION_PATH = (
    HQ_ROOT / "planning" / "open-work" / "orchestration-runs" / "retros" / "bail-classification-2026-09-13.json"
)
WORK_ASSERTION_PATTERN = re.compile(r"work[- _]?assertion|WORK_ASSERTION|workAssertionPassed", re.I)

SUMMARY_RE = re.compile(r"recovered:\s*(\d+)\s+unrecoverable:\s*(\d+)")


def run_script() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=str(REPO_ROOT), capture_output=True, text=True
    )


def fixture_snapshot() -> dict[str, str]:
    if not OUT_DIR.is_dir():
        return {}
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(OUT_DIR.glob("*.json"))}


class ExtractBailMetaFixturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CLASSIFICATION_PATH.exists():
            raise unittest.SkipTest(
                f"source classification file not present in this checkout: {CLASSIFICATION_PATH}"
            )
        cls.run1 = run_script()
        cls.snapshot1 = fixture_snapshot()
        cls.run2 = run_script()
        cls.snapshot2 = fixture_snapshot()

    def test_script_exits_zero(self) -> None:
        self.assertEqual(self.run1.returncode, 0, self.run1.stdout + self.run1.stderr)
        self.assertEqual(self.run2.returncode, 0, self.run2.stdout + self.run2.stderr)

    def test_determinism_summary_line(self) -> None:
        m1 = SUMMARY_RE.search(self.run1.stdout)
        m2 = SUMMARY_RE.search(self.run2.stdout)
        self.assertIsNotNone(m1, f"no 'recovered: N unrecoverable: M' line in: {self.run1.stdout}")
        self.assertIsNotNone(m2, f"no 'recovered: N unrecoverable: M' line in: {self.run2.stdout}")
        self.assertEqual(m1.groups(), m2.groups(), "recovered/unrecoverable counts changed across two runs")

    def test_determinism_fixture_bytes(self) -> None:
        self.assertEqual(
            self.snapshot1, self.snapshot2, "fixture file contents differ across two runs of the same script"
        )

    def test_accounting_matches_classification_filter(self) -> None:
        records = json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))
        matched = sum(1 for rec in records if WORK_ASSERTION_PATTERN.search(json.dumps(rec)))
        m = SUMMARY_RE.search(self.run1.stdout)
        recovered, unrecoverable = (int(x) for x in m.groups())
        self.assertEqual(
            recovered + unrecoverable,
            matched,
            "recovered+unrecoverable must equal every work-assertion-shaped record the classification file names",
        )

    def test_every_fixture_validates_against_meta_schema(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        required_top = schema.get("required", [])
        required_bail = schema.get("properties", {}).get("bail", {}).get("required", [])
        self.assertTrue(self.snapshot1, "expected at least one recovered fixture on disk")
        for name, content in self.snapshot1.items():
            doc = json.loads(content)
            for field in required_top:
                self.assertIn(field, doc, f"{name}: missing required top-level field {field!r}")
            self.assertEqual(doc.get("kind"), "bail", f"{name}: kind must be 'bail'")
            bail = doc.get("bail", {})
            for field in required_bail:
                self.assertIn(field, bail, f"{name}: missing required bail.{field!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
