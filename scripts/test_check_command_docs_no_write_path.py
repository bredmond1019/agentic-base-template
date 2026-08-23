#!/usr/bin/env python3
"""Fixtures over check_command_docs_no_write_path.py's instruction-vs-discussion rule.

Dependency-free, same discipline as the module it tests.

The whole check is one distinction: INSTRUCTING execution of `validate_brain.sh` /
`emit_state_write.sh` / `routine.sh` must fail; DISCUSSING one of them -- a writer-table row, a
ban list, prose explaining behaviour -- must pass. A naive substring match fails
`.agents/skills/derive-state-safely/SKILL.md`, which legitimately names all three; a checker that
fails a correct file gets disabled, so both directions are asserted here, plus the live corpus in
both its current (RED) and post-fix (GREEN, once the later task lands) states.
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
# Fixture (a): an executable instruction. Modelled directly on the two real instances in
# begin-orchestration.md / orchestrate.md -- a fenced code block whose body IS the command.
# ---------------------------------------------------------------------------

FIXTURE_INSTRUCTION_FENCED = """\
## Before finishing

Run this repo's own gates from `planning/harness.json`, then the corpus gate from `BRAIN_ROOT`:

```
./scripts/validate_brain.sh
```

Concurrent lanes pushing into one corpus is bad.
"""

FIXTURE_INSTRUCTION_FENCED_WITH_COMMENT = """\
```
./scripts/validate_brain.sh          # from the brain root — delta against the last good push
```
"""

FIXTURE_INSTRUCTION_IMPERATIVE_PROSE = """\
Run the brain's `scripts/emit_state_write.sh`. Do not stage or commit anything yourself beyond
what it wrote.
"""

FIXTURE_INSTRUCTION_ROUTINE_FENCED = """\
```bash
./scripts/routine.sh
```
"""

# ---------------------------------------------------------------------------
# Fixture (b): discussion-only, reproducing derive-state-safely's real style -- a writer-table
# row and a ban-list sentence, plus the same file's "cron run, where `validate_brain.sh` runs"
# construction that has the word "run" and a script mention on the same line WITHOUT the imperative
# governing it.
# ---------------------------------------------------------------------------

FIXTURE_DISCUSSION_TABLE_AND_BANLIST = """\
| Command | Shape | Re-runs `emit-state --write` |
|---|---|---|
| `mev emit-state --write` | the write itself | — |
| `./scripts/emit_state_write.sh` · `validate_brain.sh` · `routine.sh` | wrappers | yes |

While any measurement block is live, `syn refresh` / `emit-state --write` / `routine.sh` /
`validate_brain.sh` are **banned** -- corpus changes invalidate a measurement in flight.

The gate exists for exactly one thing: `scripts/routine.sh`'s **unattended nightly cron** run,
where `validate_brain.sh` runs `emit-state` read-only unless `BRAIN_ROLE=primary`.
"""

FIXTURE_DISCUSSION_CALL_INSTEAD = """\
Don't hand-craft the commit pathspec from `git status`, and don't call `bastion emit-state
--write` directly. Call `./scripts/emit_state_write.sh` instead -- it's the one place the
write-then-commit sequence is defined.
"""


def spec_lines(findings):
    return [(no, shape) for no, _text, shape in findings]


def main():
    # (a) instruction fixtures FAIL -- each must produce at least one finding.
    check("fenced bare instruction is flagged",
          len(checker.find_instructions(FIXTURE_INSTRUCTION_FENCED)) >= 1,
          checker.find_instructions(FIXTURE_INSTRUCTION_FENCED))
    check("fenced instruction with trailing comment is flagged",
          len(checker.find_instructions(FIXTURE_INSTRUCTION_FENCED_WITH_COMMENT)) >= 1,
          checker.find_instructions(FIXTURE_INSTRUCTION_FENCED_WITH_COMMENT))
    check("imperative 'Run the brain's `scripts/emit_state_write.sh`' is flagged",
          len(checker.find_instructions(FIXTURE_INSTRUCTION_IMPERATIVE_PROSE)) >= 1,
          checker.find_instructions(FIXTURE_INSTRUCTION_IMPERATIVE_PROSE))
    check("fenced routine.sh instruction is flagged",
          len(checker.find_instructions(FIXTURE_INSTRUCTION_ROUTINE_FENCED)) >= 1,
          checker.find_instructions(FIXTURE_INSTRUCTION_ROUTINE_FENCED))

    # (b) discussion-only fixtures PASS -- zero findings, reproducing derive-state-safely's real
    # shapes: a writer-table row, a ban-list sentence, and the "cron run, where `X` runs" sentence
    # that has "run" and a script mention on the same line without one governing the other.
    check("writer-table row + ban-list + 'cron run, where' construction is NOT flagged",
          checker.find_instructions(FIXTURE_DISCUSSION_TABLE_AND_BANLIST) == [],
          checker.find_instructions(FIXTURE_DISCUSSION_TABLE_AND_BANLIST))
    check("'Call `./scripts/emit_state_write.sh` instead' is NOT flagged",
          checker.find_instructions(FIXTURE_DISCUSSION_CALL_INSTEAD) == [],
          checker.find_instructions(FIXTURE_DISCUSSION_CALL_INSTEAD))

    # (c) the LIVE corpus: derive-state-safely's real SKILL.md must pass, unmodified -- this is
    # not just a fixture reproduction, it exercises the actual file so the check cannot pass by
    # never looking at the real thing.
    root = Path(__file__).resolve().parent.parent
    derive_state_safely = root / ".agents" / "skills" / "derive-state-safely" / "SKILL.md"
    if derive_state_safely.exists():
        text = derive_state_safely.read_text(encoding="utf-8")
        findings = checker.find_instructions(text)
        check("derive-state-safely/SKILL.md (real file) is NOT flagged",
              findings == [], findings)
    else:
        print("[skip] .agents/skills/derive-state-safely/SKILL.md not present from this checkout")

    # (d) the LIVE, CURRENTLY-UNFIXED corpus: this is task 1 -- the command files have not been
    # corrected yet (that is task 2), so the checker MUST currently exit non-zero and name
    # begin-orchestration.md and orchestrate.md (and their .agents/skills/ mirrors). A checker
    # green on its first run against the unfixed corpus has detected nothing. Once task 2 lands
    # this fixture will need updating to assert GREEN instead -- that is expected and is task 2's
    # job, not this one's; recording RED now is the point.
    exit_code = checker.main(["--root", str(root), "--quiet"])
    check("the live corpus is currently RED (task 2 has not run yet)", exit_code == 1,
          f"exit code was {exit_code}")

    begin_orch = root / ".claude" / "commands" / "begin-orchestration.md"
    orchestrate = root / ".claude" / "commands" / "orchestrate.md"
    begin_orch_mirror = root / ".agents" / "skills" / "begin-orchestration" / "SKILL.md"
    orchestrate_mirror = root / ".agents" / "skills" / "orchestrate" / "SKILL.md"
    for label, path in (
        ("begin-orchestration.md", begin_orch),
        ("orchestrate.md", orchestrate),
        ("begin-orchestration/SKILL.md mirror", begin_orch_mirror),
        ("orchestrate/SKILL.md mirror", orchestrate_mirror),
    ):
        if not path.exists():
            print(f"[skip] {label} not present from this checkout")
            continue
        findings = checker.find_instructions(path.read_text(encoding="utf-8"))
        check(f"{label} is currently flagged (unfixed instruction still present)",
              len(findings) >= 1, findings)

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_command_docs_no_write_path.py's instruction-vs-discussion rule holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
