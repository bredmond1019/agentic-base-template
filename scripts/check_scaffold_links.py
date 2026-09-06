#!/usr/bin/env python3
"""check_scaffold_links.py — lint relative markdown links inside base-template/scaffold/.

WHY THIS EXISTS. `bastion validate-brain --links` walks the CORPUS, and
`base-template/scaffold/` is not in it — so scaffold templates are never link-checked at
their source. Their links are first evaluated only after `/new-project` copies them into a
new repo, at which point a bad one is already shipped and `--links` is red FLEET-WIDE,
blocking every repo's push rather than just the new repo's.

TWO FAILURE MODES, and the second is the one that fooled a prior fix attempt.

1. DEPTH. `scaffold/planning/X.md` is three levels deep; it lands two levels deep at
   `<repo>/planning/X.md`. Every `../../` written for the source position overshoots by
   one after the copy.

2. TARGET DOES NOT TRAVEL. Fixing the depth is NOT sufficient and is the trap: the four
   links that shipped in `harness.examples.md` pointed at
   `base-template/docs/rust-sdlc-iteration-speed.md` and
   `base-template/planning/decisions/D55-...`. Neither file is shipped by the scaffold, so
   NO relative depth resolves — `../` is as dead as `../../`. A cross-repo relative link
   also climbs above the new repo's root, which mev's surface-leak rule 1 reports
   separately.

THE RULE. A relative markdown link in the scaffold may only target a path the scaffold
itself ships. Anything else is referenced by NAME in plain text, saying where it lives.
Plain text also keeps the sandbox builder simple: `rewrite_decision_links` and
`prune_dead_links` in scripts/sandbox/build-v2.sh both act on links, and a reference that
is not a link needs neither.

Exit 0 clean, 1 on any violation. Dependency-free.
"""
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SCAFFOLD = Path(__file__).resolve().parent.parent / "scaffold"


# Intentionally NOT a "does this file exist in the scaffold" check. An in-tree link to a
# file the scaffold does not ship is usually legitimate — `planning/handoff.md` is created
# later by /handoff, and directory links like `decisions/` resolve once the repo is live.
# Those are caught by `validate-brain --links` after the copy anyway. What --links can
# NEVER see, because the scaffold is not in the corpus, is a link that ESCAPES the scaffold
# root — and that is exactly the class that ships broken into every new repo.


def main() -> int:
    if not SCAFFOLD.is_dir():
        print(f"ERROR: scaffold not found at {SCAFFOLD}", file=sys.stderr)
        return 1

    violations = []

    for md in sorted(SCAFFOLD.rglob("*.md")):
        rel = md.relative_to(SCAFFOLD)
        for target in LINK_RE.findall(md.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if target.startswith("file://"):
                violations.append((rel, target, "absolute file:// URI never survives a copy"))
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            resolved = (rel.parent / clean).as_posix()
            # normalise ".." without touching the filesystem
            parts: list[str] = []
            escaped = False
            for seg in resolved.split("/"):
                if seg in ("", "."):
                    continue
                if seg == "..":
                    if parts:
                        parts.pop()
                    else:
                        escaped = True
                else:
                    parts.append(seg)
            if escaped:
                violations.append(
                    (rel, target, "climbs above the scaffold root — the target cannot travel with the copy")
                )

    if violations:
        print(f"FAIL: {len(violations)} scaffold link violation(s).\n")
        for rel, target, why in violations:
            print(f"  scaffold/{rel}\n    link:   {target}\n    reason: {why}")
        print(
            "\nFix by referencing the target BY NAME in plain text, saying where it lives\n"
            "(e.g. `base-template/docs/foo.md` (in the brain, not this repo)) — not by\n"
            "adjusting the relative depth. See this script's docstring, failure mode 2."
        )
        return 1

    md_count = len(list(SCAFFOLD.rglob("*.md")))
    print(f"PASS: {md_count} scaffold markdown file(s), no relative link escapes the scaffold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
