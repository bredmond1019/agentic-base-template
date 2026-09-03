#!/usr/bin/env python3
"""Fixture suite for BT.ticket.consolidate-fleet-since-filter (task 1: the RED baseline, D68).

Self-contained, no pytest, matching the fixture style of test_check_escalations.py: a
`check(label, condition, detail)` helper prints `[PASS]`/`[FAIL]` per named case, a `FAILURES`
list gates the exit code, and every fixture lives in a temp dir — nothing here reads the real
corpus or the real watermark file at
`planning/open-work/orchestration-runs/consolidation-watermark.json`.

Two halves, per the task:

HALF A -- the `--since` selection semantics, as source assertions over
`.claude/commands/consolidate-fleet.md`. A markdown command has no importable code, so this reads
the `## Variables` section (sliced by the `##`/`###` heading markers, never a hardcoded line
number, so a later edit that shifts lines does not silently start reading the wrong table row) and
asserts the documented contract: the flag exists, it selects by lane-log ACTIVITY DATE rather than
by roadmap, and it composes with the other selectors by narrowing, never widening.

STATUS AS OF 2026-09-03: `--since` already shipped (verified at spec-authoring time against
`.claude/commands/consolidate-fleet.md:55`). Half A is expected to PASS today, not fail --
re-implementing an already-shipped deliverable is the defect this roadmap exists to stop. Recorded
here so a reader does not read Half A green and assume the fixture is broken.

HALF B -- `scripts/lane_log_watermark.py verify` output shapes, driven as a real subprocess against
fixture roadmap trees built under `--root` (the flag `state_for`/`selected`/`cmd_verify` already
support; it needs no `brain.toml` when passed explicitly -- confirmed empirically 2026-09-03,
which corrects the parent ticket's framing that "no flag can point verify at a fixture directory"
today. `--root` already provides directory-level isolation. What is actually still missing, and
what keeps Half B red, is narrower than the ticket states):

  B1. A DEDICATED `--watermark-dir` flag, matching this repo's existing `--lock-dir` /
      `--roadmaps-dir` point-at-the-object convention (`check_lane_agents.py`,
      `check_escalations.py`), does not exist yet -- `verify --watermark-dir <dir>` exits 2 with
      argparse's "unrecognized arguments". Task 2's own acceptance criteria names this flag by the
      same convention, so this suite asserts it by that name rather than inventing a different one.
  B2. Even using the `--root` seam that already works, the ZERO-watermarks case
      ("0 watermark(s) checked, 0 drifted") is textually distinguished from the N-checked-all-clean
      case ONLY by the leading digit -- there is no wording that says "no watermarks recorded yet"
      as a distinct shape. That is the real gap: not "cannot point at a fixture" (false, measured),
      but "the zero case and the all-clean case share one template with an incidental 0".
  B3. N watermarks, none drifted -- the existing "<N> watermark(s) checked, 0 drifted" shape.
      Already correct today; asserted here as the passing counterpart to B2.
  B4. N watermarks, one drifted -- the REGRESSION GUARD: a real drift must still be reported and
      exit non-zero once B1/B2 land, so the new zero/clean distinction never swallows a real
      failure. Already correct today.

RED OUTPUT, captured verbatim, 2026-09-03 (`python3 scripts/test_consolidate_fleet_since.py`):

    [PASS] --since is documented in the Variables table
    [PASS] --since is documented to select by lane-log activity date, not by roadmap slug
    [PASS] --since is documented to narrow, never widen, when composed with other selectors
    [FAIL] B1: verify accepts a dedicated --watermark-dir flag (exit 0, not an argparse usage
      error) -- returncode=2, stdout=, stderr=usage: lane_log_watermark.py [-h] [--roadmap
      ROADMAPS] [--to-line TO_LINE]
                                 [--run-id RUN_ID] [--root ROOT] [--json]
                                 [--strict]
                                 {status,pending,advance,verify}
      lane_log_watermark.py: error: unrecognized arguments: --watermark-dir /tmp/.../wmdir
    [FAIL] B2: the zero-watermarks case says so in words, not just via a leading 0 -- stdout='0
      watermark(s) checked, 0 drifted\n'
    [PASS] B3: N watermarks, none drifted -> '<N> checked, 0 drifted' shape
    [PASS] B4 (regression guard): a genuinely drifted watermark is still reported as DRIFT with a
      non-zero exit

    2 check(s) failed:
      - B1: verify accepts a dedicated --watermark-dir flag (exit 0, not an argparse usage error)
      - B2: the zero-watermarks case says so in words, not just via a leading 0

    2 failed -- see [FAIL] lines above.

TRAP (the parent ticket's own, instrument #4): never judge absence from a truncated view -- run
this file's own output through a real terminal or redirect to a file and check `$?` on its own
line; do not pipe it to `head`.

Run: python3 scripts/test_consolidate_fleet_since.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMAND_DOC = REPO_ROOT / ".claude" / "commands" / "consolidate-fleet.md"
WATERMARK_MODULE = REPO_ROOT / "scripts" / "lane_log_watermark.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import lane_log_watermark as wm  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


# --- Half A: --since selection semantics, sliced from the doc by heading marker ------------------

def _section(text: str, start_marker: str, end_marker: str) -> str:
    """Slice `text` between two heading markers. Never a line number -- a later edit that shifts
    lines must not silently start reading the wrong table row."""
    start = text.index(start_marker)
    end = text.index(end_marker, start + len(start_marker))
    return text[start:end]


def check_half_a_since_semantics() -> None:
    text = COMMAND_DOC.read_text()
    variables = _section(text, "## Variables", "## Step 1")

    check("--since is documented in the Variables table",
          "--since <YYYY-MM-DD>" in variables, "flag row not found under ## Variables")

    since_row_start = variables.find("--since <YYYY-MM-DD>")
    since_row = variables[since_row_start:since_row_start + 400] if since_row_start != -1 else ""

    check("--since is documented to select by lane-log activity date, not by roadmap slug",
          "activity date" in since_row and "roadmap" in since_row,
          f"row text: {since_row!r}")

    check("--since is documented to narrow, never widen, when composed with other selectors",
          "narrows, never widens" in since_row,
          f"row text: {since_row!r}")


# --- Half B: lane_log_watermark.py verify output shapes --------------------------------------------

def _row(ts: str, block: str, note: str = "n") -> str:
    import json
    return json.dumps({"ts": ts, "lane": "l", "repo": "r", "block": block,
                        "status": "closed", "note": note})


def _build_roadmap(root: Path, slug: str, lines: list[str]) -> Path:
    """A fixture root with one roadmap's lane-log.jsonl and NO consolidation-watermark.json --
    the on-disk shape of a roadmap nobody has consolidated yet. Never writes brain.toml; --root
    is passed explicitly, and find_brain_root is never invoked when it is."""
    d = root / "planning" / "roadmaps" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "lane-log.jsonl").write_text("".join(l + "\n" for l in lines))
    return root


def _stamp_watermark(root: Path, slug: str, lines: list[str], at: int,
                      bad_hash: bool = False) -> None:
    """Write a consolidation-watermark.json entry for `slug` at line `at`, using the module's own
    `sha()` so the fixture's notion of a matching hash is identical to production's. `bad_hash`
    deliberately stores the wrong hash to force `state_for` to report drift."""
    import json
    real_hash = wm.sha(lines[at - 1]) if at > 0 else None
    stored_hash = "0" * 64 if bad_hash else real_hash
    marks_path = root / wm.WATERMARK_REL
    marks_path.parent.mkdir(parents=True, exist_ok=True)
    marks_path.write_text(json.dumps({
        "version": wm.SCHEMA_VERSION,
        "roadmaps": {slug: {"line": at, "last_line_sha256": stored_hash,
                             "consolidated_at": "2026-09-01T00:00:00Z", "run_id": "r0"}},
    }, indent=2))


def _run(root: Path, *args: str, use_root: bool = True) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(WATERMARK_MODULE), "verify", *args]
    if use_root:
        cmd += ["--root", str(root)]
    return subprocess.run(cmd, capture_output=True, text=True)


def check_half_b_watermark_dir_flag_missing() -> None:
    with tempfile.TemporaryDirectory() as td:
        wmdir = Path(td) / "wmdir"
        wmdir.mkdir()
        proc = subprocess.run(
            [sys.executable, str(WATERMARK_MODULE), "verify", "--watermark-dir", str(wmdir)],
            capture_output=True, text=True)
        check("B1: verify accepts a dedicated --watermark-dir flag (exit 0, not an argparse "
              "usage error)",
              proc.returncode == 0,
              f"returncode={proc.returncode}, stdout={proc.stdout}, stderr={proc.stderr}")


def check_half_b_zero_watermarks_says_so_in_words() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lines = [_row("2026-09-01T00:00:00Z", "A")]
        _build_roadmap(root, "rm-zero", lines)
        # Deliberately no watermark file at all: nobody has consolidated this roadmap yet.
        proc = _run(root)
        check("B2: the zero-watermarks case says so in words, not just via a leading 0",
              proc.returncode == 0 and (
                  "no watermark" in proc.stdout.lower()
                  or "none recorded" in proc.stdout.lower()
                  or "not yet consolidated" in proc.stdout.lower()
              ),
              f"stdout={proc.stdout!r}")


def check_half_b_all_clean_shape() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lines = [_row("2026-09-01T00:00:00Z", "A"), _row("2026-09-01T01:00:00Z", "B")]
        _build_roadmap(root, "rm-clean", lines)
        _stamp_watermark(root, "rm-clean", lines, at=2)
        proc = _run(root)
        check("B3: N watermarks, none drifted -> '<N> checked, 0 drifted' shape",
              proc.returncode == 0 and "1 watermark(s) checked, 0 drifted" in proc.stdout,
              f"returncode={proc.returncode}, stdout={proc.stdout!r}")


def check_half_b_drift_regression_guard() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lines = [_row("2026-09-01T00:00:00Z", "A"), _row("2026-09-01T01:00:00Z", "B")]
        _build_roadmap(root, "rm-drift", lines)
        _stamp_watermark(root, "rm-drift", lines, at=2, bad_hash=True)
        proc = _run(root)
        check("B4 (regression guard): a genuinely drifted watermark is still reported as DRIFT "
              "with a non-zero exit",
              proc.returncode == 2 and "DRIFT" in proc.stdout,
              f"returncode={proc.returncode}, stdout={proc.stdout!r}")


def main() -> int:
    check_half_a_since_semantics()
    check_half_b_watermark_dir_flag_missing()
    check_half_b_zero_watermarks_says_so_in_words()
    check_half_b_all_clean_shape()
    check_half_b_drift_regression_guard()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        print(f"\n{len(FAILURES)} failed -- see [FAIL] lines above.")
        return 1
    print("\nOK -- consolidate-fleet's --since documentation and lane_log_watermark.py verify "
          "output shapes both hold against the fixture corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
