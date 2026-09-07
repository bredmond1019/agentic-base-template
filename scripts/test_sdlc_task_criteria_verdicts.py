#!/usr/bin/env python3
"""Fixture suite for BT.ticket.sdlc-task-must-verify-its-blocks-acceptance-criteria (task 3).

Exercises the REAL `acceptanceCriteriaVerdicts()` pure function shipped in
`.claude/workflows/sdlc-task.js` (task 1) -- extracted via balanced-brace scanning and executed
through a real `node -e` invocation, never re-implemented in Python. Same discipline as
`scripts/test_bails_record.py` / `scripts/test_bail_path_runtime.py`: the source under test is the
actual engine file on disk, so a change to the function's behaviour shows up here without this
suite ever being hand-synced.

Four cases, per the block's testing_strategy and task 3's acceptance criteria:
  (a) all criteria met                                          -> close allowed
  (b) one criterion unmet                                       -> close refused
  (c) one criterion not-evaluated, declared gateable:false       -> reported not-evaluated,
                                                                     close allowed
  (d) one criterion not-evaluated, NO gateable:false declaration -> close REFUSED, criterion
                                                                     quoted verbatim in the reason
Case (d) is the regression control for the whole block (BT.ticket.sdlc-task-must-verify-its-
blocks-acceptance-criteria): if the refusal is ever removed or weakened, this case fails loudly.

Both `acceptance_criteria` item shapes from block.schema.json's oneOf are covered across the
cases: a bare string (gateable defaults to true) and the object form
{criterion, gateable, evidence, ...} (gateable also defaults to true when omitted on the object
form).

Self-contained python3, exits non-zero on any failure, writes nothing outside a temp dir (this
suite writes nothing to disk at all -- the engine source is only read, and node is invoked with
an inline `-e` script, no file created).

Registered in planning/harness.json as `sdlc-task-criteria-verdicts` --
run directly: python3 scripts/test_sdlc_task_criteria_verdicts.py
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"


def read_source() -> str:
    return ENGINE_PATH.read_text(encoding="utf-8")


def extract_function(text: str, name: str) -> str:
    """From `function <name>(...) {` to its matching `}`, inclusive -- balanced-brace scan."""
    m = re.search(rf"function {re.escape(name)}\([^)]*\)\s*\{{", text)
    if not m:
        raise AssertionError(f"function {name}() not found in {ENGINE_PATH}")
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


def acceptance_criteria_verdicts_src() -> str:
    return extract_function(read_source(), "acceptanceCriteriaVerdicts")


def run_node(script: str) -> str:
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"node script failed:\n{result.stderr}\n---script---\n{script}")
    return result.stdout


def call(acceptance_criteria, evidence_by_criterion):
    """Call the real, extracted acceptanceCriteriaVerdicts() with JSON-serializable args and
    return the parsed { results, refuse, reason } payload."""
    script = (
        f"{acceptance_criteria_verdicts_src()}\n"
        f"const acceptanceCriteria = {json.dumps(acceptance_criteria)}\n"
        f"const evidenceByCriterion = {json.dumps(evidence_by_criterion)}\n"
        "console.log(JSON.stringify(acceptanceCriteriaVerdicts(acceptanceCriteria, evidenceByCriterion)))"
    )
    return json.loads(run_node(script))


class AcceptanceCriteriaVerdictsTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # (a) all criteria met -> close allowed
    # ------------------------------------------------------------------
    def test_case_a_all_met_close_allowed(self):
        criteria = [
            "the CLI exits 0 on valid input",
            {"criterion": "the fixture suite covers the happy path", "gateable": True},
        ]
        evidence = {
            "the CLI exits 0 on valid input": {"evaluated": True, "met": True},
            "the fixture suite covers the happy path": {"evaluated": True, "met": True},
        }
        payload = call(criteria, evidence)

        self.assertEqual(
            [r["verdict"] for r in payload["results"]], ["met", "met"],
            f"all-met case must verdict both criteria 'met', got {payload['results']!r}",
        )
        self.assertFalse(
            payload["refuse"],
            f"all-met case must allow a clean close, got refuse={payload['refuse']!r} "
            f"reason={payload['reason']!r}",
        )
        self.assertIsNone(payload["reason"])

    # ------------------------------------------------------------------
    # (b) one criterion unmet -> close refused
    # ------------------------------------------------------------------
    def test_case_b_one_unmet_close_refused(self):
        criteria = [
            "the CLI exits 0 on valid input",
            "ingest against the live brain root reports skipped_rust: 1",
        ]
        evidence = {
            "the CLI exits 0 on valid input": {"evaluated": True, "met": True},
            "ingest against the live brain root reports skipped_rust: 1": {
                "evaluated": True, "met": False,
            },
        }
        payload = call(criteria, evidence)

        self.assertEqual(
            [r["verdict"] for r in payload["results"]], ["met", "unmet"],
            f"one-unmet case must verdict the second criterion 'unmet', got {payload['results']!r}",
        )
        self.assertTrue(
            payload["refuse"],
            "an UNMET criterion must refuse the close",
        )
        self.assertIn(
            "ingest against the live brain root reports skipped_rust: 1", payload["reason"],
            f"refusal reason must quote the unmet criterion verbatim, got {payload['reason']!r}",
        )

    # ------------------------------------------------------------------
    # (c) one criterion not-evaluated, declared gateable:false
    #     -> reported not-evaluated, close allowed
    # ------------------------------------------------------------------
    def test_case_c_declared_not_evaluated_close_allowed(self):
        criteria = [
            "the fixture suite covers all three verdicts and the refusal",
            {
                "criterion": "manual operator sign-off on the visual design",
                "gateable": False,
            },
        ]
        evidence = {
            "the fixture suite covers all three verdicts and the refusal": {
                "evaluated": True, "met": True,
            },
            # deliberately no evidence entry for the gateable:false criterion -- it must not
            # need one to avoid a refusal.
        }
        payload = call(criteria, evidence)

        verdict_by_criterion = {r["criterion"]: r["verdict"] for r in payload["results"]}
        self.assertEqual(
            verdict_by_criterion["manual operator sign-off on the visual design"],
            "not-evaluated",
            f"a gateable:false criterion must verdict 'not-evaluated', got {payload['results']!r}",
        )
        self.assertFalse(
            payload["refuse"],
            "a declared gateable:false not-evaluated criterion must NOT refuse the close, got "
            f"refuse={payload['refuse']!r} reason={payload['reason']!r}",
        )
        self.assertIsNone(payload["reason"])

    # ------------------------------------------------------------------
    # (d) one criterion not-evaluated, NO gateable:false declaration
    #     -> close REFUSED, criterion quoted verbatim. REGRESSION CONTROL.
    # ------------------------------------------------------------------
    def test_case_d_undeclared_not_evaluated_close_refused(self):
        undeclared_criterion = "jynx's own fixture exclusion still works"
        criteria = [
            "the CLI exits 0 on valid input",
            undeclared_criterion,
        ]
        evidence = {
            "the CLI exits 0 on valid input": {"evaluated": True, "met": True},
            # no evidence entry at all for `undeclared_criterion`, and it carries no
            # gateable:false -- this is the exact defect class the block exists to close.
        }
        payload = call(criteria, evidence)

        verdict_by_criterion = {r["criterion"]: r["verdict"] for r in payload["results"]}
        self.assertEqual(
            verdict_by_criterion[undeclared_criterion], "not-evaluated",
            f"an unevaluated criterion with no gateable:false must verdict 'not-evaluated', "
            f"got {payload['results']!r}",
        )
        self.assertTrue(
            payload["refuse"],
            "REGRESSION: an undeclared not-evaluated criterion must REFUSE the close -- if this "
            "assertion fails, sdlc-task can once again close a block whose stated acceptance "
            "criterion was never checked (the exact defect this block was filed to fix).",
        )
        self.assertIn(
            undeclared_criterion, payload["reason"],
            f"refusal reason must quote the undeclared not-evaluated criterion verbatim, "
            f"got {payload['reason']!r}",
        )

    # ------------------------------------------------------------------
    # Object-form item shape, gateable omitted -> defaults to true (both cases already exercise
    # the bare-string shape; this pins the object-form default explicitly).
    # ------------------------------------------------------------------
    def test_object_form_gateable_defaults_to_true(self):
        criterion_text = "the run payload carries a per-criterion verdict"
        criteria = [{"criterion": criterion_text}]  # no `gateable` key at all
        payload = call(criteria, {})  # no evidence supplied -> must be undeclared not-evaluated

        self.assertEqual(len(payload["results"]), 1)
        self.assertTrue(
            payload["results"][0]["gateable"],
            "object-form item with `gateable` omitted must default to gateable:true",
        )
        self.assertEqual(payload["results"][0]["verdict"], "not-evaluated")
        self.assertTrue(
            payload["refuse"],
            "an object-form criterion with gateable omitted (defaults true) and no evidence "
            "must refuse the close, same as the bare-string undeclared case",
        )
        self.assertIn(criterion_text, payload["reason"])


if __name__ == "__main__":
    unittest.main()
