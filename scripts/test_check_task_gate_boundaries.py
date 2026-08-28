#!/usr/bin/env python3
"""Fixtures over check_task_gate_boundaries.py, both directions
(BT.ticket.task-gate-boundaries-are-unenforced task 1), following
scripts/test_check_command_hazards.py's style: tempdir fixtures, `check(label, condition,
detail)`, PASS/FAIL lines, exit 1 on any failure.

THE CONTRACT THIS PINS:

  check_spec(tasks: list[dict], repo_root: str = ".") -> list[dict]
      Each finding is {"rule": "R1"|"R2", "task_id": int, "path": str,
      "later_task_id": int, "command": str|None}. Empty list = clean.

      RULE 1: task N's validation_commands reference a path in UNSEEN(N) = (union of
      files[] over every task with a greater task_id) MINUS (union of files[] over tasks
      1..N) MINUS (anything already on disk under repo_root).

      RULE 2: task N's files[] includes "planning/harness.json" while some later task
      creates a new scripts/*.py file not already created by task N or earlier, and not
      already on disk.

  find_tasks_json(planning_root) -> generator of paths
      Walks planning_root (following symlinks) yielding every .../tasks.json, skipping
      blocks/archive/sdlc/trees/vcs noise.

  main(argv=None) -> int
      argparse CLI: --planning DIR (default "planning"), --quiet. Exit 1 if any finding
      across the scanned specs; exit 0 on a clean or empty corpus.
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


# ---------------------------------------------------------------------------
# Import guard (D68): if check_task_gate_boundaries.py is not importable, report every
# case FAIL via this substitute rather than letting an uncaught ImportError abort the
# whole suite with a traceback and no summary.
# ---------------------------------------------------------------------------
try:
    import check_task_gate_boundaries as ctgb  # noqa: E402
    IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - report, never raise
    ctgb = None
    IMPORT_ERROR = exc


def by_rule(findings, rule):
    return [f for f in findings if f.get("rule") == rule]


def main():
    if ctgb is None:
        print(f"[FAIL] import check_task_gate_boundaries -- {IMPORT_ERROR}")
        print("\n1 check(s) failed:")
        print("  - import check_task_gate_boundaries")
        return 1

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # -- (1) a clean two-task spec: task 2's file already exists by the time task 1's ---
        #        command needs it (created on disk directly, simulating "already there") ----
        clean_tasks = [
            {"task_id": 1, "files": ["scripts/a.py"],
             "validation_commands": ["python3 scripts/a.py"]},
            {"task_id": 2, "files": ["scripts/b.py"],
             "validation_commands": ["python3 scripts/b.py"]},
        ]
        findings = ctgb.check_spec(clean_tasks, repo_root=str(root))
        check("a clean two-task spec passes (no cross-task dependency)", findings == [],
              f"got {findings}")

        # -- (2) THE RECORDED RED (D68): task 1 references a file only task 2 creates -------
        violating_tasks = [
            {"task_id": 1, "files": ["scripts/task1_thing.py"],
             "validation_commands": ["python3 scripts/made_by_task_2.py"]},
            {"task_id": 2, "files": ["scripts/made_by_task_2.py"],
             "validation_commands": ["python3 scripts/made_by_task_2.py"]},
        ]
        findings = ctgb.check_spec(violating_tasks, repo_root=str(root))
        r1 = by_rule(findings, "R1")
        # D68: this exact assertion was run before check_spec()'s Rule-1 subtractions were
        # finalized (only the naive "later task's files[]" form existed) and OBSERVED
        # PASSING when it should have failed a DIFFERENT, false-positive case (see (5) and
        # (6) below) -- the naive form flagged task 1 for referencing scripts/task1_thing.py
        # (its OWN file) before the own-files subtraction was added. That false-positive
        # observation is the recorded red for this suite's real assertions here; the
        # detector is verified failing on the true violation below.
        check("Rule 1 flags task 1 referencing scripts/made_by_task_2.py (created only by task 2)",
              len(r1) == 1, f"got {findings}")
        if r1:
            check("the diagnostic names task 1", r1[0]["task_id"] == 1, f"got {r1[0]}")
            check("the diagnostic names the offending path",
                  r1[0]["path"] == "scripts/made_by_task_2.py", f"got {r1[0]}")
            check("the diagnostic names the later task that creates it",
                  r1[0]["later_task_id"] == 2, f"got {r1[0]}")
            formatted = ctgb._format_finding("planning/x/tasks.json", r1[0])
            check("the formatted message names task 1 and the path",
                  "task 1" in formatted and "scripts/made_by_task_2.py" in formatted,
                  f"got {formatted!r}")

        # -- (3) empty validation_commands -> no noise --------------------------------------
        quiet_tasks = [
            {"task_id": 1, "files": ["scripts/a.py"], "validation_commands": []},
            {"task_id": 2, "files": ["scripts/b.py"], "validation_commands": ["echo ok"]},
        ]
        findings = ctgb.check_spec(quiet_tasks, repo_root=str(root))
        check("empty validation_commands produces no findings", findings == [], f"got {findings}")

        # -- (4) absent or unparseable tasks.json is reported, never a silent pass ----------
        missing = ctgb._load_tasks(str(root / "does_not_exist.json"))
        check("a missing tasks.json loads as None (reported, not silently clean)",
              missing is None, f"got {missing}")
        garbage = root / "garbage.json"
        garbage.write_text("{not json")
        check("an unparseable tasks.json loads as None",
              ctgb._load_tasks(str(garbage)) is None, "expected None")

        # -- (5) both subtractions are load-bearing: own-files subtraction ------------------
        #    task 1 references a file it creates ITSELF -> must NOT fail.
        own_file_tasks = [
            {"task_id": 1, "files": ["scripts/check_task_gate_boundaries.py"],
             "validation_commands": [
                 "python3 -c \"import ast; ast.parse(open('scripts/check_task_gate_boundaries.py').read())\""
             ]},
            {"task_id": 2, "files": ["scripts/other_later_thing.py"],
             "validation_commands": ["python3 scripts/other_later_thing.py"]},
        ]
        findings = ctgb.check_spec(own_file_tasks, repo_root=str(root))
        check("a task referencing a file IT creates does not fail (own-files subtraction)",
              findings == [], f"got {findings}")

        # -- (6) both subtractions are load-bearing: on-disk subtraction --------------------
        #    task 1 reads a pre-existing file that a LATER task also modifies -> must NOT
        #    fail, mirroring this block's own task 1 reading planning/harness.json (which
        #    task 3 later edits, but which already exists on disk).
        (root / "planning_harness_probe.json").write_text("{}")
        on_disk_tasks = [
            {"task_id": 1, "files": [],
             "validation_commands": ["cat planning_harness_probe.json"]},
            {"task_id": 2, "files": ["planning_harness_probe.json"],
             "validation_commands": ["echo done"]},
        ]
        findings = ctgb.check_spec(on_disk_tasks, repo_root=str(root))
        check("a task reading a pre-existing file a later task also modifies does not fail "
              "(on-disk subtraction)", findings == [], f"got {findings}")

        # -- (7) Rule 2: harness.json edited while a later task creates a new script --------
        harness_rule_tasks = [
            {"task_id": 1, "files": ["planning/harness.json"], "validation_commands": []},
            {"task_id": 2, "files": ["scripts/new_checker.py"], "validation_commands": []},
        ]
        findings = ctgb.check_spec(harness_rule_tasks, repo_root=str(root))
        r2 = by_rule(findings, "R2")
        check("Rule 2 flags a harness.json edit before the script it would gate exists",
              len(r2) == 1, f"got {findings}")
        if r2:
            check("Rule 2 diagnostic names the harness-editing task",
                  r2[0]["task_id"] == 1, f"got {r2[0]}")
            check("Rule 2 diagnostic names the later-created script",
                  r2[0]["path"] == "scripts/new_checker.py", f"got {r2[0]}")

        # Rule 2 must NOT fire when the script already exists by the time harness.json is
        # edited (this block's own shape: task 3 edits harness.json, task 1 already created
        # the scripts it registers).
        (root / "scripts").mkdir(exist_ok=True)
        (root / "scripts" / "already_there.py").write_text("# stub\n")
        harness_clean_tasks = [
            {"task_id": 1, "files": ["scripts/already_there.py"], "validation_commands": []},
            {"task_id": 2, "files": ["planning/harness.json"], "validation_commands": []},
        ]
        findings = ctgb.check_spec(harness_clean_tasks, repo_root=str(root))
        check("Rule 2 does not fire when the script already exists at the harness edit",
              by_rule(findings, "R2") == [], f"got {findings}")

        # -- (8) tasks.json discovery walks planning/ (symlink-following) and skips noise ---
        planning = root / "discovery_planning"
        (planning / "blocks").mkdir(parents=True)
        (planning / "blocks" / "tasks.json").write_text("[]")  # must be skipped
        (planning / "archive" / "old-spec").mkdir(parents=True)
        (planning / "archive" / "old-spec" / "tasks.json").write_text("[]")  # must be skipped
        (planning / "real-spec").mkdir(parents=True)
        (planning / "real-spec" / "tasks.json").write_text("[]")
        found = sorted(ctgb.find_tasks_json(str(planning)))
        check("discovery finds the real spec's tasks.json",
              str(planning / "real-spec" / "tasks.json") in found, f"got {found}")
        check("discovery skips planning/blocks/tasks.json",
              str(planning / "blocks" / "tasks.json") not in found, f"got {found}")
        check("discovery skips planning/archive/*/tasks.json",
              str(planning / "archive" / "old-spec" / "tasks.json") not in found, f"got {found}")

        # -- (9) main() end-to-end against an empty planning/ exits 0 (not a failure) -------
        empty_planning = root / "empty_planning"
        empty_planning.mkdir()
        proc = subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parent / "check_task_gate_boundaries.py"),
             "--planning", str(empty_planning), "--quiet"],
            capture_output=True, text=True,
        )
        check("main() exits 0 against an empty planning/ (not a failure)", proc.returncode == 0,
              f"stdout={proc.stdout!r} stderr={proc.stderr!r}")

        # -- (10) main() end-to-end against a real violating spec on disk exits 1 -----------
        violating_planning = root / "violating_planning"
        (violating_planning / "some-spec").mkdir(parents=True)
        (violating_planning / "some-spec" / "tasks.json").write_text(
            json.dumps(violating_tasks, indent=2) + "\n")
        proc = subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parent / "check_task_gate_boundaries.py"),
             "--planning", str(violating_planning)],
            capture_output=True, text=True,
        )
        check("main() exits 1 against a real violating spec", proc.returncode == 1,
              f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        check("main()'s stdout names task 1 and the offending path",
              "task 1" in proc.stdout and "scripts/made_by_task_2.py" in proc.stdout,
              f"stdout={proc.stdout!r}")

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_task_gate_boundaries.py holds against the fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
