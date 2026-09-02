#!/usr/bin/env python3
"""Verb/flag-invocation gate over this repo's .claude/ and .agents/ authoring surfaces.

Why this exists: a `mev`/`bastion` subcommand or flag named in a `.claude/commands/*.md` or
`.agents/skills/*/SKILL.md` prompt is never checked against the real CLI — it is prose, and
prose parses. Three live breakages shipped this way and sat undetected until a session happened
to run the command by hand: `mev lane-frontier --repo <slug>` (no such verb — the real verb is
`frontier`, and it has no `--repo` flag either), `bastion validate-brain --okf-structure` (the
real flag is `--structure`), and a `close-session` verb that does not exist anywhere in `mev`
(HQ's own `begin-session.md`, tracked separately — D54 makes it HQ's own file). This gate is
"detection before authoring" for that class of bug: it shells the two real binaries, extracts
every backtick-quoted or fenced `mev`/`bastion` invocation from the authoring surfaces, and fails
loudly on any verb or flag the binary does not actually define.

Scope, deliberately narrow: VERB checking covers every `mev`/`bastion` invocation found. FLAG
checking only covers the verbs listed in FLAG_CHECKED_VERBS below — extending flag coverage to
every verb would mean parsing free-text --help output for dozens of subcommands, most of which
have never had a live flag bug; add a verb to FLAG_CHECKED_VERBS when one does.

Caveat this check cannot avoid: it shells the INSTALLED `mev`/`bastion` binaries, which lag
source by however long it has been since the last `cargo install`. A verb added to `mev`'s source
today and not yet installed will false-positive here as "doesn't exist" until the binary catches
up — pin this check to `toolchain-freshness` first, or reinstall, if it reports something you
know is real.

Usage:
  python3 scripts/check_cli_invocations.py            # verify (gated check; wired into harness.json)
  python3 scripts/check_cli_invocations.py --quiet    # exit code only, no per-line report
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Which repo-relative globs get scanned. Deliberately just the authoring surfaces named in the
# roadmap this gate came from -- not scripts/, which is code, not prose, and has its own review.
SCAN_GLOBS = [
    ".claude/commands/**/*.md",
    ".claude/skills/**/*.md",
    ".agents/skills/**/*.md",
]

BINARIES = ["mev", "bastion"]

# Verbs whose FLAGS are also checked, not just their existence. Extend this when a live flag bug
# is found on a verb not yet listed here -- do not try to cover every verb up front (see module
# docstring).
FLAG_CHECKED_VERBS = {
    ("mev", "validate-brain"),
    ("bastion", "validate-brain"),
}

# An invocation: `mev <verb>` / `bastion <verb>` where the binary name is the FIRST token of the
# candidate line/span -- never mid-sentence. This is deliberately strict: "mev because this..." and
# "mev is not installed" are real prose that happens to say "mev", not an invocation, and matching
# them mid-string is exactly what produced false positives during authoring (see git history on
# this file). Anchoring to line/span start is what a human reads as "this IS a command" too.
INVOCATION_RE = re.compile(
    r"^\s*(?:\$\s*)?(mev|bastion)\s+([a-z][a-z0-9-]*)((?:\s+[^\n`|]*)?)", re.M
)
FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")

# Lines that only ever mention the binary name in prose, never as an invocation -- excluded by
# anchoring INVOCATION_RE to line/span start (see extract_spans, which yields line-level candidates
# for fenced blocks and whole-span candidates for inline backticks).


def get_verbs(binary: str) -> set[str] | None:
    """Real subcommand names from `<binary> --help`'s Commands: section. None if not installed."""
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
    """Real long-flag names from `<binary> <verb> --help`. None if the call fails."""
    try:
        out = subprocess.run([binary, verb, "--help"], capture_output=True, text=True, timeout=15).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return set(FLAG_RE.findall(out))


def extract_spans(text: str) -> list[str]:
    """Every inline-backtick span and every fenced-code-block body in a markdown file."""
    spans = []
    spans.extend(re.findall(r"`([^`\n]+)`", text))
    for block in re.findall(r"```(?:[a-z]*)\n(.*?)```", text, re.S):
        spans.append(block)
    return spans


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in SCAN_GLOBS:
        files.extend(sorted(root.glob(pattern)))
    return files


def check(root: Path, quiet: bool) -> int:
    verbs = {b: get_verbs(b) for b in BINARIES}
    unavailable = [b for b, v in verbs.items() if v is None]
    if unavailable:
        print(f"SKIPPED — binary not on PATH: {', '.join(unavailable)} (degrade open, not a check failure)")
        return 0

    flag_cache: dict[tuple[str, str], set[str] | None] = {}
    findings: list[tuple[Path, str, str, str]] = []  # (file, binary, verb, detail)

    for path in collect_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for span in extract_spans(text):
            for m in INVOCATION_RE.finditer(span):
                binary, verb, rest = m.group(1), m.group(2), m.group(3)
                if verb not in verbs[binary]:
                    findings.append((path, binary, verb, f"no such verb '{verb}'"))
                    continue
                if (binary, verb) in FLAG_CHECKED_VERBS:
                    key = (binary, verb)
                    if key not in flag_cache:
                        flag_cache[key] = get_flags(binary, verb)
                    real_flags = flag_cache[key]
                    if real_flags is None:
                        continue
                    for flag in FLAG_RE.findall(rest):
                        if flag not in real_flags and flag != "--help":
                            findings.append((path, binary, verb, f"'{verb}' has no flag '{flag}'"))

    if findings:
        print(f"CLI-invocation gate FAILED — {len(findings)} invocation(s) name a verb or flag the installed binary does not define:")
        for path, binary, verb, detail in findings:
            rel = path.relative_to(root)
            print(f"  - {rel}: {detail}")
        print()
        print("This shells the INSTALLED mev/bastion. If you believe the verb/flag is real and")
        print("just not installed yet, reinstall (cargo install --path core/mev or core/bastion)")
        print("and re-run before treating this as a doc bug.")
        return 1

    if not quiet:
        print(f"OK — no bad verb/flag invocations found across {sum(1 for _ in collect_files(root))} file(s).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quiet", action="store_true", help="Exit code only, no OK line.")
    args = parser.parse_args()
    sys.exit(check(ROOT, args.quiet))


if __name__ == "__main__":
    main()
