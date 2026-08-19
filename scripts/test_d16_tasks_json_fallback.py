#!/usr/bin/env python3
"""Regression tests for the D16 preflight's derive-from-tasks.md fallback.

RED-FIRST (ticket-generate-tasks-json-on-ticket, task 1): at this commit none of the SDLC engines
carried the fallback yet, so this script MUST FAIL. It was deliberately NOT registered in
planning/harness.json yet (that happened in task 5) — a red test at task 1 must not gate the rest
of the chain. Two of the four engines this suite originally covered (sdlc-run.js, sdlc-block.js)
were later retired as effectively unused (BT.ticket.retire-unused-engines); this suite now covers
only the two surviving engines.

This is a source-assertion suite, not a live-agent suite: the derivation itself is performed by an
LLM agent at runtime (mirroring /generate-tasks --from mode), so there is no pure function to
unit-test the way scripts/check_skill_sync.py tests a real Python module. Instead this asserts the
CONTRACT every engine's source must satisfy — the same idiom as
scripts/test_sync_downstream_harness.py and scripts/test_check_skill_sync.py: synthetic fixtures
plus assertions over the real engine/doc sources, stdlib only, non-zero exit on failure.

THE CONTRACT (what tasks 2-4 must land for this file to go green):

  1. `.claude/workflows/sdlc-task.js` and `sdlc-flow.js` must each contain the literal marker
     comment:
         D16 derive-from-tasks.md fallback
     positioned BEFORE the abort line `'No tasks.json (D16)'` in the same file.

  2. Between that marker and the abort, each file must read tasks.md (substring "tasks.md") and
     must name the D45 shape it writes: substrings "D45", "bare array", "task_id".

  3. Each file must contain a log line distinguishing a derived run from an authored one,
     substring:
         Derived tasks.json from tasks.md

  4. The abort itself must survive, unchanged in spirit: `.claude/workflows/sdlc-task.js` and
     `sdlc-flow.js` keep their existing `'No tasks.json (D16)'` abort.

  5. `.claude/commands/ticket.md` and `.agents/skills/ticket/SKILL.md` must both require a
     read-back verification of the written tasks.json (not merely an assertion): both must contain
     `json.load(open(`, `non-empty bare array`, and cite `D16`, and must not have drifted from each
     other on that instruction (same required-phrase set present in both).

Run: python3 scripts/test_d16_tasks_json_fallback.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".claude" / "workflows"

SEQUENTIAL_ENGINES = ["sdlc-task.js", "sdlc-flow.js"]
ALL_ENGINES = SEQUENTIAL_ENGINES

MARKER_COMMENT = "D16 derive-from-tasks.md fallback"
ABORT_SUBSTR = "No tasks.json (D16)"
DERIVED_LOG_SUBSTR = "Derived tasks.json from tasks.md"
D45_KEYWORDS = ["D45", "bare array", "task_id"]

TICKET_MD = REPO_ROOT / ".claude" / "commands" / "ticket.md"
TICKET_SKILL = REPO_ROOT / ".agents" / "skills" / "ticket" / "SKILL.md"
GENERATE_TASKS_MD = REPO_ROOT / ".claude" / "commands" / "generate-tasks.md"

# ticket-derive-tasks-json-validation-scope (task 4): the D16 STEP 3 derive prompts must honour the
# generate-tasks.md:292 validation_commands [] convention. See that ticket's Description for the
# measured false-pass baseline this pins against.
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
TICKET_SKILL_TASK = SKILLS_DIR / "sdlc-task" / "SKILL.md"
TICKET_SKILL_FLOW = SKILLS_DIR / "sdlc-flow" / "SKILL.md"

VALIDATION_SCOPE_CITATION = "generate-tasks.md"
VALIDATION_SCOPE_EMPTY_RULE_PHRASES = [
    "is [] for any task that touches source",
    "CANNOT break the build",
]
CONDITIONAL_TARGETING_PHRASES = [
    "target that task's own tests",
    "match zero or the wrong tests",
]
# Stack-specific test-runner invocations that must never be hardcoded into a derive prompt
# (CLAUDE.md standing rule 1 — the engines ship mechanism, never project facts).
HARDCODED_STACK_COMMAND_SUBSTRINGS = [
    "cargo nextest run",
    "cargo test",
    "npm test",
    "npm run test",
    "pytest ",
    "go test",
]

READBACK_REQUIRED_PHRASES = [
    "json.load(open(",
    "non-empty bare array",
    "D16",
]


def _read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"expected file missing: {path}")
    return path.read_text()


class EngineDerivationBranch(unittest.TestCase):
    """Each of the sequential engines must derive tasks.json before it aborts."""

    def test_all_engine_files_exist(self):
        for name in ALL_ENGINES:
            self.assertTrue((WORKFLOWS / name).exists(), f"missing engine file: {name}")

    def test_sequential_engines_carry_derivation_marker_before_abort(self):
        failures = []
        for name in SEQUENTIAL_ENGINES:
            src = _read(WORKFLOWS / name)
            marker_idx = src.find(MARKER_COMMENT)
            abort_idx = src.find(ABORT_SUBSTR)
            if marker_idx == -1:
                failures.append(f"{name}: missing derivation marker comment ({MARKER_COMMENT!r})")
                continue
            if abort_idx == -1:
                failures.append(f"{name}: missing the D16 abort ({ABORT_SUBSTR!r})")
                continue
            if not marker_idx < abort_idx:
                failures.append(f"{name}: derivation marker must appear BEFORE the abort, not after")
        if failures:
            self.fail(
                "engine(s) lacking the D16 derive-from-tasks.md fallback branch:\n  "
                + "\n  ".join(failures)
            )

    def test_derivation_reads_tasks_md_and_names_d45_shape(self):
        failures = []
        for name in SEQUENTIAL_ENGINES:
            src = _read(WORKFLOWS / name)
            marker_idx = src.find(MARKER_COMMENT)
            abort_idx = src.find(ABORT_SUBSTR)
            if marker_idx == -1 or abort_idx == -1 or not marker_idx < abort_idx:
                failures.append(f"{name}: derivation branch not found (see prior test)")
                continue
            span = src[marker_idx:abort_idx + len(ABORT_SUBSTR) + 400]
            if "tasks.md" not in span:
                failures.append(f"{name}: derivation branch does not mention tasks.md")
            missing_keywords = [kw for kw in D45_KEYWORDS if kw not in span]
            if missing_keywords:
                failures.append(f"{name}: derivation branch missing D45 shape keyword(s): {missing_keywords}")
        if failures:
            self.fail("\n  ".join(failures))

    def test_derivation_is_logged_distinctly(self):
        failures = [
            name for name in SEQUENTIAL_ENGINES
            if DERIVED_LOG_SUBSTR not in _read(WORKFLOWS / name)
        ]
        if failures:
            self.fail(
                f"engine(s) missing the distinguishing log line ({DERIVED_LOG_SUBSTR!r}): {failures}"
            )


class AbortSurvives(unittest.TestCase):
    """D16 must still refuse to guess when nothing is derivable."""

    def test_sdlc_task_and_flow_keep_their_existing_abort(self):
        for name in ("sdlc-task.js", "sdlc-flow.js"):
            src = _read(WORKFLOWS / name)
            self.assertIn(ABORT_SUBSTR, src, f"{name} must keep its 'No tasks.json (D16)' abort")


class TicketSelfCheckHardened(unittest.TestCase):
    """/ticket's step-8 self-check must become a real read-back verification, mirrored in the
    Gemini-facing skill guide."""

    def test_ticket_md_requires_readback_verification(self):
        src = _read(TICKET_MD)
        missing = [p for p in READBACK_REQUIRED_PHRASES if p not in src]
        if missing:
            self.fail(f".claude/commands/ticket.md missing read-back phrase(s): {missing}")

    def test_skill_guide_requires_readback_verification(self):
        src = _read(TICKET_SKILL)
        missing = [p for p in READBACK_REQUIRED_PHRASES if p not in src]
        if missing:
            self.fail(f".agents/skills/ticket/SKILL.md missing read-back phrase(s): {missing}")

    def test_ticket_md_and_skill_guide_do_not_drift_on_readback(self):
        ticket_src = _read(TICKET_MD)
        skill_src = _read(TICKET_SKILL)
        ticket_has = {p: p in ticket_src for p in READBACK_REQUIRED_PHRASES}
        skill_has = {p: p in skill_src for p in READBACK_REQUIRED_PHRASES}
        self.assertEqual(
            ticket_has, skill_has,
            "ticket.md and SKILL.md disagree on which read-back phrases are present — drift",
        )

    def test_generate_tasks_cross_references_engine_derivation(self):
        src = _read(GENERATE_TASKS_MD)
        self.assertTrue(
            "derive" in src.lower() and any(name in src for name in SEQUENTIAL_ENGINES),
            "generate-tasks.md should cross-reference the engines' derivation path so the two "
            "surfaces describe one behaviour",
        )


class DerivationShapeConformance(unittest.TestCase):
    """Independent of any engine: pins the exact D45 array shape the derivation must produce, and
    proves this shape validator itself distinguishes good arrays from the superseded D44 wrapper
    and from hand-authored status/attempt_count fields."""

    @staticmethod
    def _validate_d45_shape(tasks) -> list:
        errors = []
        if not isinstance(tasks, list):
            return ["must be a bare array, not an object (D44 wrapper is superseded)"]
        if not tasks:
            return ["must be non-empty"]
        for i, t in enumerate(tasks):
            if not isinstance(t, dict):
                errors.append(f"task[{i}] is not an object")
                continue
            if not isinstance(t.get("task_id"), int) or t.get("task_id") != i + 1:
                errors.append(f"task[{i}].task_id must be the 1-indexed integer {i + 1}")
            if not isinstance(t.get("title"), str):
                errors.append(f"task[{i}].title must be a string")
            if not isinstance(t.get("description"), str):
                errors.append(f"task[{i}].description must be a single string")
            for field in ("acceptance_criteria", "validation_commands", "files", "dependsOn"):
                if not isinstance(t.get(field), list):
                    errors.append(f"task[{i}].{field} must be an array")
            if t.get("max_attempts") != 3:
                errors.append(f"task[{i}].max_attempts must be 3")
            if "status" in t or "attempt_count" in t:
                errors.append(f"task[{i}] must not author status/attempt_count (engine-owned)")
        return errors

    def test_valid_d45_array_passes(self):
        valid = [
            {
                "task_id": 1, "title": "Do it", "description": "One string of description.",
                "acceptance_criteria": ["it works"], "validation_commands": [],
                "max_attempts": 3, "files": ["a.py"], "dependsOn": [],
            }
        ]
        self.assertEqual(self._validate_d45_shape(valid), [])

    def test_d44_wrapper_rejected(self):
        wrapped = {"tasks": [{"task_id": 1}]}
        errors = self._validate_d45_shape(wrapped)
        self.assertTrue(errors and "bare array" in errors[0])

    def test_authored_status_field_rejected(self):
        tasks = [
            {
                "task_id": 1, "title": "t", "description": "d",
                "acceptance_criteria": [], "validation_commands": [],
                "max_attempts": 3, "files": [], "dependsOn": [], "status": "pending",
            }
        ]
        errors = self._validate_d45_shape(tasks)
        self.assertTrue(any("status" in e for e in errors))

    def test_fixture_spec_dir_with_tasks_md_and_no_tasks_json(self):
        """Build a synthetic spec dir mirroring the real-world case (e.g.
        planning/ticket-compilable-task-boundaries): tasks.md with a step decomposition, no
        tasks.json. The derivation path must exist in the engines (asserted above) — this fixture
        documents the exact shape the derived output must satisfy once written."""
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = Path(tmp) / "planning" / "ticket-fixture-example"
            spec_dir.mkdir(parents=True)
            (spec_dir / "tasks.md").write_text(
                "## Step by Step Tasks\n\n"
                "1. Do the first thing\n2. Do the second thing\n\n"
                "## Acceptance Criteria\n- it works\n"
            )
            self.assertFalse((spec_dir / "tasks.json").exists())
            self.assertTrue((spec_dir / "tasks.md").exists())
            # The would-be derived output, hand-shaped to prove the validator accepts a
            # genuinely-derived-looking array.
            derived = [
                {
                    "task_id": 1, "title": "Do the first thing", "description": "Do the first thing.",
                    "acceptance_criteria": [], "validation_commands": [],
                    "max_attempts": 3, "files": [], "dependsOn": [],
                },
                {
                    "task_id": 2, "title": "Do the second thing", "description": "Do the second thing.",
                    "acceptance_criteria": ["it works"], "validation_commands": [],
                    "max_attempts": 3, "files": [], "dependsOn": [1],
                },
            ]
            self.assertEqual(self._validate_d45_shape(derived), [])


FRESH_DECOMPOSED_MARKER = "author a FRESH decomposed"
STEP4_MARKER = "STEP 4"


def _derive_prompt_span(name: str) -> str:
    """Return the STEP 3 'author a FRESH decomposed tasks.json' region of one engine's source —
    the exact prompt region task 4 pins the validation_commands scoping rule inside. Whitespace
    (including the template literal's line-wrap newlines) is collapsed to single spaces so a
    phrase check isn't defeated by where the prompt happens to wrap a line."""
    src = _read(WORKFLOWS / name)
    start = src.find(FRESH_DECOMPOSED_MARKER)
    if start == -1:
        raise AssertionError(f"{name}: missing the '{FRESH_DECOMPOSED_MARKER}' STEP 3 prompt")
    end = src.find(STEP4_MARKER, start)
    if end == -1:
        raise AssertionError(f"{name}: missing a STEP 4 marker after STEP 3 to bound the span")
    return _normalize(src[start:end])


def _normalize(text: str) -> str:
    """Collapse whitespace and drop backticks so the two authoring surfaces — an engine's
    template literal (escaped `` \\` `` around code terms) and a SKILL.md guide (bare Markdown
    backticks around the same terms) — compare on prose content, not on which register's quoting
    convention it happens to use."""
    return " ".join(text.replace("\\`", "").replace("`", "").split())


class ValidationCommandsScopingConvention(unittest.TestCase):
    """ticket-derive-tasks-json-validation-scope, task 4: the D16 STEP 3 derive prompts must
    teach the deriving agent the generate-tasks.md:292 validation_commands [] convention, per
    engine — a fix landed on one file and not the others must fail this suite."""

    def test_each_engine_states_the_empty_convention_separately(self):
        # Deliberately one assertion PER ENGINE, not a single loop assertion that is satisfied by
        # any one match — the measured defect's shape is "fixed in one file, missing in the
        # others", and a collapsed assertion would not catch that.
        for name in SEQUENTIAL_ENGINES:
            with self.subTest(engine=name):
                span = _derive_prompt_span(name)
                missing = [p for p in VALIDATION_SCOPE_EMPTY_RULE_PHRASES if p not in span]
                self.assertFalse(
                    missing,
                    f"{name}: STEP 3 derive prompt missing validation_commands [] convention "
                    f"phrase(s): {missing}",
                )

    def test_each_engine_cites_generate_tasks_md_rather_than_paraphrasing(self):
        for name in SEQUENTIAL_ENGINES:
            with self.subTest(engine=name):
                span = _derive_prompt_span(name)
                self.assertIn(
                    VALIDATION_SCOPE_CITATION, span,
                    f"{name}: STEP 3 derive prompt must cite {VALIDATION_SCOPE_CITATION} as the "
                    "convention's source rather than restating the rubric in its own words",
                )

    def test_conditional_targeting_rule_present_in_all_three(self):
        for name in SEQUENTIAL_ENGINES:
            with self.subTest(engine=name):
                span = _derive_prompt_span(name)
                missing = [p for p in CONDITIONAL_TARGETING_PHRASES if p not in span]
                self.assertFalse(
                    missing,
                    f"{name}: STEP 3 derive prompt missing conditional targeting rule "
                    f"phrase(s): {missing} — an authored override that runs tests must target "
                    "that task's own tests and fail rather than pass on a zero match",
                )

    def test_no_engine_hardcodes_a_stack_specific_test_command(self):
        # CLAUDE.md standing rule 1: the engines ship mechanism, never project facts. The worked
        # example (cargo nextest run <binary>) belongs in the ticket, not in any engine prompt.
        for name in SEQUENTIAL_ENGINES:
            with self.subTest(engine=name):
                span = _derive_prompt_span(name)
                hits = [s for s in HARDCODED_STACK_COMMAND_SUBSTRINGS if s in span]
                self.assertFalse(
                    hits,
                    f"{name}: STEP 3 derive prompt hardcodes stack-specific test command(s) {hits} "
                    "— this is engine mechanism and must stay project-agnostic",
                )

    def test_removing_the_rule_from_a_single_engine_fails_the_suite(self):
        # Proves the per-engine assertions actually discriminate rather than passing vacuously —
        # simulate the exact measured defect (rule present in some engines, absent in one) using a
        # synthetic span instead of mutating real source.
        good_span = (
            "validation_commands\" is [] for any task that touches source ... "
            "Set it ONLY for a task that CANNOT break the build ... "
            "target that task's own tests specifically ... "
            "match zero or the wrong tests ... " + VALIDATION_SCOPE_CITATION
        )
        bad_span = "author a FRESH decomposed tasks.json from tasks.md's step list."

        def _check(span: str) -> list:
            errs = []
            if any(p not in span for p in VALIDATION_SCOPE_EMPTY_RULE_PHRASES):
                errs.append("missing empty-rule phrase")
            if VALIDATION_SCOPE_CITATION not in span:
                errs.append("missing citation")
            if any(p not in span for p in CONDITIONAL_TARGETING_PHRASES):
                errs.append("missing conditional targeting phrase")
            return errs

        self.assertEqual(_check(good_span), [])
        self.assertTrue(_check(bad_span), "a span lacking the rule must be flagged, not pass")

    def test_skill_guides_do_not_drift_from_engines_on_scoping_rule(self):
        # Same no-drift idiom as test_ticket_md_and_skill_guide_do_not_drift_on_readback: each
        # SKILL.md guide must agree with its matching engine on which scoping-rule phrases are
        # present, since the guides do not auto-sync from the .js (CLAUDE.md update loop step 6).
        pairs = [
            (WORKFLOWS / "sdlc-task.js", TICKET_SKILL_TASK, "sdlc-task"),
            (WORKFLOWS / "sdlc-flow.js", TICKET_SKILL_FLOW, "sdlc-flow"),
        ]
        all_phrases = (
            VALIDATION_SCOPE_EMPTY_RULE_PHRASES
            + [VALIDATION_SCOPE_CITATION]
            + CONDITIONAL_TARGETING_PHRASES
        )
        failures = []
        for engine_path, skill_path, label in pairs:
            engine_span = _derive_prompt_span(engine_path.name)
            skill_src = _normalize(_read(skill_path))
            engine_has = {p: p in engine_span for p in all_phrases}
            skill_has = {p: p in skill_src for p in all_phrases}
            if engine_has != skill_has:
                failures.append(f"{label}: engine vs SKILL.md phrase presence disagrees — drift")
        if failures:
            self.fail("\n  ".join(failures))


class MeasuredBaseline(unittest.TestCase):
    """Observes the prose-only ticket-spec population in this repo's own planning vault.

    This class records a CENSUS, not an invariant. It originally asserted that at least one
    prose-only ticket spec (tasks.md present, tasks.json absent) existed locally, as a sanity-check
    on the baseline claim in the D16 spec's Description.

    That assertion was wrong as a gating check, and it went red on 2026-08-13 the moment the last
    three prose-only specs were decomposed by /generate-tasks during a routine /orchestrate chain.
    The population reaching zero is the harness WORKING — every spec carrying an authored tasks.json
    is the intended end state, and D16's fallback exists precisely so the remaining ones can be
    recovered. Gating on a mutable corpus census means the check fails on success, and it fails for
    the repo that finished its migration first.

    The D16 fallback BEHAVIOUR is covered by the synthetic-fixture tests above, which do not depend
    on corpus state. This class now reports the census and skips when it is empty, so a legitimate
    end state can never red-gate the fleet again. When the population is non-empty it still asserts
    something real: that each member is genuinely prose-only and would therefore exercise the
    fallback.
    """

    def _prose_only_specs(self):
        planning = REPO_ROOT / "planning"
        prose_only = []
        for d in sorted(planning.iterdir()):
            if not d.is_dir() or not d.name.startswith("ticket-"):
                continue
            if (d / "tasks.md").exists() and not (d / "tasks.json").exists():
                prose_only.append(d)
        return prose_only

    def test_prose_only_ticket_specs_when_present_are_derivable_by_the_fallback(self):
        prose_only = self._prose_only_specs()
        if not prose_only:
            self.skipTest(
                "no prose-only ticket specs remain locally — this is the intended end state, "
                "not a regression; D16 fallback behaviour is covered by the fixture tests above"
            )
        # Not a tautology: the selector above keys on FILE PRESENCE, this asserts the tasks.md is
        # substantive enough for D16's derive to have a source. A stub tasks.md is exactly the
        # underivable case D16 is documented to abort on, and it should surface here, not at run time.
        failures = []
        for d in prose_only:
            text = (d / "tasks.md").read_text(encoding="utf-8")
            if not text.startswith("---"):
                failures.append(f"{d.name}: tasks.md has no OKF frontmatter")
            if "## Acceptance Criteria" not in text:
                failures.append(f"{d.name}: tasks.md has no '## Acceptance Criteria' section")
            if len(text.split()) < 100:
                failures.append(f"{d.name}: tasks.md is a stub ({len(text.split())} words)")
        if failures:
            self.fail("\n  ".join(failures))


if __name__ == "__main__":
    unittest.main()
