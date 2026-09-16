#!/usr/bin/env python3
"""Fixture suite for BT.ticket.gate-results-and-failure-attribution (task 4).

Static-analysis style, matching scripts/test_check_prompt_templates.py's pattern of
reading the engine source as text and asserting on it -- these engines cannot be
live-invoked from a unit test (they are Workflow tool scripts, not importable
modules). Two things are pinned here:

1. TEST_SCHEMA in both sdlc-task.js and sdlc-flow.js declares the `gate_results` and
   `check_id_raw` fields task 1 added, with the required check_id/status/failing_ids
   sub-shape.
2. sdlc-task.js's per-task loop structurally calls triage() ONLY in the branch that
   runs after `testResult.allPassed` is checked false -- i.e. no triage() call sits
   between that check and its own `break` on the green path. This is a fixture proving
   the already-true control flow the block record describes, not a behavior change.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINES = {
    "sdlc-task": ROOT / ".claude/workflows/sdlc-task.js",
    "sdlc-flow": ROOT / ".claude/workflows/sdlc-flow.js",
}

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


def extract_object_literal(src: str, marker: str) -> str:
    """Return the full `{ ... }` object literal that follows `marker`, brace-matched."""
    idx = src.index(marker)
    start = src.index("{", idx)
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise ValueError(f"unterminated object literal for marker {marker!r}")


def test_schema_has_gate_results_and_check_id_raw() -> None:
    for engine, path in ENGINES.items():
        src = path.read_text()
        schema_src = extract_object_literal(src, "const TEST_SCHEMA = ")
        check(f"{engine}: TEST_SCHEMA declares gate_results", "gate_results:" in schema_src)
        check(f"{engine}: TEST_SCHEMA declares check_id_raw", "check_id_raw:" in schema_src)
        check(
            f"{engine}: gate_results item shape requires check_id/status/failing_ids",
            "required: ['check_id', 'status', 'failing_ids']" in schema_src,
        )
        check(
            f"{engine}: gate_results status is constrained to pass/fail",
            "enum: ['pass', 'fail']" in schema_src,
        )


def test_triage_only_after_allpassed_check_in_sdlc_task() -> None:
    src = ENGINES["sdlc-task"].read_text()
    run_tests_idx = src.index("const testResult = await runTests(")
    all_passed_idx = src.index(
        "if (testResult && testResult.allPassed)", run_tests_idx
    )
    break_idx = src.index("break", all_passed_idx)
    green_segment = src[all_passed_idx:break_idx]
    check(
        "sdlc-task.js: no triage() call inside the green (allPassed) branch before its break",
        "triage(" not in green_segment,
    )
    # Positive control (standing rule 11): prove the search window actually locates the
    # real control flow, rather than an incidentally-empty slice, by showing a genuine
    # red-path triage() call sits just after the green branch's break.
    next_triage_idx = src.index("triage(", break_idx)
    red_window = src[break_idx : next_triage_idx + 200]
    check(
        "sdlc-task.js: positive control -- a real triage() call for the red path follows",
        "const tr = await triage(`task" in red_window,
    )


def main() -> int:
    print("test_gate_results")
    test_schema_has_gate_results_and_check_id_raw()
    test_triage_only_after_allpassed_check_in_sdlc_task()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
