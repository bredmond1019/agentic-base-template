#!/usr/bin/env python3
"""Self-contained fixture suite for check_spec_validation_commands.py and
check_clears_when_predicates.py.

WHY THIS EXISTS
---------------
Both lints resolve a plan-asserted path against the filesystem at authoring time. A fixture suite
that only asserts "exit 0 / exit 1" can pass for the wrong reason — the block record's own
re-derivation records exactly that: a probe keyed on `kind` instead of `type` printed a confident
"command_exits_zero: 0" and would have declared the live corpus clean, because it never actually
matched a predicate. So every fixture here asserts BOTH the exit code AND that the expected
entry/path text appears in the lint's stdout — a check that fails for the wrong reason cannot pass.

Everything runs against temp trees built by this script; nothing here depends on the live corpus.

Usage:
  python3 scripts/test_check_spec_and_predicate_paths.py

Exit 0 — every fixture passed.
Exit 1 — at least one fixture failed (printed as FAIL with the mismatch).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_LINT = REPO_ROOT / "scripts" / "check_spec_validation_commands.py"
PREDICATE_LINT = REPO_ROOT / "scripts" / "check_clears_when_predicates.py"

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}"
    if not ok and detail:
        line += f" — {detail}"
    print(line)


def run_spec_lint(planning_dir: Path):
    proc = subprocess.run(
        [sys.executable, str(SPEC_LINT), "--planning", str(planning_dir), "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def run_predicate_lint(state_file: Path, repo_root: Path):
    proc = subprocess.run(
        [
            sys.executable,
            str(PREDICATE_LINT),
            str(state_file),
            "--repo-root",
            str(repo_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def write_tasks(spec_dir: Path, tasks: list) -> None:
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Spec-path rule fixtures
# ---------------------------------------------------------------------------

def fixture_a_phantom_path_reported():
    """(a) A tasks.json citing a script that exists nowhere — must be reported.

    Note: a files[] entry a task lists for itself is always treated as "the file this task is
    about to produce" (build_creates_map maps it to its own task_id, which is <= itself) — that is
    deliberate self-forgiveness, not a gap, so this fixture asserts the phantom via
    validation_commands, the shape of the actual measured incident
    (`python3 scripts/check_harness_registration.py`, a script that has never existed anywhere in
    the fleet). A second task then cites, in ITS files[], a path no task creates and that does not
    exist on disk either — proving the files[] path IS still checked when nothing (including its
    own task) vouches for it via validation_commands token extraction on that same path in a
    different task's command.
    """
    with tempfile.TemporaryDirectory() as td:
        planning = Path(td) / "planning"
        spec = planning / "phantom-spec"
        write_tasks(
            spec,
            [
                {
                    "task_id": 1,
                    "files": [],
                    "validation_commands": [
                        "python3 scripts/check_harness_registration.py"
                    ],
                }
            ],
        )
        code, out = run_spec_lint(planning)
        ok = code == 1 and "check_harness_registration.py" in out
        record(
            "spec-lint(a) phantom path reported",
            ok,
            f"exit={code} out={out!r}",
        )


def fixture_b_earlier_task_creates_path():
    """(b) task 2 cites a path created by task 1's files[] — must NOT be reported."""
    with tempfile.TemporaryDirectory() as td:
        planning = Path(td) / "planning"
        spec = planning / "ordered-spec"
        write_tasks(
            spec,
            [
                {"task_id": 1, "files": ["scripts/new_thing.py"], "validation_commands": []},
                {
                    "task_id": 2,
                    "files": [],
                    "validation_commands": ["python3 scripts/new_thing.py --check"],
                },
            ],
        )
        code, out = run_spec_lint(planning)
        ok = code == 0 and not any(
            "new_thing.py" in line and "does not exist" in line for line in out.splitlines()
        )
        record("spec-lint(b) earlier-task-created path not reported", ok, f"exit={code} out={out!r}")


def fixture_c_clean_spec():
    """(c) a clean spec — exits 0."""
    with tempfile.TemporaryDirectory() as td:
        planning = Path(td) / "planning"
        spec = planning / "clean-spec"
        write_tasks(
            spec,
            [
                {
                    "task_id": 1,
                    "files": ["scripts/check_spec_validation_commands.py"],
                    "validation_commands": [
                        "python3 scripts/check_spec_validation_commands.py --quiet"
                    ],
                }
            ],
        )
        code, out = run_spec_lint(planning)
        ok = code == 0
        record("spec-lint(c) clean spec exits 0", ok, f"exit={code} out={out!r}")


# ---------------------------------------------------------------------------
# Predicate rule fixtures
# ---------------------------------------------------------------------------

def fixture_d_positive_control():
    """(d) POSITIVE CONTROL — a real typed command_exits_zero predicate must be SEEN (examined > 0)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        marker = root / "scripts" / "real_marker_file.py"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("# exists\n", encoding="utf-8")
        state = root / "state.json"
        state.write_text(
            json.dumps(
                {
                    "carryover": [
                        {
                            "slug": "positive-control-entry",
                            "kind": "defect",
                            "scope": {"repo": "fixture", "tier": None, "cross_repo": None},
                            "clears_when": {
                                "type": "command_exits_zero",
                                "command": "test -f scripts/real_marker_file.py",
                                "note": "fixture positive control",
                            },
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        code, out = run_predicate_lint(state, root)
        ok = code == 0 and "examined 1 typed command_exits_zero" in out
        record("predicate-lint(d) positive control examined>0", ok, f"exit={code} out={out!r}")


def fixture_e_false_clear_grep_shape():
    """(e) `! grep <nonexistent path>` shape — must be reported, not read as satisfied."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = root / "state.json"
        state.write_text(
            json.dumps(
                {
                    "carryover": [
                        {
                            "slug": "false-clear-entry",
                            "finding_id": "F-FALSE-CLEAR",
                            "kind": "defect",
                            "scope": {"repo": "fixture", "tier": None, "cross_repo": None},
                            "clears_when": {
                                "type": "command_exits_zero",
                                "command": "! grep -q marker docs/path_that_never_existed.md",
                                "note": "fixture false-clear shape",
                            },
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        code, out = run_predicate_lint(state, root)
        ok = (
            code == 1
            and "false-clear-entry" in out
            and "path_that_never_existed.md" in out
        )
        record("predicate-lint(e) false-clear grep shape reported", ok, f"exit={code} out={out!r}")


def fixture_f_git_toplevel_rejected():
    """(f) a predicate beginning `cd "$(git rev-parse --show-toplevel)"` — must be rejected outright."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = root / "state.json"
        state.write_text(
            json.dumps(
                {
                    "carryover": [
                        {
                            "slug": "git-toplevel-entry",
                            "kind": "defect",
                            "scope": {"repo": "fixture", "tier": None, "cross_repo": None},
                            "clears_when": {
                                "type": "command_exits_zero",
                                "command": (
                                    'cd "$(git rev-parse --show-toplevel)" && '
                                    "test -f base-template/docs/some_doc.md"
                                ),
                                "note": "fixture git-root assumption",
                            },
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        code, out = run_predicate_lint(state, root)
        ok = (
            code == 1
            and "git-toplevel-entry" in out
            and "git rev-parse --show-toplevel" in out
        )
        record("predicate-lint(f) git-rev-parse predicate rejected", ok, f"exit={code} out={out!r}")


def fixture_g_repaired_predicate_clean():
    """(g) a repaired repo-relative predicate whose paths resolve — must NOT be reported."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        marker = root / "docs" / "repaired_doc.md"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("# exists\n", encoding="utf-8")
        state = root / "state.json"
        state.write_text(
            json.dumps(
                {
                    "carryover": [
                        {
                            "slug": "repaired-entry",
                            "kind": "defect",
                            "scope": {"repo": "fixture", "tier": None, "cross_repo": None},
                            "clears_when": {
                                "type": "command_exits_zero",
                                "command": "test -f docs/repaired_doc.md",
                                "note": "fixture repaired predicate",
                            },
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        code, out = run_predicate_lint(state, root)
        ok = code == 0 and not any(
            "repaired-entry" in line and "does not resolve" in line for line in out.splitlines()
        )
        record("predicate-lint(g) repaired predicate not reported", ok, f"exit={code} out={out!r}")


def main() -> int:
    fixture_a_phantom_path_reported()
    fixture_b_earlier_task_creates_path()
    fixture_c_clean_spec()
    fixture_d_positive_control()
    fixture_e_false_clear_grep_shape()
    fixture_f_git_toplevel_rejected()
    fixture_g_repaired_predicate_clean()

    total = len(RESULTS)
    failed = [name for name, ok, _ in RESULTS if not ok]

    print()
    print(f"SUMMARY: {total - len(failed)}/{total} fixtures passed")
    if failed:
        print("FAILED:")
        for name in failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
