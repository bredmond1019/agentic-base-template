#!/usr/bin/env python3
"""Gate the worked lane.json example in generate-roadmap.md against the real schema (D71/BT.5.B).

Task 1's replacement for the mirror test task 5 deletes: instead of re-implementing mev's
directive grammar in Python, this extracts the actual worked example that
`.claude/commands/generate-roadmap.md` ships, writes it to disk as a real `lane-<name>.json`
file, and runs it through `scripts/check_lane_records.py` -- the same checker a real lane record
is validated against. This makes the documentation mechanically checkable rather than merely
proofread, and it validates against the real schema instead of a mirror of a parser.

EXTRACTION: the example lives between two HTML-comment markers so it survives edits to the
surrounding prose without this script needing to track line numbers:

    <!-- WORKED-EXAMPLE:lane.json BEGIN -->
    ```json
    { ... }
    ```
    <!-- WORKED-EXAMPLE:lane.json END -->

A missing marker or a missing/malformed fenced block inside it is an ERROR, never a silent pass --
a worked example that quietly stopped being checked is worse than no checker at all.

TEMP-DIR TRAP (resolve deliberately, do not "simplify" this back to /tmp): check_lane_records.py's
budget.heavy cross-check resolves the lane's repo to a real path by walking UP from the lane file
looking for brain.toml (see its find_brain_root()). A tempdir under the system temp root (e.g.
/tmp/xyz) is outside the brain tree entirely, so that walk fails and the cross-check errors out
for a reason that has nothing to do with the example's correctness. Creating the temp tree under
THIS repo (`tempfile.mkdtemp(dir=<repo root>)`) keeps it inside the tree that walks up to
`agentic-portfolio/brain.toml`, so the real cross-check runs. Clean it up afterward either way.

D68: a gate never observed failing is not evidence it can fail. This script proves its own
negative path on every run -- it corrupts a copy of the extracted example (drops the required
`blocks` field) and asserts check_lane_records.py rejects it -- before it ever reports success on
the real one.

Usage:
    check_worked_example_lane.py [--command PATH] [--checker PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_COMMAND = REPO_ROOT / ".claude" / "commands" / "generate-roadmap.md"
DEFAULT_CHECKER = SCRIPT_DIR / "check_lane_records.py"

BEGIN_MARKER = "<!-- WORKED-EXAMPLE:lane.json BEGIN -->"
END_MARKER = "<!-- WORKED-EXAMPLE:lane.json END -->"

# Matches a ```json fenced block, non-greedy, DOTALL so it spans lines.
FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


class ExtractionError(Exception):
    """Raised when the marker or the fenced json block cannot be found -- always an error,
    never treated as a vacuous pass."""


def extract_worked_example(command_text: str) -> str:
    """Return the raw JSON text of the worked example between the markers. Raises
    ExtractionError (never returns silently) if the markers or the fence are missing."""
    begin_idx = command_text.find(BEGIN_MARKER)
    if begin_idx == -1:
        raise ExtractionError(f"marker not found: {BEGIN_MARKER!r}")
    end_idx = command_text.find(END_MARKER, begin_idx)
    if end_idx == -1:
        raise ExtractionError(f"marker not found (or precedes BEGIN): {END_MARKER!r}")

    between = command_text[begin_idx + len(BEGIN_MARKER):end_idx]
    match = FENCE_RE.search(between)
    if not match:
        raise ExtractionError(
            "no ```json fenced block found between the WORKED-EXAMPLE markers"
        )
    return match.group(1)


def parse_lane_name(json_text: str) -> str:
    """Parse the extracted text as JSON and return its `lane` field, used to name the file
    lane-<name>.json the way a real emitted record would be named."""
    try:
        record = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"extracted worked example is not valid JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise ExtractionError("extracted worked example's top level is not a JSON object")
    lane = record.get("lane")
    if not isinstance(lane, str) or not lane:
        raise ExtractionError("extracted worked example has no non-empty top-level `lane` field")
    return lane


def run_checker(checker: Path, planning_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(checker), "--planning", str(planning_dir), "--quiet"],
        capture_output=True, text=True, timeout=60,
    )


def write_lane_file(planning_dir: Path, lane_name: str, json_text: str) -> Path:
    """Write json_text as lane-<lane_name>.json inside a roadmap-shaped directory under
    planning_dir, mirroring the current planning/roadmaps/<slug>/lane-<name>.json layout."""
    roadmap_dir = planning_dir / "roadmaps" / "worked-example-check"
    roadmap_dir.mkdir(parents=True, exist_ok=True)
    lane_path = roadmap_dir / f"lane-{lane_name}.json"
    lane_path.write_text(json_text.rstrip() + "\n")
    return lane_path


def corrupt(json_text: str) -> str:
    """Return a deliberately-invalid copy of the example: drop the required `blocks` field.
    Used only to prove the checker path can fail (D68) before trusting a clean result."""
    record = json.loads(json_text)
    record = dict(record)
    record.pop("blocks", None)
    return json.dumps(record, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--command", type=Path, default=DEFAULT_COMMAND)
    ap.add_argument("--checker", type=Path, default=DEFAULT_CHECKER)
    args = ap.parse_args()

    if not args.command.is_file():
        print(f"FAIL: command file not found: {args.command}")
        return 1
    if not args.checker.is_file():
        print(f"FAIL: checker script not found: {args.checker}")
        return 1

    command_text = args.command.read_text()

    try:
        json_text = extract_worked_example(command_text)
        lane_name = parse_lane_name(json_text)
    except ExtractionError as exc:
        print(f"FAIL: {exc}")
        return 1

    tmp_root = Path(tempfile.mkdtemp(prefix="worked-example-lane-", dir=REPO_ROOT))
    # tmp_root is created UNDER REPO_ROOT (not /tmp) so check_lane_records.py's brain.toml walk
    # (find_brain_root, walking upward from the lane file) succeeds -- see module docstring.
    try:
        # --- D68 negative-path proof: the checker must be able to fail before we trust a pass.
        neg_root = tmp_root / "negative"
        neg_planning = neg_root
        try:
            corrupted_text = corrupt(json_text)
        except (json.JSONDecodeError, ExtractionError) as exc:
            print(f"FAIL: could not build the negative-path fixture: {exc}")
            return 1
        write_lane_file(neg_planning, lane_name, corrupted_text)
        neg_result = run_checker(args.checker, neg_planning)
        if neg_result.returncode == 0:
            print("FAIL: negative-path proof failed -- check_lane_records.py passed a corrupted "
                  "worked example (missing `blocks`), so this gate cannot be trusted to fail.")
            print(neg_result.stdout)
            print(neg_result.stderr)
            return 1

        # --- Positive path: the real, unmodified worked example must validate cleanly.
        pos_root = tmp_root / "positive"
        pos_planning = pos_root
        write_lane_file(pos_planning, lane_name, json_text)
        pos_result = run_checker(args.checker, pos_planning)
        if pos_result.returncode != 0:
            print("FAIL: the worked example in generate-roadmap.md does not validate against "
                  "lane.schema.json via check_lane_records.py:")
            print(pos_result.stdout)
            print(pos_result.stderr)
            return 1

        print(f"ok   worked example (lane `{lane_name}`) validates against lane.schema.json")
        print("ok   negative-path proof: a corrupted copy of the example was correctly rejected")
        return 0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
