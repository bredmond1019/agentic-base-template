#!/usr/bin/env python3
"""Fixture suite for roadmap-directory resolution (pre-plan residue vs a legacy roadmap).

WHAT THIS PINS
--------------
`scripts/lane_log_watermark.py`'s `roadmap_dir()` prefers `planning/roadmaps/<slug>/` and falls
back to the legacy `planning/<slug>/`. A slug present in BOTH used to be an unconditional error.
That was wrong, and wrong in the way this fleet keeps rediscovering: the rule's true-positive
population was empty while it fired constantly on normal operation.

`/assess`, `/seams` and `/sequence` all write to `planning/<slug>/`, and which successor consumes
them is unknown until `/sequence` counts the repos in its cut -- one repo goes to `/plan`, which
authors into that same directory, several go to `/generate-roadmap`, which writes
`planning/roadmaps/<slug>/`. So on the multi-repo path the slug ends up in both places every time,
by design. Measured 2026-09-03: 0 of 31 roadmap directories and 0 directories under `planning/`
carried a `lane-log.jsonl` or `roadmap.md`, so the unnarrowed rule caught nothing real and hard-
exited `lane_log_watermark.py`, wedging every consolidation in the fleet (observed on
`clean-slate-sandbox`, then immediately on `coordination-layer-port` once that was resolved).

The narrowed rule: a `planning/<slug>/` is a legacy ROADMAP only if it holds `lane-log.jsonl` or
`roadmap.md`. Anything else is pre-plan residue and resolution proceeds silently.

Both directions are asserted here. The negative direction is the one that matters -- a rule that
only ever passes is the failure this roadmap (`runs-that-can-be-believed`) exists to stop -- so the
legacy-roadmap cases must be shown to STILL error.

Run: python3 scripts/test_roadmap_dir_resolution.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "lane_log_watermark.py"

_spec = importlib.util.spec_from_file_location("lane_log_watermark", MODULE_PATH)
lane_log_watermark = importlib.util.module_from_spec(_spec)
sys.modules["lane_log_watermark"] = lane_log_watermark
_spec.loader.exec_module(lane_log_watermark)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def build(tmp: Path, *, roadmaps: bool, legacy_files: list[str]) -> Path:
    """A throwaway brain root. Never the real corpus."""
    root = tmp
    if roadmaps:
        d = root / "planning" / "roadmaps" / "probe"
        d.mkdir(parents=True, exist_ok=True)
        (d / "lane-log.jsonl").write_text("{}\n", encoding="utf-8")
    if legacy_files:
        d = root / "planning" / "probe"
        d.mkdir(parents=True, exist_ok=True)
        for name in legacy_files:
            (d / name).write_text("---\ntype: Reference\n---\n", encoding="utf-8")
    return root


def resolve(root: Path):
    """Return ('ok', path) or ('error', message)."""
    try:
        return "ok", lane_log_watermark.roadmap_dir(root, "probe")
    except SystemExit as exc:  # the module signals ambiguity by SystemExit
        return "error", str(exc)


def main() -> int:
    # --- is_roadmap_dir, the discriminator itself -------------------------------------------
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "d"
        d.mkdir()
        check("is_roadmap_dir: empty dir is NOT a roadmap",
              lane_log_watermark.is_roadmap_dir(d) is False)
        (d / "sequence.md").write_text("x", encoding="utf-8")
        (d / "assessment.md").write_text("x", encoding="utf-8")
        check("is_roadmap_dir: pre-plan artifacts are NOT a roadmap",
              lane_log_watermark.is_roadmap_dir(d) is False,
              "sequence.md/assessment.md must not read as a roadmap")
        (d / "lane-log.jsonl").write_text("{}", encoding="utf-8")
        check("is_roadmap_dir: lane-log.jsonl IS a roadmap",
              lane_log_watermark.is_roadmap_dir(d) is True)
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "d"
        d.mkdir()
        (d / "roadmap.md").write_text("x", encoding="utf-8")
        check("is_roadmap_dir: roadmap.md alone IS a roadmap",
              lane_log_watermark.is_roadmap_dir(d) is True)

    # --- resolution: residue must NOT error ------------------------------------------------
    with tempfile.TemporaryDirectory() as t:
        root = build(Path(t), roadmaps=True,
                     legacy_files=["assessment.md", "verification.md", "seams.md", "sequence.md"])
        kind, val = resolve(root)
        check("both present, legacy is PRE-PLAN RESIDUE -> resolves silently", kind == "ok",
              f"got {kind}: {val}")
        check("  ... and resolves to planning/roadmaps/, not the legacy path",
              kind == "ok" and val is not None and "roadmaps" in str(val), f"got {val}")

    # --- resolution: a real legacy roadmap must STILL error (the negative direction) -------
    with tempfile.TemporaryDirectory() as t:
        root = build(Path(t), roadmaps=True, legacy_files=["lane-log.jsonl"])
        kind, val = resolve(root)
        check("both present, legacy holds lane-log.jsonl -> STILL an error", kind == "error",
              f"got {kind}: {val}")
    with tempfile.TemporaryDirectory() as t:
        root = build(Path(t), roadmaps=True, legacy_files=["roadmap.md"])
        kind, val = resolve(root)
        check("both present, legacy holds roadmap.md -> STILL an error", kind == "error",
              f"got {kind}: {val}")

    # --- resolution: the single-location cases are unchanged --------------------------------
    with tempfile.TemporaryDirectory() as t:
        root = build(Path(t), roadmaps=True, legacy_files=[])
        kind, val = resolve(root)
        check("only planning/roadmaps/ present -> resolves there",
              kind == "ok" and val is not None and "roadmaps" in str(val), f"got {kind}: {val}")
    with tempfile.TemporaryDirectory() as t:
        root = build(Path(t), roadmaps=False, legacy_files=["lane-log.jsonl"])
        kind, val = resolve(root)
        check("only legacy planning/<slug>/ present -> resolves there (back-compat)",
              kind == "ok" and val is not None and "roadmaps" not in str(val), f"got {kind}: {val}")
    with tempfile.TemporaryDirectory() as t:
        root = build(Path(t), roadmaps=False, legacy_files=[])
        kind, val = resolve(root)
        check("neither present -> None", kind == "ok" and val is None, f"got {kind}: {val}")

    if FAILURES:
        print(f"\nFAIL {MODULE_PATH.relative_to(REPO_ROOT)} "
              f"{len(FAILURES)} case(s) failed: {', '.join(FAILURES)}")
        return 1
    print("\nall cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
