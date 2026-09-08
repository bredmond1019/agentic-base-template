#!/usr/bin/env python3
"""Fixture over `.claude/workflows/sdlc-flow.js` for BT.ticket.sdlc-flow-records-no-base-sha.

WHY THIS EXISTS
----------------
`sdlc-task.js` captures the HEAD short sha after setup / before any task commit and persists it
as `state.base_sha` (`SETUP_SCHEMA` :1006, capture :2006, assignment :2018). `sdlc-flow.js` never
did -- measured 2026-09-07, `grep -c base_sha` is 3 in `sdlc-task.js` and 0 in `sdlc-flow.js`, and
0 of 412 real `sdlc-flow-state.json` files on disk carry the key. That leaves `/close-out` (and
any other consumer) with no way to scope a flow run's diff to the commits that run actually made.

THE TRAP THIS FIXTURE GUARDS AGAINST
-------------------------------------
`sdlc-flow.js` already has a value that LOOKS like the right one: `prBase = flowCfg.prBase ||
'main'` (:2481), passed into the emoji gate as `diffBase` (:750/:2617). That is a BRANCH NAME
defaulting to the literal string 'main' -- not a sha, not pinned to when this run started.
Persisting THAT into `base_sha` would satisfy every positive assertion below (the field would
exist, be a string, look plausible) while being strictly WORSE than leaving the field absent: a
consumer would find a populated field and scope its diff against the branch tip, which is exactly
the vacuous fallback the dependent block (BT.ticket.close-out-diff-base-underscopes-a-multi-block-
run) exists to eliminate. So the load-bearing assertion here is negative: whatever the
`state.base_sha` assignment's right-hand side is, it must not be `prBase`, must not be `diffBase`,
and must not be a string literal.

Reads BOTH engine files as text (never imports/executes either -- these are Workflow-tool scripts,
not importable modules) and does balanced-brace / regex extraction, in the style of
`scripts/test_sdlc_task_criteria_verdicts.py` and `scripts/test_roadmap_dir_resolution.py`.
Stdlib-only. Exits non-zero on any failure.

D68: this fixture is run once against the UNFIXED engine (task 1, expected to fail every
positive check and the assignment-presence check) and once against the fixed engine (task 3,
expected to pass in full) -- both outputs recorded verbatim in the worklog.

Run: python3 scripts/test_sdlc_flow_base_sha.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLOW_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"
TASK_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_object_literal(text: str, anchor_pattern: str) -> str:
    """From the first `{` after a regex match to its balanced closing `}`, inclusive."""
    m = re.search(anchor_pattern, text)
    if not m:
        raise AssertionError(f"anchor pattern not found: {anchor_pattern!r}")
    brace_start = text.index("{", m.end() - 1)
    depth = 0
    i = brace_start
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start:i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces extracting object literal at {anchor_pattern!r}")


def extract_property_description(obj_literal: str, prop_name: str) -> str | None:
    """Pull the `description: '...'` (or "...") string for a `<prop_name>: { ... }` entry."""
    m = re.search(rf"{re.escape(prop_name)}\s*:\s*{{", obj_literal)
    if not m:
        return None
    # bound the property's own object literal
    depth = 0
    i = obj_literal.index("{", m.end() - 1)
    start = i
    while i < len(obj_literal):
        c = obj_literal[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                prop_obj = obj_literal[start:i + 1]
                break
        i += 1
    else:
        raise AssertionError(f"unbalanced braces extracting property {prop_name!r}")
    desc_m = re.search(r"description:\s*(['\"])((?:\\.|(?!\1).)*)\1", prop_obj)
    if not desc_m:
        return None
    return desc_m.group(2)


def main() -> int:
    flow_src = read(FLOW_PATH)
    task_src = read(TASK_PATH)

    # --- SETUP_SCHEMA: baseSha declared, description matches sdlc-task.js's exactly ----------
    try:
        flow_setup_schema = extract_object_literal(flow_src, r"const SETUP_SCHEMA\s*=\s*")
    except AssertionError as exc:
        check("sdlc-flow.js SETUP_SCHEMA found", False, str(exc))
        flow_setup_schema = ""
    else:
        check("sdlc-flow.js SETUP_SCHEMA found", True)

    try:
        task_setup_schema = extract_object_literal(task_src, r"const SETUP_SCHEMA\s*=\s*")
    except AssertionError as exc:
        raise AssertionError(
            f"sdlc-task.js SETUP_SCHEMA not found -- fixture's reference source is broken: {exc}"
        ) from exc

    task_base_sha_desc = extract_property_description(task_setup_schema, "baseSha")
    if task_base_sha_desc is None:
        raise AssertionError(
            "sdlc-task.js SETUP_SCHEMA has no baseSha description -- fixture's reference is "
            "broken; sdlc-task.js:1006 should declare one"
        )

    flow_base_sha_desc = (
        extract_property_description(flow_setup_schema, "baseSha") if flow_setup_schema else None
    )
    check(
        "sdlc-flow.js SETUP_SCHEMA declares a baseSha property",
        flow_base_sha_desc is not None,
        "no `baseSha: { ... }` entry found in SETUP_SCHEMA",
    )
    check(
        "sdlc-flow.js baseSha description matches sdlc-task.js's exactly",
        flow_base_sha_desc is not None and flow_base_sha_desc == task_base_sha_desc,
        f"flow={flow_base_sha_desc!r} task={task_base_sha_desc!r}",
    )

    # --- setup prompt instructs a `git rev-parse --short HEAD` capture ----------------------
    # The setup prompt runs from the SETUP_SCHEMA declaration up to the withModel(...) call that
    # uses it as its schema (sdlc-task.js:2054-equivalent in sdlc-flow.js).
    setup_schema_start = flow_src.find("const SETUP_SCHEMA")
    with_model_match = re.search(r"withModel\(\{[^}]*schema:\s*SETUP_SCHEMA", flow_src)
    if setup_schema_start != -1 and with_model_match:
        setup_prompt_region = flow_src[setup_schema_start:with_model_match.end()]
    else:
        setup_prompt_region = ""
    check(
        "setup prompt instructs `git rev-parse --short HEAD`",
        "rev-parse --short HEAD" in setup_prompt_region,
        "no `git rev-parse --short HEAD` instruction found between SETUP_SCHEMA and the setup "
        "withModel(...) call",
    )

    # --- state.base_sha is assigned from a captured var, not a literal/prBase/diffBase -------
    assign_m = re.search(r"state\.base_sha\s*=\s*([^\n;]+);?", flow_src)
    check(
        "state.base_sha is assigned somewhere in sdlc-flow.js",
        assign_m is not None,
        "no `state.base_sha = ...` assignment found",
    )
    rhs = assign_m.group(1).strip() if assign_m else ""

    # THE LOAD-BEARING NEGATIVE: not prBase, not diffBase, not a string literal.
    is_prbase = rhs == "prBase"
    is_diffbase = rhs == "diffBase"
    is_string_literal = bool(re.match(r"""^['"`]""", rhs))
    check(
        "state.base_sha is NOT assigned from prBase",
        assign_m is not None and not is_prbase,
        f"rhs={rhs!r} -- persisting prBase would give a populated field that is really the "
        "branch-tip fallback, strictly worse than an absent field",
    )
    check(
        "state.base_sha is NOT assigned from diffBase",
        assign_m is not None and not is_diffbase,
        f"rhs={rhs!r}",
    )
    check(
        "state.base_sha is NOT assigned a string literal",
        assign_m is not None and not is_string_literal,
        f"rhs={rhs!r} -- must be a variable captured from the setup result, not a hardcoded value",
    )

    # --- the persisted state object literal declares a base_sha key -------------------------
    try:
        state_literal = extract_object_literal(flow_src, r"const state\s*=\s*")
    except AssertionError as exc:
        check("sdlc-flow.js persisted `const state = {...}` literal found", False, str(exc))
        state_literal = ""
    else:
        check("sdlc-flow.js persisted `const state = {...}` literal found", True)
    check(
        "persisted state literal declares a base_sha key",
        bool(re.search(r"\bbase_sha\s*:", state_literal)),
        "no `base_sha:` key in the `const state = {...}` literal",
    )

    if FAILURES:
        print(f"\nFAIL {FLOW_PATH.relative_to(REPO_ROOT)} "
              f"{len(FAILURES)} case(s) failed: {', '.join(FAILURES)}")
        return 1
    print("\nall cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
