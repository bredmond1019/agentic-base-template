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
parse there is a refusal guard whose body both (a) logs a message naming
"D81" and (b) returns an object carrying an `error` key -- i.e. the guard
shape already used by the neighbouring `--test-depth` validation in each
file. The guard must appear close to the parse (not merely exist anywhere in
the file) so this does not accidentally match an unrelated, legitimate
`if (useWorktree)` branch deep in worktree setup code elsewhere in the same
file.

THE ONE SANCTIONED OVERRIDE (base-template D82)
-----------------------------------------------
This check originally demanded refusal "unconditionally -- no override, no
environment escape hatch." D81's lift needs an end-to-end worktree run to
happen SOMEWHERE, and two of its three incidents originated inside the
engines' own worktree setup, so a test that bypasses the engines cannot
answer the question that gates the lift. D82 therefore sanctions exactly one
opt-out and this check now pins its precise shape:

    if (useWorktree)                     <- original absolute refusal, still valid
    if (useWorktree && !acceptD81Risk)   <- refusal by DEFAULT, one-invocation opt-out

and, when the second form is used, requires the file to also contain
`acceptD81Risk = hasFlag('--accept-d81-risk')`, so the override can only ever
come from an explicit flag visible in the invocation. An env var, a
harness.json key, a differently-named flag, or an `acceptD81Risk` sourced from
anywhere but that flag all FAIL. This is a NARROWING of what counts as a legal
override, not a loosening of the refusal: every lane that does not type the
flag is refused exactly as before.

Delete the override branch here when D81 is formally lifted or re-affirmed --
it is scaffolding for one verification, not a permanent feature.

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
# The guard must refuse BY DEFAULT and may be opted out of only by the one sanctioned token,
# `acceptD81Risk` (parsed from an explicit `--accept-d81-risk` flag). Both shapes are accepted:
#   if (useWorktree)                     -- the original absolute refusal
#   if (useWorktree && !acceptD81Risk)   -- refusal by default, one-invocation opt-out
# Anything else -- an env var, a harness.json key, a differently-named flag, an inverted
# condition -- does NOT match, and the check fails. That is the point: this is a NARROWING of
# what counts as a legal override, not a loosening of the refusal.
GUARD_OPEN_RE = re.compile(
    r"if\s*\(\s*useWorktree\s*(?:&&\s*!\s*acceptD81Risk\s*)?\)\s*\{"
)
# When the opt-out form is used, the flag must actually be parsed from the sanctioned CLI flag --
# otherwise `acceptD81Risk` could be set from anywhere (an env read, a config field, a constant).
OVERRIDE_PARSE_RE = re.compile(
    r"\bacceptD81Risk\b[^=]*=\s*hasFlag\(\s*['\"]--accept-d81-risk['\"]\s*\)"
)
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
            # If the guard uses the opt-out form, the override must be parsed from the one
            # sanctioned CLI flag. A bare `acceptD81Risk` sourced from anywhere else would
            # let the refusal be bypassed invisibly, which is the thing this check exists
            # to prevent.
            if "acceptD81Risk" in lines[i] and not OVERRIDE_PARSE_RE.search(text):
                return (
                    f"{rel}: the refusal guard opts out on `acceptD81Risk`, but no "
                    f"`acceptD81Risk = hasFlag('--accept-d81-risk')` parse was found in the file -- "
                    "the override must come from that explicit flag and nothing else"
                )
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
            "refuse the flag BY DEFAULT. Exactly one override is sanctioned -- an explicit "
            "`--accept-d81-risk` flag parsed into `acceptD81Risk`, for the D81 lift "
            "verification only (base-template D82). No env var, no harness.json key, no "
            "other flag name. See docs/decisions/D81-worktree-moratorium.md and "
            "planning/decisions/D82-d81-lift-verification-escape-hatch.md."
        )
        return 1

    if not args.quiet:
        print(f"\nOK -- {len(targets)} engine(s) refuse --worktree per D81.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
