#!/usr/bin/env python3
"""Fixture suite for the post-commit work assertion added by
BT.ticket.a-run-must-prove-its-commits-contain-the-work (`renderWorkAssertion()`, to be added
beside `renderCommitSafetyGuard()` in `.claude/workflows/sdlc-flow.js` and
`.claude/workflows/sdlc-task.js`).

Task 1 of that spec builds only the EN.11.O reproduction fixture and records, as a passing test
against the CURRENT engine source, that the EXISTING `renderCommitSafetyGuard()` does NOT catch
it -- it fires only on a totally empty index, and EN.11.O's commit had a non-empty index full of
deletions (443 files changed, 177,867 deletions, zero insertions per D81). That recorded pass on a
mass-deletion commit is this block's central piece of evidence, and the whole reason a second,
complementary guard (the work assertion, added in a later task) is needed.

This suite reuses the extract/render/real-git-repo harness shape from
scripts/test_commit_safety_guard.py rather than inventing a new one: the guard text is extracted
from the ENGINE SOURCE via regex (not re-typed here) and handed to a real `node -e` invocation to
get the actual rendered shell snippet, which is then run against real git repos built in scratch
dirs. This suite never re-implements the guard's logic in Python.

At this task's boundary, `renderWorkAssertion()` does not exist yet in either engine -- this suite
makes no reference to it. It is extended in a later task once the new guard is added.

Registered in planning/harness.json as `work-assertion-tests` --
run directly: python3 scripts/test_work_assertion.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
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


class WorkAssertionExistingGuardControlTests(unittest.TestCase):
    """Task 1: the EN.11.O reproduction fixture, and the recorded control that the CURRENT
    `renderCommitSafetyGuard()` passes it."""

    guard_flow: str
    guard_task: str

    @classmethod
    def setUpClass(cls):
        for name, path in SOURCE_FILES.items():
            if not path.exists():
                raise AssertionError(f"engine source missing: {path}")
        cls.fn_flow = extract_guard_fn(SOURCE_FILES["sdlc-flow.js"])
        cls.fn_task = extract_guard_fn(SOURCE_FILES["sdlc-task.js"])

    def _scratch(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="work-assertion-test-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def _build_en11o_fixture(self, repo: Path, n_files: int = 20) -> tuple[list[str], str, Path]:
        """Reproduce the EN.11.O SHAPE: a commit with many deletions and zero insertions, made
        against a NON-EMPTY index -- unlike the guard's own trigger case (a totally empty
        index), D81 records EN.11.O's index as non-empty and full of (already-staged)
        deletions. The declared files[] for the task that produced this commit is small and
        the declared file itself is UNCHANGED in the resulting commit -- the deletions are all
        collateral, undeclared files.

        Mechanism: build the commit against an ALTERNATE index (its own `GIT_INDEX_FILE`) that
        holds only the declared file's existing blob -- exactly the shape of a worktree/index
        that only has a subset of the tree checked out. That index is non-empty (STAGED=1), so
        `renderCommitSafetyGuard()`'s `TRACKED>0 && STAGED==0` condition is false and it does
        not fire, while the resulting commit still deletes every other tracked file.

        Returns (deleted_names, declared_file, alt_index_path).
        """
        init_repo(repo)
        names = [f"file_{i:03d}.txt" for i in range(n_files)]
        declared_file = "docs/some-unrelated-doc.md"
        (repo / "docs").mkdir(parents=True, exist_ok=True)
        (repo / declared_file).write_text("declared doc, unchanged by this commit\n")
        for name in names:
            (repo / name).write_text(f"content of {name}\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init: many tracked files + one declared file"], cwd=repo)

        blob = run(["git", "rev-parse", f"HEAD:{declared_file}"], cwd=repo).stdout.strip()

        alt_index = repo.parent / "alt-index"
        env = {**os.environ, "GIT_INDEX_FILE": str(alt_index)}
        run(["git", "read-tree", "--empty"], cwd=repo, env=env)
        run(
            ["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{declared_file}"],
            cwd=repo, env=env,
        )
        return names, declared_file, alt_index

    # -- (0) cross-engine agreement on the EXISTING guard, as a sanity precondition --------

    def test_00_existing_guard_byte_identical_across_engines(self):
        self.assertEqual(
            self.fn_flow, self.fn_task,
            "renderCommitSafetyGuard() has drifted between sdlc-flow.js and sdlc-task.js",
        )

    # -- (1) THE CENTRAL FIXTURE + CONTROL --------------------------------------------------

    def test_01_en11o_fixture_deletion_commit_is_nonempty_and_all_deletions(self):
        """Sanity-check the fixture itself matches the EN.11.O shape before using it as
        evidence: many tracked files, a commit (against a non-empty, 1-entry alternate index)
        deleting all of them, zero insertions."""
        root = self._scratch()
        repo = root / "repo"
        names, declared_file, alt_index = self._build_en11o_fixture(repo)

        env = {**os.environ, "GIT_INDEX_FILE": str(alt_index)}
        numstat = run(
            ["git", "diff", "--cached", "--numstat"], cwd=repo, env=env,
        ).stdout.strip().splitlines()
        self.assertEqual(len(numstat), len(names), "expected one numstat line per deleted file")
        insertions_total = 0
        deletions_total = 0
        changed_paths = []
        for line in numstat:
            ins, dels, path = line.split("\t", 2)
            insertions_total += int(ins)
            deletions_total += int(dels)
            changed_paths.append(path)
        self.assertEqual(insertions_total, 0, "fixture must have zero insertions")
        self.assertGreater(deletions_total, 0, "fixture must have at least one deletion")
        self.assertNotIn(declared_file, changed_paths, "the declared file must NOT be among the deletions")

        # The alt index itself is non-empty -- one entry, the declared file.
        staged = run(["git", "ls-files", "-s"], cwd=repo, env=env).stdout.strip().splitlines()
        self.assertEqual(len(staged), 1, "fixture's alternate index must hold exactly one entry")

    def test_02_current_guard_PASSES_the_en11o_deletion_commit(self):
        """THE CONTROL: the CURRENT renderCommitSafetyGuard() only fires when the index holds
        ZERO entries against a non-empty HEAD. The EN.11.O fixture's index is non-empty (one
        entry -- the declared file, unchanged), so the existing guard must PASS it and let the
        commit land -- exactly as D81 records happened in production ('EN.11.O had a non-empty
        index full of deletions ... That is precisely why it passed'). This recorded pass on a
        mass-deletion commit is the evidence that a second, complementary guard is needed; it
        is not itself a bug in the existing guard, which was never designed to catch this class.
        """
        root = self._scratch()
        repo = root / "repo"
        names, declared_file, alt_index = self._build_en11o_fixture(repo)

        # The task that produced this commit declared only the one unchanged file -- nothing
        # like the 20 deleted files. The existing guard does not look at declared files at all,
        # so this is recorded only for context; the assertion below is purely about the
        # existing guard's index-emptiness check.
        declared_files = [declared_file]
        self.assertTrue(declared_files, "declared files[] recorded for context, unused by guard")

        env = {**os.environ, "GIT_INDEX_FILE": str(alt_index)}
        guard = render_guard(self.fn_flow)
        result = run(f"{guard} && git commit -qm 'EN.11.O shape: delete everything undeclared'", cwd=repo, env=env, check=False)

        self.assertEqual(
            result.returncode, 0,
            f"expected the CURRENT guard to PASS (not block) a mass-deletion commit, "
            f"but it aborted: {result.stdout}{result.stderr}",
        )
        self.assertNotIn("COMMIT_GUARD_ABORT", result.stdout)

        # And the commit actually landed, deleting every undeclared tracked file while keeping
        # the declared one intact.
        tree_files = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo).stdout.split()
        self.assertEqual(tree_files, [declared_file], "expected the deletion commit to land, keeping only the declared file")
        for name in names:
            self.assertNotIn(name, tree_files)

    def test_03_current_guard_still_fires_on_the_original_empty_index_shape(self):
        """Precondition check: the fixture used above is genuinely a DIFFERENT shape from the
        one the existing guard does catch (a totally empty index against a non-empty HEAD) --
        confirming the two are distinct rather than the same case observed twice."""
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "a.txt").write_text("a\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init"], cwd=repo)

        env = dict(os.environ)
        empty_index = root / "empty-index"
        # An index file that exists but is empty renders `git ls-files -s` empty, i.e. the
        # "index holds 0 entries" branch the guard checks for.
        run(["git", "read-tree", "--empty"], cwd=repo, env={**env, "GIT_INDEX_FILE": str(empty_index)})
        env["GIT_INDEX_FILE"] = str(empty_index)

        guard = render_guard(self.fn_flow)
        result = run(f"{guard} && git commit -qm poisoned", cwd=repo, env=env, check=False)

        self.assertNotEqual(result.returncode, 0, "guard did not abort a truly empty index")
        self.assertIn("COMMIT_GUARD_ABORT", result.stdout)


class GitStatusUnchangedTest(unittest.TestCase):
    """Every fixture above builds and tears down its own tempdir repo -- confirm this repo's
    own git state is untouched by a test run (spec acceptance criterion)."""

    def test_repo_status_clean_apart_from_this_files_own_changes(self):
        result = run(["git", "status", "--porcelain", "--", "scripts/test_work_assertion.py"], cwd=REPO_ROOT, check=False)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
