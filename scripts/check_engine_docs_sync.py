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
    # RE-PICKED FROM CONTENT 2026-09-08 (BT.ticket.engines-forbid-attribution-trailers, lane
    # base-template-75): PURE SHIFT of +4 on every anchor that moved, from
    # `da72104 fix: rebuild engines from shared library` -- NOT from this block's prompt edits,
    # which all land outside every hashed region. Located by searching the current tree for each
    # manifest hash's exact content, so each window is byte-identical to what the manifest already
    # records; no --update was run and no doc re-verification was owed. sdlc-task.js's
    # flags-and-defaults (111-155) and stage-list (87-96) did not move and are untouched.
    # BT.ticket.emoji-gate-fallback-must-attribute-a-range-it-did-not-author, task 2: the
    # <<shared:renderEmojiGate>> fallback rewrite inserted 35 net lines into shared.js, which is
    # inlined into both engines at that exact position -- every anchor whose range sat AFTER the
    # inline point shifted by the same +35 lines in the affected file, with no other content
    # change (confirmed against the diff: one contiguous insertion hunk per file, nothing else
    # touched). Ranges below are re-picked from CONTENT at their new positions, not blindly
    # renumbered.
    (".claude/workflows/sdlc-task.js", "flags-and-defaults", 111, 155,
     "docs/workflows/sdlc-task.md", "## Usage"),
    (".claude/workflows/sdlc-task.js", "stage-list", 87, 96,
     "docs/workflows/sdlc-task.md", "## Pipeline"),
    # BT.ticket.harness-config-must-bail-not-warn-on-a-malformed-payload, tasks 1-2: same
    # cause as the bookkeep-vault-commit note below -- the +52/+62 net line insertions sat
    # above this anchor too, so it shifted even though the EXPECT needle (at the very start
    # of the range) still happened to land inside the old fixed window. Re-picked from
    # CONTENT at the new positions (confirmed byte-identical via diff), not blindly renumbered.
    # BT.ticket.engines-must-not-author-unverified-records, tasks 1-2: the new
    # <<shared:renderOperatorGatedACRule>> block (task 1) plus the related:-resolution rule added
    # to the implement-stage prompt (task 2) were inlined ABOVE these anchors in both engines,
    # shifting every range below them by the same net line count per file -- re-picked from
    # CONTENT at the new positions (confirmed byte-identical to the pre-shift content via hash
    # match against the manifest), not blindly renumbered.
    # BT.ticket.criteria-verdict-stage-silently-no-ops-and-is-never-persisted, task 3: the
    # criteriaVerdicts state-literal field + its comment block inserted 12 net lines into
    # sdlc-task.js entirely ABOVE this anchor, shifting it 1860->1872, 1923->1935. Re-picked
    # from CONTENT at the new position (confirmed byte-identical to the pre-shift content via
    # diff), not blindly renumbered.
    # BT.ticket.sdlc-task-worktree-flag-is-intermittently-ignored, task 2: a parser helper +
    # one SETUP_SCHEMA field inserted ABOVE this anchor shifted it 1875->1902, 1956->1983
    # (+27 both ends) with NO content change to this region itself -- verified by diffing the
    # old range against the new range: byte-identical text (confirmed at shift +27). The new
    # STEP 2d (`git worktree list --porcelain` capture) landed just BELOW this anchor's end
    # (which stops at the FAIL-CLOSED note preceding STEP 2c, before the worktree recipe's
    # planning-symlink-fix / STEP 2d region), so it is a real setup-stage behavior change the
    # anchor's fixed window happens not to cover -- documented anyway (not gate-forced) in
    # docs/workflows/sdlc-task.md's "## In-place vs. `--worktree`" section (new "`git worktree
    # list` ground truth (task 2)" subsection), per base-template AGENTS.md's update-loop rule 6.
    # Re-pinned again 2026-09-08 (BT.ticket.lane-heartbeat-goes-stale-mid-block, task 4): the
    # renderTestPrompt() doc-comment + param shift (+5 net lines) landed ABOVE this anchor; the
    # runTests() heartbeatRecipe call (+2 net lines) landed BELOW it, so only +5 applies here:
    # 1906->1911, 1987->1992. Text unchanged -- verified by diffing the old range against the new
    # range: byte-identical ("WORKTREE MODE (--worktree)" onward).
    # BT.ticket.sdlc-state-status-vocabulary, task 3: the renderStateFlipScript doc-comment
    # rewrite (FLIP_REFUSED contract) + the mev-absent fallback's refusal rewrite inserted 9 net
    # lines into sdlc-task.js entirely ABOVE this anchor, shifting it 1911->1920, 1992->2001.
    # Re-picked from CONTENT at the new position (confirmed byte-identical to the pre-shift
    # content via hash match against the manifest), not blindly renumbered.
    (".claude/workflows/sdlc-task.js", "isolation-and-branch-naming", 1920, 2001,
     "docs/workflows/sdlc-task.md", "## In-place vs. `--worktree`"),
    # The triage prompt moved into the shared library (D83), so the anchor follows it. Left at the
    # engines it would hash a one-line function CALL -- green forever, blind to every change in the
    # taxonomy it exists to guard. Two entries because both docs pages describe it.
    (".claude/workflows/prompts/shared.js", "triage-bail-taxonomy", 650, 698,
     "docs/workflows/sdlc-task.md", "## Pipeline"),
    (".claude/workflows/prompts/shared.js", "triage-bail-taxonomy-flow-doc", 650, 698,
     "docs/workflows/sdlc-flow.md", "## Pipeline"),
    # BT.ticket.sdlc-bookkeep-writes-block-status-deterministically, tasks 1-3: the new
    # renderStateFlipScript deterministic `mev set-block-status` dispatch was inlined ABOVE these
    # anchors in both engines, shifting sdlc-task.js's ranges by +75 and sdlc-flow.js's by +60 --
    # re-picked from CONTENT at the new positions (confirmed byte-identical to the pre-shift
    # content via diff), not blindly renumbered.
    # BT.ticket.sdlc-task-must-verify-its-blocks-acceptance-criteria, task 2: the criteria-
    # evidence stage inserted 123 net lines into sdlc-task.js, entirely ABOVE this anchor --
    # re-picked from CONTENT at the new position (confirmed byte-identical to the pre-shift
    # content via diff), not blindly renumbered. sdlc-flow.js is untouched by this block (out of
    # scope) and needs no re-pick.
    # BT.ticket.engines-must-not-author-unverified-records, tasks 1-2 (this bookkeep-vault-commit
    # anchor is sdlc-task.js's own -- see the isolation-and-branch-naming note above for the same
    # cause): re-picked from CONTENT (hash match against the manifest), not blindly renumbered.
    # BT.ticket.criteria-verdict-stage-silently-no-ops-and-is-never-persisted, task 2: the
    # loadBlockRecordAcceptanceCriteria reason plumbing inserted 30 net lines into sdlc-task.js
    # ABOVE this anchor -- re-picked from CONTENT at the new position (confirmed byte-identical
    # to the pre-shift content via diff), not blindly renumbered. sdlc-flow.js is untouched by
    # this block (out of scope) and needs no re-pick.
    # BT.ticket.criteria-verdict-stage-silently-no-ops-and-is-never-persisted, task 3: the
    # criteriaVerdicts state-literal field + its comment block, plus the state.criteriaVerdicts
    # assignment at the point verdicts are computed, inserted 18 net lines into sdlc-task.js
    # entirely ABOVE this anchor, shifting it 3288->3306, 3315->3333. Re-picked from CONTENT at
    # the new position (confirmed byte-identical to the pre-shift content via diff), not blindly
    # renumbered. sdlc-flow.js is untouched by this block (out of scope) and needs no re-pick.
    # BT.ticket.engine-helpers-call-require-which-the-workflow-runtime-does-not-define: the
    # CRITERIA_LOAD_SCHEMA constant + loadBlockRecordAcceptanceCriteria's agent()-based rewrite
    # inserted 32 net lines into sdlc-task.js entirely ABOVE this anchor, shifting it
    # 3319->3351, 3346->3378. Re-picked from CONTENT at the new position (confirmed
    # byte-identical to the pre-shift content via diff), not blindly renumbered. sdlc-flow.js is
    # untouched by this block (out of scope) and needs no re-pick.
    # BT.ticket.engine-render-identity-schema-tdz (2026-09-07): same +10 shift as
    # check_skill_sync.py's twin anchor -- the RENDER_IDENTITY_SCHEMA const moved above the
    # top-level awaits that reach it, inserting 10 net lines above this range in both engines.
    # Content byte-identical across the move (old range in the pre-fix file vs new range in the
    # fixed file diffed clean in both engines), so the docs pages still describe exactly what is
    # there. Re-stamped on that evidence.
    # BT.ticket.sdlc-task-worktree-flag-is-intermittently-ignored, task 2: the STEP 2d capture +
    # parser helper + JS-side worktree-list cross-check landed entirely ABOVE this anchor,
    # shifting it 3412->3478 (+66) with NO content change to this region itself -- verified by
    # diffing the old range against the new range: byte-identical text ("7. Commit your edits
    # (stage explicitly" through the trailing `git log --oneline -1`). Re-stamped on that
    # evidence, not on a re-read of the docs section.
    # Re-pinned again 2026-09-08 (BT.ticket.lane-heartbeat-goes-stale-mid-block, task 4): the new
    # `heartbeatRecipe` doc-comment + param on the shared renderTestPrompt() region (+5 net lines)
    # plus the new `const heartbeatRecipe = await renderLaneHeartbeatRecipe(...)` call in
    # runTests() (+2 net lines) both landed ABOVE this anchor in sdlc-task.js, shifting it
    # 3482->3489, 3509->3516 (+7 total). Text unchanged -- verified by diffing the old range
    # against the new range: byte-identical.
    # BT.ticket.sdlc-state-status-vocabulary, task 3: same +9 net-line insertion noted above
    # (ABOVE both this anchor and isolation-and-branch-naming) shifted it 3489->3498, 3516->3525.
    # Re-picked from CONTENT at the new position (confirmed byte-identical to the pre-shift
    # content via hash match against the manifest), not blindly renumbered.
    (".claude/workflows/sdlc-task.js", "bookkeep-vault-commit", 3498, 3525,
     "docs/workflows/sdlc-task.md", "## Vaulted `planning/` writes in the per-task loop"),
    # BT.ticket.engines-must-not-author-unverified-records, tasks 1-2: the same two inlined blocks
    # noted above also landed in sdlc-flow.js (renderOperatorGatedACRule call in the wrap-up/docs
    # stages, plus the related:-resolution rule in the implement-stage prompt), each ABOVE these
    # three sdlc-flow.js anchors -- re-picked from CONTENT (hash match against the manifest), not
    # blindly renumbered.
    # Re-pinned again 2026-09-08 (BT.ticket.lane-heartbeat-goes-stale-mid-block, task 4): the
    # renderTestPrompt() doc-comment + param shift (+5 net lines) landed ABOVE this anchor;
    # shifting it 933->938, 950->955. Text unchanged -- verified by diffing the old range against
    # the new range: byte-identical ("const autoMergeFlag = hasFlag('--auto-merge')" onward).
    (".claude/workflows/sdlc-flow.js", "flags-and-defaults", 938, 955,
     "docs/workflows/sdlc-flow.md", "## Usage"),
    (".claude/workflows/sdlc-flow.js", "stage-list", 62, 74,
     "docs/workflows/sdlc-flow.md", "## Pipeline"),
    # Re-pinned again 2026-09-08 (BT.ticket.lane-heartbeat-goes-stale-mid-block, task 4): the
    # renderTestPrompt() doc-comment + param shift (+5 net lines) landed ABOVE this anchor; the
    # runTests() heartbeatRecipe call (+2 net lines) landed BELOW it, so only +5 applies here:
    # 1875->1880, 2005->2010. Text unchanged -- verified by diffing the old range against the new
    # range: byte-identical.
    (".claude/workflows/sdlc-flow.js", "isolation-and-branch-naming", 1880, 2010,
     "docs/workflows/sdlc-flow.md", "## Isolation mode — branch by default, `--worktree` for true isolation"),
    # Re-pinned again 2026-09-08 (BT.ticket.lane-heartbeat-goes-stale-mid-block, task 4): BOTH the
    # renderTestPrompt() shift (+5) and the runTests() heartbeatRecipe call (+2) sit ABOVE this
    # anchor, shifting it 3547->3554, 3582->3589 (+7 total). Text unchanged -- verified by diffing
    # the old range against the new range: byte-identical ("5. Commit (stage explicitly" through
    # the trailing `git log --oneline -1`). This is one of the two anchors
    # check_engine_docs_sync.py itself flagged as drifted onto unrelated code before this re-pin.
    (".claude/workflows/sdlc-flow.js", "bookkeep-vault-commit", 3554, 3589,
     "docs/workflows/sdlc-flow.md", "## Vaulted planning directories (D46)"),
]


EXPECT = {
    ("sdlc-task.js", "flags-and-defaults"): "const useWorktree = hasFlag('--worktree')",
    ("sdlc-task.js", "stage-list"): 'export const meta = {',
    ("sdlc-flow.js", "flags-and-defaults"): "const autoMergeFlag = hasFlag('--auto-merge')",
    ("sdlc-flow.js", "stage-list"): 'export const meta = {',
    ("shared.js", "triage-bail-taxonomy-flow-doc"): 'function renderTriagePrompt(',
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
