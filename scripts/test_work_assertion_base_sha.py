#!/usr/bin/env python3
"""Fixture suite for BT.ticket.work-assertion-base-sha-self-comparison.

Task 1 of this spec (THIS FILE): the `prepare_run.py`-side half — a new
`find_task_commits(repo_root, block_id)` that reports a block's own per-task commits from real
git history, matched against the engine's own commit-subject convention (`feat: implement
<blockId>-task<N>` / `fix: fix pass <P> for <blockId>-task<N>`). Task 2 (not this file's job)
wires the result into `sdlc-task.js`'s per-task `prevSha` resolution.

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


if __name__ == "__main__":
    unittest.main()
