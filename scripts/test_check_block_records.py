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

--- D68 observed-RED record (task 1, BT.ticket.spec-files-under-planning-cannot-compile-in-ci) ---
2026-09-03: `planning_path_checks()` below was added BEFORE the planning/-path rule existed in
check_block_records.py. Captured verbatim:

    [FAIL] a files.new path under planning/ is an ERROR -- errors: ['required field `model` is
    missing or empty', 'required field `out_of_scope` is missing or empty', "model `None` not one
    of ['either', 'gemini-flash', 'gemini-pro', 'sonnet']"]
    [FAIL] a files.modified path under planning/ is an ERROR too -- errors: ['required field
    `model` is missing or empty', 'required field `out_of_scope` is missing or empty', "model
    `None` not one of ['either', 'gemini-flash', 'gemini-pro', 'sonnet']"]

    2 check(s) failed:
      - a files.new path under planning/ is an ERROR
      - a files.modified path under planning/ is an ERROR too

    (exit code 1)

The `model`/`out_of_scope` entries above are pre-existing noise from the fixture helper's
`record()` (it never sets those two REQUIRED fields) -- present on every case in this suite,
irrelevant to the planning/-path rule, and NOT what the two failing checks assert on. The checks
assert only on messages containing the literal fixture path, and none does yet.

The negative control (tests/fixtures/x.json, not flagged) and the non-promotion control (no
files[] at all still only warns) both PASS already today -- they assert the ABSENCE of a rule
that does not yet exist, and missing-files[] was already warn-only before this task. Only the
two POSITIVE cases are red, which is the scope task 2 must close.
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


def record(spec_dir, **over):
    r = {
        "id": "HQ.9.A", "repo": "brain", "kind": "chore", "phase": 9,
        "title": "t", "description": "d", "what": "w", "why": "y",
        "sdlc_workflow": "task", "acceptance_criteria": ["a"],
        "testing_strategy": "s", "spec_dir": spec_dir,
        "created": "2026-08-21", "updated": "2026-08-21",
    }
    r.update(over)
    return r


BRAIN_TOML = """
[[repos]]
slug = "brain"
prefix = "HQ"
repo_path = "."

[[repos]]
slug = "engine-rs"
prefix = "EN"
repo_path = "engine-rs"
"""


def run(spec_dir, make_dirs=(), brain_toml=None, **over):
    """Write the record into a throwaway planning tree and return (errors, warnings).

    `brain_toml` writes a brain.toml one level above `planning/`, which is what the prefix/
    repo check walks up to find. Omit it and no brain is reachable -- the standalone-repo
    case, where that check must stay silent.
    """
    with tempfile.TemporaryDirectory() as td:
        check_block_records._PREFIX_CACHE.clear()
        if brain_toml:
            (Path(td) / "brain.toml").write_text(brain_toml)
        planning = Path(td) / "planning"
        (planning / "blocks").mkdir(parents=True)
        for d in make_dirs:
            (planning / d).mkdir(parents=True, exist_ok=True)
        rec = record(spec_dir, **over)
        p = planning / "blocks" / (rec["id"] + ".json")
        p.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
        try:
            return check_block_records.check(str(p), planning_root=str(planning))
        finally:
            check_block_records._PREFIX_CACHE.clear()


def spec_msgs(msgs):
    return [m for m in msgs if "spec_dir" in m]




def prefix_msgs(msgs):
    return [m for m in msgs if "namespace" in m or "not registered in brain.toml" in m]


def op_msgs(msgs):
    return [m for m in msgs if "slug" in m]


def operator_edge(slug):
    return [{"type": "operator", "slug": slug, "exit": "certs/prod.pem", "start": "make certs"}]


def prefix_and_operator_checks():
    """The two rules added 2026-09-01 from the context-handling-between-nodes run."""

    # --- prefix/repo agreement -------------------------------------------------------------
    # The defect: sequence.md filed the unattended-migration-runner block as `EN.14.H` with repo
    # `agentic-portfolio` ("filed under HQ because the files are HQ's"). EN is engine-rs's prefix.
    errs, warns = run("planning/EN.14.H/", brain_toml=BRAIN_TOML, id="EN.14.H", repo="brain")
    check("a block ID under another repo's prefix is an error", len(prefix_msgs(errs)) == 1,
          f"errors: {errs}")
    check("the prefix error names the prefix's owner and the authored repo",
          prefix_msgs(errs) and "engine-rs" in prefix_msgs(errs)[0] and "brain" in prefix_msgs(errs)[0],
          f"errors: {errs}")

    errs, warns = run("planning/EN.14.H/", brain_toml=BRAIN_TOML, id="EN.14.H", repo="engine-rs")
    check("a block ID whose prefix matches its repo is clean", not prefix_msgs(errs),
          f"errors: {errs}")

    # An unregistered prefix cannot be attributed to anyone -- warn, never guess an owner.
    errs, warns = run("planning/ZZ.1.A/", brain_toml=BRAIN_TOML, id="ZZ.1.A", repo="brain")
    check("an unregistered prefix warns rather than erroring", not prefix_msgs(errs),
          f"errors: {errs}")
    check("an unregistered prefix does warn", len(prefix_msgs(warns)) == 1, f"warnings: {warns}")

    # Positive control for the resolution path: the SAME record must be silent with no brain.toml
    # reachable. Without this, the cases above could pass while production resolved {} and checked
    # nothing -- a standalone repo scaffolded from this template has no brain at all.
    errs, warns = run("planning/EN.14.H/", id="EN.14.H", repo="brain")
    check("no reachable brain.toml disables the prefix check entirely",
          not prefix_msgs(errs) and not prefix_msgs(warns), f"errors: {errs} warnings: {warns}")

    # --- operator slug stutter -------------------------------------------------------------
    # mev renders an operator edge as OP.<slug>, so an `operator-` prefix stutters to
    # OP.operator-foo and raises W_STATE_OP_SLUG_STUTTER. This checker used to REQUIRE that
    # prefix, i.e. it enforced the stutter.
    errs, warns = run("planning/HQ.9.A/", depends_on=operator_edge("mac-mini-visit"))
    check("a bare kebab-case operator slug is accepted", not op_msgs(errs) and not op_msgs(warns),
          f"errors: {errs} warnings: {warns}")

    errs, warns = run("planning/HQ.9.A/", depends_on=operator_edge("operator-mac-mini-visit"))
    check("an `operator-`-prefixed slug is NOT an error", not op_msgs(errs), f"errors: {errs}")
    check("an `operator-`-prefixed slug warns about the stutter", len(op_msgs(warns)) == 1,
          f"warnings: {warns}")
    check("the stutter warning names the fix command",
          op_msgs(warns) and "normalize-op-slugs" in op_msgs(warns)[0], f"warnings: {warns}")

    errs, warns = run("planning/HQ.9.A/", depends_on=operator_edge("Mac_Mini_Visit"))
    check("a non-kebab slug is still an error", len(op_msgs(errs)) == 1, f"errors: {errs}")


def planning_path_checks():
    """The planning/-path rule (BT.ticket.spec-files-under-planning-cannot-compile-in-ci, task 1).

    A `files[]` path under `planning/` names a symlink into the private HQ vault, excluded from
    this repo's git by base-template/.gitignore:20. Code referencing such a path (include_str!,
    a fixture path, a test data file) compiles on every developer machine and on no CI runner.
    These cases are written BEFORE the rule exists (D68) and are expected to fail red until task
    2 implements it; task 2 must not promote a record with no `files[]` at all to an error either
    -- `files` stays in WARN_IF_MISSING on purpose (many blocks predate D65).
    """

    # --- POSITIVE: files.new path under planning/ -------------------------------------------
    errs, warns = run("planning/HQ.9.A/",
                       files={"new": [{"path": "planning/fixtures/x.json", "purpose": "test data"}]})
    positive = [m for m in errs if "planning/fixtures/x.json" in m]
    check("a files.new path under planning/ is an ERROR", len(positive) == 1, f"errors: {errs}")

    # --- NEGATIVE control: the identical shape under tests/ must NOT be flagged -------------
    errs, warns = run("planning/HQ.9.A/",
                       files={"new": [{"path": "tests/fixtures/x.json", "purpose": "test data"}]})
    negative = [m for m in errs if "tests/fixtures/x.json" in m]
    check("a files.new path under tests/ is NOT flagged", len(negative) == 0, f"errors: {errs}")

    # --- MODIFIED-side positive: files.modified under planning/ is flagged too --------------
    errs, warns = run("planning/HQ.9.A/",
                       files={"modified": [{"path": "planning/fixtures/y.json", "change": "edit"}]})
    modified_positive = [m for m in errs if "planning/fixtures/y.json" in m]
    check("a files.modified path under planning/ is an ERROR too", len(modified_positive) == 1,
          f"errors: {errs}")

    # --- EXCLUSION controls: authored planning artifacts are NOT flagged --------------------
    # The rule is narrowed to build-input paths only (2026-09-03, after run wf_8c8b3ca0-6ee
    # measured a first, unnarrowed version at 31 false positives / 0 true positives across
    # this repo's 74 live block records). These are the exclusions and their reasoning.
    for label, path in (
        ("planning/harness.json is NOT flagged (config, not a build input)",
         "planning/harness.json"),
        ("planning/state.json is NOT flagged (config, not a build input)",
         "planning/state.json"),
        ("a *.md under planning/ is NOT flagged (an authored ADR/status/notes doc)",
         "planning/decisions/D71-example.md"),
        ("a tasks.json under planning/ is NOT flagged (a spec's task list, not compiled)",
         "planning/HQ.9.A/tasks.json"),
        ("a path under planning/*/sdlc/ is NOT flagged (engine run state)",
         "planning/HQ.9.A/sdlc/reports/gate-baseline.md"),
    ):
        errs, warns = run("planning/HQ.9.A/",
                           files={"new": [{"path": path, "purpose": "test data"}]})
        flagged = [m for m in errs if path in m]
        check(label, len(flagged) == 0, f"errors: {errs}")

    # --- NON-PROMOTION control, load-bearing: no files[] at all must stay a WARNING ---------
    # check_block_records.py:56 lists `files` in WARN_IF_MISSING deliberately -- the new rule
    # must fire only on a files[] that IS present and names a planning/ path, never on a missing
    # files[]. This must hold both before and after task 2's implementation.
    errs, warns = run("planning/HQ.9.A/")
    check("a record with no files[] at all is never promoted to an error",
          not [m for m in errs if "files" in m],
          f"errors: {errs}")
    check("a record with no files[] at all still warns",
          any("files" in m for m in warns), f"warnings: {warns}")


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

    prefix_and_operator_checks()
    planning_path_checks()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_block_records.py's spec_dir rule holds against the fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
