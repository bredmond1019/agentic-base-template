#!/usr/bin/env python3
"""Fixture suite over the tier-spec resolution RULE implemented by
`.claude/workflows/sdlc-task.js` and `.claude/workflows/sdlc-flow.js`
(BT.ticket.sdlc-task-tier-spec-resolution).

WHY THIS RE-IMPLEMENTS THE RULE IN PYTHON
------------------------------------------
Both engines are Workflow scripts driven by an agent-executed setup STEP, not
functions this repo can import and call in-process (they don't even share
code with each other by design -- see each file's own comments). So the only
way to pin the resolution RULE as a testable, versioned contract is to mirror
it here in Python, the same way this repo mirrors other engine-embedded
rules as testable Python fixtures.

THE RULE (transcribed from sdlc-task.js ~line 1055-1092 and the identical
region in sdlc-flow.js):
  1. A "root" location is `planning/<blockId>` and a "tier" location is
     `<tierPrefix>planning/<blockId>`, where tierPrefix is the invoking
     directory's path relative to the git root (e.g. "business/", or "" at
     the root).
  2. specFoundInTier = true ONLY when the spec does NOT exist at the root AND
     DOES exist at the tier. In every other case (root only, both, neither)
     specFoundInTier = false. This is what makes the ROOT WIN whenever the
     spec exists at both locations.
  3. blockDir and everything derived from it (blockRecordFile, specFile,
     tasksJsonFile, breakdownFile, reportsDir, stateFile[, worklogFile in
     sdlc-flow.js]) are re-derived from the tier location ONLY when
     specFoundInTier is true; otherwise they stay at the root form.
  4. When the spec exists at NEITHER location, the engine aborts with
     `{error: 'Missing spec', ...}` and a log line naming BOTH the root paths
     searched and the tier paths searched.

WHAT THIS DOES NOT PROVE
-------------------------
This suite tests a Python MIRROR of the resolution rule, not the real
`.claude/workflows/*.js` engines executing under the Workflow runtime -- that
is structurally un-gateable here under D64 (the evidence lives in another
process). A one-off manual run from a tier directory is the actual evidence
for the engines themselves; see this spec's task-4 validation notes. This
suite's own value is (a) pinning the RULE so a future edit to the resolution
logic can't silently change it without a red test, and (b) asserting, against
the live engine source, that both engines actually mention `tierPrefix` --
so the mirror cannot drift into testing a rule no engine implements.

This is a GATING check (`planning/harness.json`, `tier-spec-resolution-tests`).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SDLC_TASK_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"
SDLC_FLOW_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


# --- the mirrored resolution rule -------------------------------------------

class Resolution:
    __slots__ = ("found", "block_dir", "searched_root", "searched_tier")

    def __init__(self, found: bool, block_dir: str | None, searched_root: list[str], searched_tier: list[str]):
        self.found = found
        self.block_dir = block_dir
        self.searched_root = searched_root
        self.searched_tier = searched_tier


def resolve_spec(fs_root: Path, block_id: str, tier_prefix: str) -> Resolution:
    """Mirrors the resolution order in sdlc-task.js / sdlc-flow.js STEP 4a
    and the reassignment block right after setupResult returns."""
    root_block_dir = f"planning/{block_id}"
    root_record = f"planning/blocks/{block_id}.json"
    root_legacy = f"{root_block_dir}/tasks.md"

    root_record_exists = (fs_root / root_record).exists()
    root_legacy_exists = (fs_root / root_legacy).exists()
    root_exists = root_record_exists or root_legacy_exists

    searched_root = [root_record, root_legacy]
    searched_tier: list[str] = []

    if not tier_prefix:
        # No tier candidate at all (invocation at the git root) -- root or nothing.
        if root_exists:
            return Resolution(True, root_block_dir, searched_root, searched_tier)
        return Resolution(False, None, searched_root, searched_tier)

    tier_block_dir = f"{tier_prefix}planning/{block_id}"
    tier_record = f"{tier_prefix}planning/blocks/{block_id}.json"
    tier_legacy = f"{tier_block_dir}/tasks.md"
    searched_tier = [tier_record, tier_legacy]

    tier_record_exists = (fs_root / tier_record).exists()
    tier_legacy_exists = (fs_root / tier_legacy).exists()
    tier_exists = tier_record_exists or tier_legacy_exists

    # specFoundInTier = true ONLY when root does not exist AND tier does.
    spec_found_in_tier = (not root_exists) and tier_exists

    if spec_found_in_tier:
        return Resolution(True, tier_block_dir, searched_root, searched_tier)
    if root_exists:
        # Root wins -- whether or not the tier ALSO has a copy.
        return Resolution(True, root_block_dir, searched_root, searched_tier)
    return Resolution(False, None, searched_root, searched_tier)


# --- fixture helpers ---------------------------------------------------------

def make_fixture_tree(tmp: Path, block_id: str, at_root: bool, at_tier: bool, tier_prefix: str) -> Path:
    if at_root:
        d = tmp / "planning" / block_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "tasks.md").write_text("# root spec\n", encoding="utf-8")
    if at_tier:
        d = tmp / tier_prefix / "planning" / block_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "tasks.md").write_text("# tier spec\n", encoding="utf-8")
    return tmp


# --- cases --------------------------------------------------------------------

def check_root_only() -> None:
    block_id = "TIER.ticket.root-only"
    tier_prefix = "business/"
    with tempfile.TemporaryDirectory() as td:
        tmp = make_fixture_tree(Path(td), block_id, at_root=True, at_tier=False, tier_prefix=tier_prefix)
        r = resolve_spec(tmp, block_id, tier_prefix)
        check("root-only: spec is found", r.found, f"got found={r.found}")
        check("root-only: resolves to the ROOT block dir", r.block_dir == f"planning/{block_id}", f"got {r.block_dir}")


def check_tier_only() -> None:
    block_id = "TIER.ticket.tier-only"
    tier_prefix = "business/"
    with tempfile.TemporaryDirectory() as td:
        tmp = make_fixture_tree(Path(td), block_id, at_root=False, at_tier=True, tier_prefix=tier_prefix)
        r = resolve_spec(tmp, block_id, tier_prefix)
        check("tier-only: spec is found", r.found, f"got found={r.found}")
        check(
            "tier-only: resolves to the TIER block dir",
            r.block_dir == f"{tier_prefix}planning/{block_id}",
            f"got {r.block_dir}",
        )


def check_both_root_wins() -> None:
    block_id = "TIER.ticket.both-present"
    tier_prefix = "business/"
    with tempfile.TemporaryDirectory() as td:
        tmp = make_fixture_tree(Path(td), block_id, at_root=True, at_tier=True, tier_prefix=tier_prefix)
        r = resolve_spec(tmp, block_id, tier_prefix)
        check("both-present: spec is found", r.found, f"got found={r.found}")
        check(
            "both-present: resolves to the ROOT block dir (root wins the common case)",
            r.block_dir == f"planning/{block_id}",
            f"got {r.block_dir}",
        )


def check_neither() -> None:
    block_id = "TIER.ticket.neither"
    tier_prefix = "business/"
    with tempfile.TemporaryDirectory() as td:
        tmp = make_fixture_tree(Path(td), block_id, at_root=False, at_tier=False, tier_prefix=tier_prefix)
        r = resolve_spec(tmp, block_id, tier_prefix)
        check("neither: spec is NOT found", not r.found, f"got found={r.found}")
        expected_root = [f"planning/blocks/{block_id}.json", f"planning/{block_id}/tasks.md"]
        expected_tier = [f"{tier_prefix}planning/blocks/{block_id}.json", f"{tier_prefix}planning/{block_id}/tasks.md"]
        check("neither: error names both ROOT paths searched", r.searched_root == expected_root, f"got {r.searched_root}")
        check("neither: error names both TIER paths searched", r.searched_tier == expected_tier, f"got {r.searched_tier}")


def check_no_tier_prefix() -> None:
    """When invoked at the git root, tierPrefix is "" -- root or nothing, no tier search at all."""
    block_id = "TIER.ticket.at-root-invocation"
    with tempfile.TemporaryDirectory() as td:
        tmp = make_fixture_tree(Path(td), block_id, at_root=False, at_tier=False, tier_prefix="")
        r = resolve_spec(tmp, block_id, "")
        check("empty tierPrefix, missing spec: not found and no tier paths searched", not r.found and r.searched_tier == [], f"found={r.found} searched_tier={r.searched_tier}")


def resolve_spec_deliberately_buggy(fs_root: Path, block_id: str, tier_prefix: str) -> Resolution:
    """A DELIBERATELY WRONG mirror: tier wins over root whenever both exist,
    the opposite of the real rule. This exists only so
    check_broken_fixture_is_caught can prove the suite is capable of going
    red (D68) -- a suite whose checks never observably fail is not evidence
    that they check anything. This function must NEVER be used by the real
    cases above."""
    root_block_dir = f"planning/{block_id}"
    root_exists = (fs_root / f"planning/{block_id}/tasks.md").exists() or (fs_root / f"planning/blocks/{block_id}.json").exists()
    if not tier_prefix:
        return Resolution(root_exists, root_block_dir if root_exists else None, [], [])
    tier_block_dir = f"{tier_prefix}planning/{block_id}"
    tier_exists = (fs_root / f"{tier_block_dir}/tasks.md").exists() or (fs_root / f"{tier_prefix}planning/blocks/{block_id}.json").exists()
    if tier_exists:  # BUG: tier wins even when root also exists
        return Resolution(True, tier_block_dir, [], [])
    if root_exists:
        return Resolution(True, root_block_dir, [], [])
    return Resolution(False, None, [], [])


def check_broken_fixture_is_caught() -> None:
    """Proves this suite is capable of failing (D68): runs the SAME
    both-present fixture used by check_both_root_wins() through the
    deliberately-buggy resolver above and asserts it produces the WRONG
    answer (tier instead of root) -- i.e. this suite's root-wins assertion
    would have caught the bug had it been in the real resolve_spec. The
    corresponding assertion in check_both_root_wins() is the one that would
    go red for a buggy implementation; this function is the direct evidence
    that the divergence is real and detectable, not assumed."""
    block_id = "TIER.ticket.deliberately-broken"
    tier_prefix = "business/"
    with tempfile.TemporaryDirectory() as td:
        tmp = make_fixture_tree(Path(td), block_id, at_root=True, at_tier=True, tier_prefix=tier_prefix)
        correct = resolve_spec(tmp, block_id, tier_prefix)
        buggy = resolve_spec_deliberately_buggy(tmp, block_id, tier_prefix)
        check(
            "correct resolver picks the ROOT on a both-present fixture",
            correct.block_dir == f"planning/{block_id}",
            f"got {correct.block_dir}",
        )
        check(
            "buggy resolver (tier-wins) picks the TIER on the same fixture -- proving the suite can detect this class of bug",
            buggy.block_dir == f"{tier_prefix}planning/{block_id}",
            f"got {buggy.block_dir}",
        )
        check(
            "correct and buggy resolvers DIVERGE on the both-present fixture (the suite is capable of failing here)",
            correct.block_dir != buggy.block_dir,
            f"both resolved to {correct.block_dir!r} -- no divergence, suite would not have caught the bug",
        )


def check_engines_mention_tier_prefix() -> None:
    """Guards against the mirror drifting from the implementation: assert both
    live engine files actually implement tierPrefix, not just this mirror."""
    for path in (SDLC_TASK_JS, SDLC_FLOW_JS):
        check(f"{path.name} exists", path.exists(), str(path))
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        check(f"{path.name} mentions tierPrefix", "tierPrefix" in text)
        check(f"{path.name} mentions specFoundInTier (root-wins signal)", "specFoundInTier" in text)


def main() -> int:
    check_root_only()
    check_tier_only()
    check_both_root_wins()
    check_neither()
    check_no_tier_prefix()
    check_broken_fixture_is_caught()
    check_engines_mention_tier_prefix()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- tier-spec resolution rule mirror holds against sdlc-task.js and sdlc-flow.js.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
