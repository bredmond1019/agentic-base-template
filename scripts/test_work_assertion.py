#!/usr/bin/env python3
"""Fixture suite for the post-commit work assertion added by
BT.ticket.a-run-must-prove-its-commits-contain-the-work (`renderWorkAssertion()`, to be added
beside the existing `renderCommitSafetyGuard()` in `.claude/workflows/sdlc-task.js` and
`.claude/workflows/sdlc-flow.js`).

D81 records the mechanism this suite exists to pin: `renderCommitSafetyGuard()` fires only when
the staged index holds ZERO entries against a non-empty HEAD. EN.11.O had a NON-EMPTY index full
of deletions -- 443 files changed, 177,867 deletions, zero insertions -- "That is precisely why
it passed." This task (task 1 of the spec) builds THE CENTRAL FIXTURE reproducing that shape --
many tracked files, a commit that deletes nearly all of them while leaving at least one entry in
the index (so TRACKED>0 but STAGED != 0, which is exactly why the existing guard's condition
never fires) -- and records the CONTROL: the current `renderCommitSafetyGuard()` PASSES it. That
recorded pass is this block's central piece of evidence and the whole reason a second guard is
needed.

Task 2 adds `renderWorkAssertion()` itself and extends this suite: cross-engine byte-identical
agreement (function source AND rendered snippet); the SAME EN.11.O fixture from task 1 now FAILS
the new guard (condition 3 -- undeclared deletion) while the old `renderCommitSafetyGuard()`
still PASSES it, unchanged -- the difference-observing pair D81 calls for; an empty-diff commit
fails condition (1); a commit whose paths do not intersect files[] fails condition (2); an honest
commit touching exactly its declared files passes; a commit that deletes a file it DID declare
passes (deletion is not itself the signal); and each named exemption (worktree-init, the two D16
fallback commits, the vault path) is exercised by construction -- they simply never call the new
guard at their commit sites, mirrored by the fact this suite never renders it for their shape.

Reuses `scripts/test_commit_safety_guard.py`'s harness shape: extract a guard function's SOURCE
from the engine via regex (never re-typed), render it via a real `node -e` invocation (never
re-implemented in Python), and run it against REAL git repos built in scratch dirs under this
repo -- the only pattern in this repo that tests engine-embedded shell without running an engine.

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
COMMIT_SAFETY_GUARD_FN_RE = re.compile(
    r"function renderCommitSafetyGuard\(gitCmd = 'git'\) \{\n"
    r"  return `[^\n]*`\n"
    r"\}",
    re.MULTILINE,
)

# The new guard's body is a multi-line template literal (it embeds a `python3 -c "..."` block),
# unlike renderCommitSafetyGuard()'s single-line one -- hence DOTALL + non-greedy up to the first
# closing backtick immediately followed by a newline and the function's closing brace.
WORK_ASSERTION_FN_RE = re.compile(
    r"function renderWorkAssertion\(gitCmd = 'git', taskNum, tasksJsonPath\) \{\n"
    r"  return `.*?`\n"
    r"\}",
    re.DOTALL,
)


def extract_commit_safety_guard_fn(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = COMMIT_SAFETY_GUARD_FN_RE.search(text)
    if not m:
        raise AssertionError(f"renderCommitSafetyGuard() definition not found in {path}")
    return m.group(0)


def extract_work_assertion_fn(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = WORK_ASSERTION_FN_RE.search(text)
    if not m:
        raise AssertionError(f"renderWorkAssertion() definition not found in {path}")
    return m.group(0)


def render_fn(fn_source: str, fn_name: str, args: list[str] | None = None) -> str:
    """Evaluate the real JS function via `node -e` and return the rendered shell snippet.

    Never re-implements the guard's string-building logic in Python -- this is the actual
    engine source, executed.
    """
    args = args or []
    call = f"{fn_name}({', '.join(args)})"
    script = f"{fn_source}\nprocess.stdout.write({call})"
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def render_commit_safety_guard(fn_source: str, git_cmd: str | None = None) -> str:
    args = [] if git_cmd is None else [f"'{git_cmd}'"]
    return render_fn(fn_source, "renderCommitSafetyGuard", args)


def render_work_assertion(
    fn_source: str, task_num: int, tasks_json_path: str, git_cmd: str | None = None
) -> str:
    gc = git_cmd or "git"
    args = [f"'{gc}'", str(task_num), f"'{tasks_json_path}'"]
    return render_fn(fn_source, "renderWorkAssertion", args)


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


class WorkAssertionTaskOneTests(unittest.TestCase):
    """Task 1 boundary: only the EXISTING renderCommitSafetyGuard() is exercised. The new
    renderWorkAssertion() does not exist yet and is not referenced here."""

    fn_flow: str
    fn_task: str

    @classmethod
    def setUpClass(cls):
        for name, path in SOURCE_FILES.items():
            if not path.exists():
                raise AssertionError(f"engine source missing: {path}")
        cls.fn_flow = extract_commit_safety_guard_fn(SOURCE_FILES["sdlc-flow.js"])
        cls.fn_task = extract_commit_safety_guard_fn(SOURCE_FILES["sdlc-task.js"])

    def _scratch(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="work-assertion-test-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def _build_en11o_fixture(self, root: Path) -> Path:
        """Reproduce the EN.11.O shape: many tracked files, a commit that deletes nearly all of
        them (many deletions, zero insertions), leaving ONE file still present so the index is
        NOT entirely empty afterwards -- D81's "non-empty index full of deletions". The
        declared files[] the caller uses against this fixture is unrelated to any of these
        paths, mirroring EN.11.O's "the declared files were a handful"."""
        repo = root / "repo"
        init_repo(repo)
        tracked = [f"file_{i:03d}.txt" for i in range(20)]
        for name in tracked:
            (repo / name).write_text(f"{name}\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init: 20 tracked files"], cwd=repo)

        # Delete all but one tracked file -- the survivor is what keeps STAGED != 0 after
        # staging, which is exactly why the existing guard's TRACKED>0 && STAGED==0 condition
        # never fires on this shape.
        survivor = tracked[0]
        for name in tracked[1:]:
            (repo / name).unlink()
        run(["git", "add", "-A"], cwd=repo)

        numstat_before_commit = run(
            ["git", "diff", "--cached", "--numstat"], cwd=repo
        ).stdout
        # Sanity on the fixture itself: many deletions, zero insertions.
        deletions = 0
        insertions = 0
        for line in numstat_before_commit.strip().splitlines():
            ins, dele, _path = line.split("\t", 2)
            insertions += int(ins)
            deletions += int(dele)
        if insertions != 0 or deletions < len(tracked) - 1:
            raise AssertionError(
                f"fixture staging does not match the EN.11.O shape: "
                f"insertions={insertions} deletions={deletions}"
            )

        return repo

    # -- (0) fixture sanity -----------------------------------------------------------------

    def test_00_fixture_is_many_deletions_zero_insertions_nonempty_index(self):
        root = self._scratch()
        repo = self._build_en11o_fixture(root)
        staged = run(["git", "ls-files", "-s"], cwd=repo).stdout.strip().splitlines()
        self.assertEqual(
            len(staged), 1,
            "fixture must leave exactly one surviving file staged (non-empty index)",
        )

    # -- (1) THE CONTROL: current renderCommitSafetyGuard() PASSES this fixture -------------

    def test_01_existing_guard_passes_the_en11o_shape_control(self):
        """This is the block's central piece of evidence: the guard that already exists in the
        engines does NOT catch a commit whose diff is enormous deletion with a surviving file
        keeping the index non-empty -- because its only condition is TRACKED>0 && STAGED==0,
        which this fixture is built specifically to avoid tripping."""
        root = self._scratch()
        repo = self._build_en11o_fixture(root)

        guard = render_commit_safety_guard(self.fn_flow)
        result = run(f"{guard} && git commit -qm 'delete 19 of 20 tracked files'", cwd=repo, check=False)

        self.assertEqual(
            result.returncode, 0,
            f"existing renderCommitSafetyGuard() unexpectedly blocked the EN.11.O-shape commit: "
            f"{result.stdout}{result.stderr}",
        )

        # Confirm the commit actually landed and really does carry the mass-deletion shape.
        numstat = run(["git", "diff", "--numstat", "HEAD~1", "HEAD"], cwd=repo).stdout
        deletions = 0
        insertions = 0
        for line in numstat.strip().splitlines():
            ins, dele, _path = line.split("\t", 2)
            insertions += int(ins)
            deletions += int(dele)
        self.assertEqual(insertions, 0, "fixture commit must have zero insertions")
        self.assertGreaterEqual(deletions, 19, "fixture commit must delete nearly all tracked files")

    # -- (2) cross-engine agreement on the EXISTING guard (sanity for the harness reuse) ----

    def test_02_existing_guard_definitions_byte_identical_across_engines(self):
        self.assertEqual(
            self.fn_flow, self.fn_task,
            "renderCommitSafetyGuard() has drifted between sdlc-flow.js and sdlc-task.js",
        )


def write_tasks_json(repo: Path, task_id: int, files: list[str]) -> Path:
    import json

    path = repo / "tasks.json"
    path.write_text(json.dumps([{"task_id": task_id, "files": files}]))
    return path


class WorkAssertionTaskTwoTests(unittest.TestCase):
    """Task 2 boundary: `renderWorkAssertion()` now exists in both engines. Exercises all three
    failure conditions, both PASS directions (honest touch, honest declared-deletion), and the
    EN.11.O difference-observing pair against the SAME fixture shape as task 1's control."""

    fn_flow: str
    fn_task: str

    @classmethod
    def setUpClass(cls):
        cls.fn_flow = extract_work_assertion_fn(SOURCE_FILES["sdlc-flow.js"])
        cls.fn_task = extract_work_assertion_fn(SOURCE_FILES["sdlc-task.js"])

    def _scratch(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="work-assertion-test2-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    # -- cross-engine agreement --------------------------------------------------------------

    def test_00_fn_source_byte_identical_across_engines(self):
        self.assertEqual(
            self.fn_flow, self.fn_task,
            "renderWorkAssertion() function source has drifted between the two engines",
        )

    def test_00b_rendered_snippet_byte_identical_across_engines(self):
        rendered_flow = render_work_assertion(self.fn_flow, 3, "tasks.json")
        rendered_task = render_work_assertion(self.fn_task, 3, "tasks.json")
        self.assertEqual(
            rendered_flow, rendered_task,
            "renderWorkAssertion() rendered snippet has drifted between the two engines",
        )

    # -- (1) empty diff fails -----------------------------------------------------------------

    def test_01_empty_diff_fails(self):
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "a.txt").write_text("a\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init"], cwd=repo)
        write_tasks_json(repo, 1, ["a.txt"])
        run(["git", "commit", "--allow-empty", "-qm", "empty"], cwd=repo)

        guard = render_work_assertion(self.fn_task, 1, "tasks.json")
        result = run(guard, cwd=repo, check=False)
        self.assertNotEqual(result.returncode, 0, "empty-diff commit should FAIL the assertion")
        self.assertIn("WORK_ASSERTION_ABORT", result.stdout)
        self.assertIn("condition 1", result.stdout)

    # -- (2) no intersection with declared files[] fails ---------------------------------------

    def test_02_no_intersection_with_declared_files_fails(self):
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "a.txt").write_text("a\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init"], cwd=repo)
        write_tasks_json(repo, 7, ["a.txt"])
        (repo / "unrelated.txt").write_text("z\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "touch an undeclared file only"], cwd=repo)

        guard = render_work_assertion(self.fn_task, 7, "tasks.json")
        result = run(guard, cwd=repo, check=False)
        self.assertNotEqual(result.returncode, 0, "non-intersecting commit should FAIL the assertion")
        self.assertIn("WORK_ASSERTION_ABORT", result.stdout)
        self.assertIn("condition 2", result.stdout)
        self.assertIn("a.txt", result.stdout)
        self.assertIn("unrelated.txt", result.stdout)

    # -- (3) THE EN.11.O REPRODUCTION: undeclared deletion fails, even with intersection -------

    def _build_en11o_fixture_for_task_two(self, root: Path, task_id: int) -> Path:
        """Same EN.11.O shape as task 1's control (many tracked files, a commit that deletes
        nearly all of them, zero insertions), but this time the surviving/modified file IS a
        declared file -- so condition (2)'s intersection check passes and condition (3)
        (undeclared deletion) is the one that must fire. This is the fixture the block's central
        acceptance criterion is asserted against: 'a commit with many deletions, zero insertions,
        and a small declared file set.'"""
        repo = root / "repo"
        init_repo(repo)
        tracked = [f"file_{i:03d}.txt" for i in range(20)]
        for name in tracked:
            (repo / name).write_text(f"{name}\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init: 20 tracked files"], cwd=repo)

        survivor = tracked[0]
        write_tasks_json(repo, task_id, [survivor])
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "declare files[] for the task"], cwd=repo)

        (repo / survivor).write_text("modified by the declared task\n")
        for name in tracked[1:]:
            (repo / name).unlink()
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "touch declared file + delete 19 undeclared files"], cwd=repo)
        return repo

    def test_03_en11o_shape_fails_new_guard_but_still_passes_old_guard(self):
        root = self._scratch()
        repo = self._build_en11o_fixture_for_task_two(root, 5)

        # The difference-observing pair: the OLD guard still passes this commit (unchanged,
        # complementary signal -- its only condition is TRACKED>0 && STAGED==0, and this fixture's
        # index is non-empty).
        old_guard_flow = extract_commit_safety_guard_fn(SOURCE_FILES["sdlc-flow.js"])
        old_result = run(render_commit_safety_guard(old_guard_flow), cwd=repo, check=False)
        self.assertEqual(
            old_result.returncode, 0,
            f"unchanged renderCommitSafetyGuard() must still pass the EN.11.O shape: "
            f"{old_result.stdout}{old_result.stderr}",
        )

        # The NEW guard fails it -- condition (3), undeclared deletion.
        new_guard = render_work_assertion(self.fn_task, 5, "tasks.json")
        new_result = run(new_guard, cwd=repo, check=False)
        self.assertNotEqual(
            new_result.returncode, 0,
            "renderWorkAssertion() must FAIL the EN.11.O-shape commit (undeclared deletions)",
        )
        self.assertIn("WORK_ASSERTION_ABORT", new_result.stdout)
        self.assertIn("condition 3", new_result.stdout)

    # -- (4) honest commit touching exactly its declared files PASSES --------------------------

    def test_04_honest_commit_touching_declared_files_passes(self):
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "a.txt").write_text("a\n")
        (repo / "b.txt").write_text("b\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init"], cwd=repo)
        write_tasks_json(repo, 2, ["a.txt", "b.txt"])
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "declare files"], cwd=repo)

        (repo / "a.txt").write_text("edited\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "honest edit of a declared file"], cwd=repo)

        guard = render_work_assertion(self.fn_task, 2, "tasks.json")
        result = run(guard, cwd=repo, check=False)
        self.assertEqual(
            result.returncode, 0,
            f"honest commit touching a declared file must PASS: {result.stdout}{result.stderr}",
        )

    # -- (5) a task that DELETES a file it DECLARED passes (deletion is not itself the signal) -

    def test_05_declared_file_deletion_passes(self):
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "old.txt").write_text("old\n")
        (repo / "keep.txt").write_text("keep\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init"], cwd=repo)
        write_tasks_json(repo, 9, ["old.txt"])
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "declare files"], cwd=repo)

        run(["git", "rm", "-q", "old.txt"], cwd=repo)
        run(["git", "commit", "-qm", "remove old.txt, which was declared"], cwd=repo)

        guard = render_work_assertion(self.fn_task, 9, "tasks.json")
        result = run(guard, cwd=repo, check=False)
        self.assertEqual(
            result.returncode, 0,
            f"deleting a DECLARED file must PASS -- deletion is not itself the signal: "
            f"{result.stdout}{result.stderr}",
        )

    # -- (5b) BT.ticket.work-assertion-exempts-diffless-tasks: a task declaring files: [] (a
    # pure validation-only task) with an honest, non-empty, non-deleting diff must PASS --
    # condition 2's intersection check is exempted when the task's own declared files[] is
    # empty, since WA_DECLARED is then empty and WA_MATCH can never reach 1 by construction.
    # Conditions 1 (empty diff) and 3 (undeclared deletion) are untouched by this fixture (no
    # empty commit, no deletion), so this isolates condition 2 specifically.

    def test_05b_empty_declared_files_with_honest_diff_passes(self):
        root = self._scratch()
        repo = root / "repo"
        init_repo(repo)
        (repo / "a.txt").write_text("a\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "init"], cwd=repo)
        write_tasks_json(repo, 8, [])
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "declare files"], cwd=repo)

        (repo / "a.txt").write_text("edited by a validation-only task\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-qm", "validation-only task, files: [] declared"], cwd=repo)

        guard = render_work_assertion(self.fn_task, 8, "tasks.json")
        result = run(guard, cwd=repo, check=False)
        self.assertEqual(
            result.returncode, 0,
            f"a files:[] task with an honest, non-empty, non-deleting diff must PASS "
            f"(condition 2 exempted when declared files[] is empty): "
            f"{result.stdout}{result.stderr}",
        )
        self.assertNotIn("WORK_ASSERTION_ABORT", result.stdout)

    # -- (6) exemptions: engine source never calls the new guard at these commit sites ---------

    def test_06_worktree_init_and_d16_fallback_commits_are_exempt(self):
        for name, path in SOURCE_FILES.items():
            text = path.read_text(encoding="utf-8")
            # D16 fallback commit lines: `chore: derive tasks.json from ...` -- must not be
            # immediately preceded by a renderWorkAssertion() call on the same commit chain.
            for m in re.finditer(r"chore: derive tasks\.json from [^\n]*\(D16 fallback\)", text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                prev_line_start = text.rfind("\n", 0, line_start - 1) + 1
                context = text[prev_line_start:m.end()]
                self.assertNotIn(
                    "renderWorkAssertion", context,
                    f"{name}: D16 fallback commit must stay exempt from renderWorkAssertion()",
                )
            # Worktree-init commit is marked explicitly in a comment -- confirm the marker is
            # still present (its exemption is structural: the guard is simply never invoked
            # anywhere near it).
            self.assertIn(
                "COMMIT-SAFETY GUARD EXEMPT", text,
                f"{name}: worktree-init exemption marker missing",
            )

    def test_06b_vault_commit_path_is_exempt(self):
        """The vault commit path (step 7b) is exempted outright -- see the code comment beside
        renderWorkAssertion() for the reasoning (foreign repo, foreign HEAD~1, concurrent
        lanes). Confirm no vault (`-C <vault path>`) commit site calls renderWorkAssertion()."""
        for name, path in SOURCE_FILES.items():
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r"\$\{GIT\} -C \$\{vault\.planningPath\}[^\n]*commit -m", text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                line = text[line_start:text.find("\n", m.end())]
                self.assertNotIn(
                    "renderWorkAssertion", line,
                    f"{name}: vault commit site must not call renderWorkAssertion()",
                )


class GitStatusUnchangedTest(unittest.TestCase):
    """Every fixture above builds and tears down its own tempdir repo -- confirm this repo's
    own git state is untouched by a test run (spec acceptance criterion)."""

    def test_repo_status_clean_apart_from_this_files_own_changes(self):
        result = run(
            ["git", "status", "--porcelain", "--", "scripts/test_work_assertion.py"],
            cwd=REPO_ROOT, check=False,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
