#!/usr/bin/env python3
"""Fixtures over check_block_records.py's spec_dir rule.

The rule changed on 2026-08-21 and these pin why. It used to hard-fail any `spec_dir` that was
not exactly `planning/<id>/`, which contradicted `/generate-tasks` step 2 -- explicit that LEGACY
directories still resolve and do not require migrating -- and cost a real run: HQ.9.A is a CLOSED
block whose spec is `planning/chore-fleet-parking-pass/plan.md`, and renaming that directory to
satisfy the checker would have broken nine live citations across two repos, two of them citing
`plan.md:146` by line as the operator approval for 59 promoted rows.

The question that matters is "does this point at a real spec", not "is the name canonical":

    non-canonical + resolves    -> WARN  (legacy, migrate only if the block is still open)
    non-canonical + missing     -> ERROR (a genuine dangling pointer -- the only real defect here)
    canonical     + missing     -> WARN  (/generate-tasks has not created it yet; normal)
    canonical     + resolves    -> ok

Dependency-free, same discipline as the module it tests.
"""

from __future__ import annotations

import json
import os
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


def record(spec_dir):
    return {
        "id": "HQ.9.A", "repo": "brain", "kind": "chore", "phase": 9,
        "title": "t", "description": "d", "what": "w", "why": "y",
        "sdlc_workflow": "task", "acceptance_criteria": ["a"],
        "testing_strategy": "s", "spec_dir": spec_dir,
        "created": "2026-08-21", "updated": "2026-08-21",
    }


def run(spec_dir, make_dirs=()):
    """Write the record into a throwaway planning tree and return (errors, warnings)."""
    with tempfile.TemporaryDirectory() as td:
        planning = Path(td) / "planning"
        (planning / "blocks").mkdir(parents=True)
        for d in make_dirs:
            (planning / d).mkdir(parents=True, exist_ok=True)
        p = planning / "blocks" / "HQ.9.A.json"
        p.write_text(json.dumps(record(spec_dir), indent=2, ensure_ascii=False) + "\n")
        return check_block_records.check(str(p), planning_root=str(planning))


def spec_msgs(msgs):
    return [m for m in msgs if "spec_dir" in m]


def main():
    # 1. The HQ.9.A case: legacy name, directory really exists.
    errs, warns = run("planning/chore-fleet-parking-pass/", ("chore-fleet-parking-pass",))
    check("legacy spec_dir that resolves is NOT an error", not spec_msgs(errs), f"errors: {errs}")
    check("legacy spec_dir that resolves warns instead", len(spec_msgs(warns)) == 1, f"warnings: {warns}")

    # 2. The real defect the rule exists to catch.
    errs, warns = run("planning/chore-this-was-deleted/")
    check("legacy spec_dir that does NOT resolve is an error", len(spec_msgs(errs)) == 1, f"errors: {errs}")

    # 3. A block whose spec has not been generated yet — the normal state of an open block.
    errs, warns = run("planning/HQ.9.A/")
    check("canonical spec_dir that does not exist yet is NOT an error",
          not spec_msgs(errs), f"errors: {errs}")
    check("canonical spec_dir that does not exist yet warns", len(spec_msgs(warns)) == 1, f"warnings: {warns}")

    # 4. The fully-correct case stays silent.
    errs, warns = run("planning/HQ.9.A/", ("HQ.9.A",))
    check("canonical spec_dir that resolves produces no spec_dir error", not spec_msgs(errs), f"errors: {errs}")
    check("canonical spec_dir that resolves produces no spec_dir warning",
          not spec_msgs(warns), f"warnings: {warns}")

    # 5. The real corpus: the rule must leave HQ.9.A green.
    here = Path(__file__).resolve().parent.parent.parent  # brain root
    hq = here / "planning" / "blocks" / "HQ.9.A.json"
    if hq.exists():
        errs, _ = check_block_records.check(str(hq), planning_root=str(here / "planning"))
        check("the real HQ.9.A record has no spec_dir error", not spec_msgs(errs), f"errors: {errs}")
    else:
        print("[skip] real HQ.9.A record not present from this checkout")

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_block_records.py's spec_dir rule holds against the fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
