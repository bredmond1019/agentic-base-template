#!/usr/bin/env python3
"""Fixture suite for BT.ticket.bails-must-not-mint-time-in-the-engine.

Task 1 of this spec (THIS FILE): write the failing gate first, both halves, and run it against
the UNCHANGED engines (`.claude/workflows/sdlc-task.js`, `.claude/workflows/sdlc-flow.js`) to
record the real failure output. No engine file is touched by this task -- that is tasks 2 and 3's
job, and this suite is the contract they must satisfy.

WHY THIS EXISTS (see the block record's `why`)
-----------------------------------------------
BT.ticket.bails-must-be-append-only added six `new Date().toISOString()` calls to the engines'
bail paths. `new Date()` / `Date.now()` are ILLEGAL inside the Workflow runtime that actually
executes these engines (it throws `Date.now() / new Date() are unavailable in workflow scripts
(breaks resume)`), so every one of those six call sites turns a bail -- which used to write state
and return a diagnosable result -- into a hard crash that leaves LESS trace on disk than before
the append-only fix shipped. Neither existing gate could have caught this: `node --check` accepts
`new Date()` as valid JavaScript, and `scripts/test_bails_record.py` runs the extracted bail code
through plain `node -e`, where `Date` is the real, legal V8 constructor -- it is structurally
blind to a runtime-shim violation. This suite is the fix for that blindness.

STATIC HALF
-----------
Greps both engine source files for `new Date(` / `Date.now(` and asserts zero matches, naming
every match found (file:line:text) so a violation is diagnosable without re-reading the engine.
Run today (unchanged engines): RED, naming exactly six sites --
  sdlc-task.js:1561, sdlc-task.js:1975, sdlc-task.js:2098,
  sdlc-flow.js:1736, sdlc-flow.js:2091, sdlc-flow.js:2205
-- matching the block record's `what` exactly. Shown capable of failing simply by being run now;
shown capable of passing once tasks 2-3 remove the six calls (task 5 re-demonstrates falsifiability
by reintroducing one in a scratch copy).

RUNTIME HALF -- HONEST LIMITATION, STATED PER THE TESTING STRATEGY
--------------------------------------------------------------------
The actual Workflow runtime that raises the ShimDate error is Claude Code's own script-execution
harness: closed-source from this repo's point of view, not invokable from a Python fixture or a
bare `node` process, and (per base-template CLAUDE.md standing rule 10) available only as a
launch-time snapshot inside a live orchestration session -- there is no way to spin up a faithful
instance of it from `scripts/test_bail_path_runtime.py`. A faithful runtime harness is therefore
NOT reachable from this fixture, exactly the case the testing strategy anticipates.

What this substitutes, and why it is still real runtime coverage rather than a second static
assertion: it builds the smallest faithful proxy of the ONE property that actually matters here --
that `new Date()` / `Date.now()` throw inside the execution context, and any code path that has
been fixed to route around them does not. It replaces the global `Date` binding in a real `node -e`
process with a shim class whose constructor and `.now()` both throw the exact error text the real
runtime raises, then executes the engines' OWN, UNMODIFIED bail-producing source (extracted the
same way `scripts/test_bails_record.py` extracts it -- via balanced-brace / line scanning, never
re-typed) inside that process. This is a proxy, not the real runtime: it does not reproduce every
property of the real shim (only the throw-on-Date-access behavior the ticket's own reproduction
names), and a green run here is evidence about the SOURCE TEXT's behavior under a Date-illegal
execution context, not proof that a live `/sdlc-task` or `/sdlc-flow` run, right now, in this
process, would resume cleanly after a bail -- exactly the same class of honest limitation
`scripts/test_resume_task_state_merge.py` already states for a different engine-execution gap.

Driven against the UNCHANGED engines, each runtime-half case is expected to RAISE (the shim
catches the live defect directly, which is the whole point of adding it) rather than to return a
recorded, non-throwing bail -- so this half is red today for a different, complementary reason
than the static half: the static half names the illegal calls; the runtime half proves at least
one of them actually detonates under a Date-illegal execution context. Once tasks 2-3 land, each
case must execute without raising and must return a `bails[]` entry whose `occurred_at` is either
a real ISO-8601 string (`YYYY-MM-DDTHH:MM:SSZ`, no leftover placeholder) or the exact resolution
sentinel `__BAIL_OCCURRED_AT__` the ticket's `what` names for the JS-side sites that defer
resolution to the next state write -- never `undefined`, `null`, or an empty string, and never a
value produced by a call that reached the shim.

Registered in planning/harness.json as `bail-path-runtime-tests` --
run directly: python3 scripts/test_bail_path_runtime.py
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_FILES = {
    "sdlc-task.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js",
    "sdlc-flow.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js",
}

# buildBailPayload()'s call signature differs by one parameter between the two engines --
# sdlc-flow.js threads `attempt` through for its worklog.md entry; sdlc-task.js has no worklog.
BUILD_BAIL_PAYLOAD_ARGS = {
    "sdlc-task.js": "taskNum, t, majorFallback, exhaustionFallback",
    "sdlc-flow.js": "taskNum, t, attempt, majorFallback, exhaustionFallback",
}

ILLEGAL_TIME_CALL_RE = re.compile(r"new\s+Date\s*\(|Date\.now\s*\(")

# The resolution sentinel named in the ticket's `what` for JS-side sites that defer
# occurred_at resolution to the next state write, rather than threading a shim-legal clock.
RESOLUTION_SENTINEL = "__BAIL_OCCURRED_AT__"

ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

# The exact error text the ticket's `why` quotes from the real Workflow-runtime crash.
SHIM_ERROR_TEXT = "Date.now() / new Date() are unavailable in workflow scripts (breaks resume)"

DATE_SHIM = f"""
class ShimDate {{
  constructor() {{ throw new Error({json.dumps(SHIM_ERROR_TEXT)}) }}
  static now() {{ throw new Error({json.dumps(SHIM_ERROR_TEXT)}) }}
}}
Date = ShimDate
"""


# ----------------------------------------------------------------------------
# Extraction helpers -- pull real engine source, never re-typed. Mirrors
# scripts/test_bails_record.py's extraction idiom exactly, so both suites stay in lockstep
# with the same engine text rather than drifting into two different mental models of it.
# ----------------------------------------------------------------------------

def read_source(engine: str) -> str:
    return SOURCE_FILES[engine].read_text(encoding="utf-8")


def extract_balanced(text: str, start_marker: str, label: str) -> str:
    m = re.search(re.escape(start_marker), text)
    if not m:
        raise AssertionError(f"{label!r} not found")
    brace_start = text.index("{", m.start())
    depth = 0
    i = brace_start
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[m.start():i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces extracting {label!r}")


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


def extract_line_containing(text: str, needle: str, label: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line.strip()
    raise AssertionError(f"{label!r} (containing {needle!r}) not found")


def state_literal(engine: str) -> str:
    return extract_balanced(read_source(engine), "const state = {", f"{engine} state literal")


def build_bail_payload_src(engine: str) -> str:
    return extract_function(read_source(engine), "buildBailPayload")


def bail_site_task_loop(engine: str) -> str:
    """The task-loop bail assignment, identical text at sdlc-task.js:1975 / sdlc-flow.js:2091
    (once occurred_at stops calling new Date(), the surrounding text stays a stable anchor)."""
    return extract_line_containing(
        read_source(engine),
        "if (bailed && !taskPassed) { state.status = 'blocked'; state.bail_reason = bailReason }",
        "task-loop bail site",
    )


def bail_site_terminal(engine: str) -> str:
    """The engine-specific terminal bail-append site: sdlc-task.js's D56 reconcile bail
    (check_id: 'terminal-reconcile', :2098) or sdlc-flow.js's consolidated-review bail
    (check_id: 'review', :2205). Anchored on the check_id literal, not on occurred_at, so the
    anchor survives the fix that removes new Date() from this exact line."""
    needle = "check_id: 'terminal-reconcile'" if engine == "sdlc-task.js" else "check_id: 'review'"
    return extract_line_containing(read_source(engine), needle, f"{engine} terminal bail site")


def run_node(script: str) -> str:
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"node script failed:\n{result.stderr}\n---script---\n{script}")
    return result.stdout


def run_node_expect_throw(script: str) -> str:
    """Runs `script` and returns stderr, asserting the process DID exit non-zero (i.e. something
    inside it threw) -- the inverse of run_node, used to prove the shim can fail."""
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        raise AssertionError(f"expected node script to throw, but it exited 0:\n---script---\n{script}")
    return result.stderr


PRELUDE = """
const blockId = 'test-block'
const baseBranchName = 'main'
const useWorktree = false
"""


class BailPathRuntimeTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # STATIC HALF
    # ------------------------------------------------------------------
    def test_static_no_illegal_time_calls_in_either_engine(self):
        violations = []
        for engine, path in SOURCE_FILES.items():
            for lineno, line in enumerate(read_source(engine).splitlines(), start=1):
                for m in ILLEGAL_TIME_CALL_RE.finditer(line):
                    violations.append(f"{engine}:{lineno}: {line.strip()}")
        self.assertFalse(
            violations,
            "the Workflow runtime throws "
            f"{SHIM_ERROR_TEXT!r} on `new Date()` / `Date.now()` -- found "
            f"{len(violations)} illegal call site(s):\n" + "\n".join(violations),
        )

    # ------------------------------------------------------------------
    # RUNTIME HALF -- see module docstring for exactly what this substitutes and why.
    # ------------------------------------------------------------------
    def _assert_recorded_not_thrown(self, engine: str, entry: dict, label: str) -> None:
        occurred_at = entry.get("occurred_at")
        self.assertTrue(
            occurred_at,
            f"{engine} {label}: bails[] entry has no occurred_at at all -- {entry!r}",
        )
        ok = occurred_at == RESOLUTION_SENTINEL or bool(ISO8601_RE.match(str(occurred_at)))
        self.assertTrue(
            ok,
            f"{engine} {label}: occurred_at={occurred_at!r} is neither a real ISO-8601 "
            f"timestamp nor the resolution sentinel {RESOLUTION_SENTINEL!r} -- it must never be "
            "a leftover placeholder in some OTHER shape, nor a value the shim itself produced",
        )

    def test_runtime_build_bail_payload_under_shim(self):
        for engine, args in BUILD_BAIL_PAYLOAD_ARGS.items():
            with self.subTest(engine=engine):
                fn_src = build_bail_payload_src(engine)
                worklog_global = "const worklogFile = 'worklog.md'\n" if engine == "sdlc-flow.js" else ""
                extra_call_args = ", 1" if engine == "sdlc-flow.js" else ""
                script = f"""
{DATE_SHIM}
{PRELUDE}
function buildTokensBlock() {{ return {{ stages: [], total: {{}} }} }}
const stateFile = 'state.json'
{worklog_global}let state = {{
  spec_slug: blockId,
  branch: baseBranchName,
  mode: 'branch',
  tasks: {{}},
  bail_reason: null,
  bails: [],
  tokens: {{}},
}}
{fn_src}
const t = {{ status: 'running', files: ['scripts/foo.py'] }}
const result = buildBailPayload(1, t{extra_call_args}, 'a bail happened', null)
console.log(result.stateJson)
"""
                try:
                    snapshot = json.loads(run_node(script))
                except AssertionError as exc:
                    self.fail(
                        f"{engine}: buildBailPayload() RAISED under the Date-illegal runtime "
                        f"proxy instead of recording the bail -- this is the live defect, and "
                        f"this suite is red at task 1 for exactly this reason:\n{exc}"
                    )
                bails = snapshot.get("bails") or []
                self.assertEqual(
                    len(bails), 1,
                    f"{engine}: buildBailPayload() must append exactly one bails[] entry, got {bails!r}",
                )
                self._assert_recorded_not_thrown(engine, bails[0], "buildBailPayload")

    def test_runtime_task_loop_bail_site_under_shim(self):
        for engine in SOURCE_FILES:
            with self.subTest(engine=engine):
                lit = state_literal(engine)
                site = bail_site_task_loop(engine)
                script = f"""
{DATE_SHIM}
{PRELUDE}
{lit}
let bailed = true, taskPassed = false, bailReason = 'a bail happened'
state.current_task = 1
{site}
console.log(JSON.stringify(state))
"""
                try:
                    state = json.loads(run_node(script))
                except AssertionError as exc:
                    self.fail(
                        f"{engine}: the task-loop bail-assignment site RAISED under the "
                        f"Date-illegal runtime proxy instead of recording the bail:\n{exc}"
                    )
                bails = state.get("bails") or []
                self.assertEqual(
                    len(bails), 1,
                    f"{engine}: the task-loop bail site must append exactly one bails[] entry, "
                    f"got {bails!r}",
                )
                self._assert_recorded_not_thrown(engine, bails[0], "task-loop bail site")

    def test_runtime_terminal_bail_site_under_shim(self):
        for engine in SOURCE_FILES:
            with self.subTest(engine=engine):
                lit = state_literal(engine)
                site = bail_site_terminal(engine)
                if engine == "sdlc-task.js":
                    extra = "const reconcileBailReason = 'terminal reconcile failed'\n"
                else:
                    extra = "const bailReason = 'review bailed'\nconst tr = { class: 'MAJOR' }\n"
                script = f"""
{DATE_SHIM}
{PRELUDE}
{lit}
{extra}{site}
console.log(JSON.stringify(state))
"""
                try:
                    state = json.loads(run_node(script))
                except AssertionError as exc:
                    self.fail(
                        f"{engine}: the terminal bail-append site RAISED under the Date-illegal "
                        f"runtime proxy instead of recording the bail:\n{exc}"
                    )
                bails = state.get("bails") or []
                self.assertEqual(
                    len(bails), 1,
                    f"{engine}: the terminal bail site must append exactly one bails[] entry, "
                    f"got {bails!r}",
                )
                self._assert_recorded_not_thrown(engine, bails[0], "terminal bail site")

    # ------------------------------------------------------------------
    # Falsifiability of the shim itself -- proves the proxy actually distinguishes
    # legal from illegal code, rather than being a no-op that would pass anything.
    # ------------------------------------------------------------------
    def test_shim_itself_throws_on_new_date(self):
        run_node_expect_throw(f"{DATE_SHIM}\nnew Date().toISOString()")

    def test_shim_itself_throws_on_date_now(self):
        run_node_expect_throw(f"{DATE_SHIM}\nDate.now()")

    def test_shim_itself_permits_shim_legal_code(self):
        out = run_node(f"{DATE_SHIM}\nconsole.log(JSON.stringify({{ occurred_at: '__BAIL_OCCURRED_AT__' }}))")
        self.assertEqual(json.loads(out), {"occurred_at": "__BAIL_OCCURRED_AT__"})


if __name__ == "__main__":
    unittest.main()
