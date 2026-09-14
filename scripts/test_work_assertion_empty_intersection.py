#!/usr/bin/env python3
"""Fixture suite for BT.ticket.work-assertion-cannot-express-a-correct-empty-intersection.

Task 1 of this spec (THIS FILE): write the failing gate first, against the UNCHANGED
`renderWorkAssertion()` in `.claude/workflows/sdlc-task.js` (current signature
`renderWorkAssertion(gitCmd = 'git', taskNum, tasksJsonPath)`, lines 434-443), and record the
real RED output. No engine file is touched by this task -- that is tasks 3 and 4's job, and this
suite is the contract they must satisfy.

WHY THIS EXISTS (see the block record's `why`)
-----------------------------------------------
`renderWorkAssertion()` renders a bash check the agent runs after committing a task: it aborts
(`WORK_ASSERTION_ABORT`, non-zero exit) whenever the commit's `git diff --name-status HEAD~1 HEAD`
is empty, or shares no path with the task's declared `files[]`. Measured 2026-09-08 in three
different shapes (full citations in the block record's `why`): a genuinely-correct no-op task
BAILED; the identical no-op shape reached via `--resume` PASSED; and a task whose real fix landed
entirely in a sync-manifest sibling of a declared file (a SKILL.md replication guide, a
`docs/workflows/*.md` page) BAILED even though the work was correct and complete. A gate that
reaches a different verdict on identical logical work, depending only on which code path evaluates
it, is not a strict gate -- it is an inconsistent one.

FIVE CASES, EXTRACTED VERBATIM FROM THE REAL ENGINE
----------------------------------------------------
Never re-typed: `render_work_assertion_script()` pulls the real `renderWorkAssertion` function
body out of the target engine file via balanced-brace scanning (the same idiom
`scripts/test_bail_path_runtime.py` uses), calls it through a real `node` process with the exact
arguments a case needs, and executes the resulting bash string in a real `mktemp`-rooted git
sandbox -- never a shared or real repo path.

  1. DECLARED NO-OP        -- `tasks.json` marks the task `expect_no_diff: true`; the sandbox's
                              task commit is empty. TODAY: hits condition (1) ("commit diff is
                              EMPTY") and aborts -- RED, must eventually PASS.
  2. SIBLING-ONLY DIFF      -- the task declares `.claude/workflows/sdlc-task.js`; the sandbox
                              commit touches only `.agents/skills/sdlc-task/SKILL.md`, a real
                              sibling per `scripts/skill_sync_manifest.json`'s
                              `.claude/workflows/sdlc-task.js::isolation-and-branch-naming` entry.
                              TODAY: hits condition (2) (no declared-file match) and aborts -- RED.
  3. UNDECLARED GENUINE NO-OP (the regression control) -- no `expect_no_diff`, empty diff. Must
                              ABORT both before and after the fix. Asserted as PASS (i.e. the
                              suite's own assertion that it correctly aborts already succeeds
                              today) so a later task cannot silently weaken the gate to accept
                              everything and still turn this suite green.
  4. FRESH-VS-RESUME CONSISTENCY -- two sandboxes carry the IDENTICAL task-3 diff (same declared
                              file, same content), but sandbox B has one extra "wrap-up" commit
                              landing ON TOP of the task's own commit before the assertion runs
                              (the resume-time reconcile-commit shape named in the block's `why`
                              instance 2). Because today's check hardcodes the literal `HEAD~1`,
                              sandbox A's `HEAD~1` correctly isolates the task's own commit while
                              sandbox B's `HEAD~1` now isolates the WRAP-UP commit instead --
                              same underlying work, different verdict. TODAY: A passes, B aborts --
                              RED, must converge once the check is bounded by a persisted prevSha
                              rather than a literal offset.
  5. DIRECTORY-PREFIX MATCH -- the task declares a directory (`scripts/fixtures/bail_meta/`); the
                              sandbox commit adds a file under it. TODAY: condition (2)'s match is
                              `grep -qFx` (exact whole-line match only), so a directory entry never
                              matches a file beneath it -- RED.

Run today (unmodified `.claude/workflows/sdlc-task.js`): this module's overall process exits
non-zero, naming cases 1, 2, 4, 5 FAIL. Case 3 (the regression control) reports PASS, and must
keep reporting PASS after every later task in this spec -- a change that turns 1, 2, 4, 5 green by
also loosening case 3 has removed the gate rather than fixed it.

Registered in planning/harness.json (task 6) as a new gated check --
run directly: python3 scripts/test_work_assertion_empty_intersection.py [engine-file]

TASK 4 (D83 parity): the five cases above are parameterized over BOTH engines --
`.claude/workflows/sdlc-task.js` and `.claude/workflows/sdlc-flow.js` -- run automatically, with
no CLI argument, as two independent `unittest.TestCase` subclasses sharing one mixin. Passing an
explicit engine-file argument narrows the run to that one engine only (unchanged from tasks 1-3).
A third, engine-independent check (`ParityTests`) extracts both real files' own
`<<shared:renderWorkAssertion>>` ... `<</shared:renderWorkAssertion>>` regions (the exact function
body, via the same balanced-brace scan) and asserts they are byte-identical text, printing a
unified diff when they are not -- this is what the marker comment's own "shared" contract means,
and it must hold regardless of which engine-file argument (if any) was passed on the command line.

Note (task 3 fix pass, 2026-09-13): case 2's sibling entries live in `SKILL_MANIFEST` /
`DOCS_MANIFEST` (scripts/skill_sync_manifest.json, scripts/engine_docs_sync_manifest.json) --
this task's own edits to `.claude/workflows/sdlc-task.js` shifted the load-bearing anchors those
manifests track (their content, not their line ranges, is what this suite's sibling lookup
actually reads via `skill_md`/`docs_md`, so the shift itself does not change what counts as a
sibling). The anchors were re-picked from CONTENT via `check_skill_sync.py --relocate` and a
byte-identical relocation of `check_engine_docs_sync.py`'s ANCHORS table, both manifests
re-stamped, and `scripts/test_engines_pass_agent.py`'s FROZEN_BASELINE re-pinned to the same three
invocation sites at their new line numbers -- content unchanged in every case, confirmed by each
tool's own drift/hash check before and after.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TASK_ENGINE = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"
FLOW_ENGINE = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"
DEFAULT_ENGINE = TASK_ENGINE  # kept for callers/imports written against tasks 1-3
SKILL_MANIFEST = REPO_ROOT / "scripts" / "skill_sync_manifest.json"
DOCS_MANIFEST = REPO_ROOT / "scripts" / "engine_docs_sync_manifest.json"

# Environment variables the fleet's own git-safety convention (commit-in-this-fleet skill, and
# every git invocation in this repo's SDLC engines) strips before any git command that must
# operate on a repo OTHER than whatever ambient repo the current process happens to be inside --
# our sandboxes are throwaway repos under mktemp, and must never inherit a stray GIT_DIR etc.
# pointing somewhere else.
GIT_ISOLATION_VARS = [
    "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE", "GIT_PREFIX", "GIT_CEILING_DIRECTORIES",
]


def _resolve_target_engines() -> list:
    """Accepts an optional CLI arg naming ONE engine file to test, narrowing the run to just it
    (the behavior tasks 1-3 relied on). With NO argument, the suite exercises BOTH real engines --
    sdlc-task.js and sdlc-flow.js -- since identical cases must pass identically on each (D83
    parity). Pops the arg out of sys.argv first so unittest.main() never sees an argument it
    doesn't understand."""
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        raw = sys.argv.pop(1)
        candidate = Path(raw)
        return [candidate if candidate.is_absolute() else (REPO_ROOT / raw)]
    return [TASK_ENGINE, FLOW_ENGINE]


TARGET_ENGINES = _resolve_target_engines()


def _sandbox_env() -> dict:
    env = dict(os.environ)
    for var in GIT_ISOLATION_VARS:
        env.pop(var, None)
    return env


# ----------------------------------------------------------------------------
# Extraction -- pull the real renderWorkAssertion() source, never re-typed. Mirrors
# scripts/test_bail_path_runtime.py's extract_function() idiom exactly.
# ----------------------------------------------------------------------------

def read_source(engine_path: Path) -> str:
    return engine_path.read_text(encoding="utf-8")


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


def extract_render_work_assertion(engine_path: Path) -> str:
    return extract_function(read_source(engine_path), "renderWorkAssertion")


def render_work_assertion_script(
    engine_path: Path, git_cmd: str, task_num: int, tasks_json_path: str, prev_sha: str = None,
) -> str:
    """Calls the REAL, unmodified renderWorkAssertion() (extracted from engine_path) through a
    real `node` process with the given arguments, and returns the bash script string it produces.
    Never re-types the shell logic -- only ever executes the function's own return value.

    `prev_sha`, when given, is the persisted commit the assertion's range should start from (the
    previous task's own recorded commit, or the run's base_sha for task 1) -- omitting it exercises
    the pre-fix/no-caller-context fallback to a literal `HEAD~1`."""
    fn_src = extract_render_work_assertion(engine_path)
    prev_sha_arg = json.dumps(prev_sha) if prev_sha else "undefined"
    node_script = (
        fn_src
        + "\n"
        + f"process.stdout.write(renderWorkAssertion({json.dumps(git_cmd)}, {task_num}, {json.dumps(tasks_json_path)}, {prev_sha_arg}))\n"
    )
    result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"node failed to render the work-assertion script:\n{result.stderr}")
    return result.stdout


# ----------------------------------------------------------------------------
# Sandbox helpers -- a real, throwaway git repo per case, under mktemp, never a shared path.
# ----------------------------------------------------------------------------

def git(sandbox: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=sandbox, capture_output=True, text=True, env=_sandbox_env(),
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {sandbox}:\n{result.stderr}")
    return result.stdout


def run_bash(sandbox: Path, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script], cwd=sandbox, capture_output=True, text=True, env=_sandbox_env(),
    )


def init_sandbox(tmp_root: Path) -> Path:
    sandbox = Path(tempfile.mkdtemp(prefix="wa_sandbox_", dir=str(tmp_root)))
    git(sandbox, "init", "-q")
    git(sandbox, "config", "user.email", "wa-test@example.com")
    git(sandbox, "config", "user.name", "Work Assertion Test")
    return sandbox


def write_tasks_json(sandbox: Path, tasks: list) -> str:
    (sandbox / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
    return "tasks.json"


def commit_all(sandbox: Path, message: str) -> None:
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-q", "--allow-empty", "-m", message)


def copy_sync_manifests(sandbox: Path) -> None:
    """Copies the two real sync manifests into the sandbox at the same repo-relative path the
    fixed engine reads them from (relative to the run root / CWD, matching how tasksJsonPath is
    already resolved). Needed for case 2's sibling-scope check to have real manifest data once the
    fix (task 3) consults it; harmless for the other cases."""
    scripts_dir = sandbox / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    if SKILL_MANIFEST.exists():
        shutil.copy(SKILL_MANIFEST, scripts_dir / "skill_sync_manifest.json")
    if DOCS_MANIFEST.exists():
        shutil.copy(DOCS_MANIFEST, scripts_dir / "engine_docs_sync_manifest.json")


class WorkAssertionCasesMixin:
    """The five cases, written once against `self.engine_path` -- set by each concrete
    per-engine subclass below, never by this mixin itself (it carries no engine_path and is never
    instantiated directly; unittest only collects unittest.TestCase subclasses)."""

    engine_path: Path

    def setUp(self) -> None:
        self._tmp_root = tempfile.mkdtemp(prefix="wa_root_")
        self.addCleanup(shutil.rmtree, self._tmp_root, ignore_errors=True)

    def _sandbox(self) -> Path:
        return init_sandbox(Path(self._tmp_root))

    # ------------------------------------------------------------------
    # Case 1: a declared no-op must pass.
    # ------------------------------------------------------------------
    def test_case1_declared_no_op_passes(self):
        sandbox = self._sandbox()
        tasks_json_rel = write_tasks_json(sandbox, [
            {"task_id": 1, "files": [".claude/workflows/sdlc-task.js"], "expect_no_diff": True},
        ])
        commit_all(sandbox, "base: seed tasks.json")
        commit_all(sandbox, "task 1: verified already satisfied, no diff")

        script = render_work_assertion_script(self.engine_path, "git", 1, tasks_json_rel)
        result = run_bash(sandbox, script)

        self.assertEqual(
            result.returncode, 0,
            "a task declared expect_no_diff:true with a genuinely empty diff must PASS the work "
            f"assertion, not be indistinguishable from a task that simply did nothing -- got exit "
            f"{result.returncode}:\n{result.stdout}{result.stderr}",
        )

    # ------------------------------------------------------------------
    # Case 2: a sync-manifest sibling of a declared file must satisfy scope.
    # ------------------------------------------------------------------
    def test_case2_sibling_only_diff_passes(self):
        sandbox = self._sandbox()
        tasks_json_rel = write_tasks_json(sandbox, [
            {"task_id": 1, "files": [".claude/workflows/sdlc-task.js"]},
        ])
        copy_sync_manifests(sandbox)
        skill_dir = sandbox / ".agents" / "skills" / "sdlc-task"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text("v1 -- guide body\n", encoding="utf-8")
        commit_all(sandbox, "base: seed tasks.json, manifests, skill guide")

        # Task 1's own commit touches ONLY the sibling skill guide, never the declared engine file
        # itself -- the shape of BT.ticket.sdlc-flow-records-no-base-sha task 2's real bail.
        (skill_dir / "SKILL.md").write_text("v2 -- re-verified per sync manifest\n", encoding="utf-8")
        commit_all(sandbox, "task 1: re-stamp sdlc-task SKILL.md per sync manifest")

        script = render_work_assertion_script(self.engine_path, "git", 1, tasks_json_rel)
        result = run_bash(sandbox, script)

        self.assertEqual(
            result.returncode, 0,
            "a commit landing only in a declared file's sync-manifest sibling "
            "(.agents/skills/sdlc-task/SKILL.md is a real sibling of "
            ".claude/workflows/sdlc-task.js per scripts/skill_sync_manifest.json) must PASS -- "
            f"got exit {result.returncode}:\n{result.stdout}{result.stderr}",
        )

    # ------------------------------------------------------------------
    # Case 3 (the regression control): an undeclared genuine no-op must always BAIL.
    # ------------------------------------------------------------------
    def test_case3_undeclared_no_op_still_bails_regression_control(self):
        sandbox = self._sandbox()
        tasks_json_rel = write_tasks_json(sandbox, [
            {"task_id": 1, "files": [".claude/workflows/sdlc-task.js"]},
        ])
        commit_all(sandbox, "base: seed tasks.json")
        commit_all(sandbox, "task 1: did nothing, no declaration")

        script = render_work_assertion_script(self.engine_path, "git", 1, tasks_json_rel)
        result = run_bash(sandbox, script)

        self.assertNotEqual(
            result.returncode, 0,
            "a task with NO expect_no_diff declaration and a genuinely empty diff must still BAIL "
            "-- this is the regression control; a fix that also makes this pass has weakened the "
            f"gate rather than fixed it. Got exit 0 with output:\n{result.stdout}{result.stderr}",
        )
        self.assertIn(
            "WORK_ASSERTION_ABORT", result.stdout,
            f"expected a WORK_ASSERTION_ABORT diagnostic, got:\n{result.stdout}{result.stderr}",
        )

    # ------------------------------------------------------------------
    # Case 4 (load-bearing): fresh vs. resume must reach the SAME verdict on identical work.
    # ------------------------------------------------------------------
    def test_case4_fresh_vs_resume_consistency(self):
        declared_files = [
            {"task_id": 3, "files": ["scripts/foo.py"]},
        ]

        # Sandbox A ("fresh"): exactly one commit separates task 2's final state from task 3's own
        # commit. The assertion is bounded by the PERSISTED prevSha (task 2's own recorded commit)
        # rather than a literal 'HEAD~1', which happens to coincide with it here.
        sandbox_a = self._sandbox()
        tasks_json_a = write_tasks_json(sandbox_a, declared_files)
        commit_all(sandbox_a, "task 2: final state")
        prev_sha_a = git(sandbox_a, "rev-parse", "HEAD").strip()
        (sandbox_a / "scripts").mkdir(parents=True, exist_ok=True)
        (sandbox_a / "scripts" / "foo.py").write_text("print('hi')\n", encoding="utf-8")
        commit_all(sandbox_a, "task 3: add foo.py")
        script_a = render_work_assertion_script(self.engine_path, "git", 3, tasks_json_a, prev_sha_a)
        result_a = run_bash(sandbox_a, script_a)

        # Sandbox B ("resume, with a wrap-up commit landing on top"): the IDENTICAL task-3 diff,
        # but a synthetic reconcile/wrap-up commit lands AFTER task 3's own commit, before the
        # assertion runs. Bounding the range by the SAME persisted prevSha (task 2's own recorded
        # commit -- unaffected by the wrap-up commit landing on top) is what makes A and B converge;
        # a literal 'HEAD~1' would instead isolate the wrap-up commit's diff in B, not task 3's.
        sandbox_b = self._sandbox()
        tasks_json_b = write_tasks_json(sandbox_b, declared_files)
        commit_all(sandbox_b, "task 2: final state")
        prev_sha_b = git(sandbox_b, "rev-parse", "HEAD").strip()
        (sandbox_b / "scripts").mkdir(parents=True, exist_ok=True)
        (sandbox_b / "scripts" / "foo.py").write_text("print('hi')\n", encoding="utf-8")
        commit_all(sandbox_b, "task 3: add foo.py")
        (sandbox_b / "unrelated.txt").write_text("resume-time reconcile note\n", encoding="utf-8")
        commit_all(sandbox_b, "chore: wrap-up commit landed on top of task 3")
        script_b = render_work_assertion_script(self.engine_path, "git", 3, tasks_json_b, prev_sha_b)
        result_b = run_bash(sandbox_b, script_b)

        self.assertEqual(
            result_a.returncode, result_b.returncode,
            "the IDENTICAL task-3 diff must reach the SAME verdict whether or not a wrap-up/"
            "resume commit landed on top of it before the assertion ran -- fresh (A) exit="
            f"{result_a.returncode} output={result_a.stdout!r}, with-wrap-up (B) exit="
            f"{result_b.returncode} output={result_b.stdout!r}. A gate whose verdict tracks the "
            "code path rather than the work is the defect this block exists to fix.",
        )

    # ------------------------------------------------------------------
    # Case 5: a directory entry in files[] must match as a prefix.
    # ------------------------------------------------------------------
    def test_case5_directory_prefix_match_passes(self):
        sandbox = self._sandbox()
        tasks_json_rel = write_tasks_json(sandbox, [
            {"task_id": 1, "files": ["scripts/fixtures/bail_meta/"]},
        ])
        commit_all(sandbox, "base: seed tasks.json")
        fixture_dir = sandbox / "scripts" / "fixtures" / "bail_meta" / "work_assertion"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        (fixture_dir / "case1.json").write_text("{}\n", encoding="utf-8")
        commit_all(sandbox, "task 1: add recovered fixture")

        script = render_work_assertion_script(self.engine_path, "git", 1, tasks_json_rel)
        result = run_bash(sandbox, script)

        self.assertEqual(
            result.returncode, 0,
            "a files[] entry that names a directory ('scripts/fixtures/bail_meta/') must match "
            "any changed path beneath it as a prefix, not only via exact whole-line equality -- "
            f"got exit {result.returncode}:\n{result.stdout}{result.stderr}",
        )


# ----------------------------------------------------------------------------
# Parameterization -- one concrete unittest.TestCase per target engine, sharing the mixin's five
# case methods verbatim. Built dynamically from TARGET_ENGINES so a narrowing CLI arg (tasks 1-3's
# existing behavior) still runs exactly one class, while the no-arg default runs both engines.
# ----------------------------------------------------------------------------

def _engine_class_suffix(engine_path: Path) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", engine_path.stem).strip("_") or "engine"


_ENGINE_TEST_CLASSES = {}
for _engine in TARGET_ENGINES:
    _cls_name = f"WorkAssertionEmptyIntersectionTests_{_engine_class_suffix(_engine)}"
    _ENGINE_TEST_CLASSES[_cls_name] = type(
        _cls_name,
        (WorkAssertionCasesMixin, unittest.TestCase),
        {"engine_path": _engine, "__doc__": f"Exercises renderWorkAssertion() from {_engine}."},
    )
globals().update(_ENGINE_TEST_CLASSES)


# ----------------------------------------------------------------------------
# Parity (task 4, D83): the two real engines' <<shared:renderWorkAssertion>> regions must be
# byte-identical text -- that identity is the marker comment's own contract. Engine-independent of
# any CLI narrowing above; always compares the two real on-disk files.
# ----------------------------------------------------------------------------

def extract_shared_marker_block(engine_path: Path, marker: str) -> str:
    text = read_source(engine_path)
    open_marker = f"// <<shared:{marker}>>"
    close_marker = f"// <</shared:{marker}>>"
    start = text.index(open_marker) + len(open_marker)
    end = text.index(close_marker, start)
    return text[start:end]


class ParityTests(unittest.TestCase):
    """D83 parity: sdlc-task.js and sdlc-flow.js must carry a byte-identical
    <<shared:renderWorkAssertion>> region, regardless of which engine(s) the rest of this run was
    narrowed to via an explicit CLI argument."""

    def test_shared_render_work_assertion_block_is_byte_identical_across_engines(self):
        task_block = extract_shared_marker_block(TASK_ENGINE, "renderWorkAssertion")
        flow_block = extract_shared_marker_block(FLOW_ENGINE, "renderWorkAssertion")
        if task_block != flow_block:
            import difflib

            diff = "".join(difflib.unified_diff(
                task_block.splitlines(keepends=True),
                flow_block.splitlines(keepends=True),
                fromfile=str(TASK_ENGINE),
                tofile=str(FLOW_ENGINE),
            ))
            self.fail(
                "the <<shared:renderWorkAssertion>> regions of sdlc-task.js and sdlc-flow.js have "
                f"diverged (D83 parity broken):\n{diff}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
