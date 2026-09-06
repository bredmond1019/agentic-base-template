#!/usr/bin/env python3
"""Fixture-driven test suite for `scripts/check_engine_syntax.py`.

Covers the exact regression this checker exists to close: `node --check`
exits 0 on a syntax error placed AFTER the first top-level `export` in this
fleet's Node (v26). Every fixture is written to a temp directory (never under
`planning/`) and passed to the checker as an explicit path argument.

Cases:
  1. Positive control -- an unmodified copy of each real engine parses clean.
     Proves the suite can see a passing case (not vacuously green).
  2. Negative control (the case this block exists for) -- a copy of
     sdlc-task.js with a known-bad construct appended AFTER the first
     top-level export must be rejected by the checker.
  3. Pre-export break -- the identical bad construct inserted at line 2,
     before any export, must also be rejected, proving the checker did not
     merely get stricter in one spot.
  4. Regression guard -- the post-export fixture must be a case where
     `node --check` itself is fooled (exits 0), so the suite proves this
     checker is not simply `node --check` under another name. Skipped
     gracefully if `node` is unavailable.

Exits 0 if every case passes; exits 1 and prints a one-line-per-case
pass/fail summary otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_engine_syntax.py"

ENGINES = [
    ".claude/workflows/sdlc-task.js",
    ".claude/workflows/sdlc-flow.js",
]

BOGUS = "const __bogus = (;"


def run_checker(*paths: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
    )


def run_node_check(path: Path) -> subprocess.CompletedProcess | None:
    node = shutil.which("node")
    if node is None:
        return None
    return subprocess.run(
        [node, "--check", str(path)],
        capture_output=True,
        text=True,
    )


def append_after_first_export(src: str, bad: str) -> str:
    """Insert `bad` on the line immediately after the first top-level export."""
    lines = src.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("export "):
            lines.insert(i + 1, bad + "\n")
            return "".join(lines)
    raise AssertionError("no top-level export found in fixture source")


def insert_before_export(src: str, bad: str) -> str:
    """Insert `bad` at line 2, before any export."""
    lines = src.splitlines(keepends=True)
    lines.insert(1, bad + "\n")
    return "".join(lines)


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    tmp = Path(tempfile.mkdtemp(prefix="check_engine_syntax_test_"))
    try:
        # --- Case 1: positive control -- unmodified engines parse clean ---
        clean_copies = []
        for rel in ENGINES:
            src = (REPO_ROOT / rel).read_text()
            dest = tmp / Path(rel).name
            dest.write_text(src)
            clean_copies.append(dest)

        proc = run_checker(*clean_copies)
        ok = proc.returncode == 0
        results.append(("positive control: unmodified engines parse clean", ok, proc.stderr.strip()))

        # --- Fixture source: sdlc-task.js ---
        task_src = (REPO_ROOT / ".claude/workflows/sdlc-task.js").read_text()

        # --- Case 2: negative control -- break AFTER first top-level export ---
        post_export_src = append_after_first_export(task_src, BOGUS)
        post_export_path = tmp / "sdlc-task.post-export-break.js"
        post_export_path.write_text(post_export_src)

        proc = run_checker(post_export_path)
        ok = proc.returncode != 0
        results.append((
            "negative control: post-export break is detected",
            ok,
            f"expected non-zero exit, got {proc.returncode}; stderr={proc.stderr.strip()}",
        ))

        # --- Case 3: pre-export break is also detected ---
        pre_export_src = insert_before_export(task_src, BOGUS)
        pre_export_path = tmp / "sdlc-task.pre-export-break.js"
        pre_export_path.write_text(pre_export_src)

        proc = run_checker(pre_export_path)
        ok = proc.returncode != 0
        results.append((
            "pre-export break is also detected",
            ok,
            f"expected non-zero exit, got {proc.returncode}; stderr={proc.stderr.strip()}",
        ))

        # --- Case 4: regression guard -- this checker is not `node --check` ---
        node_proc = run_node_check(post_export_path)
        if node_proc is None:
            results.append(("regression guard: checker != node --check (SKIPPED, node unavailable)", True, ""))
        else:
            node_fooled = node_proc.returncode == 0
            results.append((
                "regression guard: node --check is fooled by the post-export fixture",
                node_fooled,
                f"expected node --check to exit 0 on the fixture (proving it's blind), got {node_proc.returncode}",
            ))

        all_ok = True
        for name, ok, detail in results:
            status = "PASS" if ok else "FAIL"
            line = f"[{status}] {name}"
            if not ok and detail:
                line += f" -- {detail}"
            print(line)
            if not ok:
                all_ok = False

        return 0 if all_ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
