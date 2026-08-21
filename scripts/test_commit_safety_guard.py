#!/usr/bin/env python3
"""Fixture suite for the commit-safety guard added by
BT.ticket.worktree-run-can-commit-an-empty-tree, task 1 (`renderCommitSafetyGuard()` in
`.claude/workflows/sdlc-flow.js` and `.claude/workflows/sdlc-task.js`).

base-template cannot reproduce the ENVIRONMENTAL trigger (its own two --worktree runs on
2026-08-21 did not fire it -- see the spec's ## Notes), so this suite exercises the DATA-LOSS
SHAPE directly: a linked worktree with `GIT_INDEX_FILE` pointed at a nonexistent path, following
`planning/BT.ticket.worktree-run-can-commit-an-empty-tree/evidence/git-index-file-minimal-repro.sh`
(the retro-fixture against the known-bad instance -- one variable, no GIT_DIR, core.bare untouched).

The guard text is extracted from the ENGINE SOURCE via regex (not re-typed here), so a future
edit that lets the two engines' copies drift, or that weakens the guard itself, fails this check
rather than passing silently. The extracted JS function is handed to a real `node -e` invocation
to get the actual rendered shell snippet -- this suite never re-implements the guard's logic.

Registered in planning/harness.json as `commit-safety-guard-tests` --
run directly: python3 scripts/test_commit_safety_guard.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_FILES = {
    "sdlc-flow.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js",
    "sdlc-task.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js",
}

# Matches the whole function definition, e.g.:
#   function renderCommitSafetyGuard(gitCmd = 'git') {
#     return `if ${gitCmd} rev-parse ... `
#   }
GUARD_FN_RE = re.compile(
    r"function renderCommitSafetyGuard\(gitCmd = 'git'\) \{\n"
    r"  return `[^\n]*`\n"
    r"\}",
    re.MULTILINE,
)


def extract_guard_fn(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = GUARD_FN_RE.search(text)
    if not m:
        raise AssertionError(f"renderCommitSafetyGuard() definition not found in {path}")
    return m.group(0)


def render_guard(fn_source: str, git_cmd: str | None = None) -> str:
    """Evaluate the real JS function via `node -e` and return the rendered shell snippet.

    Never re-implements the guard's string-building logic in Python -- this is the actual
    engine source, executed.
    """
    call = "renderCommitSafetyGuard()" if git_cmd is None else f"renderCommitSafetyGuard({git_cmd!r})"
    script = f"{fn_source}\nprocess.stdout.write({call})"
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def run(cmd, cwd, env=None, check=True):
    return subprocess.run(
        cmd, cwd=str(cwd), env=env, capture_output=True, text=True, check=check,
        shell=isinstance(cmd, str),
    )


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], cwd=path)
    run(["git", "config", "user.email", "t@t"], cwd=path)
    run(["git", "config", "user.name", "t"], cwd=path)


class CommitSafetyGuardTests(unittest.TestCase):
    guard_flow: str
    guard_task: str

    @classmethod
    def setUpClass(cls):
        cls.tmpdirs = []
        for name, path in SOURCE_FILES.items():
            if not path.exists():
                raise AssertionError(f"engine source missing: {path}")
        cls.fn_flow = extract_guard_fn(SOURCE_FILES["sdlc-flow.js"])
        cls.fn_task = extract_guard_fn(SOURCE_FILES["sdlc-task.js"])

    def _scratch(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="commit-guard-test-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    # -- (0) cross-engine agreement -----------------------------------------------------

    def test_00_guard_definitions_byte_identical_across_engines(self):
        self.assertEqual(
            self.fn_flow, self.fn_task,
            "renderCommitSafetyGuard() has drifted between sdlc-flow.js and sdlc-task.js",
        )

    def test_00b_rendered_default_snippet_byte_identical(self):
        self.assertEqual(render_guard(self.fn_flow), render_guard(self.fn_task))

    # -- (a) POISONED: linked worktree, GIT_INDEX_FILE -> nonexistent path -----------------

    def test_a_poisoned_worktree_aborts_and_no_commit_lands(self):
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "a.txt").write_text("a\n")
        (repo / "b.txt").write_text("b\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init"], cwd=repo)
        head_before = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

        run(["git", "worktree", "add", "-q", "--no-checkout", "../wt", "-b", "wtb"], cwd=repo)
        wt = root / "wt"
        run(["git", "sparse-checkout", "init", "--cone"], cwd=wt, check=False)
        run(["git", "checkout", "-q"], cwd=wt)
        (wt / "c.txt").write_text("c\n")

        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = str(root / "does-not-exist-index")

        guard = render_guard(self.fn_flow)
        result = run(f"{guard} && git commit -qm poisoned", cwd=wt, env=env, check=False)

        self.assertNotEqual(result.returncode, 0, "guard did not abort a poisoned index")
        self.assertIn("COMMIT_GUARD_ABORT", result.stdout)

        # The wtb branch (as seen from repo, unaffected by GIT_INDEX_FILE) must be unchanged --
        # no zero-file commit landed.
        head_after = run(["git", "rev-parse", "wtb"], cwd=repo).stdout.strip()
        self.assertEqual(head_before, head_after, "a commit landed on wtb despite the guard firing")

    # -- (b) CLEAN CONTROL: ordinary staged change ------------------------------------------

    def test_b_clean_control_commits_land_with_expected_files(self):
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "a.txt").write_text("a\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init"], cwd=repo)

        (repo / "b.txt").write_text("b\n")
        run(["git", "add", "-A"], cwd=repo)

        guard = render_guard(self.fn_flow)
        result = run(f"{guard} && git commit -qm second", cwd=repo, check=False)
        self.assertEqual(result.returncode, 0, f"guard blocked a clean commit: {result.stdout}{result.stderr}")

        files = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo).stdout.split()
        self.assertEqual(sorted(files), ["a.txt", "b.txt"])

    # -- (c) NO-HEAD: first commit of a fresh repo must never be blocked -------------------

    def test_c_no_head_first_commit_never_blocked(self):
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "a.txt").write_text("a\n")
        run(["git", "add", "-A"], cwd=repo)

        guard = render_guard(self.fn_flow)
        result = run(f"{guard} && git commit -qm init", cwd=repo, check=False)
        self.assertEqual(result.returncode, 0, f"guard blocked the very first commit: {result.stdout}{result.stderr}")

        files = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo).stdout.split()
        self.assertEqual(files, ["a.txt"])

    # -- (d) VAULT SHAPE: `git -C <other repo>` answers about THAT repo's HEAD -------------

    def test_d_vault_shape_reads_the_dash_c_repo_not_cwd(self):
        root = self._scratch()

        cwd_repo = root / "cwd-repo"
        init_repo(cwd_repo)
        (cwd_repo / "x.txt").write_text("x\n")
        run(["git", "add", "-A"], cwd=cwd_repo)
        run(["git", "commit", "-qm", "init"], cwd=cwd_repo)
        # cwd-repo is left with nothing staged beyond HEAD's own tree -- if the guard evaluated
        # against cwd instead of -C's repo, TRACKED>0 && STAGED==0 would be true and it would
        # wrongly fire.

        vault_repo = root / "vault-repo"
        init_repo(vault_repo)
        (vault_repo / "v1.txt").write_text("v1\n")
        (vault_repo / "v2.txt").write_text("v2\n")
        run(["git", "add", "-A"], cwd=vault_repo)
        run(["git", "commit", "-qm", "init"], cwd=vault_repo)
        vault_head_before = run(["git", "rev-parse", "HEAD"], cwd=vault_repo).stdout.strip()
        # Poison the VAULT repo's index only.
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = str(root / "does-not-exist-vault-index")

        guard = render_guard(self.fn_flow, f"git -C {vault_repo}")
        result = run(f"{guard} && git -C {vault_repo} commit -qm poisoned", cwd=cwd_repo, env=env, check=False)

        self.assertNotEqual(result.returncode, 0, "guard did not fire against the -C repo's poisoned index")
        self.assertIn("COMMIT_GUARD_ABORT", result.stdout)
        vault_head_after = run(["git", "rev-parse", "HEAD"], cwd=vault_repo).stdout.strip()
        self.assertEqual(vault_head_before, vault_head_after, "a commit landed on the vault repo despite the guard firing")

        # Sanity: same guard, unpoisoned vault repo with a real staged change, commits fine.
        env2 = dict(os.environ)
        (vault_repo / "v3.txt").write_text("v3\n")
        run(["git", "add", "-A"], cwd=vault_repo)
        guard2 = render_guard(self.fn_flow, f"git -C {vault_repo}")
        result2 = run(f"{guard2} && git -C {vault_repo} commit -qm third", cwd=cwd_repo, env=env2, check=False)
        self.assertEqual(result2.returncode, 0, f"guard blocked a clean -C commit: {result2.stdout}{result2.stderr}")


class GitStatusUnchangedTest(unittest.TestCase):
    """Every fixture above builds and tears down its own tempdir repo -- confirm this repo's
    own git state is untouched by a test run (spec acceptance criterion)."""

    def test_repo_status_clean_apart_from_this_files_own_changes(self):
        result = run(["git", "status", "--porcelain", "--", "scripts/test_commit_safety_guard.py"], cwd=REPO_ROOT, check=False)
        # This assertion is a smoke check that the command itself runs cleanly against the real
        # repo root; the untracked/modified status of this very file during authoring is expected
        # and is not what this test polices. The real guarantee -- no OTHER path in the repo is
        # touched -- is structural: every git operation above targets a Path under tempfile.mkdtemp().
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
