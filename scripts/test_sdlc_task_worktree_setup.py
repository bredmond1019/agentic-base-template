#!/usr/bin/env python3
"""Fixture suite for BT.ticket.sdlc-task-worktree-flag-is-intermittently-ignored, task 3.

Exercises the setup stage's DETERMINISTIC worktree decision logic in `.claude/workflows/
sdlc-task.js` -- the `parseWorktreeListPorcelain()` function and the WORKTREE FAIL-CLOSED GUARD
block that follows it (tasks 1-2 of this same ticket) -- against real, disposable git repos and a
real `git worktree add` / `git worktree list --porcelain`. Never re-implements that logic in
Python: both pieces are extracted from the engine SOURCE verbatim (regex + brace matching, the
same technique `scripts/test_commit_safety_guard.py` uses for `renderCommitSafetyGuard()`), spliced
into a small node harness, and executed via `node -e`. A future edit to either piece is exercised
here automatically; a Python re-implementation would silently drift from it instead.

The setup STAGE itself is an LLM agent turn (locating a free branch name, running `git worktree
add`) and cannot be executed by this suite (D64: no way to invoke the model from a fixture). What
IS executed for real is everything downstream of that agent's self-report: a genuine `git worktree
add` builds the fixture worktree, a genuine `git worktree list --porcelain` produces the ground
truth, and the engine's own extracted decision code is what judges the self-report against it --
exactly the code path the real setup agent's StructuredOutput feeds into.

Three cases:
  1. slug == block id shape (e.g. "BT.ticket.foo") -- real worktree created, decision must report
     ok with runDir/branchName matching `git worktree list --porcelain` (parsed independently in
     Python as a cross-check on the extracted-JS parse, never the same code twice).
  2. slug != block id shape (e.g. "BA.ticket.live-run-workflow-type", the exact shape from the
     retired carryover this ticket preserves evidence of) -- same assertions, different block id
     shape, so the worktree-branch derivation is exercised against both forms.
  3. Forced creation-failure control: setupResult.worktreeFailed=true, as the setup agent reports
     when it cannot resolve a free branch name or `git worktree add` errors. Decision must bail
     (an `error` key), never fall back to mode:"worktree" against the main tree -- the exact
     regression this ticket exists to close (measured 2026-08-20, BA.ticket.live-run-workflow-type
     silently committing onto main).

Operates ONLY on throwaway fixture repos under a temp dir; never touches this repo's own working
tree or its `trees/` directory.

Registered in planning/harness.json as `sdlc-task-worktree-setup-tests` --
run directly: python3 scripts/test_sdlc_task_worktree_setup.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_FILE = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"

PARSE_FN_START_RE = re.compile(r"^function parseWorktreeListPorcelain\(porcelain\) \{", re.MULTILINE)
GUARD_START_RE = re.compile(r"^let \{ runDir, branchName \} = setupResult$", re.MULTILINE)
GUARD_END_RE = re.compile(r"\nstate\.branch = branchName")


def _extract_braced_block(text: str, start: int) -> str:
    """Return text[start:end] where end is just past the brace matching the first '{' at/after start."""
    open_idx = text.index("{", start)
    depth = 0
    i = open_idx
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise AssertionError("unbalanced braces while extracting block")


def extract_parse_fn(text: str) -> str:
    m = PARSE_FN_START_RE.search(text)
    if not m:
        raise AssertionError("parseWorktreeListPorcelain() definition not found in sdlc-task.js")
    return _extract_braced_block(text, m.start())


def extract_guard_block(text: str) -> str:
    start_m = GUARD_START_RE.search(text)
    end_m = GUARD_END_RE.search(text)
    if not start_m:
        raise AssertionError("WORKTREE FAIL-CLOSED GUARD start sentinel not found in sdlc-task.js")
    if not end_m or end_m.start() < start_m.start():
        raise AssertionError("WORKTREE FAIL-CLOSED GUARD end sentinel not found after its start in sdlc-task.js")
    return text[start_m.start():end_m.start()]


def build_harness(engine_text: str) -> str:
    """Wraps the extracted parse fn + guard block in a callable node function.

    `decide(useWorktree, repoRoot, blockId, setupResult)` mirrors exactly what the real engine
    does with the setup agent's StructuredOutput between `const setupResult = await tracedAgent(...)`
    and `state.branch = branchName`: either an early `return { error, reason, blockId }` (a bail),
    or falling through to report the (possibly re-assigned-from-ground-truth) runDir/branchName.
    """
    parse_fn = extract_parse_fn(engine_text)
    guard_block = extract_guard_block(engine_text)
    return f"""
{parse_fn}

function decide(useWorktree, repoRoot, blockId, setupResult) {{
  function log() {{}}
{guard_block}
  return {{ ok: true, runDir, branchName, baseSha }}
}}

const [useWorktreeArg, repoRootArg, blockIdArg, setupResultArg] = JSON.parse(
  require('fs').readFileSync(0, 'utf8')
)
process.stdout.write(JSON.stringify(decide(useWorktreeArg, repoRootArg, blockIdArg, setupResultArg)))
"""


def run(cmd, cwd=None, check=True, env=None):
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=check, env=env,
    )


def parse_porcelain_python(porcelain: str):
    """Independent Python re-parse of `git worktree list --porcelain`, used only as a
    cross-check on the extracted JS parser's own output -- never fed into decide() itself."""
    entries = []
    for block in re.split(r"\r?\n\r?\n", porcelain or ""):
        lines = block.splitlines()
        wt_line = next((l for l in lines if l.startswith("worktree ")), None)
        if not wt_line:
            continue
        path = wt_line[len("worktree "):].strip()
        branch_line = next((l for l in lines if l.startswith("branch ")), None)
        branch = None
        if branch_line:
            branch = branch_line[len("branch "):].strip()
            branch = re.sub(r"^refs/heads/", "", branch)
        entries.append({"path": path, "branch": branch})
    return entries


class WorktreeSetupFixture:
    """One disposable fixture repo with a real worktree created for it."""

    def __init__(self, tmp_root: Path, block_id: str):
        self.block_id = block_id
        self.repo = tmp_root / "repo"
        self.repo.mkdir(parents=True)
        run(["git", "init", "-q", "-b", "main"], cwd=self.repo)
        run(["git", "config", "user.email", "fixture@example.com"], cwd=self.repo)
        run(["git", "config", "user.name", "fixture"], cwd=self.repo)
        (self.repo / "README.md").write_text("fixture\n")
        run(["git", "add", "README.md"], cwd=self.repo)
        run(["git", "commit", "-q", "-m", "init"], cwd=self.repo)

        self.current_branch = run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.repo
        ).stdout.strip()

        # Mirrors sdlc-task.js: baseBranchName = `${blockId}-task`.toLowerCase().replace(/[^a-z0-9.-]/g, '-')
        self.branch_name = re.sub(r"[^a-z0-9.-]", "-", f"{block_id}-task".lower())
        self.worktree_path = tmp_root / "trees" / self.branch_name
        self.worktree_path.parent.mkdir(parents=True, exist_ok=True)
        run(
            ["git", "worktree", "add", "--no-checkout", str(self.worktree_path), "-b", self.branch_name],
            cwd=self.repo,
        )

        self.porcelain = run(
            ["git", "worktree", "list", "--porcelain"], cwd=self.repo
        ).stdout

    def setup_result(self, **overrides):
        result = {
            "runDir": str(self.worktree_path),
            "branchName": self.branch_name,
            "currentBranch": self.current_branch,
            "worktreeFailed": False,
            "worktreeFailureReason": "",
            "worktreeListPorcelain": self.porcelain,
        }
        result.update(overrides)
        return result

    def cleanup(self):
        run(["git", "worktree", "remove", "--force", str(self.worktree_path)], cwd=self.repo, check=False)


class SdlcTaskWorktreeSetupTests(unittest.TestCase):
    tmpdir: Path
    harness_js: str

    @classmethod
    def setUpClass(cls):
        if not ENGINE_FILE.exists():
            raise AssertionError(f"{ENGINE_FILE} not found")
        if shutil.which("node") is None:
            raise AssertionError("node is required to run this fixture suite")
        if shutil.which("git") is None:
            raise AssertionError("git is required to run this fixture suite")
        engine_text = ENGINE_FILE.read_text(encoding="utf-8")
        cls.harness_js = build_harness(engine_text)
        # realpath: macOS's TMPDIR (/var/folders/...) is itself a symlink into /private/..., and
        # `git worktree list` reports the RESOLVED path -- comparing against the unresolved
        # mkdtemp() path would fail every case spuriously (not a real defect, a fixture artifact).
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="sdlc-task-worktree-fixture-")).resolve()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def decide(self, use_worktree, repo_root, block_id, setup_result):
        payload = [use_worktree, repo_root, block_id, setup_result]
        proc = subprocess.run(
            ["node", "-e", self.harness_js],
            input=__import__("json").dumps(payload),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"node harness exited {proc.returncode}; stderr:\n{proc.stderr}",
        )
        import json
        return json.loads(proc.stdout)

    def _assert_real_worktree(self, fixture: WorktreeSetupFixture):
        """Positive control: the fixture's own real `git worktree list --porcelain` must
        actually contain the worktree we just created, parsed independently in Python --
        otherwise a later "decide() matched" assertion would prove nothing (standing rule 11)."""
        entries = parse_porcelain_python(fixture.porcelain)
        matching = [e for e in entries if e["path"] == str(fixture.worktree_path)]
        self.assertTrue(
            matching,
            f"positive control failed: {fixture.worktree_path} not present in real "
            f"`git worktree list --porcelain` output:\n{fixture.porcelain}",
        )
        self.assertEqual(matching[0]["branch"], fixture.branch_name)

    def test_slug_equals_block_id_shape_gets_real_worktree(self):
        fixture = WorktreeSetupFixture(self.tmpdir / "case-a", "BT.ticket.foo")
        try:
            self._assert_real_worktree(fixture)
            result = self.decide(True, str(fixture.repo), fixture.block_id, fixture.setup_result())
            self.assertNotIn("error", result, f"expected success, got bail: {result}")
            self.assertEqual(result["runDir"], str(fixture.worktree_path))
            self.assertEqual(result["branchName"], fixture.branch_name)
        finally:
            fixture.cleanup()

    def test_slug_differs_from_block_id_shape_gets_real_worktree(self):
        # Exact shape preserved in this ticket's retired-carryover evidence: spec dir
        # "ticket-live-run-workflow-type" against block id "BA.ticket.live-run-workflow-type".
        fixture = WorktreeSetupFixture(self.tmpdir / "case-b", "BA.ticket.live-run-workflow-type")
        try:
            self._assert_real_worktree(fixture)
            result = self.decide(True, str(fixture.repo), fixture.block_id, fixture.setup_result())
            self.assertNotIn("error", result, f"expected success, got bail: {result}")
            self.assertEqual(result["runDir"], str(fixture.worktree_path))
            self.assertEqual(result["branchName"], fixture.branch_name)
        finally:
            fixture.cleanup()

    def test_forced_creation_failure_bails_not_falls_back_to_main_tree(self):
        fixture = WorktreeSetupFixture(self.tmpdir / "case-c", "BT.ticket.creation-failure")
        try:
            # Force the exact self-report a setup agent gives when `git worktree add` errors or
            # every candidate branch name (base..base-10) is already taken -- the regression
            # control for the measured 2026-08-20 defect.
            forced = fixture.setup_result(
                worktreeFailed=True,
                worktreeFailureReason="all candidate branch names bt.ticket.creation-failure-task"
                " through bt.ticket.creation-failure-task-10 already exist",
                # Even though a real worktree WAS created above, the agent reporting failure must
                # win -- a bail can never be silently overridden by a leftover successful create.
            )
            result = self.decide(True, str(fixture.repo), fixture.block_id, forced)
            self.assertIn("error", result, f"expected a bail, got success: {result}")
            self.assertNotEqual(
                result.get("runDir"), str(fixture.repo),
                "bail must never report runDir as the main tree",
            )
        finally:
            fixture.cleanup()

    def test_fabricated_rundir_absent_from_worktree_list_bails(self):
        """Second regression control: a self-report that FABRICATES a plausible runDir/branchName
        without ever actually creating the worktree (worktreeFailed not set) must still be caught
        by the worktree-list cross-check -- this is what makes the silent main-tree fallback
        impossible rather than merely unlikely (task 2)."""
        fixture = WorktreeSetupFixture(self.tmpdir / "case-d", "BT.ticket.fabricated")
        try:
            fabricated = fixture.setup_result(
                runDir=str(fixture.repo / "trees" / "does-not-exist"),
                branchName="bt.ticket.fabricated-task",
            )
            result = self.decide(True, str(fixture.repo), fixture.block_id, fabricated)
            self.assertIn("error", result, f"expected a bail, got success: {result}")
        finally:
            fixture.cleanup()


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(SdlcTaskWorktreeSetupTests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
