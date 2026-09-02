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

SECOND RULE (BT.ticket.emit-state-write-needs-require-fresh, task 1): fixtures for
`mev emit-state --write` without `--require-fresh`.
  (d) instructing `mev emit-state --write` without the flag must FAIL.
  (e) the same line carrying `--require-fresh` must PASS.
  (f) a line merely DISCUSSING the bare verb (a table row, a ban list, an inline mid-sentence
      mention) must PASS -- reusing the same instruct-vs-discuss shape test as (a)/(b), not a
      second notion of instruction.
Per D68, each negative fixture here was first run against the UNMODIFIED (pre-this-task)
checker and observed FAILING TO CATCH it (0 findings, exit 0) before the rule existed --
recorded in this task's completion notes, not re-derived by this file at import time.

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
# (d)/(e)/(f) `mev emit-state --write` without `--require-fresh` -- second rule.
# ---------------------------------------------------------------------------

EMIT_STATE_MISSING_FLAG_FIXTURES = {
    "bare_fenced_line": """\
## Regenerate derived surfaces

Run it from the main working tree:

```
mev emit-state --write
```
""",
    "bare_with_comment": """\
```
mev emit-state --write          # regenerate every derived surface
```
""",
    "bare_with_other_flag": """\
```
mev emit-state --write --state
```
""",
}

EMIT_STATE_WITH_FLAG_FIXTURES = {
    "with_require_fresh": """\
```
mev emit-state --write --require-fresh
```
""",
    "with_require_fresh_and_other_flag": """\
```
mev emit-state --write --require-fresh --state
```
""",
}

EMIT_STATE_DISCUSSION_FIXTURE = """\
---
name: emit-state-discussion-fixture
description: >
  Discussion-only fixture: names `mev emit-state --write` in a table row, a ban list, and an
  inline mid-sentence mention. None of these are the whole line, so all must PASS.
---

| Command | What it does |
|---|---|
| `mev emit-state --write` | regenerates every derived surface |

While a measurement block is live, `mev emit-state --write` is **banned** -- corpus changes
invalidate a retrieval measurement in flight.

The freshness spine is what actually regenerates when `mev emit-state --write` runs; do not
hand-author it.
"""


def test_emit_state_missing_flag_fixtures_fail():
    for name, text in EMIT_STATE_MISSING_FLAG_FIXTURES.items():
        findings = checker.find_missing_require_fresh(text, name)
        check(f"emit-state missing-flag fixture '{name}' FAILS", len(findings) > 0,
              f"expected >=1 finding, got {findings!r}")


def test_emit_state_with_flag_fixtures_pass():
    for name, text in EMIT_STATE_WITH_FLAG_FIXTURES.items():
        findings = checker.find_missing_require_fresh(text, name)
        check(f"emit-state with-flag fixture '{name}' PASSES", len(findings) == 0,
              f"expected 0 findings, got {findings!r}")


def test_emit_state_discussion_fixture_passes():
    findings = checker.find_missing_require_fresh(EMIT_STATE_DISCUSSION_FIXTURE,
                                                    "emit-state-discussion-fixture")
    check("emit-state discussion fixture PASSES", len(findings) == 0,
          f"expected 0 findings, got {findings!r}")


def test_wrapper_rule_unaffected_by_emit_state_fixtures():
    """The pre-existing wrapper-script rule must not fire on any emit-state fixture, and the
    new emit-state rule must not fire on any wrapper-script fixture -- the two rules are
    independent."""
    for name, text in EMIT_STATE_MISSING_FLAG_FIXTURES.items():
        findings = checker.find_instructions(text, name)
        check(f"wrapper rule silent on emit-state fixture '{name}'", len(findings) == 0,
              f"expected 0 findings, got {findings!r}")
    for name, text in INSTRUCTING_FIXTURES.items():
        findings = checker.find_missing_require_fresh(text, name)
        check(f"emit-state rule silent on wrapper fixture '{name}'", len(findings) == 0,
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


def test_wrapper_rule_clean_against_live_root():
    """The pre-existing wrapper-script rule alone, run standalone over the whole live corpus.
    Unaffected by the new emit-state rule below -- kept as its own assertion so the two rules'
    live-corpus state can regress independently and this pins the wrapper rule's."""
    findings_total = 0
    for path in checker.collect_files(REPO_ROOT):
        text = path.read_text(encoding="utf-8")
        findings_total += len(checker.find_instructions(text, str(path)))
    check("wrapper rule alone finds 0 over the live corpus", findings_total == 0,
          f"expected 0 findings, got {findings_total}")


def test_emit_state_rule_live_root_snapshot_task1():
    """BT.ticket.emit-state-write-needs-require-fresh: the sweep has landed (positive control
    was 5 pre-sweep findings across .claude/commands/ and .agents/skills/, recorded in this
    task's completion notes per HQ standing rule 11 -- 'no findings' is only evidence once the
    identical command reported findings before). This now pins the post-sweep CLEAN state."""
    findings_total = 0
    for path in checker.collect_files(REPO_ROOT):
        text = path.read_text(encoding="utf-8")
        findings_total += len(checker.find_missing_require_fresh(text, str(path)))
    check("emit-state rule: 0 findings over the live corpus (post-sweep)",
          findings_total == 0,
          f"expected 0 (post-sweep) findings, got {findings_total} -- an instructing "
          f"`mev emit-state --write` line without --require-fresh has regressed into the corpus")


def test_main_reflects_both_rules_against_live_root():
    """main() combines both rules; with the sweep landed, both are clean over the live corpus,
    so main() must reach exit 0 -- the same command this task's own validation runs."""
    exit_code = checker.main(["--root", str(REPO_ROOT), "--quiet"])
    check("main() exit code is 0 (both rules clean over the live corpus)",
          exit_code == 0,
          f"expected 0, got {exit_code}")


# ---------------------------------------------------------------------------
# (g) the .claude/skills/ tree is scanned at all. Before this case SCAN_DIRS was
#     (".claude/commands", ".agents/skills") only, so the 14 live SKILL.md files under
#     .claude/skills/ were ungated -- a write-path instruction there was invisible.
#     Positive control (HQ standing rule 11): the same fixture is first placed under
#     .claude/commands/, where the checker is known to look, and must be found there too;
#     if the control comes back empty the instrument is broken, not the tree.
# ---------------------------------------------------------------------------

def test_claude_skills_tree_is_scanned():
    import tempfile

    fixture = INSTRUCTING_FIXTURES["bare_fenced_line"]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        control = root / ".claude/commands"
        control.mkdir(parents=True)
        (control / "control.md").write_text(fixture, encoding="utf-8")

        subject = root / ".claude/skills/some-skill"
        subject.mkdir(parents=True)
        (subject / "SKILL.md").write_text(fixture, encoding="utf-8")

        collected = {p.relative_to(root).as_posix() for p in checker.collect_files(root)}

        check("positive control: .claude/commands/control.md is collected",
              ".claude/commands/control.md" in collected,
              f"instrument broken -- collected {sorted(collected)!r}")
        check(".claude/skills/some-skill/SKILL.md is collected",
              ".claude/skills/some-skill/SKILL.md" in collected,
              f"expected the .claude/skills tree to be scanned; collected {sorted(collected)!r}")

        exit_code = checker.main(["--root", str(root), "--quiet"])
        check("main() reports a finding under .claude/skills (exit 1)", exit_code == 1,
              f"expected 1, got {exit_code}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subject = root / ".claude/skills/only-skill"
        subject.mkdir(parents=True)
        (subject / "SKILL.md").write_text(fixture, encoding="utf-8")
        exit_code = checker.main(["--root", str(root), "--quiet"])
        check("a .claude/skills finding alone is enough to fail main()", exit_code == 1,
              f"expected 1, got {exit_code} -- the tree is still unscanned")


def main():
    test_instructing_fixtures_fail()
    test_discussion_fixture_passes()
    test_live_derive_state_safely_passes()
    test_live_corpus_is_clean_after_task2_fix()
    test_wrapper_rule_clean_against_live_root()

    test_emit_state_missing_flag_fixtures_fail()
    test_emit_state_with_flag_fixtures_pass()
    test_emit_state_discussion_fixture_passes()
    test_wrapper_rule_unaffected_by_emit_state_fixtures()
    test_emit_state_rule_live_root_snapshot_task1()
    test_main_reflects_both_rules_against_live_root()

    test_claude_skills_tree_is_scanned()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print(f"\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
