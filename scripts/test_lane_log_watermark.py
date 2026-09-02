#!/usr/bin/env python3
"""Fixtures over lane_log_watermark.py.

The cursor is a LINE NUMBER, which is only valid while lane-log.jsonl is append-only. Every case
here exists because the failure mode of a broken cursor is silence: it resumes at the wrong place
and the consolidation reports a clean run over data it never read. So the drift cases assert a
REFUSAL, not a repair.

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


def check(label, cond, detail=""):
    if cond:
        print(f"[PASS] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}" + (f" -- {detail}" if detail else ""))


def row(ts, block, note="n"):
    return json.dumps({"ts": ts, "lane": "l", "repo": "r", "block": block,
                       "status": "closed", "note": note})


def build(tmp: Path, lines, slug="rm", legacy=False, also_legacy=False) -> Path:
    (tmp / "brain.toml").write_text("# brain.toml\n")
    base = tmp / "planning" / (slug if legacy else f"roadmaps/{slug}")
    base.mkdir(parents=True, exist_ok=True)
    (base / "lane-log.jsonl").write_text("".join(l + "\n" for l in lines))
    if also_legacy:
        alt = tmp / "planning" / slug
        alt.mkdir(parents=True, exist_ok=True)
        (alt / "lane-log.jsonl").write_text("")
    return tmp


def run_cli(root: Path, *args):
    return subprocess.run([sys.executable, str(MODULE), *args, "--root", str(root)],
                          capture_output=True, text=True)


def main() -> int:
    three = [row("2026-09-01T01:00:00Z", "A"), row("2026-09-01T02:00:00Z", "B"),
             row("2026-09-02T03:00:00-03:00", "C")]

    # --- the happy path: advance, then only new lines are pending -------------------------
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three)
        r = run_cli(root, "advance", "--roadmap", "rm", "--run-id", "run-1")
        check("advance consumes the whole log by default", r.returncode == 0, r.stderr)
        st = wm.state_for(root, "rm", wm.load_watermarks(root))
        check("watermark lands on the last line", st["watermark_line"] == 3, str(st))
        check("nothing is pending straight after an advance", st["new_lines"] == 0, str(st))

        # append two more, exactly as a later run would
        log = root / "planning" / "roadmaps" / "rm" / "lane-log.jsonl"
        with log.open("a") as fh:
            fh.write(row("2026-09-03T01:00:00Z", "D") + "\n")
            fh.write(row("2026-09-03T02:00:00Z", "E") + "\n")
        st = wm.state_for(root, "rm", wm.load_watermarks(root))
        check("appended lines show as new", st["new_lines"] == 2, str(st))
        p = run_cli(root, "pending", "--roadmap", "rm", "--json")
        pend = json.loads(p.stdout)["pending"]
        check("pending returns ONLY the unread lines", [x["line"] for x in pend] == [4, 5],
              p.stdout[:200])
        check("pending carries the raw line for the consumer", '"block": "D"' in pend[0]["raw"],
              pend[0]["raw"])

    # --- the whole reason for the hash: a rewritten log ------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three)
        run_cli(root, "advance", "--roadmap", "rm")
        log = root / "planning" / "roadmaps" / "rm" / "lane-log.jsonl"
        edited = three[:2] + [row("2026-09-02T03:00:00-03:00", "C", note="EDITED")]
        log.write_text("".join(l + "\n" for l in edited))
        st = wm.state_for(root, "rm", wm.load_watermarks(root))
        check("a rewritten line is detected as drift", st["drift"] is not None, str(st))
        check("drift suppresses the new-line count rather than guessing",
              st["new_lines"] is None, str(st))
        r = run_cli(root, "advance", "--roadmap", "rm")
        check("advance REFUSES over a drifted watermark", r.returncode == 2, r.stdout + r.stderr)
        check("the refusal says why", "rewritten" in r.stderr, r.stderr)
        v = run_cli(root, "verify", "--roadmap", "rm")
        check("verify exits 2 on drift", v.returncode == 2, v.stdout + v.stderr)

    # --- truncation: the log shrank ---------------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three)
        run_cli(root, "advance", "--roadmap", "rm")
        log = root / "planning" / "roadmaps" / "rm" / "lane-log.jsonl"
        log.write_text(three[0] + "\n")
        st = wm.state_for(root, "rm", wm.load_watermarks(root))
        check("a shrunk log is drift, not a fresh start", st["drift"] is not None, str(st))
        check("the shrink message names append-only", "append-only" in st["drift"], st["drift"])

    # --- malformed lines are REPORTED, never dropped ---------------------------------------
    with tempfile.TemporaryDirectory() as td:
        # mirrors the real corpus: demand-ready carries 9 lines truncated mid-note
        truncated = three[0][:40]
        root = build(Path(td), [three[0], truncated, three[1]])
        st = wm.state_for(root, "rm", wm.load_watermarks(root))
        check("a malformed line still counts toward total_lines", st["total_lines"] == 3, str(st))
        check("the malformed line is named by index", st["malformed_lines"] == [2], str(st))
        s = run_cli(root, "status", "--roadmap", "rm")
        check("status prints malformed lines", "MALFORMED" in s.stdout, s.stdout)
        check("malformed alone is not a failure exit", s.returncode == 0, s.stdout)
        strict = run_cli(root, "status", "--roadmap", "rm", "--strict")
        check("--strict turns malformed into exit 3", strict.returncode == 3, strict.stdout)
        p = run_cli(root, "pending", "--roadmap", "rm", "--json")
        pend = json.loads(p.stdout)["pending"]
        check("pending still EMITS the malformed line (never silently skipped)",
              len(pend) == 3, p.stdout[:300])
        check("pending warns about it on stderr", "malformed" in p.stderr, p.stderr)

    # --- refusing to go backwards -----------------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three)
        run_cli(root, "advance", "--roadmap", "rm")
        r = run_cli(root, "advance", "--roadmap", "rm", "--to-line", "1")
        check("advance refuses to move a watermark backwards", r.returncode == 1, r.stdout)
        r = run_cli(root, "advance", "--roadmap", "rm", "--to-line", "99")
        check("advance refuses an out-of-range --to-line", r.returncode == 1, r.stdout)

    # --- partial advance, for a run that consumed only part of a log ------------------------
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three)
        r = run_cli(root, "advance", "--roadmap", "rm", "--to-line", "2", "--json")
        check("a partial advance is allowed", r.returncode == 0, r.stderr)
        st = wm.state_for(root, "rm", wm.load_watermarks(root))
        check("a partial advance leaves the rest pending", st["new_lines"] == 1, str(st))

    # --- layout resolution ------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three, legacy=True)
        st = wm.state_for(root, "rm", wm.load_watermarks(root))
        check("the legacy planning/<slug>/ layout resolves", st["total_lines"] == 3, str(st))
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three, also_legacy=True)
        try:
            wm.state_for(root, "rm", wm.load_watermarks(root))
            check("both layouts present is an error", False, "no SystemExit raised")
        except SystemExit as exc:
            check("both layouts present is an error", "BOTH" in str(exc), str(exc))

    # --- discovery and the empty case -------------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three)
        build(root, [row("2026-09-01T01:00:00Z", "Z")], slug="other")
        check("discovery finds every roadmap with a lane log",
              wm.discover_roadmaps(root) == ["other", "rm"], str(wm.discover_roadmaps(root)))
        r = run_cli(root, "status")
        check("status with no --roadmap covers all of them",
              "rm" in r.stdout and "other" in r.stdout, r.stdout)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "brain.toml").write_text("# brain.toml\n")
        r = run_cli(root, "status")
        check("a corpus with no lane logs is not a failure", r.returncode == 0, r.stdout)

    # --- the watermark file itself ----------------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), three)
        run_cli(root, "advance", "--roadmap", "rm", "--run-id", "run-7")
        data = json.loads((root / wm.WATERMARK_REL).read_text())
        e = data["roadmaps"]["rm"]
        check("the watermark records the run id", e["run_id"] == "run-7", str(e))
        check("the watermark records a hash, not just a line",
              e["last_line_sha256"] == wm.sha(three[2]), str(e))
        check("the watermark carries last_ts for humans", e["last_ts"] is not None, str(e))
        check("verify passes on an untouched log", run_cli(root, "verify").returncode == 0)

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- lane_log_watermark.py holds against the fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
