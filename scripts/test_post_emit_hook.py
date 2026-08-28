#!/usr/bin/env python3
"""Fixture suite for the OPTIONAL post-emit commit hook decision
(BT.ticket.bookkeep-leaves-derived-output-uncommitted, task 5).

WHY THIS EXISTS
----------------
Task 4 gave both surviving engines (sdlc-task.js's bookkeep stage, sdlc-flow.js's wrap-up stage)
an OPTIONAL post-emit commit hook: after `mev emit-state --write` runs, invoke
`planning/harness.json`'s `postEmitCommitCommand` if and only if it is configured AND
`emitStateRan` is true. `emitStateRan` is itself only ever true on an in-place run where `mev` and
brain.toml are present -- it is unconditionally false in worktree mode (measured in the block
record) and false when `mev`/brain.toml are absent. Absent key -> unchanged, no-default behaviour.

Both engines express this as PROSE inside an LLM-facing prompt template, not as a JS function this
repo's own `.js` executes -- so there is nothing importable to unit-test the way a real Python
module would be. This suite therefore does two things:

1. SOURCE ASSERTIONS -- extracts the literal `postEmitCommitCommand` computation from each engine's
   live source (by content marker, never a hand-copy) and asserts the two are byte-identical, plus
   asserts the surrounding prompt text still gates the hook on step/stage's own emitStateRan=true
   and still names worktree mode as a skip condition. Drift here means the engines disagree or the
   gating prose was weakened.
2. A PYTHON MIRROR of the decision rule (`decide_hook`), executed for real against a SHIMMED hook
   command (a local marker-file script, never `commit_routine_updates.sh` or any real committer) so
   the invoke/no-invoke/failure paths are exercised as actual subprocess calls, not merely asserted
   in the abstract. A green result here does NOT prove a live /sdlc-task or /sdlc-flow run invokes
   the hook correctly end to end (D64: the engine runs under the Workflow runtime, driven by an LLM
   agent, which this repo cannot execute headless) -- it proves the mirrored rule is self-consistent
   and matches what the engine source currently instructs.

REQUIRED CASES:
  1. Key present + in-place run -> hook invoked exactly once.
  2. Key absent -> no invocation, identical to pre-hook behaviour (postEmitHookRan=False).
  3. Worktree mode -> never invoked regardless of the key being present.
  4. Hook exits non-zero -> surfaced (postEmitHookFailed=True, stderr captured), never swallowed.

Run: python3 scripts/test_post_emit_hook.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".claude" / "workflows"

ENGINE_FILES = ["sdlc-task.js", "sdlc-flow.js"]

COMPUTATION_START = "const postEmitCommitCommand = typeof harnessCfg?.postEmitCommitCommand"
COMPUTATION_END = ": ''"


def extract_computation(engine_filename: str) -> str:
    """Pull the literal `postEmitCommitCommand` computation out of an engine's live source.

    Content-anchored (not a line number, not a hand-maintained copy) so a drift in either engine's
    gating logic makes extraction fail loudly, or makes the byte-identity assertion below fail,
    rather than silently comparing stale text.
    """
    path = WORKFLOWS / engine_filename
    source = path.read_text(encoding="utf-8")
    start = source.find(COMPUTATION_START)
    if start == -1:
        raise AssertionError(
            f"{engine_filename}: could not find the postEmitCommitCommand computation "
            f"(marker {COMPUTATION_START!r} not present) -- has task 4's hook decision been "
            f"removed or rewritten?"
        )
    end_marker_pos = source.find(COMPUTATION_END, start)
    if end_marker_pos == -1:
        raise AssertionError(
            f"{engine_filename}: found the computation start but not its end ({COMPUTATION_END!r})"
            f" -- the snippet may have been truncated or rewritten."
        )
    end = end_marker_pos + len(COMPUTATION_END)
    return source[start:end]


class SourceAssertions(unittest.TestCase):
    """Asserts both engines still gate the hook the way task 4 landed it."""

    def test_both_engines_define_the_computation(self) -> None:
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                snippet = extract_computation(engine)
                self.assertIn("harnessCfg?.postEmitCommitCommand", snippet)
                self.assertIn(".trim()", snippet)

    def test_computation_is_byte_identical_across_engines(self) -> None:
        snippets = {engine: extract_computation(engine) for engine in ENGINE_FILES}
        first_engine, first_snippet = next(iter(snippets.items()))
        for engine, snippet in snippets.items():
            with self.subTest(engine=engine):
                self.assertEqual(
                    snippet,
                    first_snippet,
                    f"{engine}'s postEmitCommitCommand computation diverges from "
                    f"{first_engine}'s -- the two engines must agree on this rule.",
                )

    def test_prompt_gates_hook_on_emit_state_ran(self) -> None:
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                source = (WORKFLOWS / engine).read_text(encoding="utf-8")
                self.assertIn("run it ONLY when", source)
                self.assertIn("emitStateRan=true", source)
                self.assertIn("postEmitHookRan=false", source)
                self.assertIn("postEmitHookFailed=false", source)

    def test_prompt_names_worktree_as_a_skip_condition(self) -> None:
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                source = (WORKFLOWS / engine).read_text(encoding="utf-8")
                self.assertIn("never in worktree mode", source)

    def test_prompt_never_swallows_a_hook_failure(self) -> None:
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                source = (WORKFLOWS / engine).read_text(encoding="utf-8")
                self.assertIn("never swallowed", source)


# ----------------------------------------------------------------------------------------------
# Python mirror of the decision rule, executed against a real (shimmed) subprocess.
# ----------------------------------------------------------------------------------------------


def decide_hook(
    harness_cfg: dict,
    *,
    use_worktree: bool,
    mev_available: bool = True,
) -> dict:
    """Mirrors both engines' step-5/2d decision: invoke the configured hook iff a non-blank
    `postEmitCommitCommand` is present AND `emitStateRan` is true. `emitStateRan` is itself false
    whenever `use_worktree` is true or `mev` is unavailable -- this mirrors the upstream
    `emit-state --write` gate (task 4's own dependency), never a second independent worktree check.
    """
    raw = harness_cfg.get("postEmitCommitCommand")
    command = raw.strip() if isinstance(raw, str) else ""
    emit_state_ran = (not use_worktree) and mev_available

    if not command or not emit_state_ran:
        return {"postEmitHookRan": False, "postEmitHookFailed": False, "invoked": False}

    proc = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=REPO_ROOT
    )
    failed = proc.returncode != 0
    return {
        "postEmitHookRan": True,
        "postEmitHookFailed": failed,
        "invoked": True,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


class DecisionMirror(unittest.TestCase):
    """Cases 1-4 from the module docstring. The hook command is always a local shim -- never
    `commit_routine_updates.sh` or any real committer -- so nothing is ever actually committed."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.marker = Path(self._tmpdir.name) / "hook-invoked.marker"

    def _touch_command(self) -> str:
        # Shimmed hook: appends one line to a marker file. Never touches git, never commits.
        return f"echo invoked >> {self.marker}"

    def _invocation_count(self) -> int:
        if not self.marker.exists():
            return 0
        return len(self.marker.read_text().splitlines())

    def test_case1_key_present_in_place_invokes_once(self) -> None:
        result = decide_hook(
            {"postEmitCommitCommand": self._touch_command()}, use_worktree=False
        )
        self.assertTrue(result["invoked"])
        self.assertTrue(result["postEmitHookRan"])
        self.assertFalse(result["postEmitHookFailed"])
        self.assertEqual(self._invocation_count(), 1)

    def test_case2_key_absent_no_invocation(self) -> None:
        result = decide_hook({}, use_worktree=False)
        self.assertFalse(result["invoked"])
        self.assertFalse(result["postEmitHookRan"])
        self.assertFalse(result["postEmitHookFailed"])
        self.assertEqual(self._invocation_count(), 0)

    def test_case2b_key_blank_string_treated_as_absent(self) -> None:
        result = decide_hook({"postEmitCommitCommand": "   "}, use_worktree=False)
        self.assertFalse(result["invoked"])
        self.assertEqual(self._invocation_count(), 0)

    def test_case3_worktree_mode_never_invoked_even_with_key_present(self) -> None:
        result = decide_hook(
            {"postEmitCommitCommand": self._touch_command()}, use_worktree=True
        )
        self.assertFalse(result["invoked"])
        self.assertFalse(result["postEmitHookRan"])
        self.assertFalse(result["postEmitHookFailed"])
        self.assertEqual(self._invocation_count(), 0)

    def test_case3b_mev_absent_never_invoked_even_with_key_present(self) -> None:
        # emitStateRan is also false when mev/brain.toml are absent -- not just worktree mode.
        result = decide_hook(
            {"postEmitCommitCommand": self._touch_command()},
            use_worktree=False,
            mev_available=False,
        )
        self.assertFalse(result["invoked"])
        self.assertEqual(self._invocation_count(), 0)

    def test_case4_hook_failure_is_surfaced_not_swallowed(self) -> None:
        failing_command = f"{self._touch_command()}; echo boom 1>&2; exit 7"
        result = decide_hook({"postEmitCommitCommand": failing_command}, use_worktree=False)
        self.assertTrue(result["invoked"])
        self.assertTrue(result["postEmitHookRan"])
        self.assertTrue(result["postEmitHookFailed"])
        self.assertEqual(result["returncode"], 7)
        self.assertIn("boom", result["stderr"])
        # The hook DID still run (the marker exists) -- failure is reported, not hidden by
        # pretending the invocation never happened.
        self.assertEqual(self._invocation_count(), 1)

    def test_case4b_worktree_mode_beats_a_failing_command(self) -> None:
        # Even a command that would fail must never be invoked in worktree mode -- the gate is
        # checked before the command ever runs.
        failing_command = f"{self._touch_command()}; exit 1"
        result = decide_hook(
            {"postEmitCommitCommand": failing_command}, use_worktree=True
        )
        self.assertFalse(result["invoked"])
        self.assertEqual(self._invocation_count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
