#!/usr/bin/env python3
"""Fixture suite for sdlc-flow.js's STEP 3a clean-tree guard
(BT.ticket.clean-tree-guard-blocks-hq-root).

WHY THIS EXISTS
----------------
STEP 3a of sdlc-flow.js's branch-mode setup runs a dirty-tree check from repoRoot and aborts the
run if it reports anything dirty. At the brain root, repoRoot IS the whole vault -- every
sub-repo's planning/ symlinks into HQ's own git index (_planning/<repo>/) -- so any sibling lane's
ordinary in-flight work makes this guard fire on dirt this block will never touch. D81 forbids the
--worktree escape hatch for HQ, so a lane hitting this bug has no way to run /sdlc-flow at all
while any sibling lane is live (escalated three times by agentic-portfolio-4a during the
2026-09-03/04 clean-slate-sandbox run; see the block record's `why` field).

This is a source-assertion-plus-execution suite, not a live-agent suite: the dirty-check snippet
is embedded inside sdlc-flow.js's LLM-facing prompt template as literal bash source (the agent
copies and runs it verbatim; the engine's own .js code never executes it). This suite EXTRACTS the
literal snippet text from sdlc-flow.js's live source (by content markers, `# CLEAN_TREE_GUARD_START`
/ `# CLEAN_TREE_GUARD_END` -- never a disposable hand-copy), substitutes the real `git` binary for
the `${GIT}` JS template-literal interpolation, and actually runs it as a subprocess against three
synthetic git-repo fixtures built with `git init` in a tmp dir. If the embedded snippet in
sdlc-flow.js drifts from what these fixtures exercise, extraction either fails outright (source
assertion) or the behavioural assertions fail against the drifted text -- either way this suite
goes red, which is the point.

TASK 1 (reproduction, superseded): the snippet was not yet scoped to exempt _planning/-only
dirt at the brain root -- it just ran `git status --porcelain` unconditionally, so all three
fixtures asserted DIRTY was non-empty, INCLUDING fixture 1 (brain-root, sibling-only dirt under
_planning/) -- the reproduction of the bug: a brain-root run with only sibling-repo _planning/
dirt was wrongly blocked.

TASK 2 (this state, the fix): STEP 3a now scopes DIRTY to
`git status --porcelain | grep -v '_planning/'` when brainTomlAtRoot is true, and leaves it as the
bare `git status --porcelain` when false. Fixture 1 now asserts DIRTY is EMPTY (the fix landing);
fixtures 2 and 3 are unchanged regression guards proving the fix is conditioned on brainTomlAtRoot
and confined to the _planning/ path, not a blanket brain-root or _planning/ exemption.

FIXTURES
--------
  1. brain-root simulation, dirt confined to a `_planning/` path only
     (e.g. `_planning/other-repo/state.json`) -- the sibling-lane-dirt case this ticket exists to
     unblock.
  2. brain-root simulation, dirt OUTSIDE any `_planning/` path (e.g. `docs/notes.md`) -- must
     still block; proves the fix does not become a blanket "brain root is never dirty" escape
     hatch.
  3. NON-brain-root (leaf repo) simulation, `_planning/`-shaped dirt -- must still block; proves
     the fix is conditioned on brainTomlAtRoot, not a blanket `_planning/` exemption anywhere.

Run: python3 scripts/test_clean_tree_guard_scoping.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_FILE = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"

START_MARKER = "# CLEAN_TREE_GUARD_START"
END_MARKER = "# CLEAN_TREE_GUARD_END"


def extract_clean_tree_guard_snippet() -> str:
    """Pull the literal STEP 3a dirty-check bash snippet out of sdlc-flow.js's live prompt text.

    Extraction is content-anchored (not a line number, not a hand-maintained copy) so this suite
    tests the SAME bytes the agent would actually run. The `${GIT}` JS template-literal
    interpolation (always resolved to the literal string "git" for this repo's engines -- see
    every other GIT-prefixed command in the same prompt) is substituted with "git" so the
    extracted text is directly executable bash.
    """
    if not ENGINE_FILE.exists():
        raise AssertionError(f"{ENGINE_FILE} does not exist")
    source = ENGINE_FILE.read_text(encoding="utf-8")

    start = source.find(START_MARKER)
    if start == -1:
        raise AssertionError(
            f"sdlc-flow.js: could not find the clean-tree guard snippet "
            f"(marker {START_MARKER!r} not present) -- has STEP 3a been rewritten without the "
            f"extraction markers?"
        )
    end_marker_pos = source.find(END_MARKER, start)
    if end_marker_pos == -1:
        raise AssertionError(
            f"sdlc-flow.js: found {START_MARKER!r} but not {END_MARKER!r} -- "
            f"the clean-tree guard snippet may have been truncated or rewritten."
        )
    end = end_marker_pos + len(END_MARKER)
    snippet = source[start:end]

    if "DIRTY=" not in snippet:
        raise AssertionError(
            "sdlc-flow.js: extracted clean-tree guard snippet is missing a DIRTY= assignment -- "
            "extraction markers matched the wrong region or the contract changed shape."
        )

    return snippet.replace("${GIT}", "git")


def _init_fixture_repo(root: Path, dirty_path: str) -> None:
    """Create a synthetic git repo at `root` with one committed file and one dirty (untracked)
    file at `dirty_path` relative to `root`."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)

    committed = root / "README.md"
    committed.write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)

    dirty_file = root / dirty_path
    dirty_file.parent.mkdir(parents=True, exist_ok=True)
    dirty_file.write_text("dirty\n", encoding="utf-8")


def run_guard_snippet(cwd: Path, brain_toml_at_root: bool) -> str:
    """Execute the extracted clean-tree guard snippet in `cwd` and return the resulting DIRTY
    variable's value (echoed by an appended `echo "$DIRTY"`).

    `brain_toml_at_root` simulates the GIVEN `brainTomlAtRoot` boolean the real engine already
    resolved before building this prompt text (STEP 1) -- the extracted snippet reads it from the
    `BRAIN_TOML_AT_ROOT` environment variable exactly as the live prompt exports it (via a line
    immediately outside the marked region, so it is not part of the extracted text itself).
    """
    snippet = extract_clean_tree_guard_snippet()
    script = f"#!/bin/sh\nset -e\n{snippet}\necho \"$DIRTY\"\n"
    env = dict(os.environ)
    env["BRAIN_TOML_AT_ROOT"] = "true" if brain_toml_at_root else "false"
    result = subprocess.run(
        ["/bin/sh", "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


class CleanTreeGuardScopingTests(unittest.TestCase):
    def test_extraction_succeeds_and_contains_git_status_porcelain(self) -> None:
        snippet = extract_clean_tree_guard_snippet()
        self.assertIn("git status --porcelain", snippet)
        self.assertNotIn("${GIT}", snippet)

    def test_fixture_1_brain_root_sibling_planning_dirt_only(self) -> None:
        """Brain-root simulation, dirt confined to a _planning/ path only.

        TASK 2 (post-fix) expectation: STEP 3a is now scoped by brainTomlAtRoot, so dirt confined
        to a _planning/ path at the brain root is exempted -- DIRTY must be empty here. This is
        the fix landing: a brain-root run with only sibling-repo _planning/ dirt is no longer
        wrongly blocked.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hq-root"
            _init_fixture_repo(root, "_planning/other-repo/state.json")
            dirty = run_guard_snippet(root, brain_toml_at_root=True)
            self.assertEqual(
                dirty,
                "",
                "fix check: dirt confined to a _planning/ path at the brain root must no longer "
                "trip the guard (fixture 1) -- if this is non-empty, the scoping fix did not "
                "land or regressed.",
            )

    def test_fixture_2_brain_root_dirt_outside_planning(self) -> None:
        """Brain-root simulation, dirt OUTSIDE any _planning/ path -- must always block."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hq-root"
            _init_fixture_repo(root, "docs/notes.md")
            dirty = run_guard_snippet(root, brain_toml_at_root=True)
            self.assertNotEqual(
                dirty,
                "",
                "dirt outside any _planning/ path must still trip the guard, at the brain root "
                "or anywhere else (fixture 2).",
            )

    def test_fixture_3_non_brain_root_planning_shaped_dirt(self) -> None:
        """Non-brain-root (leaf repo) simulation, _planning/-shaped dirt -- must always block.

        Regression guard proving the eventual fix is conditioned on brainTomlAtRoot, not a
        blanket _planning/ exemption applied everywhere.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "leaf-repo"
            _init_fixture_repo(root, "_planning/other-repo/state.json")
            dirty = run_guard_snippet(root, brain_toml_at_root=False)
            self.assertNotEqual(
                dirty,
                "",
                "_planning/-shaped dirt at a normal (non-brain-root) repo root must still trip "
                "the guard exactly as before (fixture 3).",
            )


if __name__ == "__main__":
    sys.exit(unittest.main())
