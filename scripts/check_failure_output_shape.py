#!/usr/bin/env python3
"""check_failure_output_shape.py -- gate for BT.ticket.checks-must-name-their-failing-artifact.

Format under test (see docs/harness.md "The FAIL line format"):

    FAIL <path> <human text>

`FAIL` is the literal first token on a line; `<path>` is the second token -- either a real
artifact path or the explicit `<no-artifact>` token when a check genuinely has none to name.
`scripts/check_lane_agents.py` is the reference implementation this format was chosen to match.

WHAT THIS SCRIPT DOES
----------------------
Drives a small set of PROBES against a KNOWN-BAD fixture each and parses the combined
stdout+stderr for a `FAIL <path>` (or `FAIL <no-artifact>`) line. Two kinds of probe:

1. A SELF-TEST negative fixture, defined inline in this file, that deliberately fails without
   ever printing a FAIL line. This is not a registered check -- it exists only to prove the
   detector itself is capable of reporting a failure, not merely of agreeing with conforming
   input. If the detector fails to flag it, that is a bug in THIS gate and is reported
   distinctly from a real check's non-conformance.

2. REAL registered-check probes -- each drives an actual script from planning/harness.json
   against a small known-bad fixture built at run time (a malformed record, an in-corpus file
   with no frontmatter, ...). These decide the gate's exit code: any real probe whose known-bad
   run does not emit a parseable FAIL line is a violation.

Before task 3 fixes the non-conforming checks named in docs/harness.md's per-check audit, this
gate is EXPECTED to exit 1 -- that is what task 2's acceptance criteria call "shown RED before
any check is fixed." After task 3, it must exit 0.

New real probes should be added to REAL_PROBES as more checks are brought into (or kept in)
conformance; this script does not need to enumerate all 45 registered checks to do its job --
task 2 only requires it be shown red against at least one real, currently-nonconforming check,
and (via the reference) capable of confirming a conforming one.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, NamedTuple, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# First line matching this is the FAIL line a parser keys on. Group 1 is the path token --
# either a real artifact path or the literal `<no-artifact>` token.
FAIL_LINE_RE = re.compile(r"^FAIL\s+(\S+)(?:\s|$)")


def find_fail_path(output: str) -> Optional[str]:
    """Return the <path> token of the first `FAIL <path> ...` line in `output`, or None if no
    such line is present. Scans line by line so a human-text continuation line (indented, no
    leading `FAIL`) never matches."""
    for line in output.splitlines():
        m = FAIL_LINE_RE.match(line)
        if m:
            return m.group(1)
    return None


class ProbeResult(NamedTuple):
    name: str
    conforms: bool
    detail: str


class Probe(NamedTuple):
    name: str
    run: Callable[[], tuple[int, str]]  # -> (returncode, combined stdout+stderr)
    # Real checks are expected to be brought into conformance by task 3 and gate the exit code.
    # The self-test negative fixture never conforms by design and must not gate the exit code --
    # it is verified separately, as a check on the detector itself.
    is_self_test_negative: bool = False


def _run_python(args: list[str], stdin: str = "") -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


# --- probe 1: the self-test negative fixture -----------------------------------------------

def _self_test_negative_fixture() -> tuple[int, str]:
    """A fabricated check that fails while printing no FAIL line at all -- the negative control
    required so this gate is shown capable of FAILING, not merely of agreeing with input that
    already conforms."""
    return 1, "error: something broke, but nobody said what artifact broke it\n"


# --- probe 2: the reference check, lane-agent-schema (scripts/check_lane_agents.py) --------
#
# Already emits `FAIL <path>` on a real failure per docs/harness.md's audit -- this is the
# regression fixture: its output shape must never change as other checks are brought into
# conformance. Known-bad fixture: a lane-agent registry claim file that is not valid JSON, under
# a throwaway --lock-dir so the run touches no real fleet state.

def _lane_agent_schema_fixture() -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        registry_dir = lock_dir / "lane-agents"
        registry_dir.mkdir(parents=True)
        (registry_dir / "agent-known-bad.json").write_text("{ not valid json", encoding="utf-8")
        return _run_python([
            str(REPO_ROOT / "scripts" / "check_lane_agents.py"),
            "--lock-dir", str(lock_dir),
        ])


# --- probe 3: a real, currently-nonconforming check per docs/harness.md's audit ------------
#
# frontmatter-presence (scripts/check_frontmatter_presence.py) is listed there under "Can be
# made to conform" -- it names the offending path today (`{path}:1: ABSENT -- ...`) but not
# under the `FAIL <path>` prefix. Until task 3 rewrites its print statement, this probe is
# EXPECTED to find no FAIL line and the gate is EXPECTED to exit 1 because of it.

def _frontmatter_presence_fixture() -> tuple[int, str]:
    # An in-corpus path (under planning/) with empty content -- no frontmatter block at all.
    # NB: a leading `_` on the filename would exclude it from the corpus (see CLAUDE.md standing
    # rule 4), which would make the check return 0 for the wrong reason -- the fixture name must
    # not start with `_`.
    return _run_python(
        [str(REPO_ROOT / "scripts" / "check_frontmatter_presence.py"),
         "planning/known-bad-fixture-no-frontmatter.md"],
        stdin="",
    )


REAL_PROBES: list[Probe] = [
    Probe("lane-agent-schema", _lane_agent_schema_fixture),
    Probe("frontmatter-presence", _frontmatter_presence_fixture),
]

SELF_TEST_PROBE = Probe(
    "self-test-negative-fixture", _self_test_negative_fixture, is_self_test_negative=True,
)


def evaluate(probe: Probe) -> ProbeResult:
    returncode, output = probe.run()
    if returncode == 0:
        return ProbeResult(
            probe.name, False,
            "known-bad fixture did not fail (returncode 0) -- fixture is not actually bad",
        )
    path = find_fail_path(output)
    if path is None:
        return ProbeResult(
            probe.name, False,
            "failed with no parseable `FAIL <path>` (or `FAIL <no-artifact>`) line in output",
        )
    return ProbeResult(probe.name, True, f"FAIL line names `{path}`")


def main() -> int:
    failures: list[ProbeResult] = []

    # Self-test: the negative fixture MUST be detected as non-conforming. If it is instead
    # reported as conforming, the detector itself is broken -- distinct from any real check's
    # non-conformance, and always fatal regardless of the real probes below.
    self_test_result = evaluate(SELF_TEST_PROBE)
    if self_test_result.conforms:
        print(
            f"GATE BUG: {SELF_TEST_PROBE.name} was reported as CONFORMING, but it is a "
            f"deliberately non-conforming fixture -- the detector cannot be trusted",
        )
        return 1
    print(f"ok   {SELF_TEST_PROBE.name}: correctly detected as non-conforming "
          f"({self_test_result.detail})")

    # Real, registered-check probes -- these gate the exit code.
    for probe in REAL_PROBES:
        result = evaluate(probe)
        if result.conforms:
            print(f"ok   {result.name}: {result.detail}")
        else:
            print(f"FAIL {result.name}: {result.detail}")
            failures.append(result)

    if failures:
        print(
            f"\n{len(failures)} of {len(REAL_PROBES)} real check(s) do not emit a parseable "
            f"FAIL line on their known-bad fixture: "
            f"{', '.join(f.name for f in failures)}",
        )
        return 1

    print(f"\nall {len(REAL_PROBES)} real check(s) emit a parseable FAIL line")
    return 0


if __name__ == "__main__":
    sys.exit(main())
