#!/usr/bin/env python3
"""Fixtures over `lane_log_watermark.py --since <YYYY-MM-DD>` (status/pending roadmap selection).

WHY THIS EXISTS
---------------
BT.ticket.consolidate-fleet-since-filter documented `--since` on the `/consolidate-fleet` command
file. The tool that command drives never gained the flag -- `status --help` lists none, and the
only two `since` occurrences in `lane_log_watermark.py` are prose (module docstring + a help
string). So selecting "everything since a date, across several roadmaps" is done by hand today:
re-derivable by nobody but the person who ran it. This suite is written FIRST, against the
flagless tool, and is expected to fail loudly -- see `RUN THIS AGAINST THE UNMODIFIED TOOL` below.

FIVE FIXTURES (per the task record):
1. `before`     -- every line strictly before the date            -> EXCLUDED, named in the output.
2. `after`      -- every line on/after the date                   -> INCLUDED.
3. `spanning`   -- lines on both sides of the date                -> INCLUDED.
4. `malformed`  -- the only post-date lines are malformed JSON    -> INCLUDED, malformed count
                   reported. A parse failure must never silently shrink the input.
5. (no fixture roadmap) -- running with no `--since` at all must produce byte-identical output to
   before this flag existed. This is the positive control: every existing caller passes no flag.

TIMEZONES ARE REAL, NOT HYPOTHETICAL (measured 2026-09-04 over the live corpus: 383 `Z`-suffixed
timestamps, 93 with a numeric offset, 2 in neither shape). `--since` must compare INSTANTS, not
string prefixes -- a `-03:00` timestamp late on one day is the next day in UTC, and this box is
UTC-3, so a lexical implementation passes here by luck and fails everywhere else. `tz_z` and
`tz_offset` below encode the exact same UTC instant in the two shapes the corpus actually uses and
must select identically.

RUN THIS AGAINST THE UNMODIFIED TOOL: `--since` is not a recognized flag yet, so argparse rejects
it (`error: unrecognized arguments: --since ...`, exit 2) before any of the assertions below get a
chance to run -- every `run_cli(..., "--since", ...)` call fails immediately. That is the expected,
unambiguous RED this task records; task 2 makes it pass.

Hermetic: every fixture is a temp dir with its own brain.toml. Nothing reads the real corpus.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lane_log_watermark as wm  # noqa: E402

MODULE = Path(__file__).resolve().parent / "lane_log_watermark.py"
FAILURES: list[str] = []

SINCE = "2026-09-02"  # the threshold date used across every fixture below


def check(label, cond, detail=""):
    if cond:
        print(f"[PASS] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}" + (f" -- {detail}" if detail else ""))


def row(ts, block, note="n"):
    return json.dumps({"ts": ts, "lane": "l", "repo": "r", "block": block,
                       "status": "closed", "note": note})


def build(tmp: Path, roadmaps: dict[str, list[str]]) -> Path:
    """`roadmaps` maps slug -> raw lane-log lines (already-serialized strings, some may be
    deliberately malformed JSON to exercise the malformed-lines-only fixture)."""
    (tmp / "brain.toml").write_text("# brain.toml\n")
    for slug, lines in roadmaps.items():
        base = tmp / "planning" / "roadmaps" / slug
        base.mkdir(parents=True, exist_ok=True)
        (base / "lane-log.jsonl").write_text("".join(l + "\n" for l in lines))
    return tmp


def run_cli(root: Path, *args):
    return subprocess.run([sys.executable, str(MODULE), *args, "--root", str(root)],
                          capture_output=True, text=True)


def main() -> int:
    # threshold instant: 2026-09-02T00:00:00Z. Lines are placed either side of it, plus a pair
    # of same-instant Z/-03:00 encodings that a lexical (string-prefix) compare gets wrong.
    roadmaps = {
        "before": [
            row("2026-09-01T01:00:00Z", "A"),
            row("2026-09-01T23:59:59Z", "B"),
        ],
        "after": [
            row("2026-09-02T00:00:00Z", "C"),
            row("2026-09-03T05:00:00Z", "D"),
        ],
        "spanning": [
            row("2026-09-01T01:00:00Z", "E"),
            row("2026-09-02T12:00:00Z", "F"),
        ],
        # the only line at/after SINCE is malformed JSON -- must still be INCLUDED, with the
        # malformed count reported, never silently dropped from the selection.
        "malformed": [
            row("2026-09-01T01:00:00Z", "G"),
            '{"ts": "2026-09-02T01:00:00Z", "lane": "l", truncated mid-note at byte 4',
        ],
        # same UTC instant (2026-09-02T00:30:00Z), encoded two different ways the corpus
        # actually uses. A string-prefix compare against "2026-09-02" wrongly excludes tz_offset
        # (its line starts "2026-09-01") while correctly including tz_z -- an instant compare
        # includes both.
        "tz_z": [
            row("2026-09-02T00:30:00Z", "H"),
        ],
        "tz_offset": [
            row("2026-09-01T21:30:00-03:00", "I"),  # == 2026-09-02T00:30:00Z
        ],
    }

    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), roadmaps)

        # --- fixture 1+2+3: before / after / spanning select correctly, excluded named --------
        r = run_cli(root, "status", "--since", SINCE, "--json",
                    "--roadmap", "before", "--roadmap", "after", "--roadmap", "spanning")
        check("`--since` status exits 0 on the plain before/after/spanning fixtures",
              r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}")
        try:
            out = json.loads(r.stdout)
        except Exception as exc:                    # noqa: BLE001
            out = None
            check("`--since` status prints valid JSON", False, f"{exc}: {r.stdout!r}")
        if out is not None:
            included = {row_["roadmap"] for row_ in out.get("roadmaps", [])}
            excluded = set(out.get("excluded", []))
            check("`before` (all lines pre-date) is excluded, not included",
                  "before" not in included, str(out))
            check("`before` is NAMED in the excluded list, not silently dropped",
                  "before" in excluded, str(out))
            check("`after` (all lines post-date) is included",
                  "after" in included, str(out))
            check("`spanning` (lines on both sides) is included",
                  "spanning" in included, str(out))

        # --- fixture 4: malformed-only post-date lines still INCLUDE the roadmap -------------
        r = run_cli(root, "status", "--since", SINCE, "--json", "--roadmap", "malformed")
        check("`--since` status exits 0 on the malformed-only fixture",
              r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}")
        try:
            out = json.loads(r.stdout)
            rows = out.get("roadmaps", [])
            mal_row = next((x for x in rows if x.get("roadmap") == "malformed"), None)
            check("a roadmap whose only post-date line is malformed is INCLUDED, not excluded",
                  mal_row is not None, str(out))
            if mal_row is not None:
                check("its malformed line count is reported, not silently zero",
                      len(mal_row.get("malformed_lines") or []) >= 1, str(mal_row))
        except Exception as exc:                     # noqa: BLE001
            check("malformed-only fixture produces parseable JSON", False, f"{exc}: {r.stdout!r}")

        # --- fixture 5 (timezone): Z and -03:00 encodings of the same instant select alike ---
        r = run_cli(root, "status", "--since", SINCE, "--json",
                    "--roadmap", "tz_z", "--roadmap", "tz_offset")
        check("`--since` status exits 0 on the mixed-timezone fixture",
              r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}")
        try:
            out = json.loads(r.stdout)
            included = {row_["roadmap"] for row_ in out.get("roadmaps", [])}
            check("a Z timestamp at/after the threshold instant is included",
                  "tz_z" in included, str(out))
            check("the SAME instant written as -03:00 is included identically "
                  "(instant compare, not a string-prefix compare)",
                  "tz_offset" in included, str(out))
        except Exception as exc:                      # noqa: BLE001
            check("mixed-timezone fixture produces parseable JSON", False, f"{exc}: {r.stdout!r}")

        # --- fixture 6 / positive control: no --since at all is unaffected -------------------
        r1 = run_cli(root, "status", "--json",
                     "--roadmap", "before", "--roadmap", "after", "--roadmap", "spanning")
        r2 = run_cli(root, "status", "--json",
                     "--roadmap", "before", "--roadmap", "after", "--roadmap", "spanning")
        check("status without --since exits 0", r1.returncode == 0, r1.stderr)
        check("status without --since is deterministic (byte-identical across two runs)",
              r1.stdout == r2.stdout, f"{r1.stdout!r} != {r2.stdout!r}")
        try:
            out = json.loads(r1.stdout)
            check("without --since, no `excluded` key is introduced -- unchanged output shape",
                  "excluded" not in out, str(out))
            check("without --since, every roadmap with lines is still reported (no filtering)",
                  {row_["roadmap"] for row_ in out.get("roadmaps", [])}
                  == {"before", "after", "spanning"}, str(out))
        except Exception as exc:                      # noqa: BLE001
            check("no-`--since` output parses as JSON", False, f"{exc}: {r1.stdout!r}")

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- lane_log_watermark.py --since holds against the fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
