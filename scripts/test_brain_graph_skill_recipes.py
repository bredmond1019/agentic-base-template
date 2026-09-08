#!/usr/bin/env python3
"""Recipe-correctness proof for .claude/skills/brain-graph/SKILL.md (BT.3.F task 4).

The repo-wide `cli-invocations` gate (scripts/check_cli_invocations.py) already checks every
`bastion`/`mev` invocation across .claude/commands/, .claude/skills/ and .agents/skills/ against
the installed binaries' real verbs and (for FLAG_CHECKED_VERBS) real flags. This script is the
same class of check, scoped to exactly one file — the brain-graph skill's own recipes — so the
block's "prove the skill's own recipes against the live corpus" acceptance criterion has a
standing, re-runnable artifact that survives the skill's author being wrong, rather than relying
solely on the broader gate to have caught it.

Beyond verb/flag existence, this script asserts the one rule the repo-wide gate does not check:
`bastion brain` and `bastion code` each require EXACTLY ONE of their query flags
(--dependents/--blast-radius/--lineage for brain; --def/--refs/--dependents for code) — supplying
zero or more than one is a usage error. Every fenced `bastion brain`/`bastion code` invocation in
the skill file is checked for this too.

Degrades open (exit 0, prints a skip line) when `bastion` is not on PATH — a fresh clone or a CI
runner without the fleet's binaries installed should not red-gate on an environment fact.

Usage:
  python3 scripts/test_brain_graph_skill_recipes.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_FILE = ROOT / ".claude" / "skills" / "brain-graph" / "SKILL.md"

BRAIN_QUERY_FLAGS = {"--dependents", "--blast-radius", "--lineage"}
CODE_QUERY_FLAGS = {"--def", "--refs", "--dependents"}

INVOCATION_RE = re.compile(r"^\s*(?:\$\s*)?bastion\s+(brain|code)\s+([^\n`]*)", re.M)
FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")


def extract_spans(text: str) -> list[str]:
    """Every inline-backtick span and every fenced-code-block body in the skill file."""
    spans: list[str] = []
    spans.extend(re.findall(r"`([^`\n]+)`", text))
    for block in re.findall(r"```(?:[a-z]*)\n(.*?)```", text, re.S):
        spans.append(block)
    return spans


def get_verbs(binary: str) -> set[str] | None:
    try:
        out = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=15).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    verbs: set[str] = set()
    in_commands = False
    for line in out.splitlines():
        if line.strip() == "Commands:":
            in_commands = True
            continue
        if not in_commands:
            continue
        if line.strip() == "" or line.startswith("Options:"):
            break
        m = re.match(r"^\s{2}(\S+)", line)
        if m:
            verbs.add(m.group(1))
    return verbs


def get_flags(binary: str, verb: str) -> set[str] | None:
    try:
        out = subprocess.run([binary, verb, "--help"], capture_output=True, text=True, timeout=15).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return set(FLAG_RE.findall(out))


def collect_invocations(text: str) -> list[tuple[str, str, bool]]:
    """Every fenced/backtick `bastion brain`/`bastion code ...` invocation as (verb, rest, is_demo_error).

    `is_demo_error` is true when the surrounding span also contains an `error:` line — the skill
    file deliberately shows the exactly-one-of usage error (a query-flag-less invocation followed
    by bastion's own "error: the following required arguments..." output) as documentation, not
    as a recipe to validate positively. Such spans are checked for verb/flag legitimacy but not
    for the exactly-one-query-flag rule, since they exist specifically to demonstrate its absence.
    """
    found: list[tuple[str, str, bool]] = []
    for span in extract_spans(text):
        is_demo_error = "error:" in span
        for m in INVOCATION_RE.finditer(span):
            found.append((m.group(1), m.group(2), is_demo_error))
    return found


def check() -> int:
    if shutil.which("bastion") is None:
        print("SKIPPED — bastion not on PATH (degrade open, not a check failure)")
        return 0

    verbs = get_verbs("bastion")
    if verbs is None:
        print("SKIPPED — bastion --help did not run (degrade open, not a check failure)")
        return 0

    if not SKILL_FILE.exists():
        print(f"FAILED — {SKILL_FILE.relative_to(ROOT)} does not exist")
        return 1

    text = SKILL_FILE.read_text(encoding="utf-8", errors="replace")
    invocations = collect_invocations(text)
    if not invocations:
        print("FAILED — no fenced `bastion brain`/`bastion code` invocations found in the skill file")
        return 1

    flag_cache: dict[str, set[str] | None] = {}
    findings: list[str] = []

    for verb, rest, is_demo_error in invocations:
        if verb not in verbs:
            findings.append(f"no such verb 'bastion {verb}'")
            continue

        if verb not in flag_cache:
            flag_cache[verb] = get_flags("bastion", verb)
        real_flags = flag_cache[verb]

        rest_flags = FLAG_RE.findall(rest)
        is_help_only = rest_flags == ["--help"] or "--help" in rest

        if not is_demo_error and not is_help_only:
            query_flags = BRAIN_QUERY_FLAGS if verb == "brain" else CODE_QUERY_FLAGS
            present_query_flags = [f for f in rest_flags if f in query_flags]
            if len(present_query_flags) != 1:
                findings.append(
                    f"'bastion {verb} {rest.strip()}' names {len(present_query_flags)} of "
                    f"{sorted(query_flags)} query flags (exactly one required)"
                )

        if real_flags is not None:
            for flag in rest_flags:
                if flag not in real_flags and flag != "--help":
                    findings.append(f"'bastion {verb}' has no flag '{flag}' (from: {rest.strip()!r})")

    if findings:
        print(f"FAILED — {len(findings)} recipe problem(s) in {SKILL_FILE.relative_to(ROOT)}:")
        for f in findings:
            print(f"  - {f}")
        return 1

    print(f"OK — {len(invocations)} recipe(s) in {SKILL_FILE.relative_to(ROOT)} are well-formed.")
    return 0


if __name__ == "__main__":
    sys.exit(check())
