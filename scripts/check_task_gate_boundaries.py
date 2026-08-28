#!/usr/bin/env python3
"""Fail a task whose gate cannot pass at the boundary it is asked to pass at
(BT.ticket.task-gate-boundaries-are-unenforced).

Both engines call `runTests(...)` INSIDE the per-task loop
(`.claude/workflows/sdlc-task.js:2062`), so every task boundary is a full gate, not just the
end of the spec: **every task must leave the gating suite passing.** That rule is stated in
prose in four commands (`/generate-tasks`, `/ticket`, `/chore`, `/breakdown`) but was never
enforced -- a hand-authored `tasks.json` skips all four at once, and did, four times in one
session (`BT.ticket.worktree-smoke-fixture` bailed at task 1 because its gate ran checks that
could not pass until later work landed).

This checker decides the one corollary that is mechanically decidable from `tasks.json`
alone -- it does NOT try to predict whether the whole harness suite passes at each boundary
(undecidable from the spec; a checker that guesses is noise the reader learns to ignore):

RULE 1 -- a task's own `validation_commands` must not reference a path that does not exist
yet at that boundary. For task N, build:

    UNSEEN(N) = (union of files[] over every task with a GREATER task_id)
                MINUS (union of files[] over tasks 1..N, i.e. this task and every earlier one)
                MINUS (anything that already exists on disk)

and flag any `validation_commands` string in task N that contains a path in UNSEEN(N).

BOTH subtractions are load-bearing -- found by running this rule against THIS block's own
`tasks.json` before committing it. The naive form ("references a path in a later task's
files[]") produces two false positives right here: task 1 legitimately names
`scripts/check_task_gate_boundaries.py`, which task 1 itself creates (own-files subtraction);
and task 1 legitimately reads `planning/harness.json`, which task 3 later modifies but which
already exists on disk (on-disk subtraction). The rule is "depends on a path that does not
exist yet", never "mentions a later task's file".

RULE 2 -- a task that edits `planning/harness.json` (i.e. registers a gate) while a LATER
task creates the script that gate would need. The actual command text being added to
`harness.json` is not visible from `tasks.json` alone, so this is deliberately the coarse,
conservative signal named in the block record: flag task N when `planning/harness.json` is in
its `files[]` and some task M with task_id > N creates a NEW `scripts/*.py` file (not already
on disk, not created by task N or earlier). A false positive here trains readers to ignore the
gate, which is worse than the miss -- so this rule fires only on that narrow shape, never on
a task merely reading or generically mentioning harness.json.

A spec with no tasks.json, an empty array, or a task with no validation_commands is not a
failure -- say nothing about it. Every subprocess call (none here) would check its own return
code, and no check here is built on a shell pipeline.

Usage:
    check_task_gate_boundaries.py [--planning DIR] [--quiet]

    --planning DIR   scan one repo's planning/ (default: planning)
    --quiet          print only findings and the summary

Exit code 1 if any task-boundary violation is found across the scanned planning/*/tasks.json.
A repo with none is silent and exits 0.
"""

from __future__ import annotations

import argparse
import json
import os

SKIP_DIRS = {"node_modules", ".git", "archive", "target", ".fleet-locks", "sdlc", "trees", "blocks"}

HARNESS_PATH = "planning/harness.json"


def _load_tasks(path):
    """Return the tasks list, or None if the file is absent/unparseable/not-a-list."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001 - a malformed file is another check's job to report
        return None
    if not isinstance(data, list):
        return None
    return data


def _files_of(task):
    return {f for f in (task.get("files") or []) if isinstance(f, str)}


def _by_id(tasks):
    """Return {task_id: task} for every task with an integer task_id, skipping the rest."""
    out = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        tid = task.get("task_id")
        if isinstance(tid, int) and not isinstance(tid, bool):
            out[tid] = task
    return out


def check_spec(tasks, repo_root="."):
    """Return a list of finding dicts for one spec's already-loaded tasks list.

    Each finding: {"rule": "R1"|"R2", "task_id": int, "path": str, "later_task_id": int,
    "command": str|None}.
    """
    findings = []
    by_id = _by_id(tasks)
    if not by_id:
        return findings
    ids_sorted = sorted(by_id)

    for tid in ids_sorted:
        task = by_id[tid]

        earlier_and_own = set()
        for tid2 in ids_sorted:
            if tid2 <= tid:
                earlier_and_own |= _files_of(by_id[tid2])

        later_files = {}  # path -> earliest later task_id that creates it
        for tid2 in ids_sorted:
            if tid2 <= tid:
                continue
            for p in _files_of(by_id[tid2]):
                later_files.setdefault(p, tid2)

        unseen = {}
        for p, creator_tid in later_files.items():
            if p in earlier_and_own:
                continue
            if os.path.exists(os.path.join(repo_root, p)):
                continue
            unseen[p] = creator_tid

        # -- RULE 1: validation_commands referencing an UNSEEN path -------------------------
        for cmd in task.get("validation_commands") or []:
            if not isinstance(cmd, str):
                continue
            for p, creator_tid in unseen.items():
                if p in cmd:
                    findings.append({
                        "rule": "R1", "task_id": tid, "path": p,
                        "later_task_id": creator_tid, "command": cmd,
                    })

        # -- RULE 2: harness.json edited here, a new script arrives only later --------------
        if HARNESS_PATH in _files_of(task):
            seen_scripts = set()
            for p, creator_tid in later_files.items():
                if p in earlier_and_own or p in seen_scripts:
                    continue
                if not (p.startswith("scripts/") and p.endswith(".py")):
                    continue
                if os.path.exists(os.path.join(repo_root, p)):
                    continue
                seen_scripts.add(p)
                findings.append({
                    "rule": "R2", "task_id": tid, "path": p,
                    "later_task_id": creator_tid, "command": None,
                })

    return findings


def _format_finding(spec_file, finding):
    task_id = finding["task_id"]
    path = finding["path"]
    later = finding["later_task_id"]
    if finding["rule"] == "R1":
        return (f"FAIL {spec_file} task {task_id}: validation_commands references "
                f"{path!r}, which does not exist at this boundary -- created only by "
                f"task {later}. command: {finding['command']!r}")
    return (f"FAIL {spec_file} task {task_id}: registers planning/harness.json (a gate) "
            f"while {path!r} is created only by later task {later} -- the gate cannot "
            f"pass at this boundary")


def find_tasks_json(planning_root):
    """Yield every planning/*/tasks.json path under `planning_root`, following symlinks
    (planning/ is a vaulted symlink in this fleet), skipping blocks/archive/vcs noise."""
    for dirpath, dirnames, filenames in os.walk(planning_root, followlinks=True):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if "tasks.json" in filenames:
            yield os.path.join(dirpath, "tasks.json")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--planning", default="planning")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.planning):
        print(f"no {args.planning}/ found (not a failure)")
        return 0

    spec_paths = sorted(find_tasks_json(args.planning))
    if not spec_paths:
        print("no planning/*/tasks.json found (not a failure)")
        return 0

    total_findings = 0
    for spec_path in spec_paths:
        tasks = _load_tasks(spec_path)
        if tasks is None:
            continue
        findings = check_spec(tasks, repo_root=".")
        if findings:
            for finding in findings:
                total_findings += 1
                print(_format_finding(spec_path, finding))
        elif not args.quiet:
            print(f"ok   {spec_path}")

    print(f"\n{len(spec_paths)} spec(s) checked, {total_findings} finding(s)")
    return 1 if total_findings else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
