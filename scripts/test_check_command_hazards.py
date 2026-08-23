#!/usr/bin/env python3
"""Fixtures over check_command_hazards.py (BT.ticket.authored-command-hazard-check task 2).

Written BEFORE scripts/check_command_hazards.py exists (D68: the recorded red is the
evidence the gate can fail). Dependency-free, following scripts/test_check_block_records.py's
fixture style -- jsonschema is installed nowhere in this fleet.

THE CONTRACT THIS PINS (task 3 implements against this, not the other way round):

  detect_hazards(command: str) -> list[dict]
      Each finding is {"hazard": "H1"|"H2", "fix": "<prescribed fix text>"}. Empty list = clean.

  H1 NEGATED-NON-POSIX: `!` immediately negating an invocation of `rg`/`fd`/`jq`/`yq`/`ag`
      (a missing tool exits 127; the negation inverts a missing-tool crash into a vacuous
      pass). Flagged regardless of what follows. The POSIX-guaranteed replacement
      (`test -f <path> && ! grep -q '<pat>' <path>`) is never flagged.

  H2 DISCARDED-UPSTREAM-STATUS. Resolved here as a single rule, chosen to explain every
      instance measured in task 1's findings without also flagging the two measured false
      positives (a naive "any `cmd | grep -q`" rule cannot do both at once -- see the two
      cases below that are IDENTICAL in shape except for negation):
        (a) the command's FINAL top-level pipe stage is `tail`, `head`, or `cat` -- these
            near-unconditionally exit 0 regardless of what fed them, so whatever real
            assertion ran earlier in the pipe (`grep -q`, `rg -q`, a test binary) is
            silently converted to a pass. Flagged regardless of negation.
        (b) the command's FINAL top-level pipe stage is `grep -q` or `rg -q` AND the whole
            pipe expression is negated with a leading `!` -- negating a match-test built on
            top of an upstream command conflates "upstream ran fine and found nothing" with
            "upstream crashed", and the negation then reports the crash as CLEARED.
      `set -o pipefail` anywhere in the string defuses both -- disable detection when present.
      NOT flagged: an un-negated pipe ending in `grep -q`/`rg -q` (`head -1 f | grep -q PAT`)
      -- upstream failing here still yields no match, i.e. still fails closed, which is the
      correct outcome, not a hazard. Also not flagged: a pipe ending in something else
      entirely (`grep -ro PAT dir | wc -l`) -- that is a count feeding a later shell
      comparison, not itself a pass/fail gate.

  ALLOWLIST: list[{"pattern": str, "reason": str}], `pattern` matched by substring or
      regex against the collected command text.
  stale_allowlist_entries(all_commands: list[str]) -> list[str]
      Pattern strings that matched nothing in `all_commands` -- a self-check so a
      widened allowlist can never quietly swallow a real regression.

  collect_commands(planning_root: str, fleet: bool = False) -> list[dict]
      Each item is {"file": str, "container": str, "command": str}. `container` is one of
      "block.validation_commands", "tasks.validation_commands", "harness.check",
      "carryover.clears_when" -- the four containers named in the block record's `what`.
      A planning root with none of the four is silent (returns []).

  main(argv=None) -> int
      argparse CLI mirroring check_block_records.py: --planning DIR (default "planning"),
      --fleet, --quiet. Exit 1 if any hazard or stale allowlist entry is found; exit 0 on a
      clean or empty corpus.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"[PASS] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}" + (f" -- {detail}" if detail else ""))


def hazards_of(kind, findings):
    return [f for f in findings if f.get("hazard") == kind]


# ---------------------------------------------------------------------------
# Import guard: this is the recorded red. If check_command_hazards.py does not exist yet
# (task 2's state), every case below is reported FAIL via the substitute below rather than
# raising and aborting the whole suite silently -- an uncaught ImportError prints a
# traceback and no summary, which is a worse red to hand the next task than a clean report.
# ---------------------------------------------------------------------------
try:
    import check_command_hazards as cch  # noqa: E402
    IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - report, never raise
    cch = None
    IMPORT_ERROR = exc


def main():
    if cch is None:
        print(f"[FAIL] import check_command_hazards -- {IMPORT_ERROR}")
        print("\n1 check(s) failed:")
        print("  - import check_command_hazards")
        print("\nRECORDED RED (expected at task 2): scripts/check_command_hazards.py does not exist yet.")
        return 1

    # -- (1) H1: flagged on negated non-POSIX tools, clean on the prescribed fixed form ----
    h1_positive_cases = [
        "! rg -q hello /tmp/probe_hazard.txt",
        "! rg -L 'plan\": \"planning/x/roadmap.md' /Users/brandon/Dev/agentic-portfolio --glob '*state.json'",
        '! rg -n "\\"cost_usd\\":" crates/engine-core/src/nodes/terminal/',
        "! fd -e md dangling",
        "! jq -e '.ok' out.json",
        "! yq -e '.ok' out.yaml",
        "! ag TODO src/",
    ]
    for cmd in h1_positive_cases:
        found = hazards_of("H1", cch.detect_hazards(cmd))
        check(f"H1 flags negated non-POSIX invocation: {cmd!r}", len(found) == 1, f"got {found}")

    fixed_form = "test -f /tmp/probe_hazard.txt && ! grep -q 'hello' /tmp/probe_hazard.txt"
    found = hazards_of("H1", cch.detect_hazards(fixed_form))
    check("prescribed fixed form is NOT flagged H1", found == [], f"got {found}")
    found_h2 = hazards_of("H2", cch.detect_hazards(fixed_form))
    check("prescribed fixed form is NOT flagged H2 either", found_h2 == [], f"got {found_h2}")

    # -- (2) H2: flagged on a negated match-pipe / a pipe swallowed by tail-family ---------
    negated_match_pipe = "! bastion validate-brain --state 2>&1 | grep -q W_STATE_LEGACY_KIND"
    found = hazards_of("H2", cch.detect_hazards(negated_match_pipe))
    check("H2 flags a negated pipe ending in grep -q", len(found) == 1, f"got {found}")

    pipefail_guarded = "set -o pipefail; " + negated_match_pipe
    found = hazards_of("H2", cch.detect_hazards(pipefail_guarded))
    check("set -o pipefail defuses the negated-match-pipe shape", found == [], f"got {found}")

    swallowed_by_tail = "grep -q nomatch /tmp/probe_hazard.txt | tail -1"
    found = hazards_of("H2", cch.detect_hazards(swallowed_by_tail))
    check("H2 flags an assertion swallowed by a trailing tail", len(found) == 1, f"got {found}")

    unittest_shape = ("python3 -m unittest scripts.test_sync_downstream_harness -v 2>&1 "
                       "| tail -5 || python3 scripts/test_sync_downstream_harness.py")
    found = hazards_of("H2", cch.detect_hazards(unittest_shape))
    check("H2 flags the live BT.6.C `... | tail -N || fallback` shape", len(found) == 1, f"got {found}")

    # -- (3) the two measured false positives must stay CLEAN ------------------------------
    fp1 = "head -1 /tmp/probe_hazard.txt | grep -q '^---$'"
    found = cch.detect_hazards(fp1)
    check("false positive stays clean: assertion last, un-negated", found == [], f"got {found}")

    fp2 = "grep -ro PATTERN /tmp/dir | wc -l"
    found = cch.detect_hazards(fp2)
    check("false positive stays clean: a count, not a gate", found == [], f"got {found}")

    # -- (4) each of the four containers is actually reached -------------------------------
    with tempfile.TemporaryDirectory() as td:
        planning = Path(td) / "planning"
        (planning / "blocks").mkdir(parents=True)
        (planning / "some-spec").mkdir(parents=True)

        block_cmd = "! rg -q BLOCKPAT /tmp/block_probe.txt"
        (planning / "blocks" / "XX.ticket.y.json").write_text(json.dumps({
            "id": "XX.ticket.y", "repo": "test", "kind": "ticket",
            "validation_commands": [block_cmd],
        }, indent=2) + "\n")

        tasks_cmd = "! fd -e md TASKSPAT /tmp"
        (planning / "some-spec" / "tasks.json").write_text(json.dumps([
            {"task_id": 1, "title": "t", "validation_commands": [tasks_cmd]},
        ], indent=2) + "\n")

        harness_cmd = "grep -q nomatch /tmp/harness_probe.txt | tail -1"
        (planning / "harness.json").write_text(json.dumps({
            "validation": {"checks": [{"name": "probe", "command": harness_cmd, "gates": True}]},
        }, indent=2) + "\n")

        carryover_cmd = "! bastion validate-brain --state 2>&1 | grep -q CARRYOVERPAT"
        (planning / "state.json").write_text(json.dumps({
            "carryover": [{
                "slug": "probe-carryover",
                "kind": "defect",
                "scope": {"repo": "test", "tier": None, "cross_repo": None},
                "clears_when": {"type": "command_exits_zero", "command": carryover_cmd},
                "created": "2026-08-23",
            }],
        }, indent=2) + "\n")

        collected = cch.collect_commands(str(planning))
        by_container = {c["container"]: c["command"] for c in collected}

        check("block.validation_commands container is reached",
              by_container.get("block.validation_commands") == block_cmd,
              f"collected: {collected}")
        check("tasks.validation_commands container is reached",
              by_container.get("tasks.validation_commands") == tasks_cmd,
              f"collected: {collected}")
        check("harness.check container is reached",
              by_container.get("harness.check") == harness_cmd,
              f"collected: {collected}")
        check("carryover.clears_when container is reached",
              by_container.get("carryover.clears_when") == carryover_cmd,
              f"collected: {collected}")
        check("exactly the four fixture containers were collected, none dropped, none duplicated",
              len(collected) == 4, f"collected: {collected}")

        # -- (6) an empty repo is silent and exits 0 ----------------------------------------
        empty = Path(td) / "empty_planning"
        empty.mkdir()
        empty_collected = cch.collect_commands(str(empty))
        check("an empty planning/ collects nothing", empty_collected == [], f"got {empty_collected}")

        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "check_command_hazards.py"),
             "--planning", str(empty), "--quiet"],
            capture_output=True, text=True,
        )
        check("main() exits 0 against an empty planning/ (not a failure)", proc.returncode == 0,
              f"stdout={proc.stdout!r} stderr={proc.stderr!r}")

    # -- (5) a stale allowlist entry fails the check ----------------------------------------
    original_allowlist = list(cch.ALLOWLIST)
    try:
        cch.ALLOWLIST[:] = [{"pattern": "THIS_MATCHES_NOTHING_IN_THE_CORPUS_xyz123",
                              "reason": "deliberately stale, for the test"}]
        stale = cch.stale_allowlist_entries(["! rg -q realpat /tmp/x", "grep -q ok /tmp/y"])
        check("a stale allowlist entry (matches nothing) is reported",
              stale == ["THIS_MATCHES_NOTHING_IN_THE_CORPUS_xyz123"], f"got {stale}")

        cch.ALLOWLIST[:] = [{"pattern": "realpat", "reason": "matches the corpus below"}]
        stale = cch.stale_allowlist_entries(["! rg -q realpat /tmp/x"])
        check("an allowlist entry that DOES match something is not reported stale",
              stale == [], f"got {stale}")
    finally:
        cch.ALLOWLIST[:] = original_allowlist

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_command_hazards.py holds against the fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
