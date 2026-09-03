#!/usr/bin/env python3
"""Consolidation watermarks over `lane-log.jsonl` — how far a past consolidation got.

WHY THIS EXISTS
---------------
`/consolidate-run` already avoids re-proposing findings by stamping `lifecycle: consolidated` on
each run record it consumed. That mechanism works and is not duplicated here -- the count of
records carrying the stamp changes every run; measure it yourself with
`grep -rl 'lifecycle: consolidated' planning/roadmaps/*/  planning/*/*.md 2>/dev/null | wc -l`
rather than trusting a number written here. But `lane-log.jsonl` has no frontmatter and therefore
no stamp, and it is the only
artifact carrying the per-block narrative of a run (`{ts, lane, repo, block, status, note}`). A
fleet pass that wants "everything since last time, across several roadmaps, even if last time was
days ago" has nothing to resume from. This is that missing half.

WHAT A WATERMARK IS, AND IS NOT
-------------------------------
It is an ADVISORY resume point, not a completion record. Measured 2026-09-02: six lanes finished a
run and exactly ONE wrote a `LANE-CLOSE` row, and only after being asked. So "the log ends" does
not mean "the run ended", and this module never claims otherwise. It answers exactly one question:
which lines has a consolidation already read?

THE APPEND-ONLY ASSUMPTION, AND WHY IT IS CHECKED RATHER THAN TRUSTED
---------------------------------------------------------------------
Line numbers are a valid cursor only while the file is append-only. That is the contract, but a
truncation or a hand-edit would silently shift every later line and make the cursor point at the
wrong place -- the failure would look exactly like a clean resume. So the watermark stores a
sha256 of the last line it consumed, and `verify` re-reads that line and compares. A mismatch is
reported and BLOCKS an advance; it never silently re-bases. Recovery is the operator's call.

MALFORMED LINES ARE REPORTED, NEVER SKIPPED
-------------------------------------------
Measured 2026-09-03 (`python3 scripts/lane_log_watermark.py status --json` over every discovered
roadmap): 9 malformed lines out of 492 total, all in `demand-ready`, each truncated mid-`note` at
exactly 533 bytes by some writer or editor. The 9 held steady between 2026-09-02 and 2026-09-03
while the total line count moved (421 -> 492); do not treat either number as fixed -- re-run the
command above rather than citing this docstring. A miner that skips malformed lines silently loses
run data, which is the one thing this whole path exists to preserve. Every verb counts and names
them; `--strict` turns them into a nonzero exit.

TIMESTAMPS ARE NOT A CURSOR
---------------------------
`ts` values mix `Z` and `-03:00` in the same corpus, and the commander's own retro records a
three-hour misread from exactly that (I4, "the box is UTC-3"). Timestamps are carried in the
watermark for human reading only. The cursor is the line number; the integrity check is the hash.

Usage:
    lane_log_watermark.py status  [--roadmap SLUG]... [--root DIR] [--watermark-dir DIR] [--json] [--strict]
    lane_log_watermark.py pending [--roadmap SLUG]... [--root DIR] [--watermark-dir DIR] [--json] [--strict]
    lane_log_watermark.py advance --roadmap SLUG [--to-line N] [--run-id ID] [--root DIR] [--watermark-dir DIR] [--json]
    lane_log_watermark.py verify  [--roadmap SLUG]... [--root DIR] [--watermark-dir DIR] [--json]

    status   what the watermark says, per roadmap, with how many lines are new since
    pending  print the unread lines themselves (the consolidation's actual input)
    advance  move a roadmap's watermark to --to-line (default: the file's current last line)
    verify   re-check every stored hash against disk; nonzero if any roadmap drifted

    --watermark-dir DIR   point directly at the directory holding (or that should hold)
                           `consolidation-watermark.json`, overriding the default
                           `<root>/planning/open-work/orchestration-runs` location -- the same
                           point-at-the-object convention as `check_lane_agents.py --lock-dir` and
                           `check_escalations.py --roadmaps-dir`. Chiefly for tests: it makes the
                           "no watermark file exists yet" case exercisable without also having to
                           fabricate a fixture `--root` with a full `planning/` layout.

verify's two "nothing is wrong" shapes read differently on purpose: no watermark file (or a file
with no entries) for the selected roadmaps prints a sentence saying so; one or more watermarks
present with no drift prints the `<N> watermark(s) checked, 0 drifted` count line, unchanged from
before this flag existed. A real drift is reported identically either way.

Exit codes: 0 ok · 1 usage/IO error · 2 integrity drift (verify, or advance over a drifted mark)
            3 malformed lines present and --strict was passed
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

WATERMARK_REL = "planning/open-work/orchestration-runs/consolidation-watermark.json"
SCHEMA_VERSION = 1


def find_brain_root(start: Path) -> Path:
    current = Path(start).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").is_file():
            return candidate
    raise SystemExit(f"ERROR: no brain.toml found walking up from {start}")


def sha(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def roadmap_dir(root: Path, slug: str) -> Path | None:
    """`planning/roadmaps/<slug>/` first, then the legacy `planning/<slug>/`.

    Both existing is an error, not a silent preference -- the same rule /begin-orchestration and
    /consolidate-run resolve with. Returning the wrong one would consolidate a different run.
    """
    a = root / "planning" / "roadmaps" / slug
    b = root / "planning" / slug
    if a.is_dir() and b.is_dir():
        raise SystemExit(f"ERROR: `{slug}` exists in BOTH planning/roadmaps/ and planning/ — "
                         f"resolve the ambiguity before consolidating")
    if a.is_dir():
        return a
    if b.is_dir():
        return b
    return None


def discover_roadmaps(root: Path) -> list[str]:
    """Every roadmap directory holding a lane-log.jsonl, both layouts."""
    out = set()
    for base in (root / "planning" / "roadmaps", root / "planning"):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if d.is_dir() and (d / "lane-log.jsonl").is_file():
                out.add(d.name)
    return sorted(out)


def read_lines(path: Path) -> tuple[list[str], list[int]]:
    """Return (raw non-empty lines, 1-based indices of lines that do not parse as JSON).

    Blank lines are dropped and never counted as malformed -- a trailing newline is not a defect.
    Everything else that fails to parse is REPORTED, never dropped from the count, so a consumer
    cannot mistake lost data for absent data.
    """
    if not path.is_file():
        return [], []
    lines, bad = [], []
    for i, raw in enumerate(path.read_text(errors="replace").splitlines(), 1):
        s = raw.strip()
        if not s:
            continue
        lines.append(s)
        try:
            json.loads(s)
        except Exception:                          # noqa: BLE001 - report, never raise
            bad.append(i)
    return lines, bad


def resolve_watermark_path(root: Path, explicit: str | None) -> Path:
    """Resolve the `consolidation-watermark.json` path. Precedence: explicit `--watermark-dir`
    (the file lives directly inside it), else the default `<root>/WATERMARK_REL` location."""
    if explicit:
        return Path(explicit).resolve() / "consolidation-watermark.json"
    return root / WATERMARK_REL


def load_watermarks(root: Path, watermark_path: Path | None = None) -> dict:
    """Load the watermark file. `root` alone resolves to the default
    `<root>/WATERMARK_REL` location (back-compat with callers that predate the
    `--watermark-dir` seam); pass `watermark_path` to point at an explicitly-resolved
    location instead (what `main()` does after calling `resolve_watermark_path`)."""
    path = watermark_path if watermark_path is not None else root / WATERMARK_REL
    if not path.is_file():
        return {"version": SCHEMA_VERSION, "roadmaps": {}}
    try:
        data = json.loads(path.read_text())
    except Exception as exc:                       # noqa: BLE001
        raise SystemExit(f"ERROR: {path} does not parse: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("roadmaps"), dict):
        raise SystemExit(f"ERROR: {path} is not a watermark file (no `roadmaps` object)")
    return data


def save_watermarks(root: Path, data: dict, watermark_path: Path | None = None) -> Path:
    """Save the watermark file. Same `root`-alone-vs-explicit-`watermark_path` precedence
    as `load_watermarks`."""
    path = watermark_path if watermark_path is not None else root / WATERMARK_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return path


def state_for(root: Path, slug: str, marks: dict) -> dict:
    """Everything both the human report and the JSON report need, for one roadmap."""
    d = roadmap_dir(root, slug)
    if d is None:
        return {"roadmap": slug, "error": "no roadmap directory"}
    log = d / "lane-log.jsonl"
    lines, bad = read_lines(log)
    mark = marks["roadmaps"].get(slug) or {}
    at = int(mark.get("line") or 0)
    stored_hash = mark.get("last_line_sha256")

    drift = None
    if at > 0:
        if at > len(lines):
            drift = (f"watermark at line {at} but the log now has {len(lines)} — the file shrank; "
                     f"lane-log.jsonl is append-only, so this is an edit or a truncation")
        elif stored_hash and sha(lines[at - 1]) != stored_hash:
            drift = (f"line {at} no longer matches the recorded hash — the log was rewritten, so "
                     f"every line number after it points somewhere else")

    return {
        "roadmap": slug,
        "log": str(log.relative_to(root)),
        "total_lines": len(lines),
        "watermark_line": at,
        "new_lines": max(0, len(lines) - at) if drift is None else None,
        "malformed_lines": bad,
        "last_consolidated_at": mark.get("consolidated_at"),
        "last_run_id": mark.get("run_id"),
        "drift": drift,
    }


def selected(root: Path, wanted: list[str] | None) -> list[str]:
    return wanted if wanted else discover_roadmaps(root)


def cmd_status(root: Path, slugs, marks, as_json, strict) -> int:
    rows = [state_for(root, s, marks) for s in slugs]
    if as_json:
        print(json.dumps({"roadmaps": rows}, indent=2, ensure_ascii=False))
    else:
        for r in rows:
            if r.get("error"):
                print(f"{r['roadmap']:34} ERROR: {r['error']}")
                continue
            new = "DRIFTED" if r["drift"] else f"{r['new_lines']} new"
            print(f"{r['roadmap']:34} {r['watermark_line']:>4}/{r['total_lines']:<4} {new:>10}"
                  + (f"  last={r['last_consolidated_at']}" if r["last_consolidated_at"] else "  never consolidated"))
            if r["drift"]:
                print(f"    DRIFT: {r['drift']}")
            if r["malformed_lines"]:
                print(f"    MALFORMED lines (reported, not skipped): {r['malformed_lines']}")
    if any(r.get("drift") for r in rows):
        return 2
    if strict and any(r.get("malformed_lines") for r in rows):
        return 3
    return 0


def cmd_pending(root: Path, slugs, marks, as_json, strict) -> int:
    out, drifted, malformed = [], False, False
    for s in slugs:
        st = state_for(root, s, marks)
        if st.get("error"):
            continue
        if st["drift"]:
            drifted = True
            print(f"# {s}: DRIFT — {st['drift']}", file=sys.stderr)
            continue
        if st["malformed_lines"]:
            malformed = True
            print(f"# {s}: {len(st['malformed_lines'])} malformed line(s) at "
                  f"{st['malformed_lines']} — reported, not skipped", file=sys.stderr)
        d = roadmap_dir(root, s)
        lines, _ = read_lines(d / "lane-log.jsonl")
        for idx in range(st["watermark_line"], len(lines)):
            out.append({"roadmap": s, "line": idx + 1, "raw": lines[idx]})
    if as_json:
        print(json.dumps({"pending": out}, indent=2, ensure_ascii=False))
    else:
        for row in out:
            print(f"{row['roadmap']}:{row['line']}\t{row['raw']}")
    if drifted:
        return 2
    if strict and malformed:
        return 3
    return 0


def cmd_advance(root: Path, slug, to_line, run_id, marks, as_json, watermark_path: Path) -> int:
    st = state_for(root, slug, marks)
    if st.get("error"):
        print(f"ERROR: {slug}: {st['error']}", file=sys.stderr)
        return 1
    if st["drift"]:
        # Never silently re-base. A drifted mark means the line numbers no longer mean what the
        # watermark thinks; advancing over it would skip real run data and look like success.
        print(f"REFUSED: {slug} — {st['drift']}", file=sys.stderr)
        print("Resolve by hand: re-read the log, then advance with an explicit --to-line.",
              file=sys.stderr)
        return 2
    d = roadmap_dir(root, slug)
    lines, bad = read_lines(d / "lane-log.jsonl")
    target = len(lines) if to_line is None else int(to_line)
    if target < 0 or target > len(lines):
        print(f"ERROR: --to-line {target} out of range (log has {len(lines)} lines)", file=sys.stderr)
        return 1
    if target < st["watermark_line"]:
        print(f"ERROR: refusing to move {slug}'s watermark backwards "
              f"({st['watermark_line']} -> {target}); delete the entry by hand if that is intended",
              file=sys.stderr)
        return 1

    entry = {
        "line": target,
        "last_line_sha256": sha(lines[target - 1]) if target > 0 else None,
        "last_ts": (json.loads(lines[target - 1]).get("ts")
                    if target > 0 and target - 1 not in [b - 1 for b in bad] else None),
        "consolidated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
        "malformed_lines_at_advance": bad,
    }
    marks["roadmaps"][slug] = entry
    marks["version"] = SCHEMA_VERSION
    path = save_watermarks(root, marks, watermark_path)
    try:
        watermark_file = str(path.relative_to(root))
    except ValueError:
        watermark_file = str(path)
    result = {"roadmap": slug, "advanced_from": st["watermark_line"], "advanced_to": target,
              "consumed": target - st["watermark_line"], "watermark_file": watermark_file,
              "malformed_lines": bad}
    print(json.dumps(result, indent=2, ensure_ascii=False) if as_json
          else f"{slug}: {st['watermark_line']} -> {target} ({target - st['watermark_line']} lines consumed)"
               + (f"; malformed lines carried: {bad}" if bad else ""))
    return 0


def cmd_verify(root: Path, slugs, marks, as_json) -> int:
    rows = [state_for(root, s, marks) for s in slugs if (marks["roadmaps"].get(s))]
    bad = [r for r in rows if r.get("drift")]
    none_recorded = len(rows) == 0
    if as_json:
        print(json.dumps({"checked": len(rows), "drifted": bad, "none_recorded": none_recorded},
                          indent=2, ensure_ascii=False))
    else:
        for r in bad:
            print(f"DRIFT {r['roadmap']}: {r['drift']}")
        if none_recorded:
            # Distinct from "N checked, 0 drifted" below on purpose -- "no watermark exists yet"
            # and "we checked N and found nothing wrong" are different facts about the world.
            print("no watermarks recorded yet -- nothing to verify")
        else:
            print(f"{len(rows)} watermark(s) checked, {len(bad)} drifted")
    return 2 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verb", choices=["status", "pending", "advance", "verify"])
    ap.add_argument("--roadmap", action="append", dest="roadmaps")
    ap.add_argument("--to-line", type=int, default=None)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--root", default=None)
    ap.add_argument("--watermark-dir", default=None,
                    help="point directly at the directory holding consolidation-watermark.json, "
                         "overriding the default <root>/planning/open-work/orchestration-runs "
                         "location (--lock-dir / --roadmaps-dir convention)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 3 when any selected log has malformed lines")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else find_brain_root(Path.cwd())
    watermark_path = resolve_watermark_path(root, args.watermark_dir)
    marks = load_watermarks(root, watermark_path)

    if args.verb == "advance":
        if not args.roadmaps or len(args.roadmaps) != 1:
            print("ERROR: advance takes exactly one --roadmap", file=sys.stderr)
            return 1
        return cmd_advance(root, args.roadmaps[0], args.to_line, args.run_id, marks, args.json,
                            watermark_path)

    slugs = selected(root, args.roadmaps)
    if not slugs:
        print("no roadmaps with a lane-log.jsonl found (not a failure)")
        return 0
    if args.verb == "status":
        return cmd_status(root, slugs, marks, args.json, args.strict)
    if args.verb == "pending":
        return cmd_pending(root, slugs, marks, args.json, args.strict)
    return cmd_verify(root, slugs, marks, args.json)


if __name__ == "__main__":
    sys.exit(main())
