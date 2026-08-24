#!/usr/bin/env python3
"""Fixture suite for BT.ticket.bails-must-be-append-only.

Task 1 of this spec (THIS FILE): build the fixture suite and run it against the UNCHANGED
engines (`.claude/workflows/sdlc-task.js`, `.claude/workflows/sdlc-flow.js`) to record the real
failure output. No engine file is touched by this task -- that is task 2's job, and this suite is
the contract task 2 must satisfy.

WHY THIS MATTERS (see the block record's `why`): a successful retry currently erases the single
mutable `state.bail_reason` field -- a fresh run re-initialises it to `null` from the state
literal, and the field is assigned once, never appended. Eight of nine measured foreign-state
bails in one day left no trace on disk because of exactly this. Case (d) below --
`test_case_d_clean_retry_does_not_erase_the_bail` -- reproduces that defect directly and MUST be
red here. It is the block's reproduction and its acceptance evidence.

Reuses `scripts/test_work_assertion.py`'s harness shape: extract real engine source via regex /
balanced-brace scanning (never re-typed), execute it via a real `node -e` invocation (never
re-implemented in Python), and treat both engines as one suite so cross-engine drift is caught by
construction.

The nine cases below are the ones enumerated in the block record's `testing_strategy`:
  (a) no bail leaves bails == []
  (b) one bail appends one fully-populated entry
  (c) two bails append two, with the first entry unchanged
  (d) a clean retry annotates the existing entry rather than erasing it -- RED before the fix
  (e)+(f) entry shape: ownership self/foreign, failing_artifact null when none named
  (g) resume merges bails[] forward rather than re-initialising it
  (h) bail_reason mirrors the newest entry's reason
  (i) the bails-handling code is byte-identical between the two engines

Registered in planning/harness.json as `bails-record-tests` --
run directly: python3 scripts/test_bails_record.py
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

REQUIRED_ENTRY_FIELDS = [
    "occurred_at",
    "task_id",
    "check_id",
    "failing_artifact",
    "ownership",
    "bail_class",
    "reason",
    "resolution",
]


# ----------------------------------------------------------------------------
# Extraction helpers -- pull real engine source, never re-typed.
# ----------------------------------------------------------------------------

def read_source(engine: str) -> str:
    return SOURCE_FILES[engine].read_text(encoding="utf-8")


def extract_balanced(text: str, start_marker: str, label: str) -> str:
    """From the first `{` after `start_marker` to its matching `}`, inclusive of the marker."""
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
    """The task-loop bail assignment, identical text at sdlc-task.js:1936 / sdlc-flow.js:2052."""
    return extract_line_containing(
        read_source(engine),
        "if (bailed && !taskPassed) { state.status = 'blocked'; state.bail_reason = bailReason }",
        "task-loop bail site",
    )


def resume_merge_line(engine: str) -> str:
    return extract_line_containing(
        read_source(engine),
        "Object.assign(state.tasks, priorTasks)",
        "resume tasks-merge line",
    )


def run_node(script: str) -> str:
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"node script failed:\n{result.stderr}\n---script---\n{script}")
    return result.stdout


PRELUDE = """
const blockId = 'test-block'
const baseBranchName = 'main'
const useWorktree = false
"""


class BailsRecordTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # (a) no bail leaves bails == []
    # ------------------------------------------------------------------
    def test_case_a_state_literal_has_bails_array(self):
        for engine in SOURCE_FILES:
            with self.subTest(engine=engine):
                script = f"{PRELUDE}\n{state_literal(engine)}\nconsole.log(JSON.stringify(state))"
                obj = json.loads(run_node(script))
                self.assertIn(
                    "bails", obj,
                    f"{engine}: initial run-state literal has no `bails` key -- "
                    "a run that never bails should leave `bails` present and empty, not absent",
                )
                self.assertEqual(
                    obj.get("bails"), [],
                    f"{engine}: `bails` in the initial state literal must start as []",
                )

    # ------------------------------------------------------------------
    # (b) one bail appends one fully-populated entry
    # ------------------------------------------------------------------
    def test_case_b_one_bail_appends_one_entry(self):
        for engine, args in BUILD_BAIL_PAYLOAD_ARGS.items():
            with self.subTest(engine=engine):
                snapshot = self._build_bail_snapshot(engine, args, bails=[], task_id=1,
                                                       files=["scripts/foo.py"])
                bails = snapshot.get("bails")
                self.assertIsInstance(
                    bails, list,
                    f"{engine}: buildBailPayload()'s snapshot must carry a `bails` array",
                )
                self.assertEqual(
                    len(bails or []), 1,
                    f"{engine}: a bail must APPEND exactly one entry to `bails`, got {bails!r}",
                )

    # ------------------------------------------------------------------
    # (c) two bails append two, first entry unchanged
    # ------------------------------------------------------------------
    def test_case_c_second_bail_appends_second_entry_first_unchanged(self):
        for engine, args in BUILD_BAIL_PAYLOAD_ARGS.items():
            with self.subTest(engine=engine):
                first = self._build_bail_snapshot(engine, args, bails=[], task_id=1,
                                                    files=["scripts/foo.py"])
                first_bails = first.get("bails") or []
                second = self._build_bail_snapshot(engine, args, bails=first_bails, task_id=2,
                                                     files=["scripts/bar.py"])
                second_bails = second.get("bails") or []
                self.assertEqual(
                    len(second_bails), 2,
                    f"{engine}: a second bail must leave two entries in `bails`, got "
                    f"{second_bails!r}",
                )
                if len(second_bails) >= 1 and first_bails:
                    self.assertEqual(
                        second_bails[0], first_bails[0],
                        f"{engine}: the first bail entry must be byte-identical before and "
                        "after a second bail is appended",
                    )

    # ------------------------------------------------------------------
    # (d) THE CENTRAL REPRODUCTION -- a clean retry must annotate, never erase.
    # ------------------------------------------------------------------
    def test_case_d_clean_retry_does_not_erase_the_bail(self):
        """MEASURED, 2026-08-24: eight of nine foreign-state bails left no trace on disk because
        a successful retry re-initialises `bail_reason` to null from the state literal. This is
        the ticket's reproduction and its acceptance evidence -- it MUST be red before task 2."""
        for engine in SOURCE_FILES:
            with self.subTest(engine=engine):
                lit = state_literal(engine)
                site1 = bail_site_task_loop(engine)
                merge_line = resume_merge_line(engine)
                script = f"""
{PRELUDE}
function run1() {{
{lit}
  let bailed = true, taskPassed = false, bailReason = 'foreign-state gate failed on a file this task never declared'
  {site1}
  state.tasks['1'] = {{ status: 'failed' }}
  return state
}}
const run1State = run1()

function run2(priorTasks) {{
{lit}
  {merge_line}
  // Task 1 is retried and passes cleanly this run -- no bail fires.
  state.tasks['1'] = {{ ...state.tasks['1'], status: 'passed' }}
  return state
}}
const run2State = run2(run1State.tasks)

console.log(JSON.stringify({{ run1: run1State, run2: run2State }}))
"""
                result = json.loads(run_node(script))
                run2_bails = result["run2"].get("bails") or []
                matching = [
                    b for b in run2_bails
                    if isinstance(b, dict) and "foreign-state gate failed" in (b.get("reason") or "")
                ]
                self.assertTrue(
                    matching,
                    f"{engine}: run 1's bail record is CLEARED OR ABSENT after a clean retry in "
                    f"run 2 -- run2.bails = {run2_bails!r}. This is the exact defect the ticket "
                    "describes: 'a bail that is later resumed cleanly is annotated rather than "
                    "deleted' is not yet true.",
                )
                if matching:
                    self.assertEqual(
                        matching[0].get("resolution"), "resumed-clean",
                        f"{engine}: the surviving entry must be annotated resolution="
                        "'resumed-clean', not merely left present",
                    )

    # ------------------------------------------------------------------
    # (e) + (f) entry shape: required fields, and no fabricated artifact.
    # ------------------------------------------------------------------
    def test_case_e_f_entry_shape_has_required_fields(self):
        for engine in SOURCE_FILES:
            with self.subTest(engine=engine):
                src = build_bail_payload_src(engine)
                missing = [f for f in REQUIRED_ENTRY_FIELDS if f not in src]
                self.assertFalse(
                    missing,
                    f"{engine}: buildBailPayload() does not yet construct a bail entry carrying "
                    f"{missing} -- required fields per the ticket: {REQUIRED_ENTRY_FIELDS}",
                )

    def test_case_f_ownership_ties_to_renderWorkAssertion(self):
        for engine in SOURCE_FILES:
            with self.subTest(engine=engine):
                src = read_source(engine)
                # ownership must be computed by the SAME set-intersection renderWorkAssertion()
                # already uses, reused rather than reimplemented (block record `what`).
                self.assertIn(
                    "renderWorkAssertion", src,
                    f"{engine}: renderWorkAssertion() (the existing files[] set-intersection) "
                    "must exist for ownership to reuse it",
                )

    # ------------------------------------------------------------------
    # (g) resume merges bails[] forward rather than re-initialising it.
    # ------------------------------------------------------------------
    def test_case_g_resume_merges_bails_forward(self):
        for engine in SOURCE_FILES:
            with self.subTest(engine=engine):
                lit = state_literal(engine)
                merge_line = resume_merge_line(engine)
                site1 = bail_site_task_loop(engine)
                prior_bails = [
                    {"occurred_at": "t0", "task_id": 1, "check_id": "c1", "failing_artifact": None,
                     "ownership": "foreign", "bail_class": 3, "reason": "first bail",
                     "resolution": "resumed-clean"},
                    {"occurred_at": "t1", "task_id": 2, "check_id": "c2", "failing_artifact": "x.py",
                     "ownership": "self", "bail_class": 1, "reason": "second bail",
                     "resolution": None},
                ]
                script = f"""
{PRELUDE}
function run2(priorState) {{
{lit}
  const priorTasks = priorState.tasks
  {merge_line}
  let bailed = true, taskPassed = false, bailReason = 'third bail on resume'
  {site1}
  state.tasks['3'] = {{ status: 'failed' }}
  return state
}}
const priorState = {{ tasks: {{}}, bails: {json.dumps(prior_bails)} }}
const run2State = run2(priorState)
console.log(JSON.stringify(run2State))
"""
                run2_state = json.loads(run_node(script))
                run2_bails = run2_state.get("bails") or []
                self.assertEqual(
                    len(run2_bails), 3,
                    f"{engine}: a resume that starts from a two-entry snapshot and bails again "
                    f"must end with three entries, got {run2_bails!r} -- the resume path must "
                    "MERGE bails[] from the prior snapshot rather than re-initialising it",
                )

    # ------------------------------------------------------------------
    # (h) bail_reason mirrors the newest entry's reason.
    # ------------------------------------------------------------------
    def test_case_h_bail_reason_mirrors_newest_entry(self):
        for engine, args in BUILD_BAIL_PAYLOAD_ARGS.items():
            with self.subTest(engine=engine):
                first = self._build_bail_snapshot(engine, args, bails=[], task_id=1,
                                                    files=["scripts/foo.py"],
                                                    reason="first reason")
                first_bails = first.get("bails") or []
                second = self._build_bail_snapshot(engine, args, bails=first_bails, task_id=2,
                                                     files=["scripts/bar.py"],
                                                     reason="second reason")
                second_bails = second.get("bails") or []
                newest_reason = second_bails[-1]["reason"] if second_bails else None
                self.assertEqual(
                    second.get("bail_reason"), newest_reason,
                    f"{engine}: bail_reason ({second.get('bail_reason')!r}) must equal the "
                    f"newest bails[] entry's reason ({newest_reason!r})",
                )

    def test_case_h_bail_reason_null_when_bails_empty(self):
        for engine in SOURCE_FILES:
            with self.subTest(engine=engine):
                script = f"{PRELUDE}\n{state_literal(engine)}\nconsole.log(JSON.stringify(state))"
                obj = json.loads(run_node(script))
                self.assertIsNone(
                    obj.get("bail_reason"),
                    f"{engine}: bail_reason must be null when bails is empty",
                )

    # ------------------------------------------------------------------
    # (i) cross-engine byte-identical bails-handling.
    # ------------------------------------------------------------------
    def test_case_i_bails_handling_byte_identical_across_engines(self):
        task_site = bail_site_task_loop("sdlc-task.js")
        flow_site = bail_site_task_loop("sdlc-flow.js")
        self.assertEqual(
            task_site, flow_site,
            "the task-loop bail-assignment site must stay byte-identical between "
            "sdlc-task.js and sdlc-flow.js",
        )
        task_fields_missing = [f for f in REQUIRED_ENTRY_FIELDS if f not in build_bail_payload_src("sdlc-task.js")]
        flow_fields_missing = [f for f in REQUIRED_ENTRY_FIELDS if f not in build_bail_payload_src("sdlc-flow.js")]
        self.assertEqual(
            task_fields_missing, flow_fields_missing,
            "both engines must be equally (in)complete on the required bail-entry fields -- "
            f"sdlc-task.js missing {task_fields_missing}, sdlc-flow.js missing {flow_fields_missing}",
        )

    # ------------------------------------------------------------------
    # helper
    # ------------------------------------------------------------------
    def _build_bail_snapshot(self, engine: str, args: str, *, bails: list, task_id: int,
                              files: list[str], reason: str = "a bail happened") -> dict:
        fn_src = build_bail_payload_src(engine)
        worklog_global = "const worklogFile = 'worklog.md'\n" if engine == "sdlc-flow.js" else ""
        extra_call_args = ", 1" if engine == "sdlc-flow.js" else ""  # attempt=1 for flow
        t_obj = {"status": "running", "files": files}
        script = f"""
{PRELUDE}
function buildTokensBlock() {{ return {{ stages: [], total: {{}} }} }}
const stateFile = 'state.json'
{worklog_global}let state = {{
  spec_slug: blockId,
  branch: baseBranchName,
  mode: 'branch',
  tasks: {{}},
  bail_reason: null,
  bails: {json.dumps(bails)},
  tokens: {{}},
}}
{fn_src}
const t = {json.dumps(t_obj)}
const result = buildBailPayload({task_id}, t{extra_call_args}, {json.dumps(reason)}, null)
console.log(result.stateJson)
"""
        return json.loads(run_node(script))


if __name__ == "__main__":
    unittest.main()
