#!/usr/bin/env python3
"""Gate the AGENTS.md / CLAUDE.md / GEMINI.md split (BT.chore.agents-md-is-canonical).

THIS ONE CAN GATE, unlike the global-install checks, because every file it reads is present in
every clone and every CI checkout. That is the whole reason the per-repo surface was worth
restructuring: it is the half that can actually be enforced.

What it checks, and why each earns its place:

1. CLAUDE.md exists and imports AGENTS.md, and that AGENTS.md EXISTS.
   Measured 2026-09-03: a `@AGENTS.md` import pointing at a missing file produces NO error and
   NO warning - CLAUDE.md loads fine and the session is simply missing every shared convention.
   A test asked a session to list sentinels from both files; with AGENTS.md absent it reported
   only CLAUDE.md's and behaved completely normally. That silent failure is invisible at
   runtime, so this check is the only thing that would ever tell you.

2. AGENTS.md carries no tool-specific nouns.
   The whole point of the split is that AGENTS.md is surface-neutral. A `.claude/skills/` path
   creeping in makes it wrong for the other reader, silently.

3. GEMINI.md's shared region matches AGENTS.md byte-for-byte.
   GEMINI.md is generated. A hand edit there is lost on the next sync, and worse, it reads as
   authoritative until then. This is the drift that produced four forks of session-continuity
   and two of response-style before the restructure.

4. AGENT.md (singular) does not come back. It had no reader in this fleet and its own
   self-description was false; see the chore.

Exit 0 - all good.  Exit 1 - a problem, printed with the file and the fix.

Usage: python3 scripts/check_agent_docs.py [--repo <path>] [--quiet]
"""

import argparse
import re
import sys
from pathlib import Path

IMPORT_RE = re.compile(r'^@AGENTS\.md\s*$', re.M)
GENERATED_MARKER = "GENERATED FILE — do not edit by hand."
TOOL_SPECIFIC = [
    (".claude/skills", "a Claude-specific path"),
    (".agents/skills", "an Antigravity-specific path"),
    ("~/.claude/", "a Claude-specific path"),
    ("~/.gemini/", "an Antigravity-specific path"),
]
# Lines that legitimately name both surfaces while explaining the split itself.
NEUTRAL_CONTEXT = ("the Fleet & Core Skills table for", "| `CLAUDE.md` |", "| `GEMINI.md` |")

# Deliberate exceptions: a tool-specific PATH used as a FACT ABOUT THE SYSTEM that both readers
# need, rather than an instruction addressed to one reader. Enumerated explicitly, each with a
# reason, rather than loosening the rule — the same pattern as UNDISTRIBUTED_AGENT_SKILL_DIRS in
# test_sync_downstream_harness.py. Adding an entry should feel like a decision, not a shrug.
#
# The test to apply when you are tempted to add one: would the OTHER reader be misled by this
# line, or merely uninterested in it? Misled -> move it to the tool's own file. Uninterested ->
# it can stay, because it is describing the machine, not telling that agent what to do.
ALLOWED_SURFACE_MENTIONS = {
    ".agents/skills/sdlc-task/SKILL.md":
        "the update loop's step 6 tells whoever edits an engine to review the replication "
        "guides; both readers must know they exist and do not auto-sync",
    "~/.claude/projects/":
        "standing rule 10's engine-snapshot path. It is Claude Code's Workflow harness, but "
        "the rule is quoted with exact md5 commands and is load-bearing for anyone debugging "
        "a stale engine — splitting it would leave half a rule in each file",
}


def shared_region(text):
    """GEMINI.md's generated half: everything before its own Fleet & Core Skills tail."""
    i = text.find("## Fleet & Core Skills")
    return text if i == -1 else text[:i]


def check(repo, quiet=False):
    problems = []
    agents, claude, gemini = repo / "AGENTS.md", repo / "CLAUDE.md", repo / "GEMINI.md"

    if not claude.is_file():
        return [f"{repo}: no CLAUDE.md"]

    ctext = claude.read_text(encoding="utf-8")

    # 1 — the import, and its target
    if not IMPORT_RE.search(ctext):
        problems.append(
            f"{claude}: no '@AGENTS.md' import line. Claude Code does NOT read AGENTS.md on "
            f"its own (measured) — without this line the shared conventions never load."
        )
    elif not agents.is_file():
        problems.append(
            f"{claude}: imports @AGENTS.md but {agents} does not exist. This fails SILENTLY at "
            f"runtime — no error, no warning, just a session missing every shared convention."
        )

    if agents.is_file():
        atext = agents.read_text(encoding="utf-8")

        # 2 — surface neutrality
        for lineno, line in enumerate(atext.splitlines(), 1):
            if any(n in line for n in NEUTRAL_CONTEXT):
                continue
            if any(a in line for a in ALLOWED_SURFACE_MENTIONS):
                continue
            for token, what in TOOL_SPECIFIC:
                if token in line:
                    problems.append(
                        f"{agents}:{lineno}: contains '{token}' ({what}). AGENTS.md must stay "
                        f"surface-neutral — move this to CLAUDE.md or GEMINI.md."
                    )

        # 3 — the generated half really is a copy
        if gemini.is_file():
            gtext = gemini.read_text(encoding="utf-8")
            if GENERATED_MARKER not in gtext:
                problems.append(
                    f"{gemini}: missing the generated-file banner. It is generated from "
                    f"AGENTS.md; without the banner someone will hand-edit it."
                )
            g_shared = shared_region(gtext)
            a_shared = shared_region(atext)
            g_norm = g_shared.replace("# GEMINI.md", "# AGENTS.md", 1)
            g_norm = re.sub(r"\n> \*\*GENERATED FILE.*?\n\n", "\n", g_norm, flags=re.S)
            if g_norm.strip() != a_shared.strip():
                problems.append(
                    f"{gemini}: its shared region has drifted from AGENTS.md. GEMINI.md is "
                    f"GENERATED — regenerate it rather than editing it, and put the change in "
                    f"AGENTS.md."
                )

    # 4 — the retired file
    if (repo / "AGENT.md").is_file():
        problems.append(
            f"{repo / 'AGENT.md'}: AGENT.md (singular) was retired — it had no reader in this "
            f"fleet. The cross-vendor convention is the plural AGENTS.md. Delete it."
        )

    if not problems and not quiet:
        print(f"agent-docs: OK — {repo}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=None, help="repo root (default: this script's repo)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parent.parent
    problems = check(repo, args.quiet)
    if problems:
        print("agent-docs: FAILED")
        for p in problems:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
