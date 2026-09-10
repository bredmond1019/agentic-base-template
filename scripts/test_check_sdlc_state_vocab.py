#!/usr/bin/env python3
"""Fixture suite for check_sdlc_state_vocab.py (BT.ticket.sdlc-state-status-vocabulary, task 2).

Self-contained, no pytest dependency, in the fixture style of scripts/test_check_frontmatter_presence.py
and scripts/test_check_prompt_templates.py: exercises the module's functions directly via
importlib, plus a couple of real subprocess invocations for the CLI/exit-code contract.

Two controls, per the task's own framing:

  - POSITIVE control: run the checker against this repo's own real planning/ tree (the default
    root) and assert it exits 0. This must currently pass -- if it ever regresses, that is new
    information about real data, not a reason to weaken this assertion.
  - NEGATIVE control: write a temporary fixture sdlc-task-state.json with status: "completed"
    (the exact legacy value named in the block record's own audit finding) under a throwaway
    root directory, and assert the checker exits 1, naming both the fixture's path and the
    offending value in its output.

Run: python3 scripts/test_check_sdlc_state_vocab.py
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_sdlc_state_vocab.py"
VOCAB_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-state-vocab.json"

_spec = importlib.util.spec_from_file_location("check_sdlc_state_vocab", MODULE_PATH)
csv = importlib.util.module_from_spec(_spec)
sys.modules["check_sdlc_state_vocab"] = csv
_spec.loader.exec_module(csv)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def main() -> int:
    # --- module-level sanity -----------------------------------------------------------------
    check("vocab file exists", VOCAB_PATH.is_file(), f"missing: {VOCAB_PATH}")
    vocab = csv.load_vocab(VOCAB_PATH)
    check(
        "vocab has exactly the 10 canonical values",
        vocab
        == {
            "running",
            "passed",
            "failed",
            "blocked",
            "done",
            "criteria_refused",
            "reconcile_failed",
            "review",
            "docs",
            "wrapup",
        },
        f"got: {sorted(vocab)}",
    )

    # --- POSITIVE control: this repo's own real planning/ tree, via the CLI -------------------
    real_proc = subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    check(
        "positive control: check_sdlc_state_vocab.py against this repo's real planning/ tree exits 0",
        real_proc.returncode == 0,
        f"exit={real_proc.returncode} stdout={real_proc.stdout!r} stderr={real_proc.stderr!r}",
    )

    # --- NEGATIVE control: synthetic bad-status fixture ----------------------------------------
    tmp_root = Path(tempfile.mkdtemp(prefix="sdlc_state_vocab_test_"))
    try:
        fixture_dir = tmp_root / "planning" / "BT.ticket.synthetic-bad-status" / "sdlc"
        fixture_dir.mkdir(parents=True)
        fixture_path = fixture_dir / "sdlc-task-state.json"
        fixture_path.write_text(
            json.dumps(
                {
                    "spec_slug": "BT.ticket.synthetic-bad-status",
                    "mode": "in-place",
                    "branch": "main",
                    "status": "completed",
                    "tasks": {"1": {"status": "passed"}},
                },
                indent=2,
            )
        )

        # Direct function-level check.
        failures = csv.check_file(fixture_path, vocab)
        check(
            "negative control (direct call): check_file() reports a failure on the fixture",
            len(failures) == 1,
            f"failures={failures}",
        )
        if failures:
            check(
                "negative control (direct call): failure names the fixture path",
                str(fixture_path) in failures[0],
                failures[0],
            )
            check(
                "negative control (direct call): failure names the offending value 'completed'",
                "'completed'" in failures[0],
                failures[0],
            )

        # Full CLI/exit-code contract, pointed at the throwaway root via --root.
        bad_proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--root", str(tmp_root / "planning")],
            capture_output=True,
            text=True,
        )
        check(
            "negative control (CLI): exits 1 on the synthetic bad-status fixture",
            bad_proc.returncode == 1,
            f"exit={bad_proc.returncode} stdout={bad_proc.stdout!r}",
        )
        check(
            "negative control (CLI): output names the fixture path",
            str(fixture_path) in bad_proc.stdout,
            bad_proc.stdout,
        )
        check(
            "negative control (CLI): output names the offending value 'completed'",
            "'completed'" in bad_proc.stdout,
            bad_proc.stdout,
        )

        # A per-task status outside the vocab must also be caught, independent of top-level status.
        task_fixture_dir = tmp_root / "planning" / "BT.ticket.synthetic-bad-task-status" / "sdlc"
        task_fixture_dir.mkdir(parents=True)
        task_fixture_path = task_fixture_dir / "sdlc-flow-state.json"
        task_fixture_path.write_text(
            json.dumps({"status": "done", "tasks": {"1": {"status": "skipped"}}}, indent=2)
        )
        task_failures = csv.check_file(task_fixture_path, vocab)
        check(
            "a per-task status outside the vocab is caught even when top-level status is valid",
            len(task_failures) == 1 and "tasks['1'].status" in task_failures[0] and "'skipped'" in task_failures[0],
            f"failures={task_failures}",
        )

        # A file with no "status" key at all (e.g. a retired engine's shape) is not this check's
        # concern -- absence is a different question from an out-of-vocabulary value.
        no_status_dir = tmp_root / "planning" / "BT.ticket.no-status-field" / "sdlc"
        no_status_dir.mkdir(parents=True)
        no_status_path = no_status_dir / "sdlc-run-state.json"
        no_status_path.write_text(json.dumps({"current_phase": "wrap-up"}, indent=2))
        no_status_failures = csv.check_file(no_status_path, vocab)
        check(
            "a state file with no top-level status key at all produces no failure",
            no_status_failures == [],
            f"failures={no_status_failures}",
        )

        # A malformed (non-JSON) file is reported, not silently skipped.
        malformed_dir = tmp_root / "planning" / "BT.ticket.malformed" / "sdlc"
        malformed_dir.mkdir(parents=True)
        malformed_path = malformed_dir / "sdlc-task-state.json"
        malformed_path.write_text("{not valid json")
        malformed_failures = csv.check_file(malformed_path, vocab)
        check(
            "a malformed (non-JSON) state file is reported as its own failure",
            len(malformed_failures) == 1 and "not valid JSON" in malformed_failures[0],
            f"failures={malformed_failures}",
        )

        # An "archive/" subtree is skipped by the scan (matches this repo's existing convention).
        archived_dir = tmp_root / "planning" / "archive" / "BT.ticket.old" / "sdlc"
        archived_dir.mkdir(parents=True)
        archived_path = archived_dir / "sdlc-task-state.json"
        archived_path.write_text(json.dumps({"status": "closed"}, indent=2))
        found = csv.find_state_files(tmp_root / "planning")
        check(
            "find_state_files() skips planning/archive/ entirely",
            archived_path not in found,
            f"found={found}",
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    # --- --vocab / missing-file error handling --------------------------------------------------
    missing_vocab_proc = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--vocab", "/nonexistent/sdlc-state-vocab.json"],
        capture_output=True,
        text=True,
    )
    check(
        "a missing --vocab file exits 2 with a clear error, not a silent pass",
        missing_vocab_proc.returncode == 2,
        f"exit={missing_vocab_proc.returncode} stderr={missing_vocab_proc.stderr!r}",
    )

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
