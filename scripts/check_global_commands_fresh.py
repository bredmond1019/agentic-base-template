#!/usr/bin/env python3
"""Report drift between base-template/.claude/commands/ and the ~/.claude/commands/ install.

REGISTERED NON-GATING, AND THAT IS DELIBERATE — do not "fix" it into a gate.
A global install is per-machine. A CI checkout has none and a fresh clone has none, so a
gating version would fail instantly for everyone who has not run a sync, on a machine state
that has nothing to do with the change under review. `global-skills-fresh` and
`toolchain-freshness` are non-gating for exactly the same reason. What this buys instead is a
visible signal in the same place the other freshness answers live.

Context (BT.chore.consolidate-fleet-not-globally-installed, 2026-09-04): /consolidate-fleet
lived only at base-template/.claude/commands/consolidate-fleet.md for a day and had to be run
by reading the file, because nothing pinned which of the two sync paths owns an HQ-only
command, and nothing would have noticed the gap. `scripts/sync_downstream_harness.py`'s
EXCLUDED_COMMAND_FILENAMES deliberately drops a handful of HQ-only commands from every
downstream repo — an exclusion there means "globally installed only," not "unreachable" — and
`/sync-global-commands` (rsync into ~/.claude/commands/) is the sole remaining owner. This
checker watches that install for drift, the same way check_global_skills_fresh.py watches the
skills install.

DIVERGES from check_global_skills_fresh.py in one deliberate way: that script hardcodes its
SOURCE and GLOBAL paths as module constants, which is exactly why it has no test. This checker
takes --source-dir and --install-dir overrides (defaulting to <repo>/.claude/commands and
~/.claude/commands) plus --quiet, so a test suite can point it at throwaway fixture trees.

SCOPE: top-level *.md files directly under the commands dir only — no recursion into
subdirectories. `brain/` is excluded, matching /sync-global-commands' own
`rsync -av --delete --exclude='brain/'`, which is the authority for what the install is
supposed to contain.

Exit 0 — in sync, or no global install present (nothing to be stale).
Exit 1 — the install differs from source (missing / extra / content differs).

Usage: python3 scripts/check_global_commands_fresh.py [--source-dir DIR] [--install-dir DIR] [--quiet]

OBSERVED RED (2026-09-04) — this checker was run against the real machine state before being
registered, per BT.ticket.gates-must-be-observed-red:

    $ python3 scripts/check_global_commands_fresh.py
    global-commands-fresh: DRIFT (non-gating - this does not block your commit)
      content differs             : commander-retro.md

      Source : /Users/brandon/Dev/agentic-portfolio/base-template/.claude/commands
      Install: /Users/brandon/.claude/commands
      Fix: re-run /sync-global-commands
    (exit 1)

commander-retro.md was edited by commit faf43e3 and never re-synced, so the checker correctly
named it as drifting on its first real run.
"""

import argparse
import filecmp
import sys
from pathlib import Path

DEFAULT_SOURCE = Path(__file__).resolve().parent.parent / ".claude" / "commands"
DEFAULT_INSTALL = Path.home() / ".claude" / "commands"


def dir_state(root):
    """Map filename -> size for every top-level *.md file directly under root, excluding brain/."""
    out = {}
    if not root.is_dir():
        return out
    for f in sorted(root.glob("*.md")):
        if f.is_file():
            out[f.name] = f.stat().st_size
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Report drift between base-template's .claude/commands/ and ~/.claude/commands/."
    )
    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE),
        help="Path to the source commands dir (default: <repo>/.claude/commands)",
    )
    parser.add_argument(
        "--install-dir",
        default=str(DEFAULT_INSTALL),
        help="Path to the global install dir (default: ~/.claude/commands)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the in-sync success message; drift is always printed",
    )
    args = parser.parse_args(argv)

    source = Path(args.source_dir)
    install = Path(args.install_dir)
    quiet = args.quiet

    if not source.is_dir():
        print(f"global-commands-fresh: no source at {source}; nothing to compare.")
        return 0

    if not install.is_dir():
        # Not a failure: a machine that has never run the sync, or a CI checkout.
        print(
            f"global-commands-fresh: no global install at {install} — commands will resolve "
            f"per-repo only. Run /sync-global-commands to install."
        )
        return 0

    src, ins = dir_state(source), dir_state(install)
    missing = sorted(set(src) - set(ins))
    extra = sorted(set(ins) - set(src))
    differing = []

    common = sorted(set(src) & set(ins))
    if common:
        match, mismatch, errors = filecmp.cmpfiles(source, install, common, shallow=False)
        differing = sorted(mismatch + errors)

    if not (missing or extra or differing):
        if not quiet:
            print(f"global-commands-fresh: OK — {len(src)} command(s) in sync with {install}")
        return 0

    print("global-commands-fresh: DRIFT (non-gating - this does not block your commit)")
    for name in missing:
        print(f"  missing from global install : {name}")
    for name in extra:
        print(f"  present only in global      : {name}")
    for name in differing:
        print(f"  content differs             : {name}")
    print(f"\n  Source : {source}\n  Install: {install}")
    print("  Fix: re-run /sync-global-commands")
    return 1


if __name__ == "__main__":
    sys.exit(main())
