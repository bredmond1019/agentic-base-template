#!/usr/bin/env python3
"""Assert the depth-agnostic session commands have not re-forked.

BT.chore.session-commands-are-one-source. `handoff`, `wrap-up`, `log-work` and `begin-session`
resolve everything from `brain.toml` at runtime, so ONE copy is correct everywhere. They must stay
byte-identical across:

  1. base-template/.claude/commands/       - the source, and what the 18 leaf repos + the global
                                             install receive
  2. base-template/.claude/commands/brain/ - the rsync source for the five tier sub-brains
  3. the brain root's .claude/commands/    - HQ, which receives them via
                                             ENGINES_ONLY_COMMAND_ALLOWLIST despite D54
  4. each tier's .claude/commands/         - business, client, core, portfolio, side

WHY THIS GATES. Measured 2026-09-04: each of these existed in three forks. Every fork was missing
the entire carryover[]/state-routing vocabulary - wrap-up's lacked carryover, defect, deferred,
drift, env, kind, state.json, tracks, depends_on, operator-, slug, exit, start, edit-state-json,
focus and /next. These four commands are exactly where a carryover entry or an operator edge gets
filed, and HQ owns every planning/ directory in the fleet, so the repo with the most state to route
had the commands that never learned the rules. HQ's handoff additionally still delegated
(Invoke /log-work -> Invoke /commit), making the /close-out chain four levels deep - the reported
"it stops before the log entry and says it still remains" bug.

None of that was visible: a fork is only discoverable by diffing files nobody diffs.

TIER DISCOVERY IS A KNOWN HOLE, deliberately handled here. sync_all_skills_commands.py finds tiers
by scanning brain.toml for `tier = "..."` values, so a tier whose last repo is deleted becomes
invisible to the syncer while its command directory stays on disk and stays live. That is exactly
what happened to `portfolio` when rag-engine-rs was removed. This check therefore discovers tiers
from the FILESYSTEM (any sibling dir with .claude/commands/), not from brain.toml - otherwise it
would go quiet on precisely the tier that had stopped being synced.

Exit 0 - all copies agree.  Exit 1 - a fork exists; the output names the file and the fix.

Usage: python3 scripts/check_session_commands.py [--quiet]
"""

import subprocess
import sys
from pathlib import Path

SESSION_COMMANDS = ["handoff.md", "wrap-up.md", "log-work.md", "begin-session.md"]

# Not every surface carries every command: begin-session is not a tier command. A missing file is
# reported, never silently treated as agreement - "absent" and "identical" are different answers.
TIER_EXEMPT = {"begin-session.md"}


def brain_root(start: Path):
    p = start.resolve()
    while p != p.parent:
        if (p / "brain.toml").is_file():
            return p
        p = p.parent
    return None


def main():
    quiet = "--quiet" in sys.argv
    bt = Path(__file__).resolve().parent.parent
    root = brain_root(bt)
    src_dir = bt / ".claude" / "commands"

    if root is None:
        print("session-commands: no brain.toml above base-template — nothing to compare")
        return 0

    # Filesystem discovery, deliberately not brain.toml — see the module docstring. This picks up
    # tier sub-brains AND root-level leaf repos (learn-ai), which is correct: a leaf repo receives
    # these four through sync_downstream_harness and must match too.
    surfaces = [("brain root", root)]
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / ".claude" / "commands").is_dir() and child != bt:
            if (child / "brain.toml").is_file():
                continue
            surfaces.append((child.name, child))

    problems = []
    for name in SESSION_COMMANDS:
        src = src_dir / name
        if not src.is_file():
            problems.append(f"{src}: source command is missing")
            continue
        want = src.read_bytes()

        tier_src = src_dir / "brain" / name
        if name not in TIER_EXEMPT:
            if not tier_src.is_file():
                problems.append(
                    f"{tier_src}: missing — this is the rsync source for the five tiers, so the "
                    f"tiers would keep whatever they already have"
                )
            elif tier_src.read_bytes() != want:
                problems.append(f"{tier_src}: differs from {src}")

        for label, base in surfaces:
            f = base / ".claude" / "commands" / name
            if not f.is_file():
                if label != "brain root" and name in TIER_EXEMPT:
                    continue
                if label == "brain root":
                    problems.append(f"{f}: missing from the {label}")
                continue
            if f.read_bytes() != want:
                problems.append(f"{f}: differs from {src} ({label})")

    if not problems:
        if not quiet:
            print(
                f"session-commands: OK — {len(SESSION_COMMANDS)} command(s) identical across "
                f"{len(surfaces) + 1} surface(s)"
            )
        return 0

    print("session-commands: FAILED — a session command has re-forked")
    for p in problems:
        print(f"  {p}")
    print(
        "\n  These four are depth-agnostic by construction (log-work.md's own header says so), so\n"
        "  one copy is correct everywhere. Fix by re-syncing, not by editing a copy:\n"
        "    python3 base-template/scripts/sync_downstream_harness.py --apply\n"
        "    cp base-template/.claude/commands/<name>.md base-template/.claude/commands/brain/\n"
        "    python3 base-template/scripts/sync_all_skills_commands.py\n"
        "  If a surface genuinely needs different behaviour, the command is not depth-agnostic and\n"
        "  does not belong in ENGINES_ONLY_COMMAND_ALLOWLIST — fix the command instead."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
