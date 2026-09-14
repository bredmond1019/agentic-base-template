#!/usr/bin/env python3
"""Fixture suite for BT.ticket.work-assertion-cannot-express-a-correct-empty-intersection.

Task 1 of this spec (THIS FILE): write the failing gate first, against the UNCHANGED
`renderWorkAssertion()` in `.claude/workflows/sdlc-task.js`, and record the real RED output. No
engine `.js` file is touched by this task -- that is task 3's (and, for `sdlc-flow.js`, task 4's)
job, and this suite is the contract those tasks must satisfy.

WHY THIS EXISTS (see the block record's `why`)
-----------------------------------------------
The post-commit work assertion (`renderWorkAssertion`, `.claude/workflows/sdlc-task.js` around
line 435) treats an empty intersection between a task's committed diff and its declared
`files[]` as "work not done" unconditionally. That reading is wrong in at least three measured
shapes: a task whose CORRECT outcome is no diff at all (a read-back/verification task), a diff
that legitimately lands only in a sync-manifest SIBLING of a declared file (a SKILL.md
replication guide, a docs mirror), and a directory entry in `files[]` that should match anything
under it. A fourth defect is that the assertion hardcodes `HEAD~1` as the commit boundary, so the
verdict for the same logical task work differs depending on whether an extra commit (a resume-time
reconcile/wrap-up commit) landed between the previous task's commit and the point the assertion is
evaluated -- the same input reaches a different answer depending on the code path, which is what
turns "strict gate" into "defect".

EXTRACTION, NOT RE-TYPING
-------------------------
`renderWorkAssertion`'s bash-generating source is pulled directly out of the target engine file by
a balanced-brace scan (the same idiom `scripts/test_bail_path_runtime.py` and
`scripts/test_bails_record.py` already use), never re-typed here. A divergence between this suite
and the real function is therefore a real divergence in behavior, not a stale copy drifting out of
sync with what the engine actually does.

TARGET ENGINE(S)
----------------
Defaults to `.claude/workflows/sdlc-task.js` (this task's scope). `WORK_ASSERTION_TARGET_ENGINES`
may override with a comma-separated list of engine filenames (e.g. for task 4's cross-engine
parity extension) -- see `TARGET_ENGINE_NAMES` below.

THE FIVE CASES, run today (unchanged `sdlc-task.js`) via `python3
scripts/test_work_assertion_empty_intersection.py`:

  1. DECLARED NO-OP           -- `expect_no_diff: true`, empty diff.        RED  (aborts today)
  2. SIBLING-ONLY DIFF        -- declared file's manifest sibling changed.  RED  (aborts today)
  3. UNDECLARED GENUINE NO-OP -- no declaration, empty diff.                PASS (correctly aborts;
                                                                              regression control --
                                                                              must never start
                                                                              passing-as-continue)
  4. FRESH-VS-RESUME          -- identical logical task diff, an extra      RED  (verdict differs
     CONSISTENCY                 commit lands after it in one sandbox.       between the sandboxes)
  5. DIRECTORY-PREFIX MATCH   -- a `files[]` directory entry, changed path  RED  (aborts today)
                                  underneath it.

The suite's own process exit code (via `unittest.main()`) is non-zero today because cases 1, 2, 4,
5 fail their PASS assertions; case 3 is written as a regression control and correctly reports PASS
both today and after the fix -- a future change that makes case 3 also "pass by no longer
aborting" is REMOVING the gate, not fixing it, and must fail this suite's own control assertion.

Registered in planning/harness.json (task 6 of this spec) as a new gated check once the fix lands.
Run directly: python3 scripts/test_work_assertion_empty_intersection.py [--engine <path>]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ENGINE = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"

# Task 4 extends this to run every case against BOTH sdlc-task.js and sdlc-flow.js. This task
# (task 1) only targets sdlc-task.js. Overridable via WORK_ASSERTION_TARGET_ENGINES (comma
# separated filenames relative to .claude/workflows/) purely so a later task can parameterize
# without editing this constant by hand.
_ENV_OVERRIDE = os.environ.get("WORK_ASSERTION_TARGET_ENGINES", "").strip()
if _ENV_OVERRIDE:
    TARGET_ENGINES = [REPO_ROOT / ".claude" / "workflows" / name.strip() for name in _ENV_OVERRIDE.split(",")]
else:
    TARGET_ENGINES = [DEFAULT_ENGINE]


# ----------------------------------------------------------------------------
# Extraction -- pull the real `renderWorkAssertion` source, never re-typed. Mirrors
# scripts/test_bail_path_runtime.py's extraction idiom exactly.
# ----------------------------------------------------------------------------

def extract_function(text: str, name: str) -> str:
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


def render_work_assertion_src(engine_path: Path) -> str:
    text = engine_path.read_text(encoding="utf-8")
    return extract_function(text, "renderWorkAssertion")


def build_assertion_bash(engine_path: Path, git_cmd: str, task_num: int, tasks_json_path: str) -> str:
    """Calls the engine's OWN, unmodified renderWorkAssertion() via node and returns the bash
    string it renders -- the exact text a live sdlc-task/sdlc-flow run would execute."""
    fn_src = render_work_assertion_src(engine_path)
    node_script = f"""
{fn_src}
process.stdout.write(renderWorkAssertion({json.dumps(git_cmd)}, {task_num}, {json.dumps(tasks_json_path)}))
"""
    result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"failed to render work assertion via node:\n{result.stderr}")
    return result.stdout


def run_assertion(sandbox: Path, engine_path: Path, task_num: int,
                   tasks_json_path: str = "tasks.json", git_cmd: str = "git") -> subprocess.CompletedProcess:
    bash_script = build_assertion_bash(engine_path, git_cmd, task_num, tasks_json_path)
    return subprocess.run(["bash", "-c", bash_script], cwd=sandbox, capture_output=True, text=True)


# ----------------------------------------------------------------------------
# Sandbox helpers -- a real `mktemp -d` git repo per case, never a shared/real repo path.
# ----------------------------------------------------------------------------

def git(sandbox: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=sandbox, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {sandbox}:\n{result.stderr}")
    return result


def init_repo(sandbox: Path) -> None:
    git(sandbox, "init", "-q")
    git(sandbox, "config", "user.email", "wa-test@example.com")
    git(sandbox, "config", "user.name", "WA Test")


def write_file(sandbox: Path, relpath: str, content: str) -> None:
    path = sandbox / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def commit(sandbox: Path, message: str, allow_empty: bool = False) -> str:
    git(sandbox, "add", "-A")
    args = ["commit", "-q", "-m", message]
    if allow_empty:
        args.insert(1, "--allow-empty")
    git(sandbox, *args)
    return git(sandbox, "rev-parse", "HEAD").stdout.strip()


def write_tasks_json(sandbox: Path, tasks: list, filename: str = "tasks.json") -> None:
    write_file(sandbox, filename, json.dumps(tasks))


# ----------------------------------------------------------------------------
# Test cases
# ----------------------------------------------------------------------------

class WorkAssertionEmptyIntersectionTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # Case 1: DECLARED NO-OP -- expect_no_diff: true, empty HEAD~1..HEAD diff.
    # Today: hits condition (1) "commit diff is EMPTY" and ABORTS. Must PASS once the
    # engine reads expect_no_diff and skips condition (1) for it.
    # ------------------------------------------------------------------
    def test_declared_no_op_passes(self):
        for engine_path in TARGET_ENGINES:
            with tempfile.TemporaryDirectory() as tmp:
                sandbox = Path(tmp)
                init_repo(sandbox)
                write_file(sandbox, "a.txt", "baseline\n")
                commit(sandbox, "baseline commit")
                # Task 1's own commit: genuinely no diff -- the correct outcome for a
                # read-back/verification task whose ACs were already satisfied.
                commit(sandbox, "task 1: verification only, no change needed", allow_empty=True)
                write_tasks_json(sandbox, [
                    {"task_id": 1, "files": [], "expect_no_diff": True},
                ])
                result = run_assertion(sandbox, engine_path, task_num=1)
                self.assertEqual(
                    result.returncode, 0,
                    f"{engine_path.name}: a task declaring expect_no_diff=true with a genuinely "
                    f"empty diff must PASS the work assertion, not be indistinguishable from a "
                    f"task that simply did nothing. stdout={result.stdout!r}",
                )

    # ------------------------------------------------------------------
    # Case 2: SIBLING-ONLY DIFF -- declared file's real sync-manifest sibling changed.
    # Today: hits condition (2) "no changed path matches declared files[]" and ABORTS.
    # ------------------------------------------------------------------
    def test_sibling_only_diff_passes(self):
        declared_file = ".claude/workflows/sdlc-task.js"
        sibling_file = ".agents/skills/sdlc-task/SKILL.md"
        # Confirm this really is a sibling per the manifest this fix must read from, rather than
        # hand-picking a plausible-looking pair.
        manifest = json.loads((REPO_ROOT / "scripts" / "skill_sync_manifest.json").read_text())
        siblings = {
            entry["skill_md"] for key, entry in manifest.items()
            if key.split("::", 1)[0] == declared_file
        }
        self.assertIn(sibling_file, siblings, "test fixture assumption stale against the manifest")

        for engine_path in TARGET_ENGINES:
            with tempfile.TemporaryDirectory() as tmp:
                sandbox = Path(tmp)
                init_repo(sandbox)
                write_file(sandbox, declared_file, "// baseline engine text\n")
                write_file(sandbox, sibling_file, "baseline skill guide\n")
                commit(sandbox, "baseline commit")
                write_file(sandbox, sibling_file, "updated skill guide reflecting the engine change\n")
                commit(sandbox, "task 1: re-stamp SKILL.md sibling")
                write_tasks_json(sandbox, [
                    {"task_id": 1, "files": [declared_file]},
                ])
                result = run_assertion(sandbox, engine_path, task_num=1)
                self.assertEqual(
                    result.returncode, 0,
                    f"{engine_path.name}: a diff landing only in a declared file's registered "
                    f"sync-manifest sibling must PASS -- the engines themselves require this "
                    f"re-stamp when the mirrored file changes. stdout={result.stdout!r}",
                )

    # ------------------------------------------------------------------
    # Case 3: UNDECLARED GENUINE NO-OP -- the regression control. No expect_no_diff, empty
    # diff -- must ABORT today AND after the fix. If this ever starts passing, the gate has
    # been weakened rather than fixed (see the block record's out_of_scope + testing_strategy).
    # ------------------------------------------------------------------
    def test_undeclared_genuine_no_op_still_bails(self):
        for engine_path in TARGET_ENGINES:
            with tempfile.TemporaryDirectory() as tmp:
                sandbox = Path(tmp)
                init_repo(sandbox)
                write_file(sandbox, "a.txt", "baseline\n")
                commit(sandbox, "baseline commit")
                commit(sandbox, "task 1: did nothing", allow_empty=True)
                write_tasks_json(sandbox, [
                    {"task_id": 1, "files": ["a.txt"]},
                ])
                result = run_assertion(sandbox, engine_path, task_num=1)
                self.assertNotEqual(
                    result.returncode, 0,
                    f"{engine_path.name}: REGRESSION -- a task with no expect_no_diff declaration "
                    f"and a genuinely empty diff must still BAIL. A gate that passes this has been "
                    f"weakened, not fixed. stdout={result.stdout!r}",
                )
                self.assertIn("WORK_ASSERTION_ABORT", result.stdout)

    # ------------------------------------------------------------------
    # Case 4: FRESH-VS-RESUME CONSISTENCY -- the load-bearing case. Two sandboxes carry the
    # IDENTICAL logical task-3 diff (same file, same content change), differing only in
    # whether a synthetic wrap-up/reconcile commit lands on top of task 3's own commit before
    # the assertion is evaluated (the shape a --resume path can produce). Today's hardcoded
    # `HEAD~1..HEAD` boundary means sandbox A (checked immediately after task 3's commit) and
    # sandbox B (checked after an intervening commit) reach DIFFERENT verdicts for the exact
    # same underlying task-3 work -- proving the gate tracks the code path, not the work.
    # ------------------------------------------------------------------
    def _build_task3_history(self, sandbox: Path, with_wrapup_commit: bool) -> None:
        init_repo(sandbox)
        write_file(sandbox, "src/foo.py", "# baseline\n")
        write_file(sandbox, "state.json", '{"tasks": {}}\n')
        commit(sandbox, "baseline commit")
        commit(sandbox, "task 2: unrelated prior work", allow_empty=True)
        # Task 3's own, real commit -- identical logical diff in both sandboxes.
        write_file(sandbox, "src/foo.py", "# baseline\ndef added_by_task_3(): pass\n")
        commit(sandbox, "task 3: add added_by_task_3")
        if with_wrapup_commit:
            # A resume-time reconcile/wrap-up commit landing AFTER task 3's own commit --
            # e.g. state.json bookkeeping written when the engine resumes. It touches a file
            # that is NOT among task 3's declared files.
            write_file(sandbox, "state.json", '{"tasks": {"3": {"status": "done"}}}\n')
            commit(sandbox, "chore: resume bookkeeping (state.json)")
        write_tasks_json(sandbox, [
            {"task_id": 3, "files": ["src/foo.py"]},
        ])

    def test_fresh_vs_resume_consistency(self):
        for engine_path in TARGET_ENGINES:
            with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
                sandbox_a = Path(tmp_a)
                sandbox_b = Path(tmp_b)
                self._build_task3_history(sandbox_a, with_wrapup_commit=False)
                self._build_task3_history(sandbox_b, with_wrapup_commit=True)

                result_a = run_assertion(sandbox_a, engine_path, task_num=3)
                result_b = run_assertion(sandbox_b, engine_path, task_num=3)

                self.assertEqual(
                    result_a.returncode, 0,
                    f"{engine_path.name}: the FRESH path (checked immediately after task 3's own "
                    f"commit) must PASS. stdout={result_a.stdout!r}",
                )
                self.assertEqual(
                    (result_a.returncode == 0), (result_b.returncode == 0),
                    f"{engine_path.name}: the SAME logical task-3 work reached a DIFFERENT "
                    f"verdict depending on whether a wrap-up commit landed afterward -- "
                    f"fresh returncode={result_a.returncode} stdout={result_a.stdout!r}; "
                    f"resume-shaped returncode={result_b.returncode} stdout={result_b.stdout!r}",
                )

    # ------------------------------------------------------------------
    # Case 5: DIRECTORY-PREFIX MATCH -- a files[] directory entry must match a changed path
    # underneath it. Today's exact `grep -qFx` match never matches a file under a directory
    # entry, so this ABORTS.
    # ------------------------------------------------------------------
    def test_directory_prefix_match_passes(self):
        for engine_path in TARGET_ENGINES:
            with tempfile.TemporaryDirectory() as tmp:
                sandbox = Path(tmp)
                init_repo(sandbox)
                write_file(sandbox, "a.txt", "baseline\n")
                commit(sandbox, "baseline commit")
                write_file(sandbox, "scripts/fixtures/bail_meta/work_assertion/case1.json", "{}\n")
                commit(sandbox, "task 1: add a recorded bail fixture")
                write_tasks_json(sandbox, [
                    {"task_id": 1, "files": ["scripts/fixtures/bail_meta/"]},
                ])
                result = run_assertion(sandbox, engine_path, task_num=1)
                self.assertEqual(
                    result.returncode, 0,
                    f"{engine_path.name}: a files[] directory entry must match any changed path "
                    f"underneath it as a prefix. stdout={result.stdout!r}",
                )


if __name__ == "__main__":
    unittest.main()
