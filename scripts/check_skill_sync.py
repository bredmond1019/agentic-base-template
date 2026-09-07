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
#
# DUPLICATION, deliberate: the `start, end` in each tuple below and the `"lines": "<start>-<end>"`
# string stored per key in scripts/skill_sync_manifest.json are the SAME line range. **These tuples
# are authoritative**; the manifest field is derived from them and rewritten on every run (see the
# `new_manifest[key] = {... "lines": f"{start}-{end}" ...}` assignment further down). It is stored
# only as a human-readable breadcrumb for whoever reads the manifest — nothing reads it back, and
# the drift check compares hashes, never the `lines` string. So edit a range HERE and re-run with
# `--update`; hand-editing `lines` in the manifest changes nothing and will be silently overwritten.
ANCHORS = [
    # BT.ticket.emoji-gate-fallback-must-attribute-a-range-it-did-not-author, task 2: the
    # <<shared:renderEmojiGate>> fallback rewrite inserted 35 net lines into shared.js, which is
    # inlined into both engines at that exact position -- every anchor whose range sat AFTER the
    # inline point shifted by the same +35 lines in the affected file, with no other content
    # change (confirmed against the diff: one contiguous insertion hunk per file, nothing else
    # touched). Ranges below are re-picked from CONTENT at their new positions, not blindly
    # renumbered.
    # BT.ticket.harness-config-must-bail-not-warn-on-a-malformed-payload, tasks 1-2: same
    # cause as the bookkeep-vault-commit note below -- the +52/+62 net line insertions sat
    # above this anchor too, so it shifted even though the EXPECT needle (at the very start
    # of the range) still happened to land inside the old fixed window. Re-picked from
    # CONTENT at the new positions (confirmed byte-identical via diff), not blindly renumbered.
    (".claude/workflows/sdlc-task.js", "isolation-and-branch-naming", 1832, 1895,
     ".agents/skills/sdlc-task/SKILL.md"),
    # The triage prompt itself -- the five immediate-bail reasons, the "when unsure, BAIL" bias and
    # the evidence clause -- now lives ONCE in the shared library (D83) rather than twice in the
    # engines, so the anchor follows it there. Anchoring it at the engines after the extraction would
    # have left this tripwire hashing a one-line function CALL: green forever, blind to every change
    # in the text it exists to guard. Two entries because both replication guides describe the
    # taxonomy and each must be re-verified when it moves.
    (".claude/workflows/prompts/shared.js", "triage-bail-taxonomy", 630, 678,
     ".agents/skills/sdlc-task/SKILL.md"),
    (".claude/workflows/prompts/shared.js", "triage-bail-taxonomy-flow-guide", 630, 678,
     ".agents/skills/sdlc-flow/SKILL.md"),
    # BT.ticket.harness-config-must-bail-not-warn-on-a-malformed-payload, tasks 1-2: the
    # loadHarnessConfig() unwrap + bail additions inserted 52 net lines into sdlc-task.js and
    # 62 net lines into sdlc-flow.js, both entirely ABOVE this anchor -- re-picked from CONTENT
    # at the new positions (confirmed byte-identical to the pre-shift content via diff), not
    # blindly renumbered.
    # BT.ticket.sdlc-task-must-verify-its-blocks-acceptance-criteria, task 2: the criteria-
    # evidence stage (acceptance_criteria loading + the acceptanceCriteriaVerdicts() call) inserted
    # 123 net lines into sdlc-task.js, entirely ABOVE this anchor -- re-picked from CONTENT at the
    # new position (confirmed byte-identical to the pre-shift content via diff), not blindly
    # renumbered. sdlc-flow.js is untouched by this block (out of scope) and needs no re-pick.
    (".claude/workflows/sdlc-task.js", "bookkeep-vault-commit", 3228, 3255,
     ".agents/skills/sdlc-task/SKILL.md"),
    (".claude/workflows/sdlc-flow.js", "isolation-and-branch-naming", 1839, 1961,
     ".agents/skills/sdlc-flow/SKILL.md"),
    (".claude/workflows/sdlc-flow.js", "bookkeep-vault-commit", 3488, 3523,
     ".agents/skills/sdlc-flow/SKILL.md"),
]


EXPECT = {
    ("sdlc-task.js", "isolation-and-branch-naming"): 'WORKTREE MODE (--worktree)',
    ("sdlc-task.js", "bookkeep-vault-commit"): '7. Commit your edits (stage explicitly',
    ("sdlc-flow.js", "isolation-and-branch-naming"): 'const worktreeRecipe =',
    ("sdlc-flow.js", "bookkeep-vault-commit"): '5. Commit (stage explicitly',
    ("shared.js", "triage-bail-taxonomy"): 'function renderTriagePrompt(',
    ("shared.js", "triage-bail-taxonomy-flow-guide"): 'function renderTriagePrompt(',
}


def assert_anchors_still_bracket_their_subject(root: Path, anchors: list) -> list:
    """Fail loudly when an anchor's line range no longer contains the thing it is NAMED for.

    `--update` re-hashes whatever currently sits at an anchor's line numbers. If an edit ABOVE the
    anchor shifted the file, that is a DIFFERENT region -- and re-stamping blesses it, leaving a
    tripwire that watches unrelated code and reports green forever. Measured 2026-08-31: after a
    series of extractions, four of six anchors had drifted onto unrelated code
    (`isolation-and-branch-naming` was sitting on `postEmitHookRan` schema properties;
    `bookkeep-vault-commit` on `const allTasks = ...`), and each intervening `--update` had
    re-stamped the wrong window.

    EXPECT below pins one distinctive line each range must still contain, so the drift is caught
    mechanically instead of by someone thinking to look.
    """
    problems = []
    for rel, anchor, start, end, *_ in anchors:
        needle = EXPECT.get((Path(rel).name, anchor))
        if needle is None:
            # No marker declared for this anchor -- nothing to verify. Synthetic anchors in the
            # fixture suites land here. Every anchor in the real ANCHORS table is required to have
            # one, which test_every_real_anchor_declares_a_marker() asserts separately.
            continue
        chunk = "\n".join((root / rel).read_text(encoding="utf-8").splitlines()[start - 1:end])
        if needle not in chunk:
            problems.append(
                f"{rel}::{anchor}: lines {start}-{end} no longer contain {needle!r} -- "
                "the range has drifted onto unrelated code. Re-pick it from CONTENT, do not --update."
            )
    return problems

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

    drift = assert_anchors_still_bracket_their_subject(root, anchors)
    if drift:
        print('ANCHOR RANGES HAVE DRIFTED onto unrelated code:\n')
        for d in drift: print(f'  - {d}')
        print('\nRe-pick the range from CONTENT (find where the named section actually is now).')
        print('Do NOT re-stamp: --update would bless the wrong window.')
        return 1

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


def relocate_anchors(root: Path) -> int:
    """Rewrite ANCHORS' line numbers for anchors whose content moved but did not change.

    `--update` alone re-hashes whatever now sits at the OLD line numbers, so an edit ABOVE an
    anchor silently re-points it at a shifted window and reports OK -- the tripwire then measures
    the wrong region forever. That happened twice on 2026-08-19. This finds each anchor's recorded
    hash at its new offset and moves the line numbers to match, and REFUSES any anchor whose
    content genuinely changed, because that is the case a human must review rather than re-stamp.
    """
    manifest_path = root / MANIFEST_REL if "MANIFEST_REL" in globals() else root / "scripts" / "skill_sync_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    script_path = Path(__file__)
    script_src = script_path.read_text(encoding="utf-8")

    moved, unchanged, differs = [], [], []
    for rel, anchor, start, end, _skill in ANCHORS:
        key = f"{rel}::{anchor}"
        entry = manifest.get(key)
        if not entry:
            differs.append((rel, anchor, "no manifest entry"))
            continue
        lines = (root / rel).read_text(encoding="utf-8").splitlines()
        span = end - start + 1
        if hash_lines(root / rel, start, end) == entry["hash"]:
            unchanged.append((rel, anchor))
            continue
        new_start = None
        for i in range(0, max(0, len(lines) - span + 1)):
            chunk = "\n".join(lines[i:i + span])
            if hashlib.sha256(chunk.encode("utf-8")).hexdigest() == entry["hash"]:
                new_start = i + 1
                break
        if new_start is None:
            differs.append((rel, anchor, "content changed -- review the guide, do not relocate"))
            continue
        old_tuple = f'("{rel}", "{anchor}", {start}, {end},'
        new_tuple = f'("{rel}", "{anchor}", {new_start}, {new_start + span - 1},'
        if old_tuple not in script_src:
            differs.append((rel, anchor, "could not locate its ANCHORS tuple to rewrite"))
            continue
        script_src = script_src.replace(old_tuple, new_tuple)
        moved.append((rel, anchor, f"{start}-{end}", f"{new_start}-{new_start + span - 1}"))

    if differs:
        print("REFUSING to relocate -- these anchors need a human:")
        for rel, anchor, why in differs:
            print(f"  - {rel}::{anchor}: {why}")
        return 1

    if moved:
        script_path.write_text(script_src, encoding="utf-8")
        print(f"Relocated {len(moved)} anchor(s), content byte-identical in every case:")
        for rel, anchor, was, now in moved:
            print(f"  - {rel}::{anchor}: {was} -> {now}")
    if unchanged:
        print(f"{len(unchanged)} anchor(s) already correct.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true",
                         help="Re-stamp the manifest with current hashes (only after re-verifying SKILL.md)")
    parser.add_argument("--relocate", action="store_true",
                         help="Rewrite this script's ANCHORS line numbers for any anchor whose "
                              "content moved unchanged, then re-stamp. Refuses when content differs.")
    args = parser.parse_args()
    if args.relocate:
        sys.exit(relocate_anchors(ROOT))
    sys.exit(run(ROOT, ANCHORS, args.update))


if __name__ == "__main__":
    main()
