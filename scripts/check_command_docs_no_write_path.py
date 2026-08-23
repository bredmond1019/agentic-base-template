#!/usr/bin/env python3
"""Fail when a command or skill file INSTRUCTS a lane to execute one of the three
write-and-push wrappers -- `scripts/validate_brain.sh`, `scripts/emit_state_write.sh`,
`scripts/routine.sh` -- rather than merely NAMING them in discussion
(BT.ticket.validate-brain-is-a-write-and-push-path).

Dependency-free on purpose: `jsonschema` is not installed anywhere in this fleet.

WHY THIS CHECK EXISTS: on a `primary` host, `validate_brain.sh` runs `emit-state --write`
corpus-wide, commits, and pushes (it delegates to `emit_state_write.sh`, which calls
`commit_routine_updates.sh`, which pushes). `.claude/commands/begin-orchestration.md` and
`orchestrate.md` (and their `.agents/skills/` mirrors) told every lane to run it as a
*closing verification* -- a write-and-push path presented as a read-only check. See
`.agents/skills/derive-state-safely/SKILL.md` for the full mechanism; this check exists so
no command or skill file re-introduces the instruction.

THE WHOLE CHECKER IS THE DISTINCTION BETWEEN INSTRUCTING AND DISCUSSING.
`.agents/skills/derive-state-safely/SKILL.md` legitimately names all three scripts --
in a writer-table row, in a ban list, and inline mid-sentence ("Call `./scripts/
emit_state_write.sh` instead -- it's the one place the write-then-commit sequence is
defined") -- and must keep passing. An instruction has an EXECUTABLE SHAPE: the ENTIRE
line (after stripping a leading list marker/shell prompt and optional wrapping backtick)
IS the script invocation, with nothing left but optional flag-shaped args and/or a
trailing `# comment`, e.g.

    ./scripts/validate_brain.sh
    ./scripts/validate_brain.sh          # from the brain root -- delta against last push
    bash scripts/emit_state_write.sh
    scripts/routine.sh --apply

A line where the script name is only PART of a sentence -- prose text before or after it
on the same line, a markdown table cell (`| ... validate_brain.sh ... |`), or an inline
code span embedded mid-paragraph ("`validate_brain.sh` delegates to this same script...",
"Call `./scripts/emit_state_write.sh` instead -- it's the one place...") -- is discussion,
not instruction, and must PASS even though it names the script and even though it may
itself contain an imperative verb like "Call" or "Run" elsewhere in the sentence.

Usage:
    check_command_docs_no_write_path.py [--root DIR] [--quiet]

    --root DIR   repo root to scan (default: .)
    --quiet      print only findings and the summary

Exit code 1 if any file instructs execution of one of the three scripts. A corpus with no
matches at all is silent success (exit 0).
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

SKIP_DIRS = {"node_modules", ".git", "archive", "target", ".fleet-locks", "trees"}

SCAN_DIRS = (".claude/commands", ".agents/skills")

WRAPPER_SCRIPTS = (
    "validate_brain.sh",
    "emit_state_write.sh",
    "routine.sh",
)

# Matches a line that INVOKES one of the wrapper scripts as a command:
#   - optional imperative lead-in ("Run ", "Execute ", "Call ") OR
#   - the invocation is the start of the (trimmed) line, optionally after a shell
#     prefix (`./`, `bash `, `sh `, `python3 `) or inside a `-` prompt.
# Deliberately does NOT match the bare script name appearing mid-sentence or inside a
# markdown table cell (`| ... validate_brain.sh ... |`) or inline code discussing it
# (`` `validate_brain.sh` delegates to this same script `` -- no leading invocation shape).
_SCRIPT_ALT = "|".join(re.escape(s) for s in WRAPPER_SCRIPTS)

# The WHOLE (trimmed) line must be nothing but the invocation: an optional list marker or
# shell prompt, an optional wrapping backtick, an optional `./`/interpreter prefix, the
# script name, zero or more flag-shaped args (`--foo`, `-x`), an optional closing
# backtick, and then either end-of-line or a trailing shell comment. Free-form prose words
# after the script name (as in a sentence discussing it) do not match this shape, so the
# match fails and the line is correctly read as discussion, not instruction.
_FULL_LINE_INVOCATION_RE = re.compile(
    r"^(?:[-*>]\s*|\$\s*)?"                       # optional list marker or shell prompt
    r"`?"                                          # optional opening backtick
    r"(?:\./|bash\s+|sh\s+|python3?\s+)?"
    r"scripts/(?:" + _SCRIPT_ALT + r")\b"
    r"(?:\s+--?[A-Za-z][\w-]*)*"                   # optional flag-shaped args only
    r"`?"                                           # optional closing backtick
    r"\s*(?:#.*)?$"
)

# A line is DISCUSSION, not instruction, whenever the script name is only PART of a
# sentence -- prose before/after it on the same line, a markdown table cell, or an inline
# code span mid-paragraph. Those simply fail to match the shape above (no explicit
# allow-list needed): any word that isn't a flag or a trailing comment breaks the match.


def _table_row(line: str) -> bool:
    return line.strip().startswith("|")


def find_instructions(text: str, filename: str):
    """Return a list of (line_no, line_text) where `text` instructs executing one of the
    wrapper scripts."""
    findings = []
    in_fence = False
    for i, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not any(s in raw_line for s in WRAPPER_SCRIPTS):
            continue
        if _table_row(raw_line):
            continue
        # Inside or outside a fenced block, the test is the same: is the whole line just
        # the invocation? A fenced block does not change the shape test, only that a bare
        # invocation there is even more clearly "presented as what to run".
        if _FULL_LINE_INVOCATION_RE.match(stripped):
            findings.append((i, raw_line))
    return findings


def collect_files(root: Path):
    out = []
    for scan_dir in SCAN_DIRS:
        base = root / scan_dir
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if name.endswith(".md"):
                    out.append(Path(dirpath) / name)
    return sorted(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    files = collect_files(root)

    findings_total = 0
    files_checked = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 - unreadable file is another check's job
            continue
        files_checked += 1
        for line_no, line_text in find_instructions(text, str(path)):
            findings_total += 1
            print(f"FAIL {path} line {line_no}: instructs execution of a write-and-push "
                  f"wrapper: {line_text.strip()!r}")

    if not args.quiet and findings_total == 0:
        print(f"ok   {files_checked} file(s) checked, 0 write-path instructions found")

    print(f"\n{files_checked} file(s) checked, {findings_total} finding(s)")
    return 1 if findings_total else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
