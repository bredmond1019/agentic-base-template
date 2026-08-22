#!/usr/bin/env python3
"""check_frontmatter_presence.py — the presence/placement gate hooks/check_frontmatter.py punts to.

WHY THIS EXISTS
---------------
The brain's hooks/check_frontmatter.py (<brain_root>/hooks/check_frontmatter.py) is a YAML
*parse* gate, not a presence gate — by its own docstring. It contains two `return 0` escape
hatches that both punt to "a different check's job":

    if not lines or lines[0].strip() != "---":
        return 0  # no frontmatter block — not this gate's concern
    ...
    if end is None:
        return 0  # unterminated frontmatter — a structural issue, not a YAML parse one

Neither escape hatch ever pointed at a real check. On 2026-08-22 the sdlc-task bookkeep stage
wrote a paragraph into base-template/planning/status.md twice in the wrong place: once as line 1,
ABOVE the opening `---` fence (displacing the frontmatter below content), and once between
`related:` and the closing fence (inside the block). The first corruption alone made
`lines[0].strip() != "---"` true, so hatch 1 fired and returned 0 *before ever reaching* the YAML
parse that would very likely have caught the second corruption too. `bastion validate-brain`
then failed all four of --structure/--links/--graph/--state at once with "missing or unterminated
frontmatter block" — attributed to a repo, not a stage, which is why it read as a corpus-wide
regression instead of one bad write. This script is the check both hatches should have delegated
to and never did.

WHAT THIS DOES
--------------
Given a repo-relative path (for corpus-membership + display) and a file's content on stdin —
same calling convention as check_frontmatter.py: `python3 check_frontmatter_presence.py <path> <
content` — decide whether the file's OKF frontmatter is PRESENT, starts at line 1, and is
TERMINATED. Three distinct reject reasons, one accept path, and a scope test that runs first.

SCOPE — the hard part
----------------------
A file with no frontmatter at all can be perfectly legal (a stray root .md, a src/ doc, anything
outside the corpus), so "must start with `---`" is only meaningful for files the corpus actually
obliges to carry frontmatter. Membership mirrors the write-okf-markdown skill / mev's
`is_corpus_member` (core/mev/src/brain/crawl.rs) rather than inventing a second rule:

  - Excluded (ephemeral), regardless of everything else: the file name starts with `_`, or is
    exactly one of `handoff.md` / `tasks.md` / `breakdown.md` / `worklog.md`.
  - Excluded on extension: the file name carries a dot-extension and that extension is not `.md`
    (e.g. `notes.txt`). A name with NO extension at all (a bare display token such as the ones
    this script's own smoke tests pass) is NOT excluded by this rule — there is nothing to compare
    against, so it falls through to the default below.
  - Included: the path is exactly `README.md`, `CLAUDE.md`, or `index.md` with no directory
    component (repo root), OR the path has `planning` or `docs` anywhere in its parts.
  - Otherwise, if the name ends in `.md` and matched none of the inclusion rules above (e.g.
    `src/lib.md`, root-level `NOTES.md`) — excluded.
  - Otherwise (no extension at all, and not one of the ephemeral/root-special cases) — default to
    IN SCOPE. A bare label with no path structure gives no basis to *exclude* it, and defaulting
    to "check it" is the safer failure mode for a gate that exists because a default-skip escape
    hatch silently let a real corruption through once already.

Out-of-scope files exit 0 silently — no output, no exit-1 noise on files this gate has no claim
over.

THE THREE REJECT CASES
-----------------------
  - ABSENT      — in-corpus, no `---` fence pair anywhere in the file.
  - UNTERMINATED — line 1 is `---` but no closing `---` line follows it.
  - DISPLACED   — the file contains frontmatter-shaped content (a `---` line followed by
    `key: value`-looking lines) somewhere at or after line 2, but line 1 is not `---`. This is
    the 2026-08-22 failure and the one the existing hook is blind to. Detected by scanning for a
    `---` fence pair whose body has at least one line matching `^[A-Za-z0-9_-]+:` — an ordinary
    prose document that happens to contain a bare `---` horizontal rule, with no frontmatter-
    looking lines after it, is NOT flagged. FALSE-POSITIVE BOUNDARY: a prose document that
    coincidentally contains both a `---` rule AND, immediately after it, a line matching
    `word:` (e.g. a glossary entry `Note: see above`) will be flagged as DISPLACED. That trade is
    deliberate — the failure mode this script exists to close is a false negative (a real
    displacement waved through), not a false positive on an unusual document; a false positive
    here just means a human looks once and moves the fence marker or the colon.

Exit 0: out of scope, or frontmatter present/anchored/terminated (this is a presence gate, not a
YAML parse gate — a present-but-malformed block is check_frontmatter.py's job, not this one's).
Exit 1: rejected. Prints file:line, the offending line, and a fix hint to stderr, matching
check_frontmatter.py's tone.

Standard library only.

Usage: python3 check_frontmatter_presence.py <path-for-display-and-scope> < content
"""
from __future__ import annotations

import re
import sys

EPHEMERAL_NAMES = frozenset({"handoff.md", "tasks.md", "breakdown.md", "worklog.md"})
ROOT_SPECIAL_NAMES = frozenset({"README.md", "CLAUDE.md", "index.md"})
# Corpus members that are nonetheless allowed to carry NO frontmatter at all, mirroring
# mev's is_root_instruction_file (core/mev/src/brain/okf.rs): "Root instruction files
# (README.md / CLAUDE.md) without frontmatter are valid corpus leaves — they must not
# raise the OKF 'missing frontmatter' error." index.md is NOT in this set — mev requires
# it. Confirmed live: base-template's own CLAUDE.md and this brain's own root CLAUDE.md
# both carry zero frontmatter today and validate-brain --structure reports 0 errors on
# either — an unconditional ABSENT reject for ROOT_SPECIAL_NAMES would red-gate both on
# a file this gate has no real claim over. Deliberately narrower than mev: an
# UNTERMINATED or DISPLACED block on one of these two files is still rejected here even
# though mev's simpler extract_frontmatter() would silently accept it too — no currently
# committed README.md/CLAUDE.md is in either state, so the stricter behavior costs
# nothing today and closes a real gap mev also has.
ABSENT_EXEMPT_NAMES = frozenset({"README.md", "CLAUDE.md"})

# A frontmatter-looking line: `key:` or `key: value`, key made of word chars/hyphens.
_KEY_LINE_RE = re.compile(r"^[A-Za-z0-9_-]+:")


def _file_name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def is_in_scope(path: str) -> bool:
    """Corpus-membership decision — see the SCOPE section in the module docstring."""
    name = _file_name(path)

    # Ephemeral: never in scope, regardless of location.
    if name.startswith("_") or name in EPHEMERAL_NAMES:
        return False

    has_extension = "." in name
    is_md = name.endswith(".md")

    # An extension present and it isn't .md -> excluded.
    if has_extension and not is_md:
        return False

    parts = path.split("/")
    no_dir = len(parts) == 1

    if is_md:
        if no_dir and name in ROOT_SPECIAL_NAMES:
            return True
        if "planning" in parts or "docs" in parts:
            return True
        # Has .md extension but matched no inclusion rule (e.g. src/lib.md, root NOTES.md).
        return False

    # No extension at all: nothing to exclude on, and no path structure to exclude on either.
    # Default to in-scope (see docstring: the safer failure mode for this gate).
    return True


def _find_fence_pairs(lines: list[str]) -> list[tuple[int, int]]:
    """Return (start_idx, end_idx) 0-indexed pairs for every `---` ... `---` block in lines."""
    pairs = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip() == "---":
            for j in range(i + 1, n):
                if lines[j].strip() == "---":
                    pairs.append((i, j))
                    i = j  # resume scanning after this block's closing fence
                    break
            else:
                # Unterminated from this opener — stop; caller handles line-1 unterminated case
                # separately, and a non-line-1 unterminated opener with no closer isn't itself a
                # frontmatter-shaped block we can confirm, so it is not reported as DISPLACED.
                break
        i += 1
    return pairs


def _looks_like_frontmatter_body(lines: list[str], start: int, end: int) -> bool:
    """True if the body between fence lines start/end (exclusive) has >=1 key-looking line."""
    for k in range(start + 1, end):
        if _KEY_LINE_RE.match(lines[k].strip()):
            return True
    return False


def _is_absent_exempt(path: str) -> bool:
    """True for the unit-root README.md/CLAUDE.md exemption — see ABSENT_EXEMPT_NAMES."""
    parts = path.split("/")
    return len(parts) == 1 and parts[0] in ABSENT_EXEMPT_NAMES


def check(path: str, content: str) -> int:
    if not is_in_scope(path):
        return 0

    lines = content.splitlines()

    if not lines:
        if _is_absent_exempt(path):
            return 0
        print(f"{path}:1: ABSENT — in-corpus file has no frontmatter block", file=sys.stderr)
        print("  fix: add an OKF frontmatter block starting at line 1", file=sys.stderr)
        return 1

    if lines[0].strip() == "---":
        # Line 1 opens a fence — check it terminates.
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is None:
            print(
                f"{path}:1: UNTERMINATED — frontmatter opens at line 1 but no closing "
                f"'---' line follows it",
                file=sys.stderr,
            )
            print("  " + lines[0].strip(), file=sys.stderr)
            print("  fix: add a closing '---' line after the frontmatter fields", file=sys.stderr)
            return 1
        return 0

    # Line 1 is not a fence opener. Look for a displaced frontmatter-shaped block later
    # in the file — a `---` fence pair whose body contains at least one key-looking line.
    for start, end in _find_fence_pairs(lines):
        if start == 0:
            continue  # already handled above
        if _looks_like_frontmatter_body(lines, start, end):
            file_line = start + 1  # 1-indexed
            print(
                f"{path}:{file_line}: DISPLACED — frontmatter fence found at line "
                f"{file_line}, not line 1 (content precedes it)",
                file=sys.stderr,
            )
            print("  " + lines[start].strip(), file=sys.stderr)
            print(
                "  fix: move the '---'-delimited frontmatter block to the very top of the file",
                file=sys.stderr,
            )
            return 1

    # No fence at line 1, and no displaced frontmatter-shaped block found -> ABSENT.
    if _is_absent_exempt(path):
        return 0
    print(f"{path}:1: ABSENT — in-corpus file has no frontmatter block", file=sys.stderr)
    print("  fix: add an OKF frontmatter block starting at line 1", file=sys.stderr)
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        print("check_frontmatter_presence.py: missing <path> argument", file=sys.stderr)
        return 0  # non-fatal: never block on a checker misuse

    path = sys.argv[1]
    content = sys.stdin.read()
    return check(path, content)


if __name__ == "__main__":
    sys.exit(main())
