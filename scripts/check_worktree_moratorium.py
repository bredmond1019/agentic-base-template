#!/usr/bin/env python3
"""Assert both SDLC engines refuse --worktree (D81).

WHY THIS EXISTS
----------------
D81 (brain doc_id D81-worktree-moratorium, 2026-08-23) suspends --worktree
fleet-wide after three separate whole-repo-deletion incidents behind a GREEN
run. The moratorium's only real guarantee is that the engines themselves
refuse the flag -- prose (lane-record `isolation` fields, command docs) is
not parsed by anything and routes straight around a reader working from
memory. This script is the tripwire that keeps that refusal from being one
careless edit away from gone.

WHAT IT CHECKS
--------------
For each engine file: the file exists, it still parses `--worktree` into
`useWorktree` via `hasFlag('--worktree')`, and within a few lines of that
parse there is an `if (useWorktree) { ... }` guard whose body both (a) logs
a message naming "D81" and (b) returns an object carrying an `error` key --
i.e. the guard shape already used by the neighbouring `--test-depth`
validation in each file. The guard must appear close to the parse (not
merely exist anywhere in the file) so this does not accidentally match an
unrelated, legitimate `if (useWorktree)` branch deep in worktree setup code
elsewhere in the same file.

A MISSING engine file is a FAILURE, not a silent pass -- several gates in
this repo have been green because they found nothing.

This is a GATING check (once registered). It only detects that the guard
is PRESENT; it does not prove the guard FIRES at runtime -- that is verified
by invocation, separately, as this ticket's task 2 requires.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ENGINES = [
    ".claude/workflows/sdlc-task.js",
    ".claude/workflows/sdlc-flow.js",
]

# How many lines after the `useWorktree = hasFlag('--worktree')` assignment to search
# for the refusal guard. Wide enough to tolerate a few intervening lines/comments,
# narrow enough to not match an unrelated `if (useWorktree)` branch far later in the
# file (worktree setup code references useWorktree hundreds of lines further down).
SEARCH_WINDOW = 25
# How many lines to scan forward from an `if (useWorktree) {` opener while looking for
# its closing brace, before giving up on that candidate guard.
GUARD_MAX_LINES = 15

ASSIGNMENT_RE = re.compile(r"\buseWorktree\b[^=]*=\s*hasFlag\(\s*['\"]--worktree['\"]\s*\)")
GUARD_OPEN_RE = re.compile(r"if\s*\(\s*useWorktree\s*\)\s*\{")
RETURN_ERROR_RE = re.compile(r"return\s*\{[^}]*\berror\b")


def find_assignment_line(lines: list[str]) -> int | None:
    """Return the 0-based index of the `useWorktree = hasFlag('--worktree')` line, or None."""
    for i, line in enumerate(lines):
        if ASSIGNMENT_RE.search(line):
            return i
    return None


def extract_guard_block(lines: list[str], open_idx: int) -> str | None:
    """Return the joined text of the `if (useWorktree) { ... }` block starting at open_idx,
    tracking brace depth so it stops at the matching close rather than swallowing unrelated
    code. None if no matching close is found within GUARD_MAX_LINES."""
    depth = 0
    collected: list[str] = []
    for i in range(open_idx, min(open_idx + GUARD_MAX_LINES, len(lines))):
        line = lines[i]
        collected.append(line)
        depth += line.count("{") - line.count("}")
        if depth <= 0 and i > open_idx:
            return "\n".join(collected)
        # depth becomes 1 on the opener line itself; only treat <=0 as closed once
        # we've moved past the opener (handled by `i > open_idx` above). Guard the
        # single-line case `if (useWorktree) { ... }` on one line too:
        if i == open_idx and depth <= 0:
            return "\n".join(collected)
    return None


def check_worktree_guard(path: Path, rel: str) -> str | None:
    """Return None if `rel` refuses --worktree correctly; an error string otherwise."""
    if not path.exists():
        return f"{rel}: file not found"

    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    assign_idx = find_assignment_line(lines)
    if assign_idx is None:
        return (
            f"{rel}: no `useWorktree = hasFlag('--worktree')` assignment found -- "
            "the --worktree parse itself is missing or was renamed"
        )

    window_end = min(assign_idx + SEARCH_WINDOW, len(lines))
    for i in range(assign_idx, window_end):
        if not GUARD_OPEN_RE.search(lines[i]):
            continue
        block = extract_guard_block(lines, i)
        if block is None:
            continue
        has_d81 = "D81" in block
        has_return_error = bool(RETURN_ERROR_RE.search(block))
        if has_d81 and has_return_error:
            return None
        # A guard shape exists but is incomplete -- keep scanning the window in case a
        # later, more complete guard also matches (unlikely, but don't bail early on a
        # partial match when a real one might follow).

    return (
        f"{rel}: `useWorktree` is parsed at line {assign_idx + 1} but no refusal guard "
        f"(`if (useWorktree) {{ ... }}` logging D81 and returning an `error`) was found "
        f"within {SEARCH_WINDOW} lines after it -- --worktree is accepted, not refused"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("engines", nargs="*", help="engine file(s) to check (default: both SDLC engines)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    targets = args.engines or ENGINES
    failures: list[str] = []

    for rel in targets:
        path = REPO_ROOT / rel if not Path(rel).is_absolute() else Path(rel)
        err = check_worktree_guard(path, rel)
        if err:
            failures.append(err)
        elif not args.quiet:
            print(f"ok   {rel}")

    if failures:
        print("Worktree moratorium check FAILED (D81):\n")
        for f in failures:
            print(f"  - {f}")
        print(
            "\nD81 suspends --worktree fleet-wide. Both /sdlc-task and /sdlc-flow must "
            "refuse the flag unconditionally -- no override, no environment escape hatch. "
            "See docs/decisions/D81-worktree-moratorium.md."
        )
        return 1

    if not args.quiet:
        print(f"\nOK -- {len(targets)} engine(s) refuse --worktree per D81.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
