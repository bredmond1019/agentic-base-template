#!/usr/bin/env python3
"""Fixtures over check_command_docs_no_write_path.py's instructing-vs-discussing rule
(BT.ticket.validate-brain-is-a-write-and-push-path, task 1).

Two directions, both required:
  (a) a fixture INSTRUCTING execution of one of the three write-and-push wrappers must FAIL.
  (b) a fixture reproducing derive-state-safely's real discussion style (writer-table row,
      ban list, and an inline "Call `./scripts/emit_state_write.sh` instead" mid-sentence
      mention) must PASS.

Plus a live-corpus exercise so the check cannot pass by finding nothing:
  (c) the real .agents/skills/derive-state-safely/SKILL.md passes, unmodified, and the real
      .claude/commands/begin-orchestration.md and orchestrate.md (plus their two
      .agents/skills/ mirrors) pass too -- task 1 recorded those four files RED (pre-fix);
      task 2 fixed them, so this suite now pins the post-fix GREEN state instead. See task 1's
      recorded red in that task's notes for the pre-fix evidence this flip replaces.

Dependency-free, same discipline as scripts/test_check_command_hazards.py-style siblings.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_command_docs_no_write_path as checker  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"[PASS] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}" + (f" -- {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# (a) instructing fixtures -- each must produce at least one finding.
# ---------------------------------------------------------------------------

INSTRUCTING_FIXTURES = {
    "bare_fenced_line": """\
## Before finishing

Run this repo's own gates, then the corpus gate:

```
./scripts/validate_brain.sh
```
""",
    "bare_line_with_comment": """\
```
./scripts/validate_brain.sh          # from the brain root -- delta against the last good push
```
""",
    "emit_state_write_bare": """\
When you're done, write and commit:

```
./scripts/emit_state_write.sh
```
""",
    "routine_with_flag": """\
Nightly, this repo runs:

```
scripts/routine.sh --apply
```
""",
}


def test_instructing_fixtures_fail():
    for name, text in INSTRUCTING_FIXTURES.items():
        findings = checker.find_instructions(text, name)
        check(f"instructing fixture '{name}' FAILS", len(findings) > 0,
              f"expected >=1 finding, got {findings!r}")


# ---------------------------------------------------------------------------
# (b) discussion fixture -- reproduces derive-state-safely's real style. Must be clean.
# ---------------------------------------------------------------------------

DISCUSSION_FIXTURE = """\
---
name: derive-state-safely-style-fixture
description: >
  Discussion-only fixture modelled on the real derive-state-safely/SKILL.md -- names all
  three wrappers in a table row, a ban list, and an inline mid-sentence mention, and must
  PASS the checker exactly like the real file does.
---

| Command | Shape | Re-runs `emit-state --write` |
|---|---|---|
| `./scripts/emit_state_write.sh` · `validate_brain.sh` · `routine.sh` | wrappers | yes |

While any measurement block is live, `syn refresh` / `emit-state --write` / `routine.sh` /
`validate_brain.sh` are **banned** -- corpus changes invalidate a retrieval measurement in
flight.

**`BRAIN_ROLE` gates two scripts, not this command.** Only `scripts/commit_routine_updates.sh`
and `scripts/validate_brain.sh` check it -- `grep -rn BRAIN_ROLE scripts/*.sh` is the full
consumer list. `scripts/routine.sh`'s unattended nightly cron run is where `validate_brain.sh`
runs `emit-state`.

**Don't hand-craft the commit pathspec from `git status`, and don't call `bastion emit-state
--write` directly.** Call `./scripts/emit_state_write.sh` instead -- it's the one place the
write-then-commit sequence is defined. `validate_brain.sh` delegates to this same script for
its own emit-state step, so the two are identical here; use `emit_state_write.sh` directly
when you only need the write-and-commit, without a full validate-brain pass first.
"""


def test_discussion_fixture_passes():
    findings = checker.find_instructions(DISCUSSION_FIXTURE, "discussion-fixture")
    check("discussion fixture (derive-state-safely style) PASSES", len(findings) == 0,
          f"expected 0 findings, got {findings!r}")


# ---------------------------------------------------------------------------
# (c) live corpus: the real derive-state-safely SKILL.md passes unmodified, and the four
#     files this block will fix in task 2 are named RED (task 1 does not fix them).
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_live_derive_state_safely_passes():
    path = REPO_ROOT / ".agents/skills/derive-state-safely/SKILL.md"
    if not path.is_file():
        check("live derive-state-safely/SKILL.md exists", False, f"missing: {path}")
        return
    text = path.read_text(encoding="utf-8")
    findings = checker.find_instructions(text, str(path))
    check("live derive-state-safely/SKILL.md passes, unmodified", len(findings) == 0,
          f"expected 0 findings, got {findings!r}")


def test_live_corpus_is_clean_after_task2_fix():
    """Task 1 pinned begin-orchestration.md, orchestrate.md and both .agents/skills/ mirrors as
    RED (still instructing the write path). Task 2 replaced those instructions with the four
    read-only bastion validate-brain --<flag> calls -- this pins the resulting GREEN state. If
    this assertion ever fails, one of the four files has regressed back to instructing the
    write path."""
    targets = [
        REPO_ROOT / ".claude/commands/begin-orchestration.md",
        REPO_ROOT / ".claude/commands/orchestrate.md",
        REPO_ROOT / ".agents/skills/begin-orchestration/SKILL.md",
        REPO_ROOT / ".agents/skills/orchestrate/SKILL.md",
    ]
    for path in targets:
        if not path.is_file():
            check(f"live file exists: {path}", False, f"missing: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        findings = checker.find_instructions(text, str(path))
        check(f"live {path.relative_to(REPO_ROOT)} passes (no longer instructs the write path)",
              len(findings) == 0, f"expected 0 findings, got {findings!r}")


def test_main_exits_zero_against_live_root():
    exit_code = checker.main(["--root", str(REPO_ROOT), "--quiet"])
    check("main() exits zero against the fixed live corpus", exit_code == 0,
          f"expected exit 0, got {exit_code}")


def main():
    test_instructing_fixtures_fail()
    test_discussion_fixture_passes()
    test_live_derive_state_safely_passes()
    test_live_corpus_is_clean_after_task2_fix()
    test_main_exits_zero_against_live_root()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print(f"\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
