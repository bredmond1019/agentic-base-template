#!/usr/bin/env python3
"""Report drift between base-template/.claude/skills/ and the ~/.claude/skills/ install.

REGISTERED NON-GATING, AND THAT IS DELIBERATE — do not "fix" it into a gate.
A global install is per-machine. A CI checkout has none and a fresh clone has none, so a
gating version would fail instantly for everyone who has not run a sync, on a machine state
that has nothing to do with the change under review. `toolchain-freshness` is non-gating for
exactly the same reason. What this buys instead is a visible signal in the same place the
other freshness answers live.

Context (BT.chore.skills-go-global, 2026-09-03): the 17 fleet-mechanism skills used to be
copied into all 19 repos — 323 byte-identical files with zero divergence. They now install
once into ~/.claude/skills/. That removed 19 staleness surfaces and created one, and this
check watches the one. It is the payment for moving .claude/skills off
sync_downstream_harness.py, the only propagation path in the fleet with a real integrity
model (sha256 manifest + conflict detection).

Exit 0 — in sync, or no global install present (nothing to be stale).
Exit 1 — the install differs from source. Never blocks a commit; read the output.

Usage: python3 scripts/check_global_skills_fresh.py [--quiet]
"""

import filecmp
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / ".claude" / "skills"
GLOBAL = Path.home() / ".claude" / "skills"


def dir_state(root):
    """Map slug -> set of (relative path, size) for every file under that slug."""
    out = {}
    if not root.is_dir():
        return out
    for slug_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        files = {
            str(f.relative_to(slug_dir)) for f in slug_dir.rglob("*") if f.is_file()
        }
        out[slug_dir.name] = files
    return out


def main():
    quiet = "--quiet" in sys.argv

    if not SOURCE.is_dir():
        print(f"global-skills-fresh: no source at {SOURCE}; nothing to compare.")
        return 0

    if not GLOBAL.is_dir():
        # Not a failure: a machine that has never run the sync, or a CI checkout.
        print(
            f"global-skills-fresh: no global install at {GLOBAL} — skills will resolve "
            f"per-repo only. Run /sync-global-skills to install."
        )
        return 0

    src, glb = dir_state(SOURCE), dir_state(GLOBAL)
    missing = sorted(set(src) - set(glb))
    extra = sorted(set(glb) - set(src))
    differing = []

    for slug in sorted(set(src) & set(glb)):
        s_dir, g_dir = SOURCE / slug, GLOBAL / slug
        if src[slug] != glb[slug]:
            differing.append(slug)
            continue
        match, mismatch, errors = filecmp.cmpfiles(
            s_dir, g_dir, sorted(src[slug]), shallow=False
        )
        if mismatch or errors:
            differing.append(slug)

    if not (missing or extra or differing):
        if not quiet:
            print(f"global-skills-fresh: OK — {len(src)} skill(s) in sync with {GLOBAL}")
        return 0

    print("global-skills-fresh: DRIFT (non-gating — this does not block your commit)")
    for slug in missing:
        print(f"  missing from global install : {slug}")
    for slug in extra:
        print(f"  present only in global      : {slug}")
    for slug in differing:
        print(f"  content differs             : {slug}")
    print(f"\n  Source : {SOURCE}\n  Install: {GLOBAL}")
    print("  Fix: re-run /sync-global-skills")
    return 1


if __name__ == "__main__":
    sys.exit(main())
