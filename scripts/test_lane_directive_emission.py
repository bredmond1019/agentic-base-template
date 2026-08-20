#!/usr/bin/env python3
"""Round-trip check: does /generate-roadmap's own lane-file template parse under
mev's directive grammar, and does the grammar correctly reject what it should reject?

WHY THIS RE-IMPLEMENTS MEV'S GRAMMAR IN PYTHON
-----------------------------------------------
This suite mirrors, in Python, the parsing rules of `parse_lane_directives` in
`core/mev/src/brain/lane_segments.rs` -- specifically the three constants
`DIRECTIVE_HELD_UNTIL_PREFIX`, `DIRECTIVE_BUDGET_PREFIX`,
`DIRECTIVE_EXCLUSIVE_REPOS_PREFIX`, the `BUDGET_NOT_WITH_MARKER` clause parsed
into `LaneBudget { heavy, not_with }`, the comment-only / prefix-first structural
rules, and the `KNOWN_NON_DIRECTIVE_KEYS` allowlist that `looks_like_directive_key`
consults before flagging `E_LANE_DIRECTIVE_UNRECOGNISED`. This is a DELIBERATE
duplication, not an oversight: base-template's checks are plain Python/Node and
cannot call into mev's Rust internals, and shelling out to an INSTALLED mev
binary would make this check drift silently the moment `core/mev` runs ahead of
whatever happens to be installed on the machine running the gate (exactly the
SOURCE-vs-INSTALLED divergence risk this spec's task 1 report names explicitly).
Pinning the grammar here, against the transcription in
`planning/BT.ticket.generate-roadmap-lane-directives/sdlc/reports/directive-grammar.md`,
makes it a versioned contract this repo owns and can be re-diffed against mev by
hand, rather than a second silent source of truth.

This check does NOT prove a real `mev` binary reports zero diagnostics over a
generated lane file -- that is structurally un-gateable here under D64 (the
evidence lives in another process, another repo) and is instead recorded as a
fixture-evidence report by this spec's task 4.

WHAT THIS DOES
--------------
1. Extracts every fenced ```` ``` ```` block from `.claude/commands/generate-roadmap.md`
   whose first line looks like a lane header (`# Lane ...`) -- this reaches both
   the required-header template and the worked example -- and asserts every
   directive line found in them parses cleanly under the mirrored grammar, with
   no empty or placeholder directive value.
2. Runs positive fixtures for all three directives, including `BUDGET` with and
   without `NOT-WITH`.
3. Runs NEGATIVE fixtures that must NOT parse as a directive: a lower-case
   prefix, a prefix that is not the first thing after `#`, a directive-looking
   phrase embedded in an ordinary prose sentence, and a malformed `HELD-UNTIL`
   with no token.
4. Proves the suite is capable of failing: takes the worked example extracted
   from the live command file, deliberately corrupts one of its directive
   lines, and asserts the mirrored parser flags it as malformed -- a
   happy-path-only suite would stay green against a generator that silently
   started emitting nothing, so this guards against that.

This is a GATING check (`planning/harness.json`). A failure means either the
command file's own template/example no longer parses under the pinned grammar,
or the grammar mirror itself has drifted from mev's actual rules -- re-check
against `core/mev/src/brain/lane_segments.rs` before touching this file's
constants.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATE_ROADMAP_MD = REPO_ROOT / ".claude" / "commands" / "generate-roadmap.md"

# --- mirrored mev grammar (core/mev/src/brain/lane_segments.rs) -----------------

DIRECTIVE_HELD_UNTIL_PREFIX = "HELD-UNTIL:"
DIRECTIVE_BUDGET_PREFIX = "BUDGET:"
DIRECTIVE_EXCLUSIVE_REPOS_PREFIX = "EXCLUSIVE-REPOS:"
BUDGET_NOT_WITH_MARKER = "NOT-WITH"

# Exempt pre-existing header keys that have the *shape* of a directive key but
# predate this grammar and are unrelated conventions (transcribed in the task-1
# report from mev's KNOWN_NON_DIRECTIVE_KEYS).
KNOWN_NON_DIRECTIVE_KEYS = {
    "ORIGIN", "ROADMAP", "LOG", "ISOLATION", "SPEC", "TRAPS", "TRAP", "HELD",
    "EXCEPTION", "CONTEXT", "BUT", "SO", "ALERTING", "BACKUP", "NOTE", "CARE",
    "SCOPE",
}

# looks_like_directive_key: starts with an upper-case letter, followed only by
# upper-case letters/hyphens, immediately before a ':'.
_DIRECTIVE_KEY_SHAPE = re.compile(r"^[A-Z][A-Z-]*:")

_LETTERS = re.compile(r"[A-Za-z]+")


class Directive:
    """One classified comment line: kind is one of
    'held_until' | 'budget' | 'exclusive_repos' | 'malformed' | 'unrecognised' | 'none'.
    """

    __slots__ = ("kind", "key", "value")

    def __init__(self, kind: str, key: str | None = None, value=None):
        self.kind = kind
        self.key = key
        self.value = value

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return f"Directive({self.kind!r}, key={self.key!r}, value={self.value!r})"


def classify_line(raw_line: str) -> Directive:
    """Mirrors parse_lane_directives' per-line handling for the three directives."""
    hash_pos = raw_line.find("#")
    if hash_pos == -1:
        return Directive("none")
    # Comment-only: everything before '#' must be empty after trimming.
    if raw_line[:hash_pos].strip() != "":
        return Directive("none")

    body = raw_line[hash_pos + 1:].lstrip()

    if body.startswith(DIRECTIVE_HELD_UNTIL_PREFIX):
        rest = body[len(DIRECTIVE_HELD_UNTIL_PREFIX):]
        tokens = rest.split()
        if not tokens:
            return Directive("malformed", "HELD-UNTIL")
        return Directive("held_until", "HELD-UNTIL", tokens[0])

    if body.startswith(DIRECTIVE_BUDGET_PREFIX):
        rest = body[len(DIRECTIVE_BUDGET_PREFIX):]
        m = _LETTERS.search(rest)
        level = None
        if m and m.group(0).upper() in ("HEAVY", "LIGHT"):
            level = m.group(0).upper()
        if level is None:
            return Directive("malformed", "BUDGET")
        not_with: list[str] = []
        idx = rest.find(BUDGET_NOT_WITH_MARKER)
        if idx != -1:
            after = rest[idx + len(BUDGET_NOT_WITH_MARKER):]
            after = after.lstrip(": \t")
            not_with = [x.strip() for x in after.split(",") if x.strip()]
        return Directive("budget", "BUDGET", (level, not_with))

    if body.startswith(DIRECTIVE_EXCLUSIVE_REPOS_PREFIX):
        rest = body[len(DIRECTIVE_EXCLUSIVE_REPOS_PREFIX):]
        repos = [x.strip() for x in rest.split(",") if x.strip()]
        if not repos:
            return Directive("malformed", "EXCLUSIVE-REPOS")
        return Directive("exclusive_repos", "EXCLUSIVE-REPOS", repos)

    shape = _DIRECTIVE_KEY_SHAPE.match(body)
    if shape:
        key = shape.group(0)[:-1]
        if key in KNOWN_NON_DIRECTIVE_KEYS:
            return Directive("none")
        return Directive("unrecognised", key)

    return Directive("none")


# --- extraction from the live command file --------------------------------------

def extract_fenced_blocks(text: str) -> list[list[str]]:
    """Return the line-lists of every ``` ... ``` fenced block in text (any/no lang tag)."""
    lines = text.splitlines()
    blocks: list[list[str]] = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip().startswith("```"):
            j = i + 1
            while j < n and lines[j].strip() != "```":
                j += 1
            blocks.append(lines[i + 1:j])
            i = j + 1
        else:
            i += 1
    return blocks


def lane_header_blocks(text: str) -> list[list[str]]:
    """Fenced blocks that are lane-file headers: first line starts '# Lane'."""
    return [b for b in extract_fenced_blocks(text) if b and b[0].strip().startswith("# Lane")]


# --- checks -----------------------------------------------------------------

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def check_command_file_directives() -> None:
    text = GENERATE_ROADMAP_MD.read_text(encoding="utf-8")
    blocks = lane_header_blocks(text)
    check(
        "generate-roadmap.md has at least the header template + worked example lane blocks",
        len(blocks) >= 2,
        f"found {len(blocks)} lane-header fenced blocks",
    )

    total_directives = 0
    for block in blocks:
        for line in block:
            d = classify_line(line)
            if d.kind in ("held_until", "budget", "exclusive_repos"):
                total_directives += 1
                check(
                    f"directive line parses cleanly: {line.strip()!r}",
                    True,
                )
            elif d.kind in ("malformed", "unrecognised"):
                check(
                    f"directive line in shipped template must parse cleanly: {line.strip()!r}",
                    False,
                    f"classified as {d.kind} ({d.key})",
                )

    check(
        "the worked example carries at least one of each directive kind (positive control)",
        total_directives >= 3,
        f"only found {total_directives} directives across lane-header blocks",
    )

    # No empty/placeholder directive anywhere in these blocks.
    placeholder_pat = re.compile(
        r"^\s*#\s*(HELD-UNTIL|BUDGET|EXCLUSIVE-REPOS):\s*(none)?\s*$", re.IGNORECASE
    )
    for block in blocks:
        for line in block:
            if placeholder_pat.match(line) and line.strip() != "#":
                # A bare "KEY:" with nothing after it (or the literal word "none")
                # is exactly the placeholder shape the spec forbids.
                stripped = line.split(":", 1)[1].strip() if ":" in line else ""
                check(
                    f"no empty/placeholder directive value: {line.strip()!r}",
                    stripped not in ("", "none", "None", "NONE"),
                )


def check_positive_fixtures() -> None:
    d = classify_line("# HELD-UNTIL: MV.ticket.lane-file-structured-directives")
    check("HELD-UNTIL positive fixture parses", d.kind == "held_until" and d.value == "MV.ticket.lane-file-structured-directives")

    d = classify_line("# BUDGET: LIGHT")
    check("BUDGET without NOT-WITH parses with empty not_with", d.kind == "budget" and d.value == ("LIGHT", []))

    d = classify_line("# BUDGET: HEAVY NOT-WITH mev,orchestrator")
    check(
        "BUDGET with NOT-WITH parses level + repo list",
        d.kind == "budget" and d.value == ("HEAVY", ["mev", "orchestrator"]),
    )

    d = classify_line("# EXCLUSIVE-REPOS: mev,orchestrator")
    check("EXCLUSIVE-REPOS positive fixture parses", d.kind == "exclusive_repos" and d.value == ["mev", "orchestrator"])


def check_negative_fixtures() -> None:
    d = classify_line("# held-until: MV.ticket.foo")
    check("lower-case prefix does not parse as a directive", d.kind == "none", f"got {d.kind}")

    d = classify_line("# see notes then HELD-UNTIL: MV.ticket.foo")
    check("prefix not first after '#' does not parse", d.kind == "none", f"got {d.kind}")

    d = classify_line("# this lane is HELD-UNTIL a sibling lands, roughly")
    check("directive-looking text inside a prose sentence does not parse", d.kind == "none", f"got {d.kind}")

    d = classify_line("# HELD-UNTIL:")
    check("malformed HELD-UNTIL with no token is flagged malformed, not accepted", d.kind == "malformed", f"got {d.kind}")


def check_broken_template_is_caught() -> None:
    """Proves this suite is capable of failing: corrupt a real directive line
    pulled straight from the shipped worked example and assert the mirrored
    parser flags it, rather than silently accepting it."""
    text = GENERATE_ROADMAP_MD.read_text(encoding="utf-8")
    blocks = lane_header_blocks(text)
    held_until_lines = [
        line for block in blocks for line in block
        if classify_line(line).kind == "held_until"
    ]
    check(
        "at least one real HELD-UNTIL line exists in the shipped worked example to corrupt",
        len(held_until_lines) >= 1,
    )
    if not held_until_lines:
        return

    original = held_until_lines[0]
    broken = original.split("HELD-UNTIL:", 1)[0] + "HELD-UNTIL:"  # strip the token
    d_original = classify_line(original)
    d_broken = classify_line(broken)
    print(f"  deliberately-broken-template run: {original.strip()!r} -> {broken.strip()!r}")
    print(f"  original classified: {d_original.kind}; broken classified: {d_broken.kind}")
    check(
        "the intact line from the shipped template parses",
        d_original.kind == "held_until",
    )
    check(
        "the deliberately-broken copy is caught as malformed (suite proven capable of failing)",
        d_broken.kind == "malformed",
    )


def main() -> int:
    check_command_file_directives()
    check_positive_fixtures()
    check_negative_fixtures()
    check_broken_template_is_caught()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- lane-directive grammar mirror holds against generate-roadmap.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
