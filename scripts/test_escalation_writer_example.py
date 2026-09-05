#!/usr/bin/env python3
"""Fixture proving the escalation record example documented in the writer instructions actually
passes `check_escalations.py` (BT.ticket.escalation-writer-emits-the-pre-schema-shape, task 1).

Deliberately NOT added to `scripts/test_check_escalations.py`: that file is registered in
`planning/harness.json` as `escalations-schema-tests` with `gates: true`, and a gated test file
can never again pin a new red case -- the harness copy runs uninverted and turns a gating check
red on committed code for every concurrent lane. This file is registered separately once it is
green (task 2).

Extracts the example from BOTH `.claude/commands/begin-orchestration.md` and
`.agents/skills/begin-orchestration/SKILL.md` at runtime -- never duplicates the example inline --
because a test carrying its own copy of the example proves nothing about the file an agent
actually reads. Runs two runtime inversions rather than a frozen committed red fixture: D68's
"a checker never observed going red is not evidence" is met by breaking the precondition inside
the test, observing the failure, then restoring it and observing the pass, leaving no gate red at
any boundary (BT.ticket.escalations-gate-attributes-foreign-records task 1 tried the
committed-red-fixture shape and it mis-bailed the engine's test stage).

Never touches the real `planning/roadmaps/` corpus -- every fixture tree lives under
`tempfile.mkdtemp()`.

OBSERVED RED (bare-adjective verified_by, captured while writing this fixture):

    $ python3 - <<'PY'
    import copy, json, subprocess, sys, tempfile
    from pathlib import Path
    sys.path.insert(0, "scripts")
    from test_escalation_writer_example import extract_json_block, COMMAND_PATH
    record = extract_json_block(COMMAND_PATH.read_text())
    record["verified_by"] = "measured"
    tmp = Path(tempfile.mkdtemp())
    roadmap_dir = tmp / "planning" / "roadmaps" / "probe-roadmap"
    roadmap_dir.mkdir(parents=True)
    (roadmap_dir / "escalations.jsonl").write_text(json.dumps(record) + "\n")
    proc = subprocess.run(
        [sys.executable, "scripts/check_escalations.py", "--roadmaps-dir", str(tmp / "planning" / "roadmaps"), "--quiet"],
        capture_output=True, text=True,
    )
    print("exit code:", proc.returncode)
    print(proc.stdout + proc.stderr)
    PY
    exit code: 1
    FAIL /tmp/.../planning/roadmaps/probe-roadmap/escalations.jsonl:1
           `verified_by` value `measured` is neither `UNVERIFIED: <claimant>` nor a
           command-plus-output block (a command line, then its output on a following line) -- a
           bare adjective such as 'measured' does not satisfy this field

    1 record(s) checked, 1 gating failure(s)

Run: python3 scripts/test_escalation_writer_example.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_PATH = REPO_ROOT / "scripts" / "check_escalations.py"
COMMAND_PATH = REPO_ROOT / ".claude" / "commands" / "begin-orchestration.md"
SKILL_PATH = REPO_ROOT / ".agents" / "skills" / "begin-orchestration" / "SKILL.md"

_spec = importlib.util.spec_from_file_location("check_escalations", CHECKER_PATH)
check_escalations = importlib.util.module_from_spec(_spec)
sys.modules["check_escalations"] = check_escalations
_spec.loader.exec_module(check_escalations)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n[ \t]*```", re.DOTALL)


def extract_json_block(markdown_text: str) -> dict:
    """Find the (sole) fenced ```json block in the escalation-writing section and parse it."""
    matches = JSON_FENCE_RE.findall(markdown_text)
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one fenced json block, found {len(matches)}")
    return json.loads(matches[0])


def run_checker(roadmaps_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER_PATH), "--roadmaps-dir", str(roadmaps_dir), "--quiet"],
        capture_output=True,
        text=True,
    )


def write_corpus(tmp_root: Path, roadmap: str, record: dict) -> Path:
    roadmaps_dir = tmp_root / "planning" / "roadmaps"
    roadmap_dir = roadmaps_dir / roadmap
    roadmap_dir.mkdir(parents=True, exist_ok=True)
    (roadmap_dir / "escalations.jsonl").write_text(json.dumps(record) + "\n")
    return roadmaps_dir


def main() -> int:
    command_text = COMMAND_PATH.read_text()
    skill_text = SKILL_PATH.read_text()

    command_record = extract_json_block(command_text)
    skill_record = extract_json_block(skill_text)

    check(
        "example extracts from begin-orchestration.md",
        isinstance(command_record, dict) and len(command_record) > 0,
    )
    check(
        "example extracts from SKILL.md",
        isinstance(skill_record, dict) and len(skill_record) > 0,
    )
    check(
        "both examples parse to the same object",
        command_record == skill_record,
        f"command={command_record!r} skill={skill_record!r}",
    )

    # --- Positive case: the documented example passes check_escalations.py ---
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        roadmaps_dir = write_corpus(tmp_root, "probe-roadmap", command_record)
        proc = run_checker(roadmaps_dir)
        check(
            "documented example passes check_escalations.py",
            proc.returncode == 0,
            f"exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}",
        )

    # --- Runtime inversion 1: bare-adjective verified_by (D68 evidence, 9 live records' shape) ---
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        bad_record = copy.deepcopy(command_record)
        bad_record["verified_by"] = "measured"
        roadmaps_dir = write_corpus(tmp_root, "probe-roadmap", bad_record)
        proc = run_checker(roadmaps_dir)
        check(
            "bare-adjective verified_by is rejected (observed red)",
            proc.returncode != 0,
            f"exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}",
        )
        check(
            "bare-adjective failure names verified_by",
            "verified_by" in (proc.stdout + proc.stderr),
            proc.stdout + proc.stderr,
        )

    # Restore and re-observe green, proving the failure above was caused by the mutation and not
    # by fixture plumbing.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        roadmaps_dir = write_corpus(tmp_root, "probe-roadmap", command_record)
        proc = run_checker(roadmaps_dir)
        check(
            "unmodified example still passes after the inversion above",
            proc.returncode == 0,
            f"exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}",
        )

    # --- Runtime inversion 2: one per required field, derived from the checker module itself ---
    for field in check_escalations.ESCALATION_REQUIRED:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            missing_record = copy.deepcopy(command_record)
            del missing_record[field]
            # `options` is required exactly when channel == "notification"; the documented
            # example uses "notification", so dropping any of the eleven ESCALATION_REQUIRED
            # fields is still expected to fail specifically because that field is missing (not
            # merely because options went missing too) -- these fields are disjoint from
            # `options` itself, so this holds for every entry in ESCALATION_REQUIRED.
            roadmaps_dir = write_corpus(tmp_root, "probe-roadmap", missing_record)
            proc = run_checker(roadmaps_dir)
            output = proc.stdout + proc.stderr
            check(
                f"missing required field '{field}' is rejected",
                proc.returncode != 0,
                output,
            )
            check(
                f"missing '{field}' failure names the field",
                field in output,
                output,
            )

    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
