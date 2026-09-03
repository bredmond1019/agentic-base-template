#!/usr/bin/env python3
"""check_observed_red.py -- gate for BT.ticket.gates-must-be-observed-red.

WHY THIS EXISTS
----------------
A `gates: true` check in `planning/harness.json` can be wired up, registered, green forever --
and never once have been watched actually fail. That is the exact failure mode the 2026-09-02
pattern analysis (M1) names: seventeen instances across the fleet where a gates:true check
reports clean forever because nothing ever provoked it. A check that only agrees with conforming
input is not evidence the check works; it might just never fire.

WHAT THIS SCRIPT CHECKS
-------------------------
For every check in `<harness>.validation.checks[]` with `gates: true`, an `observed_red` object
must be present with:
  - `date`      a `YYYY-MM-DD` string -- when the check was actually run against known-bad input
                and observed to fail.
  - `evidence`  a non-empty (post-strip) string -- the literal known-bad input, the command run,
                and the real failure output it produced (or, for a check that genuinely cannot be
                provoked, a `CANNOT-PROVOKE:` prefixed account of what was tried).
  - `note`      present as a key (schema requires it); this gate does not additionally require it
                be non-empty -- `evidence` is where the load-bearing proof lives.

A `gates: false` check is never required to carry one.

SELF-PROBE (the same discipline as check_failure_output_shape.py's SELF_TEST_PROBE)
-------------------------------------------------------------------------------------
Before judging the real target file, this script evaluates a fabricated in-memory check --
`gates: true`, no `observed_red` at all -- through the exact same `evaluate_check()` function
used on real checks. If that fabricated, deliberately-bad check is reported as CONFORMING, the
detector itself is broken and this script aborts with a distinct `GATE BUG:` message rather than
silently agreeing with whatever the real file happens to contain. A checker whose only evidence
is "good input passes" proves nothing -- this is what the block record calls out by name.

FAIL LINE FORMAT
-----------------
Every violation is printed as `FAIL <path> <human text>`, matching the fleet-wide format gated
by scripts/check_failure_output_shape.py (`docs/harness.md` "The FAIL line format"). `<path>` is
the harness file that was checked (the `--harness` value, or the default), so a parser can name
the artifact that is wrong.

Usage:
    check_observed_red.py [--harness PATH] [--quiet]

    --harness PATH   path to the harness.json to check (default: planning/harness.json,
                     resolved relative to this repo's root)
    --quiet          print only failures and the summary

TRAP (re-confirmed twice in this ticket's source pattern-analysis run): a piped command's exit
code is the pipe's, not this script's. Redirect this script's output to a file and check `$?` on
its own line -- never `check_observed_red.py | tail` and then trust `$?`.

Exit code 1 if the self-probe fails to detect its own known-bad fixture (a GATE BUG), or if any
real gates:true check lacks a valid observed_red record. Exit code 0 otherwise, including a
harness file with zero checks (never a state this repo is actually in, but not this script's
job to opine on).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The known-bad self-probe: a fabricated gates:true check with NO observed_red at all. This is
# never a real registered check -- it exists only to prove evaluate_check() is capable of
# flagging a violation, not merely of agreeing with input that already conforms. Mirrors
# check_failure_output_shape.py's SELF_TEST_PROBE / _self_test_negative_fixture pattern.
SELF_PROBE_CHECK = {
    "name": "self-probe-known-bad-no-observed-red",
    "command": "false",
    "purpose": "inline known-bad fixture for check_observed_red.py's own self-probe; never a real check",
    "gates": True,
}


def evaluate_check(check: dict) -> Optional[str]:
    """Return None if `check` conforms (gates:false, or gates:true with a valid observed_red).
    Otherwise return a human-readable detail string naming why it does not."""
    if not check.get("gates"):
        return None

    name = check.get("name", "<unnamed>")
    observed_red = check.get("observed_red")

    if observed_red is None:
        return f"check `{name}` (gates:true) has no observed_red record"
    if not isinstance(observed_red, dict):
        return f"check `{name}`'s observed_red is not an object"

    date = observed_red.get("date")
    if not isinstance(date, str) or not DATE_RE.fullmatch(date):
        return f"check `{name}`'s observed_red.date `{date!r}` is not YYYY-MM-DD"

    evidence = observed_red.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        return f"check `{name}`'s observed_red.evidence is empty or whitespace"

    return None


def evaluate_checks(checks: list[dict]) -> list[str]:
    """Return the list of failure-detail strings for every non-conforming gates:true check in
    `checks`, in order. Empty list means every gates:true check conforms."""
    details = []
    for check in checks:
        detail = evaluate_check(check)
        if detail is not None:
            details.append(detail)
    return details


def run(harness_path: Path, quiet: bool) -> int:
    # Self-probe first: this must run and be flagged as non-conforming before the real file is
    # ever judged. A detector that cannot detect its own known-bad fixture cannot be trusted to
    # judge anything else.
    self_probe_detail = evaluate_check(SELF_PROBE_CHECK)
    if self_probe_detail is None:
        print(
            "GATE BUG: self-probe-known-bad-no-observed-red was reported as CONFORMING, but it "
            "is a deliberately non-conforming fixture (gates:true, no observed_red at all) -- "
            "the detector cannot be trusted",
        )
        return 1
    if not quiet:
        print(f"ok   self-probe: correctly detected as non-conforming ({self_probe_detail})")

    try:
        data = json.loads(harness_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL {harness_path} could not be read/parsed: {exc}")
        return 1

    checks = data.get("validation", {}).get("checks", [])
    failures: list[str] = []
    for check in checks:
        detail = evaluate_check(check)
        name = check.get("name", "<unnamed>")
        if detail is None:
            if not quiet and check.get("gates"):
                print(f"ok   {name}: carries a valid observed_red record")
        else:
            print(f"FAIL {harness_path} {detail}")
            failures.append(detail)

    gated_count = sum(1 for c in checks if c.get("gates"))
    if failures:
        print(
            f"\n{len(failures)} of {gated_count} gates:true check(s) lack a valid observed_red "
            f"record",
        )
        return 1

    print(f"\nall {gated_count} gates:true check(s) carry a valid observed_red record")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", default=str(REPO_ROOT / "planning" / "harness.json"),
                     help="path to the harness.json to check (default: planning/harness.json)")
    ap.add_argument("--quiet", action="store_true", help="print only failures and the summary")
    args = ap.parse_args()
    return run(Path(args.harness), args.quiet)


if __name__ == "__main__":
    sys.exit(main())
