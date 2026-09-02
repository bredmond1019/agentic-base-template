#!/usr/bin/env python3
"""Source-assertion fixture over `/begin-orchestration` Steps 3 and 4's exclusive-lease contract
(BT.ticket.begin-orchestration-lease-steps-are-wrong, task 2).

D68: this fixture is written and run FIRST against the two documents as they stand today (after
task 1's Step 2 repair, task 2 itself edits neither document), and is EXPECTED TO FAIL --
assertions A, B and C are red on both files; assertion D is the positive control and must already
be green, proving the Step 3/Step 4 slices are actually located rather than coming back empty.
Task 3 makes A, B and C green by editing both documents; this file is not touched again after
task 2.

Checks BOTH `.claude/commands/begin-orchestration.md` and its Gemini-facing replication copy
`.agents/skills/begin-orchestration/SKILL.md`, reporting the file alongside each assertion so a
later regression names WHICH copy drifted -- the `scripts/test_step2_reverify_rules.py` pattern.

The Step 3 and Step 4 regions are each located by their own `## Step N` heading and the NEXT
`## ` heading, never by line number -- line numbers move with every edit above them.

Four independent, named assertions per file:

  A -- the Step 3 region names the quiesce consequence Step 3 currently omits entirely: taking
       an exclusive lease refuses this repo's `mev` write verbs with `E_QUIESCE_LEASE_HELD` for
       the length of the chain, and that this must NOT be retried (a different condition from
       `E_EMIT_LOCK_HELD` contention).
  B -- the Step 3/Step 4 regions (checked together) name `--agent` as the lease holder's
       self-exemption and state that a lane must pass it on every `mev` write verb it runs while
       holding its own lease -- connecting the lease Step 4 makes a lane take to the `register`
       check Step 3 already describes.
  C -- the Step 3 region states the correct absent-scope semantics (`scope` absent defaults to
       `repo`; only `scope: fleet` quiesces the whole fleet) AND no longer carries the false
       claim that an exclusive lease refuses `every other agent`'s register `regardless of
       category or heaviness` -- that sentence describes only a `scope: fleet` lease, not every
       exclusive lease.
  D -- POSITIVE CONTROL, must pass before and after the edits: both the Step 3 and Step 4 regions
       were located and are non-empty, and Step 4 still mentions the lease path
       `<lock_dir>/leases/lease-<repo>.json`. If the slice comes back empty this fails, so A/B/C
       failing can never be mistaken for a bad slice. (The command doc's Step 4 already names
       `kind: exclusive` explicitly for the ordinary per-lane lease; the `.agents/` copy's Step 4
       currently only reaches the lease path via its heartbeat-re-stamp paragraph and is missing
       the ordinary-lane "claim identity, take the lease" instructions the command doc has --
       that gap is real drift, not a slicing bug, and this assertion is scoped to what is common
       to both copies today so it stays a true positive control rather than failing on content
       task 3 was never asked to add.)

## Live E_QUIESCE_LEASE_HELD refusal, observed 2026-09-02

Recorded evidence for the block's second acceptance criterion (UN-GATEABLE per D64 -- the
evidence lives in an installed binary outside this repo's checks, so it is carried here as a
docstring record, not asserted by the suite going green). Observed by running the INSTALLED `mev`
binary (`mev --build-stamp` reported `{"dirty":false,"git_sha":
"dbc53b36356405adfe88bc8858200064e6495515","source_dir":"/Users/brandon/Dev/agentic-portfolio/core/mev"}`,
`mev --version` reported `mev 0.1.0`) against a disposable lock dir (NOT `.fleet-locks`)
containing one fresh, non-stale `kind: exclusive` lease naming a repo (`base-template`) and agent
("some-other-agent") that is not the caller:

    $ mev set-block-status base-template:<a-block-id> in_progress --write --lock-dir <tmp>
    (stdout was empty; exit code was 1, checked separately from the piped stderr capture --
    a piped command's `$?` is the pipe's, not the command's)

stderr, VERBATIM:

    error [E_QUIESCE_LEASE_HELD] refusing to set-block-status: lane 'some-other-lane' (agent
    'some-other-agent') holds a repo-scope exclusive lease at
    <tmp>/leases/lease-base-template.json — this is a declared quiet window, a different
    condition from E_EMIT_LOCK_HELD (contention; retry shortly). Do NOT retry: wait for the
    lease to be released, or contact the holding lane — or, if you ARE the holding lane, re-run
    with `--agent <holder>` naming that agent. Nothing was written.

The remedy string the corrected docs must match is `--agent <holder>`. (A first attempt at this
observation, using an `acquired_at`/`heartbeat` roughly 24h in the past, was wrongly judged stale
by mev's 3-hour lease staleness threshold and the write went through with exit 0 -- confirmed via
`git status --porcelain` in the brain repo immediately after, and immediately reverted with
`git checkout --` against the exact paths the write's own `I_EMIT_WROTE` log lines named, nothing
force-added or swept. The lease used for the observation above carries a timestamp taken at
run time, which is why it was actually held.)

Usage:
    python3 scripts/test_lease_steps_contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TARGET_FILES = [
    REPO_ROOT / ".claude" / "commands" / "begin-orchestration.md",
    REPO_ROOT / ".agents" / "skills" / "begin-orchestration" / "SKILL.md",
]

STEP3_HEADING_RE = re.compile(r"^##\s+Step 3\b.*$", re.MULTILINE)
STEP4_HEADING_RE = re.compile(r"^##\s+Step 4\b.*$", re.MULTILINE)
NEXT_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)

# --- Assertion A: the quiesce consequence, stated in Step 3 ------------------------------------
QUIESCE_CONSEQUENCE_PHRASES = [
    "e_quiesce_lease_held",
    "write verb",
    "do not retry",
]

# --- Assertion B: --agent named as the self-exemption, connecting Step 3 and Step 4 ------------
SELF_EXEMPTION_PHRASES = [
    "self-exemption",
    "--agent",
    "every `mev` write verb",
]

# --- Assertion C: correct absent-scope semantics; false "regardless of category" wording gone --
CORRECT_SCOPE_PHRASES = [
    "absent defaults to `repo`",
    "only `scope: fleet`",
    "quiesces the whole fleet",
]
FALSE_SCOPE_PHRASE = "regardless of category or heaviness"

# --- Assertion D: positive control — regions located, Step 4 still writes the exclusive lease --
STEP4_LEASE_WRITE_PHRASES = [
    "leases/lease-<repo>.json",
]


class RegionNotFound(Exception):
    """Raised when a `## Step N` heading (or its closing next heading) cannot be located --
    always an error, never a silent empty-string pass."""


def _extract_region(text: str, heading_re: re.Pattern[str], label: str) -> str:
    match = heading_re.search(text)
    if not match:
        raise RegionNotFound(f"no `{label}` heading found")
    start = match.end()
    next_match = NEXT_HEADING_RE.search(text, start)
    end = next_match.start() if next_match else len(text)
    region = text[start:end]
    if not region.strip():
        raise RegionNotFound(f"`{label}` region is empty")
    return region


def extract_step3_region(text: str) -> str:
    return _extract_region(text, STEP3_HEADING_RE, "## Step 3")


def extract_step4_region(text: str) -> str:
    return _extract_region(text, STEP4_HEADING_RE, "## Step 4")


def _missing(phrases: list[str], haystack: str) -> list[str]:
    return [p for p in phrases if p.lower() not in haystack.lower()]


def assert_a_quiesce_consequence(step3: str) -> str | None:
    missing = _missing(QUIESCE_CONSEQUENCE_PHRASES, step3)
    if missing:
        return (
            "assertion A FAILED: Step 3 does not name the quiesce consequence of taking an "
            f"exclusive lease -- missing phrase(s): {missing}"
        )
    return None


def assert_b_self_exemption(step3: str, step4: str) -> str | None:
    combined = f"{step3}\n{step4}"
    missing = _missing(SELF_EXEMPTION_PHRASES, combined)
    if missing:
        return (
            "assertion B FAILED: Step 3/Step 4 do not name `--agent` as the lease holder's "
            f"self-exemption on every mev write verb -- missing phrase(s): {missing}"
        )
    return None


def assert_c_scope_semantics(step3: str) -> str | None:
    missing = _missing(CORRECT_SCOPE_PHRASES, step3)
    if missing:
        return (
            "assertion C FAILED: Step 3 does not state the correct absent-scope-means-repo "
            f"semantics -- missing phrase(s): {missing}"
        )
    if FALSE_SCOPE_PHRASE.lower() in step3.lower():
        return (
            "assertion C FAILED: Step 3 still carries the false claim that an exclusive lease "
            f"refuses every other agent's register {FALSE_SCOPE_PHRASE!r}"
        )
    return None


def assert_d_regions_located(step3: str, step4: str) -> str | None:
    # step3/step4 being non-empty strings here already proves extraction succeeded (extraction
    # raises RegionNotFound otherwise, handled by the caller) -- this assertion additionally
    # pins that Step 4 still mentions the lease path, common to both copies today.
    missing = _missing(STEP4_LEASE_WRITE_PHRASES, step4)
    if missing:
        return (
            "assertion D FAILED: Step 4 no longer mentions the lease path "
            f"`<lock_dir>/leases/lease-<repo>.json` -- missing phrase(s): {missing}"
        )
    return None


def main() -> int:
    failures: list[str] = []
    any_region_missing = False

    for path in TARGET_FILES:
        if not path.is_file():
            print(f"FAIL: file not found: {path}")
            failures.append(str(path))
            any_region_missing = True
            continue

        text = path.read_text()
        try:
            step3 = extract_step3_region(text)
            step4 = extract_step4_region(text)
        except RegionNotFound as exc:
            print(f"FAIL: {path}: {exc}")
            failures.append(f"{path}: {exc}")
            any_region_missing = True
            continue

        checks = [
            ("A", lambda: assert_a_quiesce_consequence(step3)),
            ("B", lambda: assert_b_self_exemption(step3, step4)),
            ("C", lambda: assert_c_scope_semantics(step3)),
            ("D", lambda: assert_d_regions_located(step3, step4)),
        ]
        for label, fn in checks:
            result = fn()
            if result is None:
                print(f"ok   {path}: assertion {label} passed")
            else:
                print(f"FAIL {path}: {result}")
                failures.append(f"{path}: assertion {label}")

    if any_region_missing:
        print("FAIL: at least one file's Step 3/Step 4 region could not be located -- see above")
        return 1

    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ok   all assertions passed for both files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
