#!/usr/bin/env python3
"""Mechanical drift tripwire between the SDLC engines and their docs/workflows/*.md prose guides.

Why this exists: docs/workflows/sdlc-task.md and docs/workflows/sdlc-flow.md are hand-written
explanatory prose for the two SDLC engines — usage, the pipeline diagram, model tiering,
run-state contracts. They do not auto-sync from .claude/workflows/sdlc-task.js /
sdlc-flow.js. On 2026-08-22 an audit (BT.ticket.engine-docs-drift-tripwire task 4) found
docs/workflows/sdlc-task.md missing the `--test-depth` flag entirely, and the sibling surface
(.agents/skills/*/SKILL.md, guarded by scripts/check_skill_sync.py) had already measured ~20
behavioural discrepancies per guide accumulating silently across engine changes before that
tripwire existed.

This script CANNOT verify SEMANTIC correctness of a doc page against the engine — that requires
an agent to actually read and compare them (see base-template/CLAUDE.md, "update loop" step 6,
and the adversarial-verify pattern used for the SKILL.md rewrite). What it CAN do cheaply and
deterministically is notice that a load-bearing region of an engine changed without anyone
telling it the matching docs page was re-checked, and fail loudly rather than silently drifting
again. A hash cannot tell whether prose is true, only that the thing it describes moved — this is
a tripwire, not a diff tool and not a correctness proof.

Mechanism: a fixed set of line ranges in each engine (ANCHORS below) covers the five
behaviour-defining surfaces named in the block's acceptance criteria — flags and their defaults,
the stage list, isolation/branch naming, the triage/bail taxonomy, and the bookkeep/state-write
contract. Each anchor's content is hashed; the hash is pinned in
scripts/engine_docs_sync_manifest.json at the moment a human/agent last confirmed the matching
docs/workflows/*.md section was accurate. If an anchor's hash no longer matches the manifest,
this check fails — the fix is to re-verify (and, if needed, update) the doc section by hand, then
re-stamp the manifest.

Three of the five surfaces (isolation-and-branch-naming, triage-bail-taxonomy,
bookkeep-vault-commit) reuse the EXACT line ranges already anchored in
scripts/skill_sync_manifest.json for the same engines, so the two manifests never disagree about
where a region is. The other two (flags-and-defaults, stage-list) are new to this manifest.

Anchor line ranges are position-based (not marker-comments in the .js) deliberately, so nothing
is injected into the engines' own agent prompts — see base-template CLAUDE.md standing rule 6.

Usage:
  python3 scripts/check_engine_docs_sync.py            # verify (gated check; wired into harness.json)
  python3 scripts/check_engine_docs_sync.py --update    # re-stamp the manifest — run ONLY after you
                                                          # (or an agent) have actually re-verified the
                                                          # matching docs/workflows/*.md section against
                                                          # the new code. Never run this blind: a
                                                          # manifest stamped without re-reading the doc
                                                          # section pins drift instead of catching it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "scripts" / "engine_docs_sync_manifest.json"

# (engine file, anchor name, start line, end line [1-indexed, inclusive], matching docs page,
#  doc section the anchor maps to)
#
# isolation-and-branch-naming / triage-bail-taxonomy / bookkeep-vault-commit reuse the identical
# line ranges already stamped in scripts/skill_sync_manifest.json for the same engine + anchor
# name — do not re-derive different ranges for the same region.
ANCHORS = [
    (".claude/workflows/sdlc-task.js", "flags-and-defaults", 111, 148,
     "docs/workflows/sdlc-task.md", "## Usage"),
    (".claude/workflows/sdlc-task.js", "stage-list", 87, 96,
     "docs/workflows/sdlc-task.md", "## Pipeline"),
    (".claude/workflows/sdlc-task.js", "isolation-and-branch-naming", 811, 917,
     "docs/workflows/sdlc-task.md", "## In-place vs. `--worktree`"),
    (".claude/workflows/sdlc-task.js", "triage-bail-taxonomy", 1115, 1395,
     "docs/workflows/sdlc-task.md", "## Pipeline"),
    (".claude/workflows/sdlc-task.js", "bookkeep-vault-commit", 1633, 1752,
     "docs/workflows/sdlc-task.md", "## Vaulted `planning/` writes in the per-task loop"),
    (".claude/workflows/sdlc-flow.js", "flags-and-defaults", 238, 251,
     "docs/workflows/sdlc-flow.md", "## Usage"),
    (".claude/workflows/sdlc-flow.js", "stage-list", 62, 74,
     "docs/workflows/sdlc-flow.md", "## Pipeline"),
    (".claude/workflows/sdlc-flow.js", "isolation-and-branch-naming", 925, 1096,
     "docs/workflows/sdlc-flow.md", "## Isolation mode — branch (default) vs `--worktree`"),
    (".claude/workflows/sdlc-flow.js", "triage-bail-taxonomy", 1316, 1555,
     "docs/workflows/sdlc-flow.md", "## Pipeline"),
    (".claude/workflows/sdlc-flow.js", "bookkeep-vault-commit", 2071, 2226,
     "docs/workflows/sdlc-flow.md", "## Vaulted planning directories (D46)"),
]


def hash_lines(path: Path, start: int, end: int) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    chunk = "\n".join(lines[start - 1:end])
    return hashlib.sha256(chunk.encode("utf-8")).hexdigest()


def manifest_key(engine_file: str, anchor: str) -> str:
    return f"{engine_file}::{anchor}"


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def run(root: Path, anchors: list, update: bool) -> int:
    existing_manifest = load_manifest()
    new_manifest = {}
    mismatches = []

    for engine_file, anchor, start, end, docs_md, section in anchors:
        engine_path = root / engine_file
        if not engine_path.exists():
            print(f"ERROR: {engine_file} not found", file=sys.stderr)
            return 1

        key = manifest_key(engine_file, anchor)
        current_hash = hash_lines(engine_path, start, end)
        new_manifest[key] = {
            "hash": current_hash,
            "lines": f"{start}-{end}",
            "docs_md": docs_md,
            "section": section,
        }

        if update:
            continue

        expected = existing_manifest.get(key, {}).get("hash")
        if expected is None:
            mismatches.append((engine_file, anchor, docs_md, section,
                                "no manifest entry — run --update after first verifying the docs page"))
        elif expected != current_hash:
            mismatches.append((engine_file, anchor, docs_md, section,
                                "engine content changed since the docs page was last verified"))

    if update:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(json.dumps(new_manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Manifest updated: {MANIFEST_PATH.relative_to(root)}")
        return 0

    if mismatches:
        print("Engine/docs drift check FAILED — the following anchors changed without a re-verified doc page:\n")
        for engine_file, anchor, docs_md, section, reason in mismatches:
            print(f"  - {engine_file} [{anchor}] -> review {docs_md} {section}: {reason}")
        print("\nThis does NOT mean the docs page is wrong — it means this line range moved or changed")
        print("since the page was last checked against it. Re-read the anchor and the matching")
        print("docs/workflows/*.md section (an agent-driven adversarial comparison is the reliable way")
        print("to do this — see base-template/CLAUDE.md 'update loop' step 6), fix the page if needed,")
        print("then run:")
        print("  python3 scripts/check_engine_docs_sync.py --update")
        return 1

    print(f"OK — {len(anchors)} anchors match the manifest.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true",
                         help="Re-stamp the manifest with current hashes (only after re-verifying the "
                              "matching docs/workflows/*.md section)")
    args = parser.parse_args()
    sys.exit(run(ROOT, ANCHORS, args.update))


if __name__ == "__main__":
    main()
