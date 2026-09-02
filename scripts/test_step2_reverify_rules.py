#!/usr/bin/env python3
"""Source-assertion fixture over `/begin-orchestration` Step 2's isolation re-verify rules
(BT.ticket.begin-orchestration-step2-reverify-rules).

D68: this fixture is written and run FIRST against the two documents as they stand today, and is
expected to FAIL -- a fixture first observed passing proves nothing. Task 1 only creates this file;
it does not edit either document.

Checks BOTH `.claude/commands/begin-orchestration.md` and its Gemini-facing replication copy
`.agents/skills/begin-orchestration/SKILL.md`, reporting the file alongside each assertion so a
later regression names WHICH copy drifted.

The Step 2 region is located by its `## Step 2` heading and the NEXT `## ` heading, never by line
number -- line numbers move with every edit above them, which is why every existing fixture in this
repo slices command docs by marker (see scripts/test_d16_tasks_json_fallback.py,
scripts/check_worked_example_lane.py).

Four independent, named assertions per file:

  A -- the Step 2 region names a runnable control for the `base-template` isolation row: a command
       or path the lane can actually execute, not only a prose argument. The prescribed control is
       listing real `sdlc-*-wf_*.js` engine snapshot copies under
       `~/.claude/projects/<proj>/<session>/workflows/scripts/`.
  B -- the Step 2 region states that a re-verification control must exercise the SAME code path the
       system actually takes, and points at `/generate-master-plan` as that rule's home rather than
       restating the rule in full.
  C -- the Step 2 region states the lane-record isolation override rule with BOTH branches present:
       record the basis checked (and the command run to check it), or fall back to the table.
  D -- the isolation table holds exactly its four rows (the fourth, added by commit 21d12f7, is the
       "any repo that already has another session live in it" concurrent-lane row), and both the
       `base-template` row and the brain-root row still read `--no-worktree`. This is the
       no-new-forced-rows guard; it must pass BEFORE and AFTER the edits -- it is the fixture's own
       positive control, proving the Step 2 region was actually located and read rather than the
       other assertions failing because the slice came back empty.

Usage:
    python3 scripts/test_step2_reverify_rules.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TARGET_FILES = [
    REPO_ROOT / ".claude" / "commands" / "begin-orchestration.md",
    REPO_ROOT / ".agents" / "skills" / "begin-orchestration" / "SKILL.md",
]

STEP2_HEADING_RE = re.compile(r"^##\s+Step 2\b.*$", re.MULTILINE)
NEXT_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)

# --- Assertion A: a runnable control for the base-template row -------------------------------
CONTROL_PHRASES = [
    "sdlc-*-wf_",
    "workflows/scripts",
]

# --- Assertion B: same-code-path requirement, cited (not restated) at its REAL home ------------
# The rule lives in HQ CLAUDE.md standing rule 11, amended by
# BT.ticket.positive-control-must-take-the-same-code-path, with its enforceable form in
# scripts/check_command_hazards.py's H1_FIX. It is NOT in /generate-master-plan -- that file
# contains the phrase "same code path" in an unrelated sentence about `/plan --founding`, which is
# precisely the false-positive grep hit that put the wrong citation here in the first place.
SAME_CODE_PATH_PHRASES = [
    "same code path",
]
GENERATE_MASTER_PLAN_CITATION = "check_command_hazards"

# --- Assertion C: lane-record isolation override rule, both branches ---------------------------
LANE_RECORD_PHRASES = [
    "lane record",
    "isolation",
]
OVERRIDE_BRANCH_PHRASES = [
    "basis",
]
FALLBACK_BRANCH_PHRASES = [
    "fall back to the table",
]

# --- Assertion D: exactly four rows, base-template and brain-root read --no-worktree -----------
EXPECTED_ROW_COUNT = 4
BASE_TEMPLATE_ROW_RE = re.compile(
    r"\|\s*`base-template`\s*\|[^\n]*`--no-worktree`", re.IGNORECASE
)
BRAIN_ROOT_ROW_RE = re.compile(
    r"\|\s*the brain root[^\n|]*\|[^\n]*`--no-worktree`", re.IGNORECASE
)
TABLE_ROW_RE = re.compile(r"^\|\s*`?[^\n|]+?`?\s*\|\s*\*?\*?`--", re.MULTILINE)


class RegionNotFound(Exception):
    """Raised when the `## Step 2` heading (or its closing next heading) cannot be located --
    always an error, never a silent empty-string pass."""


def extract_step2_region(text: str) -> str:
    match = STEP2_HEADING_RE.search(text)
    if not match:
        raise RegionNotFound("no `## Step 2` heading found")
    start = match.end()
    next_match = NEXT_HEADING_RE.search(text, start)
    end = next_match.start() if next_match else len(text)
    region = text[start:end]
    if not region.strip():
        raise RegionNotFound("`## Step 2` region is empty")
    return region


def _missing(phrases: list[str], haystack: str) -> list[str]:
    return [p for p in phrases if p.lower() not in haystack.lower()]


def assert_a_named_control(region: str) -> str | None:
    missing = _missing(CONTROL_PHRASES, region)
    if missing:
        return (
            f"assertion A FAILED: Step 2 does not name a runnable control for the "
            f"`base-template` row -- missing phrase(s): {missing}"
        )
    return None


def assert_b_same_code_path_cited(region: str) -> str | None:
    missing_phrase = _missing(SAME_CODE_PATH_PHRASES, region)
    if missing_phrase:
        return (
            f"assertion B FAILED: Step 2 does not state the same-code-path requirement -- "
            f"missing phrase(s): {missing_phrase}"
        )
    if GENERATE_MASTER_PLAN_CITATION.lower() not in region.lower():
        return (
            f"assertion B FAILED: Step 2 does not cite {GENERATE_MASTER_PLAN_CITATION!r} as "
            "the same-code-path rule's home"
        )
    return None


def assert_c_lane_record_override_rule(region: str) -> str | None:
    missing_lane = _missing(LANE_RECORD_PHRASES, region)
    if missing_lane:
        return (
            f"assertion C FAILED: Step 2 does not mention the lane record's own `isolation` "
            f"field -- missing phrase(s): {missing_lane}"
        )
    missing_basis = _missing(OVERRIDE_BRANCH_PHRASES, region)
    if missing_basis:
        return (
            "assertion C FAILED: Step 2 does not require a checked basis for a lane-record "
            f"isolation override -- missing phrase(s): {missing_basis}"
        )
    missing_fallback = _missing(FALLBACK_BRANCH_PHRASES, region)
    if missing_fallback:
        return (
            "assertion C FAILED: Step 2 does not state the fall-back-to-the-table branch -- "
            f"missing phrase(s): {missing_fallback}"
        )
    return None


def assert_d_table_unchanged(region: str) -> str | None:
    rows = TABLE_ROW_RE.findall(region)
    if len(rows) != EXPECTED_ROW_COUNT:
        return (
            f"assertion D FAILED: expected exactly {EXPECTED_ROW_COUNT} isolation table rows, "
            f"found {len(rows)}: {rows}"
        )
    if not BASE_TEMPLATE_ROW_RE.search(region):
        return "assertion D FAILED: `base-template` row no longer reads `--no-worktree`"
    if not BRAIN_ROOT_ROW_RE.search(region):
        return "assertion D FAILED: brain-root row no longer reads `--no-worktree`"
    return None


ASSERTIONS = [
    ("A", assert_a_named_control),
    ("B", assert_b_same_code_path_cited),
    ("C", assert_c_lane_record_override_rule),
    ("D", assert_d_table_unchanged),
]


def main() -> int:
    failures: list[str] = []
    any_region_missing = False

    for path in TARGET_FILES:
        if not path.is_file():
            print(f"FAIL: file not found: {path}")
            failures.append(str(path))
            any_region_missing = True
            continue

        text = path.read_text()
        try:
            region = extract_step2_region(text)
        except RegionNotFound as exc:
            print(f"FAIL: {path}: {exc}")
            failures.append(f"{path}: {exc}")
            any_region_missing = True
            continue

        for label, fn in ASSERTIONS:
            result = fn(region)
            if result is None:
                print(f"ok   {path}: assertion {label} passed")
            else:
                print(f"FAIL {path}: {result}")
                failures.append(f"{path}: assertion {label}")

    if any_region_missing:
        print("FAIL: at least one file's Step 2 region could not be located -- see above")
        return 1

    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ok   all assertions passed for both files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
