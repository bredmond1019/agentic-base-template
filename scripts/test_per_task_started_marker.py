#!/usr/bin/env python3
"""Fixture suite for BT.ticket.per-task-state-write-before-implement, task 1.

WHY THIS EXISTS (see the block record's `what`/`why`)
-------------------------------------------------------
A crash between a task's commit and its normal end-of-task state write left zero record on disk
that the task ever ran (reproduced twice, 2026-09-16/17, on real engine-rs runs -- see the block
record). This task adds a per-task 'started' marker: the implement agent's OWN turn now runs a
STEP 0, BEFORE any edit or commit, that merges `tasks[N] = {status:'running', start_sha:<HEAD>,
marker_at:<UTC ISO now>}` into the run's own state file -- never a separate agent turn (that would
cost one Workflow call per task; `writeTaskState()`/`writeFlowState()` are agent turns, not disk
writes, since the Workflow runtime has no filesystem access of its own).

WHAT THIS DOES
--------------
Modelled on `scripts/test_resume_task_state_merge.py`'s structural extraction of engine code and
`scripts/test_work_assertion_empty_intersection.py` / `scripts/test_work_assertion_base_sha.py`'s
"extract the REAL function via balanced-brace scanning, evaluate it through a real `node` process,
never re-type the logic under test" idiom:

  1. `renderImplementPrompt()` is extracted verbatim from `.claude/workflows/sdlc-task.js` (the
     built/inlined copy -- see `scripts/build_engines.py`) along with the three real helper
     functions it calls (`renderCommitSafetyGuard`, `renderNoAttributionTrailer`,
     `renderWorkAssertion`), rendered through `node` with `startedMarker: true`, and STEP 0's own
     `python3 - <<'PY' ... PY` heredoc body is pulled out of the RENDERED TEXT (never re-typed) and
     executed for real, against a real git sandbox under `tempfile.mkdtemp`:
       (a) an EXISTING state file carrying other tasks/bails/setup -> tasks[N] ends at `running`
           with `start_sha` equal to the sandbox's real `HEAD`, and every other key is preserved.
       (b) a MISSING state file -> a minimal valid `{"tasks": {...}}` document is created.
       (c) `startedMarker: false` -> STEP 0 is not rendered at all (no marker text, no PY heredoc).
  2. Runtime inversion: rendering with `startedMarker: false` and then asserting case (a)'s
     assertions FAIL against that rendering proves the suite actually discriminates -- it is not
     trivially satisfied regardless of the flag.
  3. `resolvePrevSha()` is extracted verbatim from `.claude/workflows/sdlc-task.js` (unchanged
     idiom from `scripts/test_work_assertion_base_sha.py`) and evaluated to confirm
     `state.tasks[N].start_sha` now wins over `state.tasks[N-1].commit` (highest precedence, source
     `'start_sha'`), and that the pre-existing self-attribution guard still applies on top of it.
  4. `ParityTests` extracts both real engines' `<<shared:renderImplementPrompt>>` regions (the
     exact function body, same balanced-region scan the marker comment's own contract promises) and
     asserts they are byte-identical -- D83 parity, unconditional on which engine a caller cares
     about.

OBSERVED RED (registered in planning/harness.json, task 1)
------------------------------------------------------------
Against the pre-task-1 committed `.claude/workflows/sdlc-task.js` (`git show
ea95e3e:.claude/workflows/sdlc-task.js`) neither `STEP 0`, `startedMarker`, nor `start_sha` occurs
anywhere in the file -- confirmed via `grep -c`. `renderImplementPrompt()`'s pre-task-1 signature
does not destructure `stateFile`/`startedMarker`/`resumingRunning` at all, so passing those keys
into it is silently a no-op and the rendered prompt never contains a STEP 0 or a `python3 - <<'PY'`
block under any input -- case (a) below fails against that old source with
"no STEP 0 marker rendered even though startedMarker=True was requested", which is exactly the gap
this task closes.

Run directly: python3 scripts/test_per_task_started_marker.py
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
TASK_ENGINE = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"
FLOW_ENGINE = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"

GIT_ISOLATION_VARS = [
    "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE", "GIT_PREFIX", "GIT_CEILING_DIRECTORIES",
]


def _sandbox_env() -> dict:
    env = dict(os.environ)
    for var in GIT_ISOLATION_VARS:
        env.pop(var, None)
    return env


def git(sandbox: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=sandbox, capture_output=True, text=True, env=_sandbox_env(),
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {sandbox}:\n{result.stderr}")
    return result.stdout


def init_sandbox(tmp_root: Path) -> Path:
    sandbox = Path(tempfile.mkdtemp(prefix="marker_sandbox_", dir=str(tmp_root)))
    git(sandbox, "init", "-q")
    git(sandbox, "config", "user.email", "marker-test@example.com")
    git(sandbox, "config", "user.name", "Marker Test")
    (sandbox / "README.md").write_text("sandbox\n", encoding="utf-8")
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-q", "-m", "base: seed sandbox")
    return sandbox


# ----------------------------------------------------------------------------
# Extraction -- pull the REAL functions out of the engine source, never re-typed. Handles BOTH
# destructured-object params (renderImplementPrompt: `function f({ a, b }) {`) and plain positional
# params (resolvePrevSha, renderCommitSafetyGuard, renderWorkAssertion) -- the paren-depth scan
# below finds the closing `)` of the parameter list itself (respecting any nested `{...}`
# destructuring), then balances the function BODY's own braces from there, which is what
# `scripts/test_bail_path_runtime.py`'s simpler `extract_function()` (used elsewhere in this repo
# only against plain-positional-param functions) would get wrong on a destructured signature: its
# `text.index("{", m.start())` lands on the destructuring brace, not the body's, and returns a
# truncated function.
# ----------------------------------------------------------------------------

def read_source(engine_path: Path) -> str:
    return engine_path.read_text(encoding="utf-8")


def extract_function(text: str, name: str) -> str:
    m = re.search(rf"function {re.escape(name)}\(", text)
    if not m:
        raise AssertionError(f"function {name}() not found")
    start = m.start()
    paren_idx = text.index("(", m.start())
    depth = 0
    j = paren_idx
    while j < len(text):
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    else:
        raise AssertionError(f"unbalanced parens extracting function {name}()")
    brace_idx = text.index("{", j)
    depth = 0
    i = brace_idx
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


def extract_const_arrow(text: str, name: str) -> str:
    m = re.search(rf"const {re.escape(name)} = \([^)]*\) => \{{", text)
    if not m:
        raise AssertionError(f"const {name} = (...) => {{ not found")
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
    raise AssertionError(f"unbalanced braces extracting const {name}")


def extract_shared_marker_block(engine_path: Path, marker: str) -> str:
    text = read_source(engine_path)
    open_marker = f"// <<shared:{marker}>>"
    close_marker = f"// <</shared:{marker}>>"
    start = text.index(open_marker) + len(open_marker)
    end = text.index(close_marker, start)
    return text[start:end]


# ----------------------------------------------------------------------------
# Render renderImplementPrompt() through a real `node` process -- the real functions it calls
# (renderCommitSafetyGuard, renderNoAttributionTrailer, renderWorkAssertion) are extracted from the
# SAME engine file and defined in the same script, never re-typed.
# ----------------------------------------------------------------------------

def render_implement_prompt(
    engine_path: Path,
    *,
    run_root: str,
    state_file: str,
    started_marker: bool,
    resuming_running: bool,
    task_num: int = 1,
    prev_sha=None,
) -> str:
    src = read_source(engine_path)
    render_commit_safety_guard_src = extract_function(src, "renderCommitSafetyGuard")
    render_no_attribution_trailer_src = extract_const_arrow(src, "renderNoAttributionTrailer")
    render_work_assertion_src = extract_function(src, "renderWorkAssertion")
    render_implement_prompt_src = extract_function(src, "renderImplementPrompt")

    args = {
        "roleIntro": "You are the test implementation agent.",
        "runRootLabel": "run root",
        "runRoot": run_root,
        "extraReturnFields": "",
        "isFix": False,
        "taskNum": task_num,
        "attempt": 1,
        "stem": "TEST.marker-task1",
        "blockId": "TEST.marker",
        "specFile": "planning/blocks/TEST.marker.json",
        "specDesc": "(JSON block record)",
        "tasksJsonFile": "planning/TEST.marker/tasks.json",
        "breakdownFile": "planning/TEST.marker/breakdown.md",
        "prevFailBlob": None,
        "vault": {"vaulted": False, "planningPath": f"{run_root}/planning"},
        "GIT": "git",
        "prevSha": prev_sha,
        "stateFile": state_file,
        "startedMarker": started_marker,
        "resumingRunning": resuming_running,
    }
    # renderCommitSafetyGuard / renderWorkAssertion are passed as live function REFERENCES, so the
    # object literal below is built from the JSON-safe fields plus those two identifiers, never
    # from a plain JSON.stringify() (which cannot carry a function value at all).
    args_json = json.dumps(args)
    node_script = (
        render_commit_safety_guard_src + "\n"
        + render_no_attribution_trailer_src + "\n"
        + render_work_assertion_src + "\n"
        + render_implement_prompt_src + "\n"
        + f"const __args = {args_json};\n"
        + "__args.renderCommitSafetyGuard = renderCommitSafetyGuard;\n"
        + "__args.renderWorkAssertion = renderWorkAssertion;\n"
        + "process.stdout.write(renderImplementPrompt(__args));\n"
    )
    result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"node failed to render renderImplementPrompt():\n{result.stderr}")
    return result.stdout


STEP0_PY_RE = re.compile(r"<<'PY'\n(.*?)\nPY\n", re.DOTALL)


def extract_step0_python(rendered: str) -> str | None:
    """Pulls STEP 0's python3 heredoc body out of the RENDERED prompt text -- never re-typed.
    Returns None when no marker was rendered (startedMarker was false)."""
    if "STEP 0" not in rendered:
        return None
    m = STEP0_PY_RE.search(rendered)
    return m.group(1) if m else None


def run_step0(sandbox: Path, python_source: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", "-c", python_source], cwd=sandbox, capture_output=True, text=True,
        env=_sandbox_env(),
    )


class StartedMarkerRenderTests(unittest.TestCase):
    """Cases (a)-(c): STEP 0's marker, extracted from the rendered prompt and executed for real."""

    def setUp(self) -> None:
        self._tmp_root = tempfile.mkdtemp(prefix="marker_root_")
        self.addCleanup(__import__("shutil").rmtree, self._tmp_root, ignore_errors=True)

    def _sandbox(self) -> Path:
        return init_sandbox(Path(self._tmp_root))

    # ------------------------------------------------------------------
    # Case (a): an EXISTING state file with other tasks/bails/setup -- tasks[N] ends at `running`
    # with start_sha == HEAD, every other key preserved byte-for-byte in meaning.
    # ------------------------------------------------------------------
    def test_case_a_existing_state_file_merged_not_overwritten(self):
        sandbox = self._sandbox()
        state_path = sandbox / "sdlc" / "sdlc-task-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        fixture = {
            "started_at": "2026-09-17T10:00:00Z",
            "base_sha": "0000000",
            "setup": {"prepareRun": {"repo_root": str(sandbox)}},
            "bails": [{"task_id": 1, "reason": "prior bail", "resolution": "resumed-clean"}],
            "tasks": {
                "1": {"status": "passed", "commit": "aaaaaaa", "summary": "task 1 done"},
            },
        }
        state_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")

        rendered = render_implement_prompt(
            TASK_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-task-state.json",
            started_marker=True, resuming_running=False, task_num=2,
        )
        py_source = extract_step0_python(rendered)
        self.assertIsNotNone(py_source, "startedMarker=True must render STEP 0's python heredoc")

        result = run_step0(sandbox, py_source)
        self.assertEqual(
            result.returncode, 0,
            f"STEP 0's marker script failed:\n{result.stdout}{result.stderr}",
        )
        self.assertIn("STARTED_MARKER:", result.stdout)

        head_sha = git(sandbox, "rev-parse", "--short", "HEAD").strip()
        after = json.loads(state_path.read_text(encoding="utf-8"))

        # New per-task marker, this task only.
        self.assertEqual(after["tasks"]["2"]["status"], "running")
        self.assertEqual(after["tasks"]["2"]["start_sha"], head_sha)
        self.assertIn("marker_at", after["tasks"]["2"])

        # Every other key preserved byte-for-byte in meaning -- a merge, never a rewrite.
        self.assertEqual(after["started_at"], fixture["started_at"])
        self.assertEqual(after["base_sha"], fixture["base_sha"])
        self.assertEqual(after["setup"], fixture["setup"])
        self.assertEqual(after["bails"], fixture["bails"])
        self.assertEqual(after["tasks"]["1"], fixture["tasks"]["1"])

    # ------------------------------------------------------------------
    # Case (b): a MISSING state file -- a minimal valid document is created.
    # ------------------------------------------------------------------
    def test_case_b_missing_state_file_creates_minimal_valid_document(self):
        sandbox = self._sandbox()
        state_path = sandbox / "sdlc" / "sdlc-task-state.json"
        self.assertFalse(state_path.exists())

        rendered = render_implement_prompt(
            TASK_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-task-state.json",
            started_marker=True, resuming_running=False, task_num=1,
        )
        py_source = extract_step0_python(rendered)
        self.assertIsNotNone(py_source)

        result = run_step0(sandbox, py_source)
        self.assertEqual(
            result.returncode, 0,
            f"STEP 0's marker script failed against a missing state file:\n{result.stdout}{result.stderr}",
        )

        self.assertTrue(state_path.exists(), "STEP 0 must create the state file when absent")
        after = json.loads(state_path.read_text(encoding="utf-8"))
        head_sha = git(sandbox, "rev-parse", "--short", "HEAD").strip()
        self.assertEqual(after["tasks"]["1"]["status"], "running")
        self.assertEqual(after["tasks"]["1"]["start_sha"], head_sha)

    # ------------------------------------------------------------------
    # Case (c) + runtime inversion: startedMarker=False renders NO STEP 0 at all, which is what
    # proves this suite actually discriminates the flag rather than always finding a marker.
    # ------------------------------------------------------------------
    def test_case_c_started_marker_false_renders_no_step0(self):
        sandbox = self._sandbox()
        rendered = render_implement_prompt(
            TASK_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-task-state.json",
            started_marker=False, resuming_running=False, task_num=1,
        )
        py_source = extract_step0_python(rendered)
        self.assertIsNone(
            py_source,
            "startedMarker=False must render no STEP 0 / no python heredoc at all -- a fix attempt "
            "(attempt > 1) or a resumed running task must never re-stamp start_sha",
        )

    def test_runtime_inversion_case_a_fails_against_no_marker_rendering(self):
        """Runtime inversion (testing_strategy): re-run case (a)'s own assertion against a
        startedMarker=False rendering and confirm it FAILS -- proving the suite discriminates the
        flag rather than trivially passing regardless of it."""
        sandbox = self._sandbox()
        rendered = render_implement_prompt(
            TASK_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-task-state.json",
            started_marker=False, resuming_running=False, task_num=1,
        )
        py_source = extract_step0_python(rendered)
        with self.assertRaises(AssertionError):
            self.assertIsNotNone(
                py_source, "startedMarker=True must render STEP 0's python heredoc",
            )

    # ------------------------------------------------------------------
    # A resuming `running` task renders the crashed-prior-attempt note, and (per the engine's own
    # attempt===1 && !t.start_sha gate) never renders STEP 0 alongside it.
    # ------------------------------------------------------------------
    def test_resuming_running_renders_note_without_a_fresh_marker(self):
        sandbox = self._sandbox()
        rendered = render_implement_prompt(
            TASK_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-task-state.json",
            started_marker=False, resuming_running=True, task_num=1,
        )
        self.assertIn(
            "found at status", rendered,
            "resumingRunning=True must render the crashed-prior-attempt note",
        )
        self.assertIsNone(
            extract_step0_python(rendered),
            "a resumed running task keeps its existing start_sha and must not get a fresh marker",
        )


class FlowEngineStartedMarkerRenderTests(StartedMarkerRenderTests):
    """Same three cases, against the sdlc-flow.js engine (D83 parity)."""

    def test_case_a_existing_state_file_merged_not_overwritten(self):
        sandbox = self._sandbox()
        state_path = sandbox / "sdlc" / "sdlc-flow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        fixture = {
            "started_at": "2026-09-17T10:00:00Z",
            "base_sha": "0000000",
            "tasks": {"1": {"status": "passed", "commit": "aaaaaaa"}},
        }
        state_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        rendered = render_implement_prompt(
            FLOW_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-flow-state.json",
            started_marker=True, resuming_running=False, task_num=2,
        )
        py_source = extract_step0_python(rendered)
        self.assertIsNotNone(py_source)
        result = run_step0(sandbox, py_source)
        self.assertEqual(result.returncode, 0, f"{result.stdout}{result.stderr}")
        head_sha = git(sandbox, "rev-parse", "--short", "HEAD").strip()
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(after["tasks"]["2"]["status"], "running")
        self.assertEqual(after["tasks"]["2"]["start_sha"], head_sha)
        self.assertEqual(after["tasks"]["1"], fixture["tasks"]["1"])

    def test_case_b_missing_state_file_creates_minimal_valid_document(self):
        sandbox = self._sandbox()
        state_path = sandbox / "sdlc" / "sdlc-flow-state.json"
        rendered = render_implement_prompt(
            FLOW_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-flow-state.json",
            started_marker=True, resuming_running=False, task_num=1,
        )
        py_source = extract_step0_python(rendered)
        result = run_step0(sandbox, py_source)
        self.assertEqual(result.returncode, 0, f"{result.stdout}{result.stderr}")
        self.assertTrue(state_path.exists())

    def test_case_c_started_marker_false_renders_no_step0(self):
        sandbox = self._sandbox()
        rendered = render_implement_prompt(
            FLOW_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-flow-state.json",
            started_marker=False, resuming_running=False, task_num=1,
        )
        self.assertIsNone(extract_step0_python(rendered))

    def test_runtime_inversion_case_a_fails_against_no_marker_rendering(self):
        sandbox = self._sandbox()
        rendered = render_implement_prompt(
            FLOW_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-flow-state.json",
            started_marker=False, resuming_running=False, task_num=1,
        )
        with self.assertRaises(AssertionError):
            self.assertIsNotNone(extract_step0_python(rendered))

    def test_resuming_running_renders_note_without_a_fresh_marker(self):
        sandbox = self._sandbox()
        rendered = render_implement_prompt(
            FLOW_ENGINE, run_root=str(sandbox), state_file="sdlc/sdlc-flow-state.json",
            started_marker=False, resuming_running=True, task_num=1,
        )
        self.assertIn("found at status", rendered)
        self.assertIsNone(extract_step0_python(rendered))


# ----------------------------------------------------------------------------
# resolvePrevSha() -- sdlc-task.js only (sdlc-flow.js has no equivalent; it stays on a literal
# HEAD~1, unchanged, out of scope per the block record). start_sha now wins over
# state.tasks[N-1].commit, and the pre-existing self-attribution guard still applies on top.
# ----------------------------------------------------------------------------

def resolve_prev_sha_via_node(state: dict, task_num: int, task_commits: dict) -> dict:
    src = read_source(TASK_ENGINE)
    fn_src = extract_function(src, "resolvePrevSha")
    node_script = (
        fn_src + "\n"
        + f"process.stdout.write(JSON.stringify(resolvePrevSha({json.dumps(state)}, {task_num}, {json.dumps(task_commits)})))\n"
    )
    result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"node failed to evaluate resolvePrevSha():\n{result.stderr}")
    return json.loads(result.stdout)


class ResolvePrevShaStartShaTests(unittest.TestCase):
    def test_start_sha_wins_over_prior_task_commit(self):
        state = {
            "tasks": {
                "1": {"commit": "aaaaaaa"},
                "2": {"start_sha": "bbbbbbb"},
            },
            "base_sha": "ccccccc",
        }
        result = resolve_prev_sha_via_node(state, 2, {})
        self.assertEqual(result["prevSha"], "bbbbbbb")
        self.assertEqual(result["source"], "start_sha")
        self.assertFalse(result["guardFired"])

    def test_no_start_sha_falls_back_to_prior_task_commit_unchanged(self):
        state = {"tasks": {"1": {"commit": "aaaaaaa"}, "2": {}}, "base_sha": "ccccccc"}
        result = resolve_prev_sha_via_node(state, 2, {})
        self.assertEqual(result["prevSha"], "aaaaaaa")
        self.assertEqual(result["source"], "state")

    def test_self_attribution_guard_still_applies_over_start_sha(self):
        """A resumed task's own start_sha can, in principle, coincide with one of its own
        commit's shas (e.g. a marker re-read after this task's own fix-pass history) -- the
        pre-existing self-attribution guard must still fire and fall back to earliest_parent,
        exactly as it does for the other three sources."""
        state = {"tasks": {"2": {"start_sha": "bbbbbbb"}}, "base_sha": "ccccccc"}
        task_commits = {"2": {"shas": ["bbbbbbb"], "earliest_parent": "zzzzzzz"}}
        result = resolve_prev_sha_via_node(state, 2, task_commits)
        self.assertTrue(result["guardFired"])
        self.assertEqual(result["source"], "guard:earliest_parent")
        self.assertEqual(result["prevSha"], "zzzzzzz")


# ----------------------------------------------------------------------------
# Parity (D83): the two real engines' <<shared:renderImplementPrompt>> regions must be
# byte-identical -- the marker comment's own contract, verified by scripts/build_engines.py's gate
# too, but asserted here directly against this ticket's own change.
# ----------------------------------------------------------------------------

class ParityTests(unittest.TestCase):
    def test_shared_render_implement_prompt_block_is_byte_identical_across_engines(self):
        task_block = extract_shared_marker_block(TASK_ENGINE, "renderImplementPrompt")
        flow_block = extract_shared_marker_block(FLOW_ENGINE, "renderImplementPrompt")
        if task_block != flow_block:
            import difflib

            diff = "".join(difflib.unified_diff(
                task_block.splitlines(keepends=True),
                flow_block.splitlines(keepends=True),
                fromfile=str(TASK_ENGINE),
                tofile=str(FLOW_ENGINE),
            ))
            self.fail(
                "the <<shared:renderImplementPrompt>> regions of sdlc-task.js and sdlc-flow.js "
                f"have diverged (D83 parity broken):\n{diff}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
