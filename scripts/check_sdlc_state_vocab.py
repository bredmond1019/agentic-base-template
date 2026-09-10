#!/usr/bin/env python3
"""check_sdlc_state_vocab.py — gate every sdlc-*-state.json's status value against the canonical enum.

WHY THIS EXISTS
---------------
state.json's block status is already a closed, gated enum: mev's `set-block-status` validates at
write time and `validate-brain --state` validates at commit/push time (core/mev/src/brain/state.rs).
sdlc-task-state.json / sdlc-flow-state.json's `status` field has neither. A fleet audit (2026-09-10)
found `completed` hand-written into several repos' sdlc-state files even though neither current
engine (`sdlc-task.js` / `sdlc-flow.js`) ever emits it — a dead/legacy value nothing ever caught,
because nothing checked this field at all. See planning/decisions/D86.

WHAT THIS DOES
--------------
Loads the canonical vocabulary from `.claude/workflows/sdlc-state-vocab.json` (one entry per
allowed status value, keyed by the value itself), finds every `sdlc-*-state.json` file reachable
under a root directory (default: this repo's own `planning/` tree; pass `--root <dir>` to point it
at a different tree so the same script can later run against another repo), and checks:

  - the file's top-level `"status"` field, if present, against the vocabulary
  - every per-task `"status"` field under a top-level `"tasks"` object, if present, against the
    same vocabulary (sdlc-task's per-task entries use `passed`/`failed`, both in the vocab)

A file with neither field present at all (e.g. an older/retired engine's state shape that never
had a `status` key, or a `tasks` object with no per-entry `status`) is not this check's concern —
absence is not an out-of-vocabulary value, it is a different question. A malformed (non-JSON) file
is reported as its own failure rather than silently skipped.

`planning/archive/` is excluded from the scan, matching this repo's existing convention
(scripts/check_lane_records.py, check_command_hazards.py, check_command_docs_no_write_path.py,
check_task_gate_boundaries.py all skip the same directory name). A spec under `planning/archive/`
is a frozen historical snapshot retired via `/archive` (D35), not a live file either engine still
writes to -- and, measured 2026-09-10, real archived data already carries a stray hand-written
`"status": "closed"` (planning/archive/BT.3.I/sdlc/sdlc-task-state.json) that predates this gate
and neither engine ever emits; gating archived history would force either inventing an unearned
vocabulary entry or rewriting a historical record, and this check's job is the live vocabulary
engines actually emit today, not archaeology.

This is a GATING check (`sdlc-state-vocab` in planning/harness.json). A failure names the exact
file and the offending value — fix the value (or, if it is genuinely a new terminal status one of
the engines needs, add it to sdlc-state-vocab.json AND docs/workflows/sdlc-state-vocabulary.md
first), never silence this check.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VOCAB_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-state-vocab.json"

# Matches sdlc-task-state.json, sdlc-flow-state.json, sdlc-run-state.json, and any future
# sdlc-<engine>-state.json — the naming convention every engine's state file follows.
STATE_FILE_GLOB = "sdlc-*-state.json"

# Directories this scan never descends into. "archive" mirrors the convention already used by
# scripts/check_lane_records.py, check_command_hazards.py, check_command_docs_no_write_path.py
# and check_task_gate_boundaries.py — a spec retired under planning/archive/ (D35) is frozen
# history, not a live file either engine still writes.
SKIP_DIRS = {"node_modules", ".git", "archive", "target", ".fleet-locks", "trees"}


def load_vocab(path: Path = VOCAB_PATH) -> set[str]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{path}: expected a non-empty JSON object of status -> {{meaning, emitters}}")
    return set(data.keys())


def find_state_files(root: Path) -> list[Path]:
    """Walk root, skipping SKIP_DIRS, collecting files matching STATE_FILE_GLOB."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if fnmatch.fnmatch(name, STATE_FILE_GLOB):
                found.append(Path(dirpath) / name)
    return sorted(found)


def check_file(path: Path, vocab: set[str]) -> list[str]:
    """Return a list of human-readable failure lines for this one file (empty = clean)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"  - {path}: could not read ({exc})"]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"  - {path}: not valid JSON ({exc})"]

    if not isinstance(data, dict):
        return [f"  - {path}: top level is not a JSON object"]

    failures: list[str] = []

    top_status = data.get("status")
    if isinstance(top_status, str) and top_status not in vocab:
        failures.append(f"  - {path}: top-level status {top_status!r} is not in the canonical vocabulary")

    tasks = data.get("tasks")
    if isinstance(tasks, dict):
        for task_key, task_val in tasks.items():
            if not isinstance(task_val, dict):
                continue
            task_status = task_val.get("status")
            if isinstance(task_status, str) and task_status not in vocab:
                failures.append(
                    f"  - {path}: tasks[{task_key!r}].status {task_status!r} is not in the "
                    "canonical vocabulary"
                )

    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT / "planning"),
        help="Directory tree to scan for sdlc-*-state.json files (default: this repo's planning/).",
    )
    parser.add_argument(
        "--vocab",
        default=str(VOCAB_PATH),
        help="Path to the canonical sdlc-state-vocab.json (default: .claude/workflows/sdlc-state-vocab.json).",
    )
    args = parser.parse_args(argv[1:])

    vocab_path = Path(args.vocab)
    if not vocab_path.is_file():
        print(f"ERROR: vocab file not found: {vocab_path}", file=sys.stderr)
        return 2
    try:
        vocab = load_vocab(vocab_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not load vocab from {vocab_path}: {exc}", file=sys.stderr)
        return 2

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: --root {root} is not a directory", file=sys.stderr)
        return 2

    state_files = find_state_files(root)
    all_failures: list[str] = []
    for path in state_files:
        all_failures.extend(check_file(path, vocab))

    if all_failures:
        print("sdlc-state vocabulary check FAILED:\n")
        print("\n".join(all_failures))
        print(
            f"\nEvery status value in an sdlc-*-state.json file must be one of the {len(vocab)} "
            f"values in {vocab_path.relative_to(REPO_ROOT) if vocab_path.is_relative_to(REPO_ROOT) else vocab_path}.\n"
            "If this is a genuinely new terminal status an engine needs, add it there (and to\n"
            "docs/workflows/sdlc-state-vocabulary.md) first -- do not silence this check."
        )
        return 1

    print(f"OK -- {len(state_files)} sdlc-*-state.json file(s) under {root} use only vocabulary status values.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
