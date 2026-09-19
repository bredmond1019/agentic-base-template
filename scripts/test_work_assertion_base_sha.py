#!/usr/bin/env python3
"""Fixture suite for BT.ticket.work-assertion-base-sha-self-comparison.

Task 1 of this spec: the `prepare_run.py`-side half — a new `find_task_commits(repo_root,
block_id)` that reports a block's own per-task commits from real git history, matched against the
engine's own commit-subject convention (`feat: implement <blockId>-task<N>` / `fix: fix pass <P>
for <blockId>-task<N>`).

Task 2 of this spec (also in THIS FILE, appended below): the engine-side half — `sdlc-task.js`'s
`resolvePrevSha()`, which wires `find_task_commits()`'s result into the per-task `prevSha`
resolution (state, else git history, else `base_sha`, never task N's own commit).

WHY THIS EXISTS (see the block record's `what`/`why`)
-------------------------------------------------------
`sdlc-task.js`'s per-task work assertion diffs `prevSha..HEAD`. When task N-1's commit is absent
from `state.tasks` (a task-range launch, or a relaunch after a crash lost `sdlc-task-state.json`),
today's fallback is `state.base_sha` — the pre-RUN HEAD. If task N's own commit was already HEAD
at launch, `base_sha` IS that commit, so the diff is a structurally empty self-comparison and the
work assertion false-negatives on real, correctly-committed work (reproduced 2026-09-17 on a real
engine-rs `EN.19.C` run, full timeline in the block record).

This file proves `find_task_commits()` can recover the real predecessor commit from git history
alone, deterministically, with no model judgement and no extra agent turn — the fix task 2 wires
in.

Cases
-----
Built against one throwaway git repo (`tempfile.mkdtemp`, real `git init`/`git commit` — never a
real repo's history) carrying, in order:
  1. `init`                                             — decoy base commit
  2. `feat: implement BT.x.A-task1`                      — the task-1 commit
  3. `feat: implement BT.x.A-task2`                      — the task-2 commit
  4. `fix: fix pass 1 for BT.x.A-task2`                   — a fix-pass commit for task 2
  5. `feat: implement BT.x.AB-task1`                      — decoy: a DIFFERENT, prefix-sharing
                                                             block id (`BT.x.AB`, not `BT.x.A`)
  6. `feat: implement BT.x.A-task1 (vault)`               — decoy: the vault-suffixed variant of
                                                             the task-1 subject (lives in the
                                                             brain repo, never this one)

Assertions:
  - `find_task_commits(repo, "BT.x.A")["1"]` reports ONLY the real task-1 commit (sha from commit
    2) — both decoys (5 and 6) are excluded.
  - `find_task_commits(repo, "BT.x.A")["2"]` reports both matching shas (commits 3 and 4) newest
    first, and `earliest_parent` equals the task-1 commit's sha (commit 2) — the oldest matching
    commit for task 2 is commit 3, whose parent is commit 2.
  - No `block_id` -> `{}`.
  - A directory that is not a git repo at all -> `{}` (never raises, never refuses a run).

Registered in planning/harness.json (this task) as `work-assertion-base-sha-tests` --
run directly: python3 scripts/test_work_assertion_base_sha.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BIN_DIR = _REPO_ROOT / '.claude' / 'workflows' / 'bin'
sys.path.insert(0, str(_BIN_DIR))

import prepare_run  # noqa: E402


def _run(cmd, cwd):
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, check=True,
    )


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], cwd=path)
    _run(["git", "config", "user.email", "t@t"], cwd=path)
    _run(["git", "config", "user.name", "t"], cwd=path)


def _commit(path: Path, subject: str, *, filename: str | None = None) -> str:
    """Write one new file (so each commit is non-empty), commit it with `subject` as the whole
    commit message (no body), and return its short sha."""
    target = path / (filename or f"f-{subject!r}.txt".replace('/', '_'))
    target.write_text(subject + "\n", encoding="utf-8")
    _run(["git", "add", target.name], cwd=path)
    _run(["git", "commit", "-q", "-m", subject], cwd=path)
    return _run(["git", "rev-parse", "--short", "HEAD"], cwd=path).stdout.strip()


def _build_fixture_repo(root: Path) -> tuple[Path, dict[str, str]]:
    """Build the six-commit repo described in the module docstring. Returns (repo_root, shas)
    where shas maps a short label ('init', 'task1', 'task2', 'task2-fix', 'decoy-prefix',
    'decoy-vault') to the commit's short sha."""
    repo = root / "fixture-repo"
    _init_repo(repo)
    shas = {}
    shas["init"] = _commit(repo, "init", filename="README.md")
    shas["task1"] = _commit(repo, "feat: implement BT.x.A-task1")
    shas["task2"] = _commit(repo, "feat: implement BT.x.A-task2")
    shas["task2-fix"] = _commit(repo, "fix: fix pass 1 for BT.x.A-task2")
    shas["decoy-prefix"] = _commit(repo, "feat: implement BT.x.AB-task1")
    shas["decoy-vault"] = _commit(repo, "feat: implement BT.x.A-task1 (vault)")
    return repo, shas


class FindTaskCommitsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo, cls.shas = _build_fixture_repo(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_task1_reports_only_the_real_task1_commit(self):
        result = prepare_run.find_task_commits(str(self.repo), "BT.x.A")
        self.assertIn("1", result)
        self.assertEqual(result["1"]["shas"], [self.shas["task1"]])
        self.assertEqual(result["1"]["newest"], self.shas["task1"])
        # Neither decoy (the prefix-sharing block id, nor the vault-suffixed subject) leaks in.
        self.assertNotIn(self.shas["decoy-prefix"], result["1"]["shas"])
        self.assertNotIn(self.shas["decoy-vault"], result["1"]["shas"])

    def test_task2_reports_both_commits_newest_first_with_correct_parent(self):
        result = prepare_run.find_task_commits(str(self.repo), "BT.x.A")
        self.assertIn("2", result)
        # newest first: the fix-pass commit landed after the feat commit.
        self.assertEqual(result["2"]["shas"], [self.shas["task2-fix"], self.shas["task2"]])
        self.assertEqual(result["2"]["newest"], self.shas["task2-fix"])
        # earliest_parent is the parent of the OLDEST matching commit (task2's feat commit),
        # which is task1's own commit.
        self.assertEqual(result["2"]["earliest_parent"], self.shas["task1"])

    def test_decoy_block_id_never_matches(self):
        result = prepare_run.find_task_commits(str(self.repo), "BT.x.AB")
        self.assertEqual(result.get("1", {}).get("shas"), [self.shas["decoy-prefix"]])

    def test_no_block_id_returns_empty(self):
        self.assertEqual(prepare_run.find_task_commits(str(self.repo), None), {})
        self.assertEqual(prepare_run.find_task_commits(str(self.repo), ""), {})

    def test_non_git_directory_returns_empty_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain_dir = Path(tmp) / "not-a-repo"
            plain_dir.mkdir()
            self.assertEqual(prepare_run.find_task_commits(str(plain_dir), "BT.x.A"), {})

    def test_prepare_run_top_level_exposes_task_commits(self):
        """Runtime inversion / observed_red control: without --block-id, prepare_run()'s
        top-level `task_commits` key is {} even though this fixture repo has real matching
        history -- proving the field is actually wired to block_id, not always populated. Run
        2026-09-18 against the pre-fix prepare_run() (no block_id parameter at all): this call
        raised TypeError('prepare_run() got an unexpected keyword argument 'block_id'') -- the RED
        this suite is registered to guard against going back to."""
        result = prepare_run.prepare_run(
            None, explicit_repo_root=str(self.repo), cwd=str(self.repo),
        )
        self.assertEqual(result.get("task_commits"), {})

        result_with_id = prepare_run.prepare_run(
            None, explicit_repo_root=str(self.repo), cwd=str(self.repo), block_id="BT.x.A",
        )
        self.assertEqual(
            result_with_id["task_commits"]["1"]["shas"], [self.shas["task1"]],
        )


# ============================================================================
# Task 2 of this spec: sdlc-task.js's engine-side resolvePrevSha() -- wires find_task_commits()
# (task 1, above) into the per-task prevSha resolution. Extracts the REAL function body from the
# engine file via balanced-brace scanning (same idiom as
# scripts/test_work_assertion_empty_intersection.py's extract_function(), itself modelled on
# scripts/test_bail_path_runtime.py) and evaluates it through a real `node` process -- never
# re-types the resolution logic under test.
# ============================================================================

_TASK_ENGINE = _REPO_ROOT / '.claude' / 'workflows' / 'sdlc-task.js'


def _extract_function(text: str, name: str) -> str:
    m = re.search(rf"function {re.escape(name)}\([^)]*\)\s*\{{", text)
    if not m:
        raise AssertionError(f"function {name}() not found")
    depth = 0
    i = text.index("{", m.start())
    start = m.start()
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces extracting function {name}()")


def _resolve_prev_sha_via_node(state: dict, task_num: int, task_commits: dict) -> dict:
    """Extracts the REAL resolvePrevSha() body from sdlc-task.js and evaluates it through a real
    node process."""
    src = _TASK_ENGINE.read_text(encoding="utf-8")
    fn_src = _extract_function(src, "resolvePrevSha")
    node_script = (
        fn_src
        + "\n"
        + f"process.stdout.write(JSON.stringify(resolvePrevSha({json.dumps(state)}, {task_num}, {json.dumps(task_commits)})))\n"
    )
    result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"node failed to evaluate resolvePrevSha():\n{result.stderr}")
    return json.loads(result.stdout)


def _old_formula_via_node(state: dict, task_num: int) -> str:
    """Runtime inversion: evaluate the OLD, pre-fix one-line formula directly -- it no longer
    exists in the engine source -- and return what it resolves to. Proves the reproduction case
    below actually discriminates between the old (broken) and new (fixed) behavior."""
    node_script = (
        f"const state = {json.dumps(state)};\n"
        f"const taskNum = {task_num};\n"
        "const prevSha = (state.tasks[String(taskNum - 1)] || {}).commit || state.base_sha;\n"
        "process.stdout.write(prevSha || '')\n"
    )
    result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"node failed to evaluate the old formula:\n{result.stderr}")
    return result.stdout


class ResolvePrevShaEngineTests(unittest.TestCase):
    """Task 2: sdlc-task.js's resolvePrevSha(), extracted verbatim from source and evaluated
    through node -- the reproduction shape, the ordinary path, the fallback-unchanged path, and the
    self-attribution guard."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo, cls.shas = _build_fixture_repo(Path(cls._tmp.name))
        cls.task_commits = prepare_run.find_task_commits(str(cls.repo), "BT.x.A")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_reproduction_no_state_base_sha_is_own_commit_resolves_to_predecessor(self):
        """(a) engine-rs EN.19.C shape: state.tasks is empty (crash lost the state file before any
        write), base_sha == task 2's own commit (it was already HEAD at re-launch). The resolution
        must land on task 1's commit -- never task 2's own commit."""
        state = {"tasks": {}, "base_sha": self.shas["task2"]}
        result = _resolve_prev_sha_via_node(state, 2, self.task_commits)
        self.assertEqual(result["prevSha"], self.shas["task1"])
        self.assertIn(result["source"], ("git-history", "guard:earliest_parent"))

        # Runtime inversion: the OLD one-line formula on the SAME inputs resolves to task 2's own
        # commit -- proving this case actually discriminates old (broken) from new (fixed).
        old_result = _old_formula_via_node(state, 2)
        self.assertEqual(old_result, self.shas["task2"])

    def test_ordinary_path_state_commit_present_is_unchanged(self):
        """(b) The fresh-run path: state.tasks['1'].commit is present -- prevSha is exactly that
        value, regardless of what git history or base_sha say."""
        state = {"tasks": {"1": {"commit": self.shas["task1"]}}, "base_sha": self.shas["init"]}
        result = _resolve_prev_sha_via_node(state, 2, self.task_commits)
        self.assertEqual(result["prevSha"], self.shas["task1"])
        self.assertEqual(result["source"], "state")
        self.assertFalse(result["guardFired"])

    def test_no_history_no_state_falls_back_to_base_sha_unchanged(self):
        """(c) No task_commits at all (e.g. a resume seeded from a pre-change state.setup with no
        `task_commits` field) and no state.tasks entry -- prevSha is exactly state.base_sha, the
        fallback unchanged from before this fix."""
        state = {"tasks": {}, "base_sha": self.shas["init"]}
        result = _resolve_prev_sha_via_node(state, 2, {})
        self.assertEqual(result["prevSha"], self.shas["init"])
        self.assertEqual(result["source"], "base_sha")
        self.assertFalse(result["guardFired"])

    def test_guard_fires_when_base_sha_is_own_commit_and_no_predecessor_anywhere(self):
        """(d) base_sha equals task N's own commit AND task N-1 has no commit anywhere (no state,
        no git history) -- the guard fires against base_sha itself and falls back to
        earliest_parent."""
        state = {"tasks": {}, "base_sha": self.shas["task1"]}
        task_commits_task1_only = {"1": self.task_commits["1"]}
        result = _resolve_prev_sha_via_node(state, 1, task_commits_task1_only)
        self.assertTrue(result["guardFired"])
        self.assertEqual(result["source"], "guard:earliest_parent")
        self.assertEqual(result["prevSha"], self.shas["init"])


if __name__ == "__main__":
    unittest.main()
