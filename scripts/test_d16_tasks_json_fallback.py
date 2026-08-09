#!/usr/bin/env python3
"""Regression tests for the D16 preflight's derive-from-tasks.md fallback.

RED-FIRST (ticket-generate-tasks-json-on-ticket, task 1): at this commit none of the four SDLC
engines carry the fallback yet, so this script MUST FAIL. It is deliberately NOT registered in
planning/harness.json yet (that happens in task 5) — a red test at task 1 must not gate the rest
of the chain.

This is a source-assertion suite, not a live-agent suite: the derivation itself is performed by an
LLM agent at runtime (mirroring /generate-tasks --from mode), so there is no pure function to
unit-test the way scripts/check_skill_sync.py tests a real Python module. Instead this asserts the
CONTRACT every engine's source must satisfy — the same idiom as
scripts/test_sync_downstream_harness.py and scripts/test_check_skill_sync.py: synthetic fixtures
plus assertions over the real engine/doc sources, stdlib only, non-zero exit on failure.

THE CONTRACT (what tasks 2-4 must land for this file to go green):

  1. `.claude/workflows/sdlc-task.js`, `sdlc-flow.js` and `sdlc-run.js` must each contain the
     literal marker comment:
         D16 derive-from-tasks.md fallback
     positioned BEFORE the abort line `'No tasks.json (D16)'` in the same file (sdlc-run.js
     currently has neither — task 3 adds both the preflight and the fallback to reach parity).

  2. Between that marker and the abort, each of the three files must read tasks.md (substring
     "tasks.md") and must name the D45 shape it writes: substrings "D45", "bare array", "task_id".

  3. Each of the three files must contain a log line distinguishing a derived run from an authored
     one, substring:
         Derived tasks.json from tasks.md

  4. The abort itself must survive, unchanged in spirit: `.claude/workflows/sdlc-task.js` and
     `sdlc-flow.js` keep their existing `'No tasks.json (D16)'` abort; sdlc-run.js gains one.

  5. `.claude/workflows/sdlc-block.js` keeps its pre-existing generator (the
     "no tasks.json - generating from the plan's block" line) intact, and gains a comment
     cross-referencing the three sibling engines by filename (task 3's parity note).

  6. `.claude/commands/ticket.md` and `.agents/skills/ticket/SKILL.md` must both require a
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

SEQUENTIAL_ENGINES = ["sdlc-task.js", "sdlc-flow.js", "sdlc-run.js"]
ALL_ENGINES = SEQUENTIAL_ENGINES + ["sdlc-block.js"]

MARKER_COMMENT = "D16 derive-from-tasks.md fallback"
ABORT_SUBSTR = "No tasks.json (D16)"
DERIVED_LOG_SUBSTR = "Derived tasks.json from tasks.md"
D45_KEYWORDS = ["D45", "bare array", "task_id"]

TICKET_MD = REPO_ROOT / ".claude" / "commands" / "ticket.md"
TICKET_SKILL = REPO_ROOT / ".agents" / "skills" / "ticket" / "SKILL.md"
GENERATE_TASKS_MD = REPO_ROOT / ".claude" / "commands" / "generate-tasks.md"

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
    """Each of the three sequential engines must derive tasks.json before it aborts."""

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

    def test_sdlc_run_gains_the_same_abort(self):
        src = _read(WORKFLOWS / "sdlc-run.js")
        self.assertIn(
            ABORT_SUBSTR, src,
            "sdlc-run.js has no D16 preflight at all today (no hasTasks check, no abort) — "
            "task 3 must add one so all three sequential engines refuse to guess identically",
        )


class BlockEngineParity(unittest.TestCase):
    """sdlc-block.js already generates tasks.json — assert it stays intact and cross-references
    its three siblings (task 3's parity note)."""

    def test_existing_generator_intact(self):
        src = _read(WORKFLOWS / "sdlc-block.js")
        self.assertIn(
            "no tasks.json", src.lower(),
            "sdlc-block.js's pre-existing tasks.json generator appears to have been removed",
        )

    def test_cross_references_sibling_engines(self):
        src = _read(WORKFLOWS / "sdlc-block.js")
        gen_idx = src.lower().find("no tasks.json")
        self.assertNotEqual(gen_idx, -1)
        # Look at a generous window around the generator for the cross-reference comment.
        window = src[max(0, gen_idx - 2000):gen_idx + 4000]
        missing = [f for f in SEQUENTIAL_ENGINES if f not in window]
        if missing:
            self.fail(
                "sdlc-block.js's generator does not cross-reference its sibling engine(s) by "
                f"filename: {missing}"
            )


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


class MeasuredBaseline(unittest.TestCase):
    """Sanity-checks the fleet-wide baseline claim from this spec's Description: prose-only ticket
    specs (tasks.md present, tasks.json absent) exist in this repo's own planning vault today."""

    def test_at_least_one_prose_only_ticket_spec_exists_locally(self):
        planning = REPO_ROOT / "planning"
        prose_only = []
        for d in sorted(planning.iterdir()):
            if not d.is_dir() or not d.name.startswith("ticket-"):
                continue
            if (d / "tasks.md").exists() and not (d / "tasks.json").exists():
                prose_only.append(d.name)
        self.assertTrue(
            prose_only,
            "expected at least one prose-only ticket spec (tasks.md, no tasks.json) locally — "
            "see this spec's Amendment Log for the measured baseline",
        )


if __name__ == "__main__":
    unittest.main()
