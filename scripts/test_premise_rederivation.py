#!/usr/bin/env python3
"""Source-assertion fixture over `/begin-orchestration`'s premise re-derivation step
(BT.ticket.re-derive-block-premises-before-tasks).

D68: this fixture is written and run FIRST against the two documents as they stand today, and is
expected to FAIL -- a fixture first observed passing proves nothing. Task 1 only creates this
file; it does not edit either document.

Checks BOTH `.claude/commands/begin-orchestration.md` and its Gemini-facing replication copy
`.agents/skills/begin-orchestration/SKILL.md`, reporting the file alongside each assertion so a
later regression names WHICH copy drifted. Modelled on `scripts/test_step2_reverify_rules.py`.

The premise-rederivation region is located by a `## `-level heading containing the word
"premise" and the NEXT `## ` heading, never by line number -- line numbers move with every edit
above them.

TRAP (confirmed before writing this fixture): the two documents ALREADY contain re-derivation
language today -- `grep -in 're-deriv|premise'` returns hits in both copies -- but those hits are
Step 2's ISOLATION re-verification (`BT.ticket.begin-orchestration-step2-reverify-rules`, closed),
a different question in a different step. Assertion A must not be satisfied by that text: it
requires a HEADING containing "premise", not merely the word appearing in prose anywhere in the
document, so Step 2's prose mentions of "premise" (if any) cannot accidentally satisfy it.

Four independent, named assertions per file:

  A -- a premise re-derivation step EXISTS, locatable by its own `## ` heading containing the
       word "premise".
  B -- ORDER: that step's heading appears strictly BEFORE the `## Step N -- Confirm` heading
       (the step whose body hands off to `/orchestrate`, where `/generate-tasks` actually runs),
       compared by BYTE OFFSET of the two headings, never by line number.
  C -- the step names amendment-in-place, cites D18, and requires a COMMAND PER CLAIM. This is
       written so the WEAKER wording "re-read the record" does NOT satisfy it -- an internal
       synthetic fixture case (not one of the two real files) feeds exactly that weaker phrasing
       through the same assertion function and the run below asserts it still reports failure.
  D -- POSITIVE CONTROL, must pass before and after the edits: both files were located, are
       non-empty, and the `## Step N -- Confirm` heading was found in each. If this fails, a
       failure in A/B/C can never be mistaken for a bad slice -- it means the anchor itself moved.

--- Observed RED, captured 2026-09-03, run against the unmodified documents (exit code 1) ---

ok   /Users/brandon/Dev/agentic-portfolio/base-template/.claude/commands/begin-orchestration.md: assertion D passed
FAIL /Users/brandon/Dev/agentic-portfolio/base-template/.claude/commands/begin-orchestration.md: assertion A FAILED: no `## `-level heading containing "premise" found
FAIL /Users/brandon/Dev/agentic-portfolio/base-template/.claude/commands/begin-orchestration.md: assertion B FAILED: no premise-rederivation step heading found (assertion A already failed)
FAIL /Users/brandon/Dev/agentic-portfolio/base-template/.claude/commands/begin-orchestration.md: assertion C FAILED: no premise-rederivation step region to check (assertion A already failed)
ok   /Users/brandon/Dev/agentic-portfolio/base-template/.agents/skills/begin-orchestration/SKILL.md: assertion D passed
FAIL /Users/brandon/Dev/agentic-portfolio/base-template/.agents/skills/begin-orchestration/SKILL.md: assertion A FAILED: no `## `-level heading containing "premise" found
FAIL /Users/brandon/Dev/agentic-portfolio/base-template/.agents/skills/begin-orchestration/SKILL.md: assertion B FAILED: no premise-rederivation step heading found (assertion A already failed)
FAIL /Users/brandon/Dev/agentic-portfolio/base-template/.agents/skills/begin-orchestration/SKILL.md: assertion C FAILED: no premise-rederivation step region to check (assertion A already failed)
ok   internal self-test: assertion C correctly rejects the weaker "re-read the record" wording
FAIL: 6 assertion(s) failed:
  - .claude/commands/begin-orchestration.md: assertion A
  - .claude/commands/begin-orchestration.md: assertion B
  - .claude/commands/begin-orchestration.md: assertion C
  - .agents/skills/begin-orchestration/SKILL.md: assertion A
  - .agents/skills/begin-orchestration/SKILL.md: assertion B
  - .agents/skills/begin-orchestration/SKILL.md: assertion C

-----------------------------------------------------------------------------------------------

Usage:
    python3 scripts/test_premise_rederivation.py
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

# A "## " heading containing the word "premise" -- deliberately requires a HEADING, not just the
# word appearing somewhere in prose, so Step 2's existing re-verification text (which is NOT under
# a "premise" heading) cannot accidentally satisfy this.
PREMISE_HEADING_RE = re.compile(r"^##\s+.*\bpremise\b.*$", re.IGNORECASE | re.MULTILINE)
NEXT_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)

# The step whose body hands off to `/orchestrate` -- titled "Confirm" in both copies today,
# regardless of which step number it carries after a new step is inserted ahead of it.
CONFIRM_HEADING_RE = re.compile(r"^##\s+Step\s+\d+\s*\W*\s*Confirm\b", re.MULTILINE)

# --- Assertion C: amendment-in-place, D18 citation, command-per-claim --------------------------
AMENDMENT_PHRASES = ["amend", "in place"]
D18_CITATION = "D18"
COMMAND_PER_CLAIM_PHRASES = ["command per claim"]
# The weaker wording the fixture must NOT accept as satisfying the command-per-claim requirement.
WEAK_WORDING = "re-read the record"


class RegionNotFound(Exception):
    """Raised when the premise-rederivation heading (or the region after it) cannot be located --
    always an error, never a silent empty-string pass."""


def extract_premise_region(text: str) -> tuple[re.Match[str], str]:
    heading_match = PREMISE_HEADING_RE.search(text)
    if not heading_match:
        raise RegionNotFound('no `## `-level heading containing "premise" found')
    start = heading_match.end()
    next_match = NEXT_HEADING_RE.search(text, start)
    end = next_match.start() if next_match else len(text)
    region = text[start:end]
    if not region.strip():
        raise RegionNotFound('the "premise" heading region is empty')
    return heading_match, region


def _missing(phrases: list[str], haystack: str) -> list[str]:
    return [p for p in phrases if p.lower() not in haystack.lower()]


def assert_a_step_exists(text: str) -> tuple[str | None, re.Match[str] | None, str | None]:
    """Returns (failure-or-None, heading_match-or-None, region-or-None)."""
    try:
        heading_match, region = extract_premise_region(text)
    except RegionNotFound as exc:
        return (f"assertion A FAILED: {exc}", None, None)
    return (None, heading_match, region)


def assert_b_order(heading_match: re.Match[str] | None, text: str) -> str | None:
    if heading_match is None:
        return "assertion B FAILED: no premise-rederivation step heading found (assertion A already failed)"
    confirm_match = CONFIRM_HEADING_RE.search(text)
    if not confirm_match:
        return "assertion B FAILED: no `## Step N -- Confirm` heading found to order against"
    if heading_match.start() >= confirm_match.start():
        return (
            "assertion B FAILED: premise-rederivation heading (byte offset "
            f"{heading_match.start()}) does not appear before the Confirm heading "
            f"(byte offset {confirm_match.start()})"
        )
    return None


def assert_c_amendment_in_place(region: str | None) -> str | None:
    if region is None:
        return "assertion C FAILED: no premise-rederivation step region to check (assertion A already failed)"
    missing_amendment = _missing(AMENDMENT_PHRASES, region)
    if missing_amendment:
        return (
            "assertion C FAILED: step does not name amendment-in-place -- missing phrase(s): "
            f"{missing_amendment}"
        )
    if D18_CITATION.lower() not in region.lower():
        return "assertion C FAILED: step does not cite D18"
    missing_command = _missing(COMMAND_PER_CLAIM_PHRASES, region)
    if missing_command:
        return (
            "assertion C FAILED: step does not require a command per claim -- missing phrase(s): "
            f"{missing_command}"
        )
    return None


def assert_d_positive_control(path: Path, text: str) -> str | None:
    if not text.strip():
        return f"assertion D FAILED: {path} is empty"
    if not CONFIRM_HEADING_RE.search(text):
        return f"assertion D FAILED: `## Step N -- Confirm` heading not found in {path}"
    return None


def run_internal_self_test() -> str | None:
    """Assertion C must reject the weaker 're-read the record' wording -- prove it here with a
    synthetic region, independent of the two real files, so this holds regardless of what those
    files say."""
    weak_region = (
        "Amend the record in place, per D18. For each block, re-read the record to confirm "
        "each claim is still true."
    )
    result = assert_c_amendment_in_place(weak_region)
    if result is None:
        return (
            "internal self-test FAILED: assertion C accepted the weaker 're-read the record' "
            "wording as satisfying the command-per-claim requirement"
        )
    return None


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

        d_result = assert_d_positive_control(path, text)
        if d_result is None:
            print(f"ok   {path}: assertion D passed")
        else:
            print(f"FAIL {path}: {d_result}")
            failures.append(f"{path}: assertion D")
            any_region_missing = True

        a_result, heading_match, region = assert_a_step_exists(text)
        if a_result is None:
            print(f"ok   {path}: assertion A passed")
        else:
            print(f"FAIL {path}: {a_result}")
            failures.append(f"{path}: assertion A")

        b_result = assert_b_order(heading_match, text)
        if b_result is None:
            print(f"ok   {path}: assertion B passed")
        else:
            print(f"FAIL {path}: {b_result}")
            failures.append(f"{path}: assertion B")

        c_result = assert_c_amendment_in_place(region)
        if c_result is None:
            print(f"ok   {path}: assertion C passed")
        else:
            print(f"FAIL {path}: {c_result}")
            failures.append(f"{path}: assertion C")

    self_test_result = run_internal_self_test()
    if self_test_result is None:
        print('ok   internal self-test: assertion C correctly rejects the weaker "re-read the record" wording')
    else:
        print(f"FAIL {self_test_result}")
        failures.append("internal self-test")

    if any_region_missing:
        print("FAIL: at least one file could not be located or is missing its positive-control anchor -- see above")

    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ok   all assertions passed for both files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
