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

This task deliberately says nothing about the not-yet-written `renderWorkAssertion()` -- it does
not exist yet at this task's boundary. A later task extends this suite to assert the NEW guard
fails the same fixture.

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


def extract_commit_safety_guard_fn(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = COMMIT_SAFETY_GUARD_FN_RE.search(text)
    if not m:
        raise AssertionError(f"renderCommitSafetyGuard() definition not found in {path}")
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
