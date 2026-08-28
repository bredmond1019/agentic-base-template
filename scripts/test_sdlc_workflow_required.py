#!/usr/bin/env python3
"""Regression guard pinning check_block_records.py's sdlc_workflow enforcement (BT.2.A).

MEASURED BEFORE WRITING THIS FILE: scripts/check_block_records.py already treats
sdlc_workflow as required -- it is in REQUIRED (~line 37-38), the loop at ~line 73 errors
on a missing/empty value, and the enum check at ~line 122 errors on a value outside
{none,patch,task,run,flow}. Positive control run directly against a fixture copy of
BT.2.A.json with the field deleted:

    FAIL planning/blocks/BT.2.A.json
           required field `sdlc_workflow` is missing or empty
           sdlc_workflow `None` not one of ['flow','none','patch','run','task']

So the base-template block-record half of BT.2.A is already satisfied by shipped code.
Cases (a)-(c) below therefore PIN EXISTING CORRECT BEHAVIOUR and go green immediately
against today's check_block_records.py -- they did not start red, because there was
nothing to fix on this side. That is what a regression guard is: nothing here
manufactures a fake red by breaking the checker. What WOULD go red is a future edit to
REQUIRED or the enum check that silently demoted this to a warning -- case (e) proves
that by editing a throwaway COPY of the checker module's constants, never the real file.

NO DELTA ATTRIBUTION HERE. That belongs to the mev half (core/mev/src/brain/state.rs),
which validates sdlc_workflow on state.json BLOCKS against the fleet's 303 pre-existing
missing values. This file validates planning/blocks/ RECORDS, a different corpus: today
it is 50 records, 0 failing on this field -- there is nothing pre-existing here to
grandfather. check_block_naming.py's own header documents that a stored-baseline model
was tried in this repo and rejected (concurrent lanes create non-conforming items between
baseline resolution and the run); this file does not reintroduce that model.

Dependency-free, same discipline as the module it tests.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_block_records  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"[PASS] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}" + (f" -- {detail}" if detail else ""))


def base_record(**overrides):
    rec = {
        "id": "HQ.9.A", "repo": "brain", "kind": "chore",
        "title": "t", "description": "d", "what": "w", "why": "y",
        "sdlc_workflow": "task", "model": "sonnet", "out_of_scope": ["n/a"],
        "acceptance_criteria": ["a"], "testing_strategy": "s",
        "spec_dir": "planning/HQ.9.A/",
        "created": "2026-08-21", "updated": "2026-08-21",
        "files": {"new": [], "modified": [{"path": "x", "change": "y"}]},
        "validation_commands": ["true"],
    }
    rec.update(overrides)
    return rec


def run(record, spec_dirname="HQ.9.A"):
    """Write the record into a throwaway planning tree and return (errors, warnings)."""
    with tempfile.TemporaryDirectory() as td:
        planning = Path(td) / "planning"
        (planning / "blocks").mkdir(parents=True)
        (planning / spec_dirname).mkdir(parents=True, exist_ok=True)
        p = planning / "blocks" / "HQ.9.A.json"
        p.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        return check_block_records.check(str(p), planning_root=str(planning))


def sdlc_msgs(msgs):
    return [m for m in msgs if "sdlc_workflow" in m]


def main():
    # (a) missing sdlc_workflow FAILS.
    rec = base_record()
    del rec["sdlc_workflow"]
    errs, _ = run(rec)
    check("(a) missing sdlc_workflow is an error [PINS EXISTING BEHAVIOUR -- not new-red]",
          len(sdlc_msgs(errs)) >= 1, f"errors: {errs}")

    # (a2) empty-string sdlc_workflow FAILS the same way (the required-field emptiness rule).
    errs, _ = run(base_record(sdlc_workflow=""))
    check("(a2) empty-string sdlc_workflow is an error [PINS EXISTING BEHAVIOUR]",
          len(sdlc_msgs(errs)) >= 1, f"errors: {errs}")

    # (b) out-of-enum value FAILS.
    errs, _ = run(base_record(sdlc_workflow="bogus"))
    check("(b) out-of-enum sdlc_workflow is an error [PINS EXISTING BEHAVIOUR]",
          len(sdlc_msgs(errs)) == 1, f"errors: {errs}")

    # (c) a valid value PASSES (no sdlc_workflow error/warning at all).
    for value in sorted(check_block_records.WORKFLOWS):
        errs, warns = run(base_record(sdlc_workflow=value))
        check(f"(c) valid sdlc_workflow `{value}` produces no sdlc_workflow problem",
              not sdlc_msgs(errs) and not sdlc_msgs(warns),
              f"errors: {errs} warnings: {warns}")

    # (d) empty files/validation_commands still only WARN, per the checker's own rationale --
    # unaffected by this block's change, asserted here so a future edit can't couple the two.
    rec = base_record(sdlc_workflow="task")
    rec["files"] = {}
    rec["validation_commands"] = []
    errs, warns = run(rec)
    check("(d) empty files/validation_commands are warnings, not errors",
          not any(("files" in m or "validation_commands" in m) for m in errs),
          f"errors: {errs}")
    check("(d) empty files/validation_commands are reported as warnings",
          any("files" in m for m in warns), f"warnings: {warns}")

    # (e) THE REGRESSION GUARD ITSELF: prove this suite would catch a demotion to warning-only.
    # Edit a throwaway COPY of the checker's module-level sets inside this process -- never the
    # real scripts/check_block_records.py on disk -- to simulate the failure this block exists
    # to prevent, then restore it immediately.
    real_required = list(check_block_records.REQUIRED)
    real_workflows = set(check_block_records.WORKFLOWS)
    try:
        check_block_records.REQUIRED = [f for f in real_required if f != "sdlc_workflow"]
        check_block_records.WORKFLOWS = real_workflows | {None}
        rec = base_record()
        del rec["sdlc_workflow"]
        errs_demoted, _ = run(rec)
        check("(e) demoting sdlc_workflow enforcement is detectable by this suite "
              "(missing value no longer errors under the demoted checker)",
              len(sdlc_msgs(errs_demoted)) == 0, f"errors under demoted checker: {errs_demoted}")
    finally:
        check_block_records.REQUIRED = real_required
        check_block_records.WORKFLOWS = real_workflows

    # Sanity: restoring state leaves the real checker's behaviour intact for the rest of the run.
    errs, _ = run(base_record(sdlc_workflow="bogus"))
    check("REQUIRED/WORKFLOWS restored after the (e) simulation",
          len(sdlc_msgs(errs)) == 1, f"errors: {errs}")

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_block_records.py's sdlc_workflow enforcement holds against the "
          "fixtures (regression guard; (a)-(d) pin pre-existing correct behaviour).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
