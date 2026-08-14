#!/usr/bin/env python3
"""Before/after fixture suite for D63 (planning/decisions/D63-per-task-validation-commands-augment-gating.md).

ticket-tasks-json-validation-commands-override, task 4. Before this ticket, a task-level
`validation_commands` array in tasks.json FULLY REPLACED planning/harness.json's `gates:true`
check list for that task's per-task tripwire in BOTH engines, silently, with the `validated:`
field recording the single literal string `'per-task validation_commands (tasks.json override)'`
regardless of whether any real gate ran. D63 changed the semantics per engine (augment-gating-only
for /sdlc-task, unchanged pure-substitute for /sdlc-flow, both engines now visible) — this suite
proves the fix, mechanically, against the REAL engine source, not a paraphrase of it.

This is a source-assertion + real-extracted-logic suite, not a live-agent suite: both engines drive
real LLM subagents end to end, so there is no way to run a full `/sdlc-task`/`/sdlc-flow` pass
headless (the same constraint documented in scripts/test_d16_tasks_json_fallback.py and
scripts/test_emoji_gate_diff_scoped.py). Instead this suite:

  (a) extracts the REAL, literal decision logic (the `passValidatedLabel` computation, the
      `gatingChecks()` filter, `buildPassPayload()`) out of `.claude/workflows/sdlc-task.js` and
      `sdlc-flow.js` and EXECUTES it under Node with synthetic inputs -- proving the actual shipped
      code, not a description of it, produces the right `validated:` value and the right run-state
      JSON; and
  (b) pins the surrounding structural guarantees (the harness gating checks are AUGMENTED, not
      skipped, when an override is present in /sdlc-task; the fast/cheap form is what augments, so
      the cost-saving is preserved; /sdlc-flow's end review still re-runs the full suite
      unconditionally) to the exact source text, so a regression that guts any of these is a diff
      this suite can see.

Registered in planning/harness.json as `validation-commands-override-tests` --
run directly: python3 scripts/test_validation_commands_override.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".claude" / "workflows"
TASK_JS = WORKFLOWS / "sdlc-task.js"
FLOW_JS = WORKFLOWS / "sdlc-flow.js"

# The exact literal label the pre-D63 code wrote to `validated:` for EVERY overridden task,
# regardless of whether any harness check ran. If this string reappears in either engine, the old,
# invisible, fully-replaces behaviour has come back.
OLD_LABEL = "per-task validation_commands (tasks.json override)"

# D63's shared vocabulary -- identical strings in both engines (the ADR's core requirement).
EXPECTED_LABELS = {
    "ranHarnessList": "ran the harness list",
    "substitutedSubset": "substituted a documented subset (gates:true checks still ran)",
    "ranNoneOfHarnessList": "ran none of the harness list (tasks.json override, /sdlc-flow end review will reconcile)",
}


def _read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"expected file missing: {path}")
    return path.read_text(encoding="utf-8")


def run_node(js_code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "-e", js_code],
        capture_output=True, text=True, encoding="utf-8",
    )


def extract(text: str, pattern: str, label: str) -> str:
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        raise AssertionError(f"{label}: pattern not found in source -- {pattern!r}")
    return m.group(0)


# ---------------------------------------------------------------------------------------------
# Extraction: the REAL `VALIDATED_LABEL` object literal, verbatim, from each engine.
# ---------------------------------------------------------------------------------------------
VALIDATED_LABEL_PATTERN = (
    r"const VALIDATED_LABEL = \{\n"
    r"\s*ranHarnessList: '[^']*',\n"
    r"\s*substitutedSubset: '[^']*',\n"
    r"\s*ranNoneOfHarnessList: '[^']*',\n"
    r"\}"
)


def extract_validated_label_object(text: str, label: str) -> str:
    return extract(text, VALIDATED_LABEL_PATTERN, label)


# ---------------------------------------------------------------------------------------------
# Extraction: the REAL `gatingChecks()` filter (sdlc-task.js only -- sdlc-flow.js has no
# equivalent, per D63's deliberate per-engine asymmetry).
# ---------------------------------------------------------------------------------------------
GATING_CHECKS_PATTERN = (
    r"function gatingChecks\(cfg\) \{\n"
    r"\s*return \(cfg\?\.validation\?\.checks \?\? \[\]\)\.filter\(c => c\.gates && c\.perTask !== false\)\n"
    r"\}"
)

# ---------------------------------------------------------------------------------------------
# Extraction: the REAL per-task decision line(s) computing `passValidatedLabel`.
# ---------------------------------------------------------------------------------------------
TASK_DECISION_PATTERN = (
    r"const passValidatedLabel = !hasOverride\n"
    r"\s*\? VALIDATED_LABEL\.ranHarnessList\n"
    r"\s*: \(harnessGatingCheckCount > 0 \? VALIDATED_LABEL\.substitutedSubset : VALIDATED_LABEL\.ranNoneOfHarnessList\)"
)
FLOW_DECISION_PATTERN = (
    r"const passValidatedLabel = hasOverride \? VALIDATED_LABEL\.ranNoneOfHarnessList : VALIDATED_LABEL\.ranHarnessList"
)

# ---------------------------------------------------------------------------------------------
# Extraction: the REAL `buildPassPayload()` used to fold the `validated:` value into the run-state
# JSON that /sdlc-task and /sdlc-flow actually write to disk.
# ---------------------------------------------------------------------------------------------
TASK_BUILD_PASS_PAYLOAD_PATTERN = (
    r"function buildPassPayload\(taskNum, t, validatedLabel\) \{\n"
    r"\s*const snapshot = JSON\.parse\(JSON\.stringify\(state\)\)\n"
    r"\s*snapshot\.tasks\[String\(taskNum\)\] = \{ \.\.\.t, status: 'passed', validated: validatedLabel \}\n"
    r"\s*snapshot\.tokens = buildTokensBlock\(\)\n"
    r"\s*return \{ stateFile, stateJson: JSON\.stringify\(snapshot, null, 2\) \}\n"
    r"\}"
)
FLOW_BUILD_PASS_PAYLOAD_PATTERN = (
    r"function buildPassPayload\(taskNum, t, attempt, validatedLabel\) \{\n"
    r"\s*const snapshot = JSON\.parse\(JSON\.stringify\(state\)\)\n"
    r"\s*snapshot\.tasks\[String\(taskNum\)\] = \{ \.\.\.t, status: 'passed', validated: validatedLabel \}\n"
    r"\s*snapshot\.tokens = buildTokensBlock\(\)\n"
    r"\s*const worklogEntry = \[[\s\S]*?\n\s*\]\.filter\(Boolean\)\.join\('\\n'\)\n"
    r"\s*return \{\n"
    r"\s*stateFile,\n"
    r"\s*stateJson: JSON\.stringify\(snapshot, null, 2\),\n"
    r"\s*worklogFile,\n"
    r"\s*worklogEntry,\n"
    r"\s*\}\n"
    r"\}"
)

# ---------------------------------------------------------------------------------------------
# Structural pins: the /sdlc-task augment branch inside runTests()'s usingOverride block. This is
# the mechanism that keeps a task from ever running zero harness gates:true checks silently, and
# the ONE place the cost-saving claim (fast form, not the authoritative one) lives.
# ---------------------------------------------------------------------------------------------
TASK_HARNESS_AUGMENT_PATTERN = (
    r"if \(usingOverride\) \{\n"
    r"\s*const harnessPart = harnessGatingCheckCount > 0\n"
    r"\s*\? renderCheckList\(harnessCfg, \{ gatingOnly: true, cwd: runDir, engineFiles: \[\] \}\)\n"
    r"\s*: ''\n"
)
TASK_ZERO_GATES_REPORTED_PATTERN = (
    r"overrideNote = harnessGatingCheckCount > 0\n"
    r"\s*\? '[^']*'\n"
    r"\s*: '[^']*\(D63 (?:—|--) reported, not silent\)'"
)

# The /sdlc-flow per-task override branch: taskPart REPLACES the harness list (no harnessPart at
# all) -- proves the cost-saving is untouched there too, structurally different from /sdlc-task.
FLOW_OVERRIDE_REPLACES_PATTERN = (
    r"\$\{usingOverride\n"
    r"\s*\? renderTaskCheckList\(taskCommands, worktreePath\)\n"
    r"\s*: renderCheckList\(harnessCfg, \{ gatingOnly, cwd: worktreePath, engineFiles \}\)\}"
)

# /sdlc-flow's end review re-runs the FULL suite unconditionally -- no reference to any per-task
# override anywhere near it. Regression guard for task 3's "unregressed" AC.
FLOW_END_REVIEW_FULL_SUITE_PATTERN = (
    r"\$\{renderCheckList\(harnessCfg, \{ gatingOnly: false, cwd: worktreePath, "
    r"engineFiles: \[\.\.\.new Set\(taskList\.flatMap\(n => engineFilesFor\(n\)\)\)\] \}\)\}"
)

# The terminal-output visibility line, both engines -- must be conditioned on the exact
# `ranNoneOfHarnessList` sentinel, not a separate ad hoc flag that could drift out of sync.
TASK_LOG_LINE_PATTERN = (
    r"log\(`Task \$\{taskNum\}: validated (?:→|->) \"\$\{passValidatedLabel\}\"\."
    r"\$\{passValidatedLabel === VALIDATED_LABEL\.ranNoneOfHarnessList \? ' WARNING: [^']*' : ''\}`\)"
)
FLOW_LOG_LINE_PATTERN = (
    r"log\(`Task \$\{taskNum\}: validated (?:→|->) \"\$\{passValidatedLabel\}\"\."
    r"\$\{passValidatedLabel === VALIDATED_LABEL\.ranNoneOfHarnessList \? ' NOTE: [^']*' : ''\}`\)"
)


class NegativeCaseTest(unittest.TestCase):
    """The pre-D63 behaviour (fully-replace, one undifferentiated label, silent) must be
    demonstrably ABSENT now and demonstrably able to be DETECTED if it ever came back."""

    def test_old_undifferentiated_label_absent_from_both_engines(self):
        task_src = _read(TASK_JS)
        flow_src = _read(FLOW_JS)
        self.assertNotIn(
            OLD_LABEL, task_src,
            "sdlc-task.js still contains the pre-D63 undifferentiated override label -- "
            "the fully-replaces-silently behaviour has regressed",
        )
        self.assertNotIn(
            OLD_LABEL, flow_src,
            "sdlc-flow.js still contains the pre-D63 undifferentiated override label -- "
            "the fully-replaces-silently behaviour has regressed",
        )

    def test_this_check_can_actually_detect_the_regression(self):
        """Sanity check on the assertion above: prove it fails on a synthetic pre-D63 fixture,
        so a future edit to this test can't quietly make it unable to fail."""
        fixture = "const passValidatedLabel = " + repr(OLD_LABEL).replace('"', "'")
        with self.assertRaises(AssertionError):
            self.assertNotIn(OLD_LABEL, fixture)

    def test_new_visible_trichotomy_present_in_both_engines(self):
        task_obj = extract_validated_label_object(_read(TASK_JS), "sdlc-task.js")
        flow_obj = extract_validated_label_object(_read(FLOW_JS), "sdlc-flow.js")
        for label in EXPECTED_LABELS.values():
            self.assertIn(label, task_obj, f"sdlc-task.js VALIDATED_LABEL missing {label!r}")
            self.assertIn(label, flow_obj, f"sdlc-flow.js VALIDATED_LABEL missing {label!r}")


class TrichotomyDecisionLogicTest(unittest.TestCase):
    """Executes the REAL extracted `passValidatedLabel` decision from each engine under Node,
    against synthetic inputs, and checks the actual output -- not a description of the logic."""

    def _run_task_decision(self, has_override: bool, harness_gating_check_count: int) -> str:
        decision = extract(_read(TASK_JS), TASK_DECISION_PATTERN, "sdlc-task.js decision")
        label_obj = extract_validated_label_object(_read(TASK_JS), "sdlc-task.js")
        js = f"""
{label_obj}
const hasOverride = {str(has_override).lower()}
const harnessGatingCheckCount = {harness_gating_check_count}
{decision}
process.stdout.write(passValidatedLabel)
"""
        result = run_node(js)
        self.assertEqual(result.returncode, 0, f"node failed: {result.stderr}")
        return result.stdout

    def _run_flow_decision(self, has_override: bool) -> str:
        decision = extract(_read(FLOW_JS), FLOW_DECISION_PATTERN, "sdlc-flow.js decision")
        label_obj = extract_validated_label_object(_read(FLOW_JS), "sdlc-flow.js")
        js = f"""
{label_obj}
const hasOverride = {str(has_override).lower()}
{decision}
process.stdout.write(passValidatedLabel)
"""
        result = run_node(js)
        self.assertEqual(result.returncode, 0, f"node failed: {result.stderr}")
        return result.stdout

    def test_task_engine_no_override_runs_harness_list(self):
        self.assertEqual(self._run_task_decision(False, 5), EXPECTED_LABELS["ranHarnessList"])

    def test_task_engine_override_with_gating_checks_substitutes_subset(self):
        # This is the case the pre-D63 bug silently skipped -- gates:true checks STILL run.
        self.assertEqual(self._run_task_decision(True, 5), EXPECTED_LABELS["substitutedSubset"])

    def test_task_engine_override_with_zero_gating_checks_reports_ran_none(self):
        # The one case /sdlc-task can still land on "ran none" -- must be reported, not silent.
        self.assertEqual(self._run_task_decision(True, 0), EXPECTED_LABELS["ranNoneOfHarnessList"])

    def test_flow_engine_no_override_runs_harness_list(self):
        self.assertEqual(self._run_flow_decision(False), EXPECTED_LABELS["ranHarnessList"])

    def test_flow_engine_override_always_ran_none_backstopped_by_end_review(self):
        self.assertEqual(self._run_flow_decision(True), EXPECTED_LABELS["ranNoneOfHarnessList"])

    def test_flow_engine_never_lands_on_substituted_subset(self):
        # Per the ADR: /sdlc-flow only ever resolves to {ranHarnessList, ranNoneOfHarnessList} --
        # substitutedSubset is exclusively an /sdlc-task outcome.
        for has_override in (True, False):
            self.assertNotEqual(self._run_flow_decision(has_override), EXPECTED_LABELS["substitutedSubset"])


class GatingChecksFilterTest(unittest.TestCase):
    """Executes the REAL extracted `gatingChecks()` filter under Node."""

    def _run(self, checks: list[dict]) -> list[str]:
        fn = extract(_read(TASK_JS), GATING_CHECKS_PATTERN, "sdlc-task.js gatingChecks()")
        js = f"""
{fn}
const cfg = {{ validation: {{ checks: {json.dumps(checks)} }} }}
process.stdout.write(JSON.stringify(gatingChecks(cfg).map(c => c.name)))
"""
        result = run_node(js)
        self.assertEqual(result.returncode, 0, f"node failed: {result.stderr}")
        return json.loads(result.stdout)

    def test_non_gating_checks_excluded(self):
        names = self._run([
            {"name": "a", "gates": True},
            {"name": "b", "gates": False},
        ])
        self.assertEqual(names, ["a"])

    def test_per_task_false_checks_excluded_even_if_gating(self):
        names = self._run([
            {"name": "a", "gates": True, "perTask": False},
            {"name": "b", "gates": True},
        ])
        self.assertEqual(names, ["b"])

    def test_empty_checks_yields_empty(self):
        self.assertEqual(self._run([]), [])

    def test_missing_validation_config_yields_empty(self):
        fn = extract(_read(TASK_JS), GATING_CHECKS_PATTERN, "sdlc-task.js gatingChecks()")
        js = f"{fn}\nprocess.stdout.write(JSON.stringify(gatingChecks(null)))"
        result = run_node(js)
        self.assertEqual(result.returncode, 0, f"node failed: {result.stderr}")
        self.assertEqual(json.loads(result.stdout), [])


class RunStateVisibilityTest(unittest.TestCase):
    """Builds a REAL run-state JSON file with each engine's extracted, unmodified
    `buildPassPayload()`, then inspects the WRITTEN FILE (never terminal output) for the
    `validated:` field -- per the ticket's testing strategy: 'by inspecting the run-state file,
    not by reading logs.'"""

    def setUp(self):
        self._tmpdirs: list[str] = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def _write_task_run_state(self, validated_label: str) -> Path:
        fn = extract(_read(TASK_JS), TASK_BUILD_PASS_PAYLOAD_PATTERN, "sdlc-task.js buildPassPayload()")
        tmpdir = Path(tempfile.mkdtemp(prefix="validation-override-runstate-"))
        self._tmpdirs.append(str(tmpdir))
        out_path = tmpdir / "state.json"
        js = f"""
const fs = require('fs')
const state = {{ tasks: {{}} }}
const stateFile = {json.dumps(str(out_path))}
function buildTokensBlock() {{ return {{}} }}
{fn}
const t = {{ status: 'running', attempts: 1, summary: 'docs-only edit', issues: [], fixes: [], decisions: [], files_changed: ['docs/x.md'], commit: 'abc1234' }}
const payload = buildPassPayload(7, t, {json.dumps(validated_label)})
fs.writeFileSync(payload.stateFile, payload.stateJson)
"""
        result = run_node(js)
        self.assertEqual(result.returncode, 0, f"node failed: {result.stderr}")
        self.assertTrue(out_path.exists(), "buildPassPayload did not write a run-state file")
        return out_path

    def _write_flow_run_state(self, validated_label: str) -> Path:
        fn = extract(_read(FLOW_JS), FLOW_BUILD_PASS_PAYLOAD_PATTERN, "sdlc-flow.js buildPassPayload()")
        tmpdir = Path(tempfile.mkdtemp(prefix="validation-override-runstate-"))
        self._tmpdirs.append(str(tmpdir))
        out_path = tmpdir / "state.json"
        js = f"""
const fs = require('fs')
const state = {{ tasks: {{}} }}
const stateFile = {json.dumps(str(out_path))}
const worklogFile = {json.dumps(str(tmpdir / "worklog.md"))}
function buildTokensBlock() {{ return {{}} }}
{fn}
const t = {{ status: 'running', attempts: 1, summary: 'docs-only edit', issues: [], fixes: [], decisions: [], commit: 'abc1234' }}
const payload = buildPassPayload(3, t, 1, {json.dumps(validated_label)})
fs.writeFileSync(payload.stateFile, payload.stateJson)
"""
        result = run_node(js)
        self.assertEqual(result.returncode, 0, f"node failed: {result.stderr}")
        self.assertTrue(out_path.exists(), "buildPassPayload did not write a run-state file")
        return out_path

    def test_task_engine_run_state_records_ran_harness_list(self):
        path = self._write_task_run_state(EXPECTED_LABELS["ranHarnessList"])
        data = json.loads(path.read_text())
        self.assertEqual(data["tasks"]["7"]["validated"], EXPECTED_LABELS["ranHarnessList"])

    def test_task_engine_run_state_records_substituted_subset(self):
        path = self._write_task_run_state(EXPECTED_LABELS["substitutedSubset"])
        data = json.loads(path.read_text())
        self.assertEqual(data["tasks"]["7"]["validated"], EXPECTED_LABELS["substitutedSubset"])

    def test_task_engine_run_state_records_ran_none(self):
        path = self._write_task_run_state(EXPECTED_LABELS["ranNoneOfHarnessList"])
        data = json.loads(path.read_text())
        self.assertEqual(data["tasks"]["7"]["validated"], EXPECTED_LABELS["ranNoneOfHarnessList"])

    def test_flow_engine_run_state_records_ran_harness_list(self):
        path = self._write_flow_run_state(EXPECTED_LABELS["ranHarnessList"])
        data = json.loads(path.read_text())
        self.assertEqual(data["tasks"]["3"]["validated"], EXPECTED_LABELS["ranHarnessList"])

    def test_flow_engine_run_state_records_ran_none(self):
        path = self._write_flow_run_state(EXPECTED_LABELS["ranNoneOfHarnessList"])
        data = json.loads(path.read_text())
        self.assertEqual(data["tasks"]["3"]["validated"], EXPECTED_LABELS["ranNoneOfHarnessList"])

    def test_run_state_field_never_a_fourth_ad_hoc_label(self):
        """A run-state validated field must always be one of the three ADR strings -- proves the
        inspection above is meaningful (it CAN fail on a stray fourth value)."""
        path = self._write_task_run_state("some ad hoc string that is not in the trichotomy")
        data = json.loads(path.read_text())
        self.assertNotIn(data["tasks"]["7"]["validated"], EXPECTED_LABELS.values())  # sanity: fixture is off-vocabulary
        with self.assertRaises(AssertionError):
            self.assertIn(data["tasks"]["7"]["validated"], EXPECTED_LABELS.values())


class GatingChecksNeverSilentlySkippedTest(unittest.TestCase):
    """Case 2 of the required set: a task carrying validation_commands does not end up running
    zero harness.json gates:true checks without that being reported -- pinned to the exact
    structural mechanism in each engine (not a paraphrase)."""

    def test_task_engine_augments_harness_gating_checks_when_override_present(self):
        src = _read(TASK_JS)
        # Must exist verbatim: when an override is present AND the project has gates:true checks,
        # the harness list still renders (fast form) -- this is what makes "substituted a
        # documented subset (gates:true checks still ran)" true rather than aspirational.
        extract(src, TASK_HARNESS_AUGMENT_PATTERN, "sdlc-task.js augment-gating-only mechanism")

    def test_task_engine_reports_rather_than_silently_substitutes_when_zero_gating_checks(self):
        src = _read(TASK_JS)
        note = extract(src, TASK_ZERO_GATES_REPORTED_PATTERN, "sdlc-task.js overrideNote")
        self.assertIn("reported, not silent", note)

    def test_task_engine_visibility_log_line_conditioned_on_ran_none_sentinel(self):
        extract(_read(TASK_JS), TASK_LOG_LINE_PATTERN, "sdlc-task.js visibility log line")

    def test_flow_engine_visibility_log_line_conditioned_on_ran_none_sentinel(self):
        extract(_read(FLOW_JS), FLOW_LOG_LINE_PATTERN, "sdlc-flow.js visibility log line")

    def test_this_pin_can_detect_a_reversion_to_silent_full_replace(self):
        """Sanity check: the augment-mechanism pattern must NOT match a source string shaped like
        the pre-D63 code (which skipped renderCheckList entirely inside usingOverride)."""
        pre_d63_shape = (
            "if (usingOverride) {\n"
            "    checklistBody = renderTaskCheckList(taskCommands, runDir)\n"
        )
        with self.assertRaises(AssertionError):
            extract(pre_d63_shape, TASK_HARNESS_AUGMENT_PATTERN, "synthetic pre-D63 fixture")


class CostCaseSurvivesTest(unittest.TestCase):
    """Case 4 of the required set: a docs-only task with cheap validation_commands must still
    avoid paying for the full gating suite in either engine, or the feature was destroyed rather
    than fixed."""

    def test_task_engine_augmentation_uses_fast_form_hardcoded_true(self):
        src = _read(TASK_JS)
        block = extract(src, TASK_HARNESS_AUGMENT_PATTERN, "sdlc-task.js augment mechanism")
        # `gatingOnly: true` must be a HARDCODED literal in this branch, independent of the outer
        # `testDepth`/`gatingOnly` flag -- if this ever reads the outer (possibly full-suite)
        # value instead, an overridden task could pay for the authoritative form per task, which
        # is exactly the cost this feature exists to avoid.
        self.assertIn("renderCheckList(harnessCfg, { gatingOnly: true, cwd: runDir, engineFiles: [] })", block)

    def test_flow_engine_override_still_fully_substitutes_not_augments(self):
        # Confirms /sdlc-flow's per-task override still costs only the task's own commands (never
        # the harness list too) -- augmenting here would add cost with no corresponding safety
        # gain, per the ADR's explicit rejection of "always augment".
        extract(_read(FLOW_JS), FLOW_OVERRIDE_REPLACES_PATTERN, "sdlc-flow.js override-replaces mechanism")

    def test_flow_engine_end_review_unconditionally_reruns_full_suite(self):
        # Regression guard for task 3's "unregressed" AC: the backstop that makes /sdlc-flow's
        # substitute-not-augment choice safe must still be unconditional.
        src = _read(FLOW_JS)
        extract(src, FLOW_END_REVIEW_FULL_SUITE_PATTERN, "sdlc-flow.js end-review full suite")

    def test_cost_case_pin_can_fail_if_full_suite_becomes_hardcoded_in_augment_branch(self):
        """Sanity check: the fast-form assertion must fail against a synthetic 'always pay full
        cost' regression, proving it is not vacuously true."""
        regressed_block = (
            "if (usingOverride) {\n"
            "    const harnessPart = harnessGatingCheckCount > 0\n"
            "      ? renderCheckList(harnessCfg, { gatingOnly: false, cwd: runDir, engineFiles: [] })\n"
            "      : ''\n"
        )
        self.assertNotIn(
            "renderCheckList(harnessCfg, { gatingOnly: true, cwd: runDir, engineFiles: [] })",
            regressed_block,
        )


class CrossEngineVocabularyTest(unittest.TestCase):
    """Case 5 of the required set: both engines agree on the validated: vocabulary, cross-site,
    same shape as the five-site emoji-gate suite."""

    def test_validated_label_object_byte_for_byte_identical_across_engines(self):
        task_obj = extract_validated_label_object(_read(TASK_JS), "sdlc-task.js")
        flow_obj = extract_validated_label_object(_read(FLOW_JS), "sdlc-flow.js")
        self.assertEqual(task_obj, flow_obj, "VALIDATED_LABEL must be byte-for-byte identical in both engines")

    def test_no_engine_ever_emits_a_fourth_label(self):
        key_pattern = re.compile(r"^\s*(\w+): '", re.MULTILINE)
        for path in (TASK_JS, FLOW_JS):
            src = _read(path)
            obj = extract_validated_label_object(src, path.name)
            keys = key_pattern.findall(obj)
            # Exactly the three ADR keys -- a fourth entry would be an unreviewed ad hoc label.
            self.assertEqual(
                sorted(keys), sorted(["ranHarnessList", "substitutedSubset", "ranNoneOfHarnessList"]),
                f"{path.name}: VALIDATED_LABEL must have exactly the three ADR keys, got {keys}",
            )

    def test_suite_can_detect_cross_engine_disagreement(self):
        """Sanity check: prove assertEqual above actually fails on a synthetic divergence."""
        task_obj = "const VALIDATED_LABEL = { ranHarnessList: 'ran the harness list' }"
        flow_obj = "const VALIDATED_LABEL = { ranHarnessList: 'DIFFERENT TEXT' }"
        with self.assertRaises(AssertionError):
            self.assertEqual(task_obj, flow_obj)


class HarnessRegistrationTest(unittest.TestCase):
    """This suite must itself be registered as a gates:true check in planning/harness.json."""

    def test_registered_as_gating_check_with_purpose(self):
        harness_path = REPO_ROOT / "planning" / "harness.json"
        cfg = json.loads(harness_path.read_text())
        checks = cfg.get("validation", {}).get("checks", [])
        matches = [c for c in checks if "test_validation_commands_override.py" in (c.get("command") or "")]
        self.assertTrue(matches, "planning/harness.json has no check running test_validation_commands_override.py")
        for c in matches:
            self.assertTrue(c.get("gates") is True, f"check {c.get('name')} must be gates: true")
            self.assertTrue((c.get("purpose") or "").strip(), f"check {c.get('name')} must state a purpose")


if __name__ == "__main__":
    unittest.main()
