#!/usr/bin/env python3
"""Fixture suite for check_failure_output_shape.py.

Referenced by the base-template carryover entry `failure-output-shape-gate-drives-only-two-checks`
(clears_when: `test -f scripts/test_check_failure_output_shape.py`) as the sibling fixture suite 6
of check_failure_output_shape.py's 7 checker siblings already carry
(check_frontmatter_presence, check_lane_agents, check_messages, fleet_concurrency_check,
nextest_artifact_wrapper, sync_downstream_harness). This does not widen the gate itself (that is
the entry's OTHER, still-open coverage gap — driving more than the current two real checks); it
only closes the "no fixture suite" half.

Self-contained, no pytest dependency, in the fixture style of the other scripts/test_check_*.py
suites: the module under test is loaded directly via importlib so its pure functions
(`find_fail_path`, `evaluate`) can be exercised without shelling out, plus one subprocess
invocation to pin the CLI/exit-code contract end to end.

Run: python3 scripts/test_check_failure_output_shape.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_failure_output_shape.py"

_spec = importlib.util.spec_from_file_location("check_failure_output_shape", MODULE_PATH)
cfos = importlib.util.module_from_spec(_spec)
sys.modules["check_failure_output_shape"] = cfos
_spec.loader.exec_module(cfos)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name}: {detail}")
        FAILURES.append(name)


# --- find_fail_path -------------------------------------------------------------------------

def test_find_fail_path_matches_leading_token():
    path = cfos.find_fail_path("some noise\nFAIL scripts/foo.py bad thing happened\nmore noise\n")
    check("find_fail_path finds a real FAIL line", path == "scripts/foo.py", repr(path))


def test_find_fail_path_matches_no_artifact_token():
    path = cfos.find_fail_path("FAIL <no-artifact> no path to name\n")
    check("find_fail_path accepts <no-artifact>", path == "<no-artifact>", repr(path))


def test_find_fail_path_ignores_indented_continuation():
    # A continuation line does not start with FAIL at column 0, so it must never match even
    # though it contains the word FAIL later in the text.
    path = cfos.find_fail_path("  this line mentions FAIL but is not one\nFAIL real/path.py x\n")
    check("find_fail_path ignores non-leading FAIL", path == "real/path.py", repr(path))


def test_find_fail_path_returns_none_when_absent():
    path = cfos.find_fail_path("error: something broke, but nobody said what artifact broke it\n")
    check("find_fail_path returns None with no FAIL line", path is None, repr(path))


# --- evaluate ---------------------------------------------------------------------------------

def test_evaluate_flags_conforming_probe():
    probe = cfos.Probe("fixture-conforming", lambda: (1, "FAIL scripts/thing.py bad\n"))
    result = cfos.evaluate(probe)
    check("evaluate marks a real FAIL line as conforming", result.conforms, result.detail)


def test_evaluate_flags_missing_fail_line():
    probe = cfos.Probe("fixture-no-fail-line", lambda: (1, "boom, no FAIL line at all\n"))
    result = cfos.evaluate(probe)
    check(
        "evaluate marks a failure with no FAIL line as non-conforming",
        not result.conforms,
        result.detail,
    )


def test_evaluate_flags_zero_returncode_as_not_actually_bad():
    probe = cfos.Probe("fixture-not-actually-bad", lambda: (0, "FAIL scripts/thing.py bad\n"))
    result = cfos.evaluate(probe)
    check(
        "evaluate rejects a returncode-0 known-bad fixture",
        not result.conforms,
        result.detail,
    )


# --- self-test negative fixture stays non-conforming (the detector-on-itself check) -----------

def test_self_test_probe_is_never_conforming():
    result = cfos.evaluate(cfos.SELF_TEST_PROBE)
    check(
        "SELF_TEST_PROBE is detected as non-conforming",
        not result.conforms,
        result.detail,
    )


# --- end-to-end CLI contract -------------------------------------------------------------------

def test_cli_runs_and_reports_real_probes():
    proc = subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    combined = proc.stdout + proc.stderr
    check(
        "CLI reports the self-test-negative-fixture as correctly detected",
        "self-test-negative-fixture: correctly detected as non-conforming" in combined,
        combined,
    )
    check(
        "CLI exit code is 0 or 1 (never a crash)",
        proc.returncode in (0, 1),
        f"returncode={proc.returncode}",
    )


def main() -> int:
    test_find_fail_path_matches_leading_token()
    test_find_fail_path_matches_no_artifact_token()
    test_find_fail_path_ignores_indented_continuation()
    test_find_fail_path_returns_none_when_absent()
    test_evaluate_flags_conforming_probe()
    test_evaluate_flags_missing_fail_line()
    test_evaluate_flags_zero_returncode_as_not_actually_bad()
    test_self_test_probe_is_never_conforming()
    test_cli_runs_and_reports_real_probes()

    total = 9
    passed = total - len(FAILURES)
    print(f"\nSUMMARY: {passed}/{total} fixtures passed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
