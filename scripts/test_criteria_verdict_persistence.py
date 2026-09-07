#!/usr/bin/env python3
"""Fixture suite for BT.ticket.criteria-verdict-stage-silently-no-ops-and-is-never-persisted
(task 1).

RED-FIRST: at this commit `loadBlockRecordAcceptanceCriteria` in `.claude/workflows/sdlc-task.js`
collapses every failure cause (missing record, unparseable JSON, absent key, deliberately-empty
array) into the same silent `[]`, and `criteriaVerdicts` is computed in memory but never written
into `sdlc-task-state.json`'s `state` object literal. This suite MUST fail against the unfixed
engine (task 2/3 make it pass).

Same discipline as `scripts/test_sdlc_task_criteria_verdicts.py` /
`scripts/test_bails_record.py`: the source under test is the REAL engine file on disk, extracted
via balanced-brace scanning and executed through a real `node` subprocess -- never a Python
re-implementation of the engine's behaviour.

THE CONTRACT this suite pins (what task 2 must land for cases 2-6 to go green):

  1. `loadBlockRecordAcceptanceCriteria(cwd, recordFile)` must stop returning a bare array on
     every path. Post-fix it must return an object `{criteria, reason}`:
       - criteria: the acceptance_criteria array (possibly empty)
       - reason: null/falsy when criteria is non-empty (the happy path); otherwise a non-empty,
         human-readable string naming WHY the list is empty, and that string must be DIFFERENT
         for each of the four distinct causes (record missing / record unparseable / key absent /
         key present but empty) so a caller -- and a log line -- can tell them apart.
  2. The `state` object literal (Block A, around sdlc-task.js:1712) must carry a top-level
     `criteriaVerdicts` key, initialised to `[]`, alongside `bails`.
  3. The engine must assign the computed verdicts onto `state.criteriaVerdicts` at the point they
     are computed (immediately after `criteriaVerdicts = verdict.results` in the Criteria phase),
     so the terminal `writeTaskState()` call -- which serializes the whole `state` object verbatim
     -- persists them. A run that never reaches the Criteria stage (bail / reconcile_failed /
     legacy tasks.md spec) leaves the key at its initial `[]` rather than omitting it.

Six cases, per the block record's task 1 description:
  1. CRITERIA PRESENT (mixed bare-string + object-form, one gateable:false)  -> all N returned,
     no failure reason.
  2. RECORD MISSING                                                          -> distinguishable
     named reason, criteria == [].
  3. RECORD UNPARSEABLE (invalid JSON)                                       -> distinguishable
     named reason, criteria == [].
  4. acceptance_criteria KEY ABSENT                                          -> distinguishable
     named reason, criteria == [].
  5. acceptance_criteria EMPTY ARRAY (deliberately empty, not a failure)     -> distinguishable
     named reason, criteria == [].
  6. STATE ROUND-TRIP: the real `state` object literal carries `criteriaVerdicts: []`, and the
     Criteria phase assigns the computed verdicts onto `state.criteriaVerdicts`.

Every fixture is built under a real OS temp dir (`tempfile.TemporaryDirectory()`); nothing is ever
written into this repository's working tree.

Registered in planning/harness.json's testing_strategy for this block -- run directly:
  python3 scripts/test_criteria_verdict_persistence.py
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"


def read_source() -> str:
    return ENGINE_PATH.read_text(encoding="utf-8")


def _balanced_scan(text: str, brace_start_idx: int, literal_start_idx: int) -> str:
    """From `brace_start_idx` (index of the opening `{`) scan to its matching `}` and return the
    slice [literal_start_idx, close] inclusive."""
    depth = 0
    i = brace_start_idx
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[literal_start_idx:i + 1]
        i += 1
    raise AssertionError("unbalanced braces during extraction")


def extract_function(text: str, name: str) -> str:
    """From `[async ]function <name>(...) {` to its matching `}`, inclusive -- balanced-brace
    scan. Captures a leading `async ` keyword when present so an extracted async function stays
    syntactically valid (an extraction that dropped `async` while keeping an `await` inside its
    body would be a SyntaxError under `node`, not merely wrong behaviour)."""
    m = re.search(rf"(async\s+)?function {re.escape(name)}\([^)]*\)\s*\{{", text)
    if not m:
        raise AssertionError(f"function {name}() not found in {ENGINE_PATH}")
    literal_start = m.start(1) if m.group(1) else m.start()
    return _balanced_scan(text, text.index("{", m.start()), literal_start)


def extract_const_object(text: str, name: str) -> str:
    """From `const <name> = {` to its matching top-level `}`, inclusive -- balanced-brace scan."""
    m = re.search(rf"const {re.escape(name)}\s*=\s*\{{", text)
    if not m:
        raise AssertionError(f"const {name} = {{...}} not found in {ENGINE_PATH}")
    return _balanced_scan(text, text.index("{", m.start()), m.start())


def run_node(script: str) -> str:
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"node script failed:\n{result.stderr}\n---script---\n{script}")
    return result.stdout


def load_block_record_acceptance_criteria_src() -> str:
    source = read_source()
    # loadBlockRecordAcceptanceCriteria() references CRITERIA_LOAD_SCHEMA (an agent() schema
    # option) at call time, so an extraction of the function alone throws ReferenceError the
    # moment it runs -- prepend the real, extracted schema const rather than a hand-authored
    # stand-in.
    schema_src = extract_const_object(source, "CRITERIA_LOAD_SCHEMA")
    fn_src = extract_function(source, "loadBlockRecordAcceptanceCriteria")
    return f"{schema_src}\n{fn_src}"


def extract_shared_const(name: str) -> str:
    return extract_const_object(read_source(), name)


# loadBlockRecordAcceptanceCriteria() is `async` and calls `agent(prompt, opts)` -- the ONLY
# thing the real Workflow runtime provides for file I/O (measured 2026-09-07:
# BT.ticket.engine-helpers-call-require-which-the-workflow-runtime-does-not-define; `process`,
# and therefore `require`, do not exist there at all). A bare `node -e` subprocess is the wrong
# sandbox for this function (no `agent`), so `agent()` is stubbed here to do exactly what a real
# subagent is instructed to do: extract the ONE fenced ```...``` script from the prompt verbatim
# and execute it for real via `bash -c`, then parse its tagged output lines -- never a
# reimplementation of the classification logic, which lives entirely inside that script.
AGENT_STUB_JS = r"""
global.agent = async function (prompt, opts) {
  const { execSync } = require('child_process')
  const m = prompt.match(/```\n([\s\S]*?)\n```/)
  if (!m) return { found: false, criteria: [], reason: 'no fenced script found in prompt' }
  let out
  try {
    out = execSync(m[1], { shell: '/bin/bash' }).toString()
  } catch (e) {
    out = (e.stdout || '').toString()
  }
  const foundMatch = out.match(/^FOUND:(true|false)$/m)
  const found = !!foundMatch && foundMatch[1] === 'true'
  const reasonMatch = out.match(/^REASON:(.*)$/m)
  const criteriaMatch = out.match(/^CRITERIA_JSON:(.*)$/m)
  let criteria = []
  if (found && criteriaMatch) {
    try { criteria = JSON.parse(criteriaMatch[1]) } catch (e) { criteria = [] }
  }
  return { found, criteria, reason: reasonMatch ? reasonMatch[1] : '' }
};
"""


def call_load(cwd: str, record_file: str):
    """Call the REAL, extracted loadBlockRecordAcceptanceCriteria() -- async, agent()-based --
    with `agent()` stubbed per AGENT_STUB_JS, and return its parsed result normalized to
    {"criteria": [...], "reason": <str-or-None>}."""
    script = (
        f"{load_block_record_acceptance_criteria_src()}\n"
        f"{AGENT_STUB_JS}\n"
        f";(async () => {{\n"
        f"  const result = await loadBlockRecordAcceptanceCriteria({json.dumps(cwd)}, {json.dumps(record_file)})\n"
        f"  process.stdout.write(JSON.stringify(result))\n"
        f"}})();\n"
    )
    raw = json.loads(run_node(script))
    if isinstance(raw, list):
        # Pre-fix shape: bare array, no distinguishable failure cause.
        return {"criteria": raw, "reason": None}
    if isinstance(raw, dict):
        return {"criteria": raw.get("criteria", []), "reason": raw.get("reason")}
    raise AssertionError(f"unexpected return shape from loadBlockRecordAcceptanceCriteria: {raw!r}")


class LoadBlockRecordAcceptanceCriteriaTests(unittest.TestCase):
    """Cases 1-5: the five load-failure causes from the block record's task 1 description."""

    def test_case1_criteria_present_returns_all_and_no_reason(self):
        criteria = [
            "the CLI exits 0 on valid input",
            {"criterion": "manual operator sign-off on the visual design", "gateable": False},
            {"criterion": "the fixture suite covers the happy path"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            record_path = Path(tmp) / "block.json"
            record_path.write_text(json.dumps({"acceptance_criteria": criteria}), encoding="utf-8")
            result = call_load(tmp, "block.json")

        self.assertEqual(
            result["criteria"], criteria,
            f"criteria-present case must return every entry verbatim, got {result!r}",
        )
        self.assertFalse(
            result["reason"],
            f"criteria-present case must not report a failure reason, got reason={result['reason']!r}",
        )

    def test_case2_record_missing_has_distinguishable_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            # deliberately never create block.json
            result = call_load(tmp, "block.json")

        self.assertEqual(result["criteria"], [])
        self.assertTrue(
            result["reason"],
            "a missing block record must report a NAMED reason, not a bare [] -- this is the "
            "measured defect (run wf_5ef1102e-490, 2026-09-07)",
        )

    def test_case3_record_unparseable_has_distinguishable_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = Path(tmp) / "block.json"
            record_path.write_text("{ not valid json,,,", encoding="utf-8")
            result = call_load(tmp, "block.json")

        self.assertEqual(result["criteria"], [])
        self.assertTrue(
            result["reason"],
            "invalid JSON must report a NAMED reason, not a bare []",
        )

    def test_case4_acceptance_criteria_key_absent_has_distinguishable_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = Path(tmp) / "block.json"
            record_path.write_text(json.dumps({"id": "BT.ticket.example", "kind": "ticket"}), encoding="utf-8")
            result = call_load(tmp, "block.json")

        self.assertEqual(result["criteria"], [])
        self.assertTrue(
            result["reason"],
            "a record with no acceptance_criteria key at all must report a NAMED reason",
        )

    def test_case5_acceptance_criteria_empty_array_has_distinguishable_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = Path(tmp) / "block.json"
            record_path.write_text(json.dumps({"acceptance_criteria": []}), encoding="utf-8")
            result = call_load(tmp, "block.json")

        self.assertEqual(result["criteria"], [])
        self.assertTrue(
            result["reason"],
            "a deliberately-empty acceptance_criteria array must still report a NAMED reason "
            "(distinguishing 'the author declared no criteria' from a load failure)",
        )

    def test_all_four_failure_causes_are_mutually_distinguishable(self):
        """REGRESSION CONTROL for the whole block: today all four causes collapse to the SAME
        (None) reason. If this ever regresses back to collapsing them, this test fails loudly."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = call_load(tmp, "does-not-exist.json")

            unparseable_path = Path(tmp) / "unparseable.json"
            unparseable_path.write_text("{ not valid json,,,", encoding="utf-8")
            unparseable = call_load(tmp, "unparseable.json")

            key_absent_path = Path(tmp) / "key-absent.json"
            key_absent_path.write_text(json.dumps({"id": "x"}), encoding="utf-8")
            key_absent = call_load(tmp, "key-absent.json")

            empty_path = Path(tmp) / "empty.json"
            empty_path.write_text(json.dumps({"acceptance_criteria": []}), encoding="utf-8")
            empty = call_load(tmp, "empty.json")

        reasons = [missing["reason"], unparseable["reason"], key_absent["reason"], empty["reason"]]
        self.assertTrue(
            all(reasons),
            f"every one of the four failure causes must report a truthy reason, got {reasons!r}",
        )
        self.assertEqual(
            len(set(reasons)), 4,
            "the four failure causes must be MUTUALLY DISTINGUISHABLE (four distinct reason "
            f"strings) -- today they all collapse to the same bare [], got {reasons!r}",
        )


class StateRoundTripTests(unittest.TestCase):
    """Case 6: sdlc-task-state.json's `state` object literal and the Criteria-phase assignment
    that persists computed verdicts onto it."""

    def test_state_literal_carries_criteria_verdicts_key_default_empty(self):
        source = read_source()
        state_literal = extract_const_object(source, "state")

        self.assertIn(
            "criteriaVerdicts", state_literal,
            "the `state` object literal (sdlc-task-state.json's in-memory source of truth) must "
            "carry a top-level criteriaVerdicts key -- absent today, so a populated verdict list "
            "dies with the session (measured 2026-09-07)",
        )

        # Execute the extracted literal under node with the free variables it references stubbed,
        # and confirm it actually parses to a JS object carrying criteriaVerdicts: [] by default --
        # a plain substring match could be fooled by a comment; this is not.
        script = (
            "const blockId = 'BT.ticket.example';\n"
            "const useWorktree = false;\n"
            "const baseBranchName = 'sdlc/example';\n"
            f"{state_literal}\n"
            "console.log(JSON.stringify(state))"
        )
        parsed = json.loads(run_node(script))
        self.assertIn(
            "criteriaVerdicts", parsed,
            f"the real state object, once constructed, must carry criteriaVerdicts, got keys {sorted(parsed.keys())!r}",
        )
        self.assertEqual(
            parsed["criteriaVerdicts"], [],
            "criteriaVerdicts must default to [] (absent-or-empty, never missing) until the "
            f"Criteria stage computes it, got {parsed['criteriaVerdicts']!r}",
        )
        # Sibling key `bails` follows the same "append-only, defaults empty" discipline -- pin
        # that the new key sits alongside it rather than replacing/reshuffling it.
        self.assertIn("bails", parsed)

    def test_criteria_phase_assigns_computed_verdicts_onto_state(self):
        source = read_source()

        results_assignment = re.search(r"criteriaVerdicts\s*=\s*verdict\.results", source)
        self.assertIsNotNone(
            results_assignment,
            "expected `criteriaVerdicts = verdict.results` in the Criteria phase (sdlc-task.js) "
            "-- if this literal changed, update this test's anchor",
        )

        state_assignment = re.search(r"state\.criteriaVerdicts\s*=\s*criteriaVerdicts", source)
        self.assertIsNotNone(
            state_assignment,
            "the engine must assign the computed verdicts onto `state.criteriaVerdicts` so the "
            "terminal writeTaskState() call (which serializes the whole `state` object verbatim) "
            "persists them -- today `criteriaVerdicts` is only ever a local variable, so it is "
            "returned in the run payload but never written to sdlc-task-state.json (measured "
            "2026-09-07: sdlc-task-state.json's keys are spec_slug, mode, branch, started_at, "
            "updated_at, worktree_path, status, current_task, emitStateRan, tasks_run, tasks, "
            "bail_reason, bails, tokens, base_sha -- no criteria field exists)",
        )
        self.assertGreater(
            state_assignment.start(), results_assignment.start(),
            "the state.criteriaVerdicts assignment must come AFTER the verdicts are computed, "
            "not before",
        )


if __name__ == "__main__":
    unittest.main()
