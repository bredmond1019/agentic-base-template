#!/usr/bin/env python3
"""Mechanical drift tripwire between the SDLC engines and their Gemini-facing SKILL.md guides.

Why this exists: .agents/skills/sdlc-task/SKILL.md and .agents/skills/sdlc-flow/SKILL.md are
hand-written manual-replication guides for agents (Gemini/Antigravity) that cannot invoke the
`claude` CLI or run .claude/workflows/sdlc-{task,flow}.js directly. They do not auto-sync from the
engines. A 2026-08 audit found ~20 behavioral discrepancies per guide that had accumulated silently
across engine changes — including two (D46 vault-commit routing, the sdlc-flow isolation default)
that would have corrupted real git state in a vaulted repo, not just read as stale prose.

This script cannot verify SEMANTIC correctness of a guide against the engine — that requires an
agent to actually read and compare them (see base-template/CLAUDE.md, "update loop" step 6, and
the adversarial-verify pattern used for the 2026-08 rewrite). What it CAN do cheaply and
deterministically is notice that a load-bearing region of an engine changed without anyone telling
it the matching guide was re-checked, and fail loudly rather than silently drifting again.

Mechanism: a fixed set of line ranges in each engine (ANCHORS below) covers the highest-risk
translated-into-prose sections — isolation-mode defaults + branch naming, the triage/bail
taxonomy, and the D46 vault-aware commit routing. Each anchor's content is hashed; the hash is
pinned in scripts/skill_sync_manifest.json at the moment a human/agent last confirmed the matching
SKILL.md section was accurate. If an anchor's hash no longer matches the manifest, this check
fails — the fix is to re-verify (and, if needed, update) the SKILL.md section by hand, then
re-stamp the manifest.

This is a tripwire, not a diff tool: it flags "this changed, go look," not "here is what's wrong."
Anchor line ranges are position-based (not marker-comments in the .js) deliberately, so nothing is
injected into the engines' own agent prompts.

Usage:
  python3 scripts/check_skill_sync.py            # verify (gated check; wired into harness.json)
  python3 scripts/check_skill_sync.py --update    # re-stamp the manifest — run ONLY after you (or
                                                    # an agent) have actually re-verified the
                                                    # matching SKILL.md section against the new code
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "scripts" / "skill_sync_manifest.json"

# (engine file, anchor name, start line, end line [1-indexed, inclusive], matching SKILL.md)
# Ranges were hand-picked from the current engines to bracket exactly the load-bearing section
# named by `anchor` — see the file for the surrounding phase/comment markers if a range needs
# re-picking after a refactor moves code around.
ANCHORS = [
    (".claude/workflows/sdlc-task.js", "isolation-and-branch-naming", 771, 877,
     ".agents/skills/sdlc-task/SKILL.md"),
    (".claude/workflows/sdlc-task.js", "triage-bail-taxonomy", 1017, 1238,
     ".agents/skills/sdlc-task/SKILL.md"),
    (".claude/workflows/sdlc-task.js", "bookkeep-vault-commit", 1476, 1595,
     ".agents/skills/sdlc-task/SKILL.md"),
    (".claude/workflows/sdlc-flow.js", "isolation-and-branch-naming", 889, 1056,
     ".agents/skills/sdlc-flow/SKILL.md"),
    (".claude/workflows/sdlc-flow.js", "triage-bail-taxonomy", 1216, 1454,
     ".agents/skills/sdlc-flow/SKILL.md"),
    (".claude/workflows/sdlc-flow.js", "bookkeep-vault-commit", 1965, 2119,
     ".agents/skills/sdlc-flow/SKILL.md"),
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
    manifest = load_manifest() if not update else {}
    existing_manifest = load_manifest()
    new_manifest = {}
    mismatches = []

    for engine_file, anchor, start, end, skill_file in anchors:
        engine_path = root / engine_file
        if not engine_path.exists():
            print(f"ERROR: {engine_file} not found", file=sys.stderr)
            return 1

        key = manifest_key(engine_file, anchor)
        current_hash = hash_lines(engine_path, start, end)
        new_manifest[key] = {"hash": current_hash, "lines": f"{start}-{end}", "skill_md": skill_file}

        if update:
            continue

        expected = existing_manifest.get(key, {}).get("hash")
        if expected is None:
            mismatches.append((engine_file, anchor, skill_file,
                                "no manifest entry — run --update after first verifying SKILL.md"))
        elif expected != current_hash:
            mismatches.append((engine_file, anchor, skill_file,
                                "engine content changed since SKILL.md was last verified"))

    if update:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(json.dumps(new_manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Manifest updated: {MANIFEST_PATH.relative_to(root)}")
        return 0

    if mismatches:
        print("SKILL.md drift check FAILED — the following anchors changed without a re-verified guide:\n")
        for engine_file, anchor, skill_file, reason in mismatches:
            print(f"  - {engine_file} [{anchor}] -> review {skill_file}: {reason}")
        print("\nThis does NOT mean SKILL.md is wrong — it means this line range moved or changed")
        print("since the guide was last checked against it. Re-read the anchor and the matching")
        print("SKILL.md section (an agent-driven adversarial comparison is the reliable way to do")
        print("this — see base-template/CLAUDE.md 'update loop' step 6), fix the guide if needed,")
        print("then run:")
        print("  python3 scripts/check_skill_sync.py --update")
        return 1

    print(f"OK — {len(anchors)} anchors match the manifest.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true",
                         help="Re-stamp the manifest with current hashes (only after re-verifying SKILL.md)")
    args = parser.parse_args()
    sys.exit(run(ROOT, ANCHORS, args.update))


if __name__ == "__main__":
    main()
