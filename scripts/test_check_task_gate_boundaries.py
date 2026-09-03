#!/usr/bin/env python3
"""Fixtures over check_task_gate_boundaries.py, both directions
(BT.ticket.task-gate-boundaries-are-unenforced task 1), following
scripts/test_check_command_hazards.py's style: tempdir fixtures, `check(label, condition,
detail)`, PASS/FAIL lines, exit 1 on any failure.

THE CONTRACT THIS PINS:

  check_spec(tasks: list[dict], repo_root: str = ".") -> list[dict]
      Each finding is {"rule": "R1"|"R2"|"R3", "task_id": int, "path": str,
      "later_task_id": int, "command": str|None}. Empty list = clean.

      RULE 1: task N's validation_commands reference a path in UNSEEN(N) = (union of
      files[] over every task with a greater task_id) MINUS (union of files[] over tasks
      1..N) MINUS (anything already on disk under repo_root).

      RULE 2: task N's files[] includes "planning/harness.json" while some later task
      creates a new scripts/*.py file not already created by task N or earlier, not
      already on disk, and never previously git-tracked (a deletion of a pre-existing
      script is not a first-time creation, even once it is gone from the working tree).

      RULE 3 (NOT YET IMPLEMENTED as of this file's task 1 -- expected RED, D68): task N
      modifies a file that some registered gates:true check (read from repo_root's
      planning/harness.json) INVOKES as its detector script, while a later task M (task_id
      > N) modifies a file that the SAME check reads as input (a non-script path also
      named in that check's `command`). Neither RULE 1 nor RULE 2 can see this shape --
      the artifact's path already exists and no gate is being registered; only the
      artifact's CONTENT is stale at the boundary. Fixture below mirrors bella's real
      instance: a check whose command is
      "python3 scripts/check_screenshot_floor.py assets/screenshot.png" -- task 3
      tightens the floor in the script, task 4 regenerates the screenshot.

      OBSERVED RED (D68), 2026-09-03, `python3 scripts/test_check_task_gate_boundaries.py`,
      exit code 1 -- captured verbatim (RULE 1/RULE 2 cases still PASS in this same run;
      the failure is scoped to the new RULE 3 positive case, which cannot pass until
      check_task_gate_boundaries.py implements RULE 3 in task 2):

          [FAIL] RULE 3 flags a detector-tightening task ahead of the task that
          regenerates the artifact it reads (bella's case) -- got []

          1 check(s) failed:
            - RULE 3 flags a detector-tightening task ahead of the task that regenerates
              the artifact it reads (bella's case)

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

        # -- (7b) Rule 2 must NOT fire when the "later" file is a DELETION of a script that
        #    already existed and was git-tracked -- not a first-time creation. Regression
        #    fixture for the false positive found running the checker against this repo's
        #    real corpus (BT.5.B task 2 registering harness.json while task 5, unrelated,
        #    both removed scripts/test_lane_directive_emission.py and its own harness.json
        #    entry): the path is absent from disk by the time the checker runs, but it has
        #    git history, so it is a deletion, not a not-yet-created script.
        git_root = root / "git_repo"
        git_root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=git_root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=git_root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=git_root, check=True)
        deleted_script = git_root / "scripts"
        deleted_script.mkdir()
        (deleted_script / "old_gate.py").write_text("# stub\n")
        subprocess.run(["git", "add", "scripts/old_gate.py"], cwd=git_root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "add old_gate.py"], cwd=git_root, check=True)
        (deleted_script / "old_gate.py").unlink()
        subprocess.run(["git", "add", "-A"], cwd=git_root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "remove old_gate.py"], cwd=git_root, check=True)
        deletion_tasks = [
            {"task_id": 1, "files": ["planning/harness.json"], "validation_commands": []},
            {"task_id": 2, "files": ["scripts/old_gate.py", "planning/harness.json"],
             "validation_commands": []},
        ]
        findings = ctgb.check_spec(deletion_tasks, repo_root=str(git_root))
        check("Rule 2 does not fire when the later path is a git-tracked deletion, not a "
              "first-time creation", by_rule(findings, "R2") == [], f"got {findings}")

        # -- (7c) RULE 3 (NOT YET IMPLEMENTED -- expected RED, D68): a task that tightens a
        #    gating threshold/floor/detector in a script a gates:true check INVOKES, while a
        #    LATER task regenerates the artifact that same check READS AS INPUT. Neither RULE
        #    1 (path-existence) nor RULE 2 (harness.json registration) can see this shape --
        #    the artifact's path already exists here and no gate is being newly registered;
        #    only the artifact's CONTENT is stale at the boundary. This is bella's real
        #    instance: its ticket bailed at task 3 twice identically because task 3 sharpened
        #    a gates:true MIN_PNG_BYTES floor before task 4 re-captured the screenshot the
        #    same check reads.
        #
        #    Fixture shape: planning/harness.json registers one gates:true check whose
        #    `command` names BOTH a detector script (scripts/*.py) and a non-script artifact
        #    path (e.g. assets/screenshot.png) as arguments -- mirroring a real check command
        #    like `python3 scripts/check_screenshot_floor.py assets/screenshot.png`.
        rule3_root = root / "rule3_fixtures"
        (rule3_root / "planning").mkdir(parents=True)
        (rule3_root / "planning" / "harness.json").write_text(json.dumps({
            "validation": {
                "checks": [
                    {
                        "name": "screenshot-floor",
                        "gates": True,
                        "command": ("python3 scripts/check_screenshot_floor.py "
                                    "assets/screenshot.png"),
                    }
                ]
            }
        }, indent=2))
        (rule3_root / "scripts").mkdir()
        (rule3_root / "scripts" / "check_screenshot_floor.py").write_text(
            "MIN_PNG_BYTES = 100\n")
        (rule3_root / "assets").mkdir()
        (rule3_root / "assets" / "screenshot.png").write_bytes(b"stub-png-bytes")

        # POSITIVE (bella's real instance): task 3 tightens the floor in the detector
        # script; task 4 regenerates the artifact the same check reads. Must be FLAGGED.
        rule3_positive_tasks = [
            {"task_id": 3, "files": ["scripts/check_screenshot_floor.py"],
             "validation_commands": []},
            {"task_id": 4, "files": ["assets/screenshot.png"], "validation_commands": []},
        ]
        findings = ctgb.check_spec(rule3_positive_tasks, repo_root=str(rule3_root))
        r3 = by_rule(findings, "R3")
        check("RULE 3 flags a detector-tightening task ahead of the task that regenerates "
              "the artifact it reads (bella's case)", len(r3) == 1, f"got {findings}")
        if r3:
            check("RULE 3 diagnostic names the detector-tightening task",
                  r3[0]["task_id"] == 3, f"got {r3[0]}")
            check("RULE 3 diagnostic names the artifact path",
                  r3[0]["path"] == "assets/screenshot.png", f"got {r3[0]}")
            check("RULE 3 diagnostic names the later task that regenerates the artifact",
                  r3[0]["later_task_id"] == 4, f"got {r3[0]}")

        # MERGED control: the same two edits done in ONE task. Must NOT be flagged -- this
        # is what RULE 3 is telling the author to do, so it has to be reachable.
        rule3_merged_tasks = [
            {"task_id": 1,
             "files": ["scripts/check_screenshot_floor.py", "assets/screenshot.png"],
             "validation_commands": []},
        ]
        findings = ctgb.check_spec(rule3_merged_tasks, repo_root=str(rule3_root))
        check("RULE 3 does not fire when the detector and the artifact are fixed in the "
              "same task (merged control)", by_rule(findings, "R3") == [], f"got {findings}")

        # NEGATIVE control (load-bearing, not optional): a threshold changes with NO later
        # artifact-regenerating task. Must NOT be flagged -- RULE 3 is the most
        # false-positive-prone rule in the file and a checker that guesses is noise the
        # reader learns to ignore.
        rule3_negative_tasks = [
            {"task_id": 1, "files": ["scripts/check_screenshot_floor.py"],
             "validation_commands": []},
            {"task_id": 2, "files": ["scripts/unrelated_other_thing.py"],
             "validation_commands": []},
        ]
        findings = ctgb.check_spec(rule3_negative_tasks, repo_root=str(rule3_root))
        check("RULE 3 does not fire on a threshold change with no later "
              "artifact-regenerating task (negative control)",
              by_rule(findings, "R3") == [], f"got {findings}")

        # NON-INTERFERENCE: an existing RULE 2 fixture (harness.json edited + a later task
        # creates a brand-new script) still produces exactly its RULE 2 finding, not a
        # duplicate RULE 3 finding on the same task -- even against a repo_root whose
        # planning/harness.json carries a real gates:true check (rule3_root above).
        rule3_noninterference_tasks = [
            {"task_id": 1, "files": ["planning/harness.json"], "validation_commands": []},
            {"task_id": 2, "files": ["scripts/new_checker.py"], "validation_commands": []},
        ]
        findings = ctgb.check_spec(rule3_noninterference_tasks, repo_root=str(rule3_root))
        r2_ni = by_rule(findings, "R2")
        r3_ni = by_rule(findings, "R3")
        check("RULE 2's own fixture still fires exactly once and produces no duplicate "
              "RULE 3 finding on the same task (non-interference)",
              len(r2_ni) == 1 and r3_ni == [], f"got {findings}")

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
