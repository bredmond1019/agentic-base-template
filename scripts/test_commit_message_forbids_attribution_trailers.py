#!/usr/bin/env python3
"""Structural completeness test: every commit-message heredoc site in the SDLC
engines must reference the shared anti-attribution-trailer instruction.

For each of prompts/shared.js, sdlc-task.js and sdlc-flow.js, this counts
occurrences of the literal commit-heredoc opener (`commit -m "$(cat <<'EOF'`)
and occurrences of the `renderNoAttributionTrailer(` marker in that same
file, and asserts the two counts are equal per file. A file that gains a
15th commit site in the future without a matching reminder reference fails
this test -- that forward-looking guarantee is the actual value of the
check, not merely confirming today's count.

Run directly: `python3 scripts/test_commit_message_forbids_attribution_trailers.py`
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

HEREDOC_OPENER = "commit -m \"$(cat <<'EOF'"
REMINDER_MARKER = "renderNoAttributionTrailer("

FILES = [
    REPO_ROOT / ".claude/workflows/prompts/shared.js",
    REPO_ROOT / ".claude/workflows/sdlc-task.js",
    REPO_ROOT / ".claude/workflows/sdlc-flow.js",
]


def count_occurrences(text: str, substring: str) -> int:
    return text.count(substring)


def main() -> int:
    failures = []
    results = []

    for path in FILES:
        if not path.exists():
            print(f"FAIL: {path} does not exist")
            return 1

        text = path.read_text(encoding="utf-8")
        heredoc_count = count_occurrences(text, HEREDOC_OPENER)
        reminder_count = count_occurrences(text, REMINDER_MARKER)
        results.append((path, heredoc_count, reminder_count))

        if heredoc_count != reminder_count:
            failures.append((path, heredoc_count, reminder_count))

    print("Commit-heredoc site count vs. anti-attribution-trailer reminder count:")
    for path, heredoc_count, reminder_count in results:
        rel = path.relative_to(REPO_ROOT)
        status = "OK" if heredoc_count == reminder_count else "MISMATCH"
        print(f"  {rel}: heredoc_sites={heredoc_count} reminder_refs={reminder_count} [{status}]")

    if failures:
        print()
        print("FAILED: heredoc-site count and reminder-reference count must be equal in every file.")
        for path, heredoc_count, reminder_count in failures:
            rel = path.relative_to(REPO_ROOT)
            print(f"  {rel}: {heredoc_count} heredoc sites but only {reminder_count} reminder references")
        return 1

    print()
    print("PASSED: every commit-heredoc site is matched by an anti-attribution-trailer reminder reference.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
