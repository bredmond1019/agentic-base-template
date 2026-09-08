#!/usr/bin/env python3
"""Dependency-free fixture for BT.8.B task 1.

Asserts four things over the coord-verb / fallback-labelling contract:

  (A) FALLBACK LABELLING — every line that instructs a write to
      `<lock_dir>/lane-agents/...` or `<lock_dir>/leases/...` in
      begin-orchestration.md / orchestrate.md sits inside a section whose
      nearest preceding markdown heading is labelled "fallback"
      (case-insensitive).
  (B) NO PHANTOM VERB — none of the three files ever mentions
      `bastion coord emit-schema`. That verb does not exist (BA.25.C shipped
      nine write verbs, not ten).
  (C) VERBS EXIST — every verb named in a `bastion coord <verb>` occurrence
      across the three files is a real subcommand, per `bastion coord --help`.
      Skipped cleanly (not failed) when the `bastion` binary is not on PATH.
  (D) POINTERS SURVIVE — both command files still carry their
      `.claude/workflows/finding-discipline.md` pointer.

No third-party imports. Exits non-zero with one named failure line per
violated assertion; exits 0 (with any SKIP lines) when everything holds.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BEGIN_ORCHESTRATION = REPO_ROOT / ".claude" / "commands" / "begin-orchestration.md"
ORCHESTRATE = REPO_ROOT / ".claude" / "commands" / "orchestrate.md"
PING_AGENT_SKILL = REPO_ROOT / ".claude" / "skills" / "ping-agent" / "SKILL.md"

# Files checked by assertion (B) no-phantom-verb and (D) pointer-survives
# apply only to the two command files that carry the pointer; (B) and (C)
# scan all three.
COMMAND_FILES = [BEGIN_ORCHESTRATION, ORCHESTRATE]
ALL_FILES = [BEGIN_ORCHESTRATION, ORCHESTRATE, PING_AGENT_SKILL]

PHANTOM_VERB = "bastion coord emit-schema"
FINDING_DISCIPLINE_POINTER = "finding-discipline.md"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LANE_AGENTS_PATH_RE = re.compile(r"lane-agents/")
LEASES_PATH_RE = re.compile(r"leases/")
COORD_VERB_RE = re.compile(r"bastion coord ([a-z][a-z0-9-]*)")

# Non-verb tokens that can legitimately follow "bastion coord" in prose
# (flags, placeholders) without naming a subcommand.
COORD_VERB_STOPWORDS = {"verbs", "verb"}


def read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def check_fallback_labelling(failures):
    for path in COMMAND_FILES:
        if not path.exists():
            failures.append(f"(A) fallback-labelling: missing file {path}")
            continue
        current_heading = ""
        for lineno, line in enumerate(read_lines(path), start=1):
            m = HEADING_RE.match(line)
            if m:
                current_heading = m.group(2)
                continue
            if LANE_AGENTS_PATH_RE.search(line) or LEASES_PATH_RE.search(line):
                if "fallback" not in current_heading.lower():
                    failures.append(
                        f"(A) fallback-labelling: {path.relative_to(REPO_ROOT)}:{lineno} "
                        f"writes a lane-agents/ or leases/ path outside a 'fallback' "
                        f"section (current heading: {current_heading!r}): {line.strip()!r}"
                    )


def check_no_phantom_verb(failures):
    for path in ALL_FILES:
        if not path.exists():
            failures.append(f"(B) no-phantom-verb: missing file {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if PHANTOM_VERB in text:
            failures.append(
                f"(B) no-phantom-verb: {path.relative_to(REPO_ROOT)} mentions "
                f"'{PHANTOM_VERB}', which does not exist (BA.25.C shipped nine "
                f"write verbs, not ten)"
            )


def get_installed_coord_verbs():
    """Returns (verbs, error). error is None on success."""
    bastion = shutil.which("bastion")
    if not bastion:
        return None, "bastion not on PATH"
    try:
        result = subprocess.run(
            [bastion, "coord", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"bastion coord --help failed to run: {exc}"
    if result.returncode != 0:
        return None, f"bastion coord --help exited {result.returncode}"
    verbs = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        m = re.match(r"^([a-z][a-z0-9-]*)\b", stripped)
        if m:
            verbs.add(m.group(1))
    return verbs, None


def check_verbs_exist(failures, skips):
    named_verbs = set()
    for path in ALL_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for m in COORD_VERB_RE.finditer(text):
            verb = m.group(1)
            if verb in COORD_VERB_STOPWORDS:
                continue
            named_verbs.add(verb)

    if not named_verbs:
        return

    verbs, error = get_installed_coord_verbs()
    if error is not None:
        skips.append(f"(C) verbs-exist: SKIP ({error})")
        return

    for verb in sorted(named_verbs):
        if verb not in verbs:
            failures.append(
                f"(C) verbs-exist: command text names 'bastion coord {verb}', "
                f"which is not in `bastion coord --help` output "
                f"(known verbs: {sorted(verbs)})"
            )


def check_pointer_survives(failures):
    for path in COMMAND_FILES:
        if not path.exists():
            failures.append(f"(D) pointer-survives: missing file {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if FINDING_DISCIPLINE_POINTER not in text:
            failures.append(
                f"(D) pointer-survives: {path.relative_to(REPO_ROOT)} no longer "
                f"carries the '{FINDING_DISCIPLINE_POINTER}' pointer"
            )


def main():
    failures = []
    skips = []

    check_fallback_labelling(failures)
    check_no_phantom_verb(failures)
    check_verbs_exist(failures, skips)
    check_pointer_survives(failures)

    for skip in skips:
        print(skip)

    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS: all assertions hold (coord-verbs-documented)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
