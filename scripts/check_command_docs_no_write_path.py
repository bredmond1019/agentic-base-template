#!/usr/bin/env python3
"""Fail any `.claude/commands/` or `.agents/skills/` file that INSTRUCTS a reader to
execute a write-and-push wrapper as if it were a check (BT.ticket.validate-brain-is-a-
write-and-push-path).

WHY THIS EXISTS
----------------
`scripts/validate_brain.sh` (and the two scripts it fronts, `scripts/emit_state_write.sh` and
`scripts/routine.sh`) run `emit-state --write` corpus-wide and, on a `primary` host, commit and
push -- see `.agents/skills/derive-state-safely/SKILL.md`. Two command files told a lane to run
`./scripts/validate_brain.sh` as its CLOSING VERIFICATION, which on this host performs a write and
a push, not a read. This check is the ratchet: it fails the moment any `.claude/commands/` or
`.agents/skills/` file re-introduces that instruction.

THE ONE DISTINCTION THIS CHECK MAKES
-------------------------------------
INSTRUCTING execution of one of the three scripts must fail; DISCUSSING one of them -- naming it
in a table row, a ban list, or prose explaining its behaviour -- must pass.
`.agents/skills/derive-state-safely/SKILL.md` legitimately does the latter throughout (a writer
table row, an embargo ban list, and prose walking through what the wrapper does) and must keep
passing unmodified.

Two executable shapes are flagged, matching how the two real instances actually read:

  A. A FENCED CODE BLOCK LINE presented as what to run -- the line, after stripping a trailing
     `# comment`, starts with (optionally `./`) `scripts/<name>.sh`. This is exactly the shape of
     both original instances: a fenced ```` ``` ```` block whose body is
     `./scripts/validate_brain.sh` (optionally followed by a trailing comment).

  B. An IMPERATIVE "run" directly governing a backticked script reference outside a fenced block
     and outside a markdown table row -- the word `run`/`Run` followed by at most three more
     words then a backtick-wrapped `scripts/<name>.sh` reference, e.g. "Run the brain's
     `scripts/emit_state_write.sh`." This is deliberately a TIGHT window: it must not fire on a
     sentence that merely happens to contain both the word "run" and a script mention elsewhere
     (e.g. derive-state-safely's "...unattended nightly cron** run, where `validate_brain.sh`
     runs `emit-state`..." -- "run" there is a noun, not an instruction, and the nearest script
     mention is not what it governs).

A markdown TABLE ROW (line whose stripped form starts with `|`) is never flagged under shape B --
that is exactly derive-state-safely's writer-table shape.

Bare mentions without a `scripts/` path prefix (e.g. "`validate_brain.sh` runs `emit-state`") are
never flagged -- only a path-shaped reference reads as a command to execute.

USAGE
-----
    check_command_docs_no_write_path.py [--root DIR] [--quiet]

    --root DIR   repo root to scan (default: the repo containing this script)
    --quiet      print only findings and the summary

Exit code 1 if any instruction is found, 0 otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

SCRIPT_NAMES = ("validate_brain", "emit_state_write", "routine")
SCRIPT_ALT = "|".join(SCRIPT_NAMES)

# Shape A: a fenced-code-block line that IS the command -- optionally `./`, then `scripts/<name>.sh`,
# anchored at the start of the (stripped) line. Args or a trailing comment may follow.
SHAPE_A_RE = re.compile(r"^(?:\./)?scripts/(?:" + SCRIPT_ALT + r")\.sh\b")

# Shape B: "run" (any case) governing a backticked scripts/<name>.sh reference within a tight
# window of at most three intervening words.
SHAPE_B_RE = re.compile(
    r"\brun\b(?:\s+\S+){0,3}\s*`(?:\./)?scripts/(?:" + SCRIPT_ALT + r")\.sh`",
    re.IGNORECASE,
)

SCAN_DIRS = (".claude/commands", ".agents/skills")


def _strip_trailing_comment(line):
    """Strip a trailing `  # comment` from a fenced-block command line. Naive on purpose --
    these are shell command lines, not strings containing '#'."""
    idx = line.find("#")
    if idx == -1:
        return line
    return line[:idx]


def find_instructions(text):
    """Return a list of (line_no, line_text, shape) for every INSTRUCTING reference to one of
    the three write-and-push scripts in `text`. `line_no` is 1-indexed."""
    findings = []
    in_fence = False
    for i, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue

        if in_fence:
            candidate = _strip_trailing_comment(raw_line).strip()
            if SHAPE_A_RE.match(candidate):
                findings.append((i, raw_line.rstrip(), "A"))
            continue

        # Shape B: never inside a fenced block, never on a markdown table row.
        if stripped.startswith("|"):
            continue
        if SHAPE_B_RE.search(raw_line):
            findings.append((i, raw_line.rstrip(), "B"))

    return findings


def iter_target_files(root):
    for scan_dir in SCAN_DIRS:
        base = os.path.join(root, scan_dir)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                if name.endswith(".md"):
                    yield os.path.join(dirpath, name)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None,
                    help="repo root to scan (default: the repo containing this script)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent

    files_checked = 0
    findings_total = 0
    for path in iter_target_files(str(root)):
        files_checked += 1
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"FAIL {path}: could not read ({exc})")
            findings_total += 1
            continue
        rel = os.path.relpath(path, root)
        for line_no, line_text, shape in find_instructions(text):
            findings_total += 1
            print(f"FAIL {rel}:{line_no} [shape {shape}] instructs executing a write-and-push "
                  f"wrapper: {line_text!r}")

    if not args.quiet and findings_total == 0:
        print(f"ok   {files_checked} file(s) checked, 0 instructions to execute a "
              f"write-and-push wrapper")

    print(f"\n{files_checked} file(s) checked, {findings_total} finding(s)")
    return 1 if findings_total else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
