#!/usr/bin/env python3
"""Assert that both orchestration commands name all four run artifacts and link
the ledger contract (BT.ticket.run-artifacts-are-named-in-the-commands).

A run leaves four artifacts: `notes.md`, `review.md`, `verification-ledger.json`,
`verification-ledger.md`. Before this ticket, `.claude/commands/begin-orchestration.md`
and `.claude/commands/orchestrate.md` named the run-record and lane-log artifacts but
never the verification ledger, so a run produced that evidence only when an operator
happened to ask for it in the prompt. This checker pins that both command files name
every one of the four artifacts and link
`docs/sandbox/run-verification-ledger-prompt.md` as the schema's authority, so the
regression back to zero mentions is caught mechanically rather than by a human
re-grepping.

Dependency-free on purpose: no third-party imports, bare python3.

Usage:
    python3 scripts/check_run_artifacts_documented.py

Exit 0 and print nothing noisy on success. Exit non-zero and print one line per
missing item -- naming the offending command file and the missing artifact or link
-- on failure. Exits non-zero (rather than silently passing) if either command file
is missing entirely, since a checker that passes when its target is absent has
detected nothing.

OBSERVED-RED EVIDENCE (task 1, D68): run against the unpatched tree on 2026-09-07,
this checker exited non-zero (exit 1) and printed six lines -- for each of
`.claude/commands/begin-orchestration.md` and `.claude/commands/orchestrate.md`: a
missing `verification-ledger.json`, a missing `verification-ledger.md`, and a missing
link to `docs/sandbox/run-verification-ledger-prompt.md` (`notes.md` and `review.md`
were already named in both files, so only the ledger-related items were flagged),
confirming the checker fails closed before the commands are patched. Task 4 records
the narrower single-item removal-and-restore observation required by AC5.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

COMMAND_FILES = [
    ".claude/commands/begin-orchestration.md",
    ".claude/commands/orchestrate.md",
]

REQUIRED_ARTIFACTS = [
    "notes.md",
    "review.md",
    "verification-ledger.json",
    "verification-ledger.md",
]

LEDGER_PROMPT_LINK = "docs/sandbox/run-verification-ledger-prompt.md"


def check_file(rel_path: str) -> list[str]:
    """Return a list of failure messages for one command file (empty = clean)."""
    path = REPO_ROOT / rel_path
    if not path.is_file():
        return [f"{rel_path}: MISSING command file -- cannot check artifact names"]

    text = path.read_text(encoding="utf-8")

    failures = []
    for artifact in REQUIRED_ARTIFACTS:
        if artifact not in text:
            failures.append(f"{rel_path}: missing artifact name '{artifact}'")
    if LEDGER_PROMPT_LINK not in text:
        failures.append(f"{rel_path}: missing link to '{LEDGER_PROMPT_LINK}'")
    return failures


def main() -> int:
    all_failures: list[str] = []
    for rel_path in COMMAND_FILES:
        all_failures.extend(check_file(rel_path))

    if all_failures:
        for line in all_failures:
            print(line)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
