#!/usr/bin/env python3
"""Fixture suite pinning both rules of BT.ticket.engines-must-not-author-unverified-records.

WHY THIS EXISTS
----------------
Both engines authored records without checking that what they asserted was true: /sdlc-flow's
wrap-up stage wrote a COMPLETED sign-off naming the operator for a criterion no operator had
actually reviewed, and /sdlc-task wrote a `related:` doc_id invented from a sibling filename that
resolves to nothing in the corpus. Both measured 2026-08-21 (finding_id
sdlc-engine-record-authoring-2026-08). See planning/blocks/BT.ticket.engines-must-not-author-
unverified-records.json for the full record.

This suite asserts, against the REAL source of both `.claude/workflows/sdlc-task.js` and
`.claude/workflows/sdlc-flow.js`:

  RULE 1 (operator-gated AC recorded PENDING, never attributed) is present in every stage that
  authors a human-facing record:
    - sdlc-task.js:  the `bookkeep` stage (the only record-authoring stage the lean engine has)
    - sdlc-flow.js:  the `docs` stage and the `wrap-up` stage

  RULE 2 (every `related:` doc_id resolved against the corpus before writing, or omitted) is
  present in the IMPLEMENT-stage prompt of BOTH engines specifically -- not merely in bookkeep/docs
  -- because the measured defect was an implement-stage task authoring a brand-new planning file.
  Both engines share ONE `renderImplementPrompt` function (inlined from
  `.claude/workflows/prompts/shared.js` via the `<<shared:NAME>>` build_engines.py convention), so
  this suite locates that exact shared region in each engine file and checks inside it.

POSITIVE CONTROLS
-------------------
Every region this suite searches WITHIN is itself asserted to exist first. A renamed stage anchor
or a shared-block tag that no longer matches must make the corresponding case FAIL, never pass
vacuously -- standing rule 11 ("a case that matches nothing must fail, never pass").

DELETION CASES
----------------
For each engine and each rule, this suite also asserts that DELETING the rule's marker text from
an in-memory copy of the real region text makes the same assertion function fail. This is what
pins "the suite must fail if either rule is removed" (block AC4) without requiring a second,
mutated copy of either engine file on disk.

Usage:
    python3 scripts/test_engine_record_authoring.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"
FLOW_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"

# The load-bearing phrases each rule's rendered text must contain. Deliberately specific enough
# that unrelated prose mentioning "operator" or "related:" elsewhere in an engine cannot satisfy
# these by accident, and specific enough that a case run against a *deletion* of the real text
# actually goes red.
RULE1_MARKERS = [
    "OPERATOR-GATED ACCEPTANCE CRITERIA",
    "PENDING (operator gate)",
    "NEVER attribute a verdict",
]
RULE1_CALL_MARKER = "renderOperatorGatedACRule()"

RULE2_MARKERS = [
    "RELATED: DOC_ID RESOLUTION",
    "An unresolvable target is OMITTED, not guessed",
]

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def slice_between(text: str, start_marker: str, end_marker: str | None) -> str | None:
    """Return the text strictly between the END of start_marker and the START of end_marker
    (or end of string if end_marker is None / not found after start_marker). None if start_marker
    itself is not found -- the positive-control failure case."""
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return None
    region_start = start_idx + len(start_marker)
    if end_marker is None:
        return text[region_start:]
    end_idx = text.find(end_marker, region_start)
    if end_idx == -1:
        return text[region_start:]
    return text[region_start:end_idx]


def region_has_all(region: str | None, markers: list[str]) -> bool:
    if region is None:
        return False
    return all(m in region for m in markers)


def region_has_any(region: str | None, marker: str) -> bool:
    if region is None:
        return False
    return marker in region


def rule1_present(region: str | None) -> bool:
    """Pure predicate: does this region correctly INVOKE rule 1? Used both for the real check and
    for the deletion case, so the two can never disagree about what "present" means. Whether the
    invoked function itself renders the right text is a separate, function-level check (the call
    site is just `${renderOperatorGatedACRule()}` -- the actual PENDING/attribution prose lives in
    the function body, not at the call site)."""
    if region is None:
        return False
    return RULE1_CALL_MARKER in region


def check_rule1_stage(engine_label: str, region_name: str, region: str | None) -> None:
    if region is None:
        fail(
            f"{engine_label}: positive control failed -- could not locate the '{region_name}' "
            "stage anchor at all (it was renamed or removed), so rule 1 cannot be checked there"
        )
        return
    if not rule1_present(region):
        fail(
            f"{engine_label}: '{region_name}' stage region does not invoke "
            f"{RULE1_CALL_MARKER} -- the operator-gated-AC rule is not wired into this "
            "record-authoring stage"
        )
        return
    ok(f"{engine_label}: rule 1 (operator-gated AC -> PENDING, unattributed) invoked in '{region_name}'")

    # Deletion case: strip the call marker out of an in-memory copy and confirm the SAME predicate
    # now reports absent, rather than silently still passing.
    mutated = region.replace(RULE1_CALL_MARKER, "")
    if rule1_present(mutated):
        fail(
            f"{engine_label}: deletion case for rule 1 in '{region_name}' did not go red -- "
            "removing the call marker should have made rule1_present() return False"
        )
    else:
        ok(f"{engine_label}: deleting rule 1's call from '{region_name}' correctly fails the check")


def check_rule2_implement(engine_label: str, region: str | None) -> None:
    if region is None:
        fail(
            f"{engine_label}: positive control failed -- could not locate the shared "
            "<<shared:renderImplementPrompt>> region at all, so rule 2 cannot be checked in the "
            "implement stage"
        )
        return
    if not region_has_all(region, RULE2_MARKERS):
        fail(
            f"{engine_label}: implement-stage (renderImplementPrompt) region is missing the "
            f"related:-resolution rule -- required phrases {RULE2_MARKERS} not all present"
        )
        return
    ok(f"{engine_label}: rule 2 (related: doc_id resolution) present in the implement-stage prompt")

    # Deletion case.
    mutated = region.replace(RULE2_MARKERS[0], "")
    if region_has_all(mutated, RULE2_MARKERS):
        fail(
            f"{engine_label}: deletion case for rule 2 did not go red -- removing "
            f"{RULE2_MARKERS[0]!r} should have failed the check"
        )
    else:
        ok(f"{engine_label}: deleting rule 2's anchor phrase correctly fails the check")


def check_rule1_function_body(engine_label: str, text: str) -> None:
    """The call sites only invoke `renderOperatorGatedACRule()` -- the actual PENDING /
    non-attribution prose lives in the function's own body. Assert that body is present and
    intact (byte-identity with shared.js is check_shared_inlined_parity's job, not this one's)."""
    region = slice_between(
        text, "// <<shared:renderOperatorGatedACRule>>", "// <</shared:renderOperatorGatedACRule>>"
    )
    if region is None:
        fail(
            f"{engine_label}: positive control failed -- no <<shared:renderOperatorGatedACRule>> "
            "block found at all, so rule 1's rendered text cannot exist anywhere in this engine"
        )
        return
    if not region_has_all(region, RULE1_MARKERS):
        fail(
            f"{engine_label}: renderOperatorGatedACRule() body is missing one of the required "
            f"phrases: {RULE1_MARKERS}"
        )
        return
    ok(f"{engine_label}: renderOperatorGatedACRule() body carries the required PENDING/attribution phrases")

    mutated = region.replace(RULE1_MARKERS[0], "")
    if region_has_all(mutated, RULE1_MARKERS):
        fail(
            f"{engine_label}: deletion case for rule 1's function body did not go red -- "
            f"removing {RULE1_MARKERS[0]!r} should have failed the phrase check"
        )
    else:
        ok(f"{engine_label}: deleting a rule-1 phrase from the function body correctly fails the check")


def main() -> int:
    task_text = read(TASK_JS)
    flow_text = read(FLOW_JS)

    # --- Rule 1: the function body itself (source of the PENDING/attribution prose) ----------
    check_rule1_function_body("sdlc-task.js", task_text)
    check_rule1_function_body("sdlc-flow.js", flow_text)

    # --- Rule 1: sdlc-task.js's bookkeep stage (its only record-authoring stage) --------------
    task_bookkeep = slice_between(
        task_text,
        "You are the lean bookkeeping close-out for an /sdlc-task run.",
        None,  # bookkeep is the last stage prompt in the file
    )
    check_rule1_stage("sdlc-task.js", "bookkeep", task_bookkeep)

    # --- Rule 1: sdlc-flow.js's docs stage, then its wrap-up stage ----------------------------
    flow_wrapup_anchor = "You are the wrap-up agent for an /sdlc-flow run."
    flow_docs = slice_between(
        flow_text,
        "You are the documentation agent for the /sdlc-flow pipeline",
        flow_wrapup_anchor,
    )
    check_rule1_stage("sdlc-flow.js", "docs", flow_docs)

    flow_wrapup = slice_between(flow_text, flow_wrapup_anchor, None)
    check_rule1_stage("sdlc-flow.js", "wrap-up", flow_wrapup)

    # --- Rule 2: the shared renderImplementPrompt region, inlined into both engines ----------
    task_implement = slice_between(
        task_text, "// <<shared:renderImplementPrompt>>", "// <</shared:renderImplementPrompt>>"
    )
    check_rule2_implement("sdlc-task.js", task_implement)

    flow_implement = slice_between(
        flow_text, "// <<shared:renderImplementPrompt>>", "// <</shared:renderImplementPrompt>>"
    )
    check_rule2_implement("sdlc-flow.js", flow_implement)

    # --- AC3: both engines carry both rules (a cross-check over everything already asserted) --
    if not FAILURES:
        ok("both engines carry both rules (AC3)")

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s).", file=sys.stderr)
        return 1

    print("\nOK: engine-record-authoring-tests all green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
