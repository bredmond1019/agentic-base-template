#!/usr/bin/env python3
"""Fixture for BT.ticket.sdlc-task-cannot-express-a-deliberate-failing-test, task 1.

D68: this fixture is written and run FIRST, against the UNMODIFIED `.claude/workflows/sdlc-task.js`
and `.claude/commands/generate-tasks.md`, and is expected to FAIL -- a fixture first observed
passing proves nothing. This repo cannot execute either the engine or the command doc (D64); every
assertion below is a source-text check, in the established style of
`scripts/test_worktree_setup_binding_guard.py`.

**Why this fixture is not itself run as a validation command in task 1:** a deliberately-red check
is exactly what `/sdlc-task`'s per-task fast-test gate cannot express today -- that gap is this
block's whole subject. Registering this script gating before the fix lands would either fail task 1
outright (defeating D68's "observe it failing" step, since the run would never complete) or require
inverting the gate by hand, which is the workaround CLAUDE.md's D68 discipline exists to replace.
Task 1 therefore only asserts the fixture *parses* and that the engine/docs/harness are untouched;
this script's real, non-zero exit is captured by hand into the task notes instead.

Five named, independent assertions (A-E), each checked against the file SOURCE as plain text and
located by symbol/heading -- never by line number, because `scripts/skill_sync_manifest.json` and
`scripts/engine_docs_sync_manifest.json` already pin `sdlc-task.js` by line range and this block's
own `ENUMERATE_SCHEMA` edit shifts every one of them (see the block record's step 5):

  A. `ENUMERATE_SCHEMA` in `sdlc-task.js` declares a `taskExpectRed` array whose items carry both
     `taskId` and `commands` properties.
  B. somewhere in the per-task render path, wording exists that states the check PASSES on a
     non-zero exit AND FAILS on exit 0, close enough together to be describing one condition
     rather than two unrelated mentions.
  C. the engine SOURCE (not only the docs) states the subset constraint: an `expect_red` entry
     must also appear in that same task's own `validation_commands`.
  D. the engine SOURCE states the harness-check boundary -- that `expect_red` is scoped to the
     task's own declared commands so it can never invert a project-wide `gates:true` harness
     check -- and the function that computes the harness gating check list (`gatingChecks`)
     contains no mention of expect-red at all, i.e. that computation was never touched.
  E. `.claude/commands/generate-tasks.md` documents `expect_red` in the tasks.json Output Format
     section AND states the subset rule in its step 8 property self-check section.

Each assertion fails independently and prints its own PASS/FAIL line; the script exits non-zero if
any assertion fails. Never piped -- this script's own exit code is the answer (CLAUDE.md standing
rule / trap 1), so callers must check `$?` directly, not through `| tail` or similar.

Registered in planning/harness.json (task 5) as `expect-red-contract` --
run directly: python3 scripts/test_expect_red_contract.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ENGINE_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"
# BT.ticket.sdlc-flow-cannot-express-a-deliberate-failing-test: D68 shipped expect_red to the lean
# engine only, so a block whose deliverable is a failing test could not be run through /sdlc-flow at
# all. The engine half of that port has landed; this fixture's flow half had not -- the suite matched
# `sdlc-flow` zero times while `expect-red-contract` was already a gating check, so a regression that
# removed expect_red from sdlc-flow.js alone would have left this suite green.
FLOW_ENGINE_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"
GENERATE_TASKS_PATH = REPO_ROOT / ".claude" / "commands" / "generate-tasks.md"

# The two engines carry expectRedFor() between a matched pair of sync anchors; the region must be
# byte-identical across them (assertion F) -- the rule is about the spec, not about which engine
# reads it, so a fix applied to one engine and not the other is the defect this pins.
EXPECT_RED_ANCHOR_OPEN = "// <<shared:expectRedFor>>"
EXPECT_RED_ANCHOR_CLOSE = "// <</shared:expectRedFor>>"

# sdlc-flow.js has no `gatingChecks(cfg)`; its harness gating SET is computed by the
# `if (gatingOnly)` filter inside renderCheckList(), so assertion D's "the gating-set computation
# never consults expect_red" is checked against that function's body there.
FLOW_CHECKLIST_FN_RE = re.compile(
    r"function\s+renderCheckList\s*\(\s*cfg\s*,\s*\{[^}]*\}\s*=\s*\{\}\s*\)\s*\{"
)
FLOW_GATING_FILTER_RE = re.compile(
    r"if\s*\(gatingOnly\)\s*checks\s*=\s*checks\.filter\("
)

# --- Assertion A: ENUMERATE_SCHEMA declares taskExpectRed {taskId, commands} ------------------
ENUMERATE_SCHEMA_RE = re.compile(r"const\s+ENUMERATE_SCHEMA\s*=\s*\{")
TASK_EXPECT_RED_PROP_RE = re.compile(r"taskExpectRed\s*:\s*\{")
# How far past the `taskExpectRed:` property key to look for its nested `taskId`/`commands` item
# fields -- wide enough to span a multi-line `items: { properties: { ... } }` block, narrow enough
# not to accidentally wander into an unrelated sibling schema property further down the object.
SCHEMA_PROP_WINDOW = 700

# --- Assertion B: inverted-verdict wording in the per-task render path -------------------------
INVERTED_PASS_RE = re.compile(r"PASS[A-Za-z]*[^.\n]{0,160}NON-?ZERO", re.IGNORECASE)
INVERTED_FAIL_RE = re.compile(r"FAIL[A-Za-z]*[^.\n]{0,160}exit\s*0\b", re.IGNORECASE)
# How close the PASS-side and FAIL-side wording must sit to count as describing the SAME
# inverted-verdict check, rather than two unrelated mentions of "pass"/"fail" elsewhere in the file
# (e.g. the harness gating check wording, which is a wholly separate render path).
INVERTED_VERDICT_PAIR_WINDOW = 600

# --- Assertion C: subset constraint stated in engine SOURCE -------------------------------------
# Requires "expect_red" and "validation_commands" (its own/that task's) and a rejection/must-appear
# verb, all within one window -- loose enough to survive reasonable phrasing, tight enough that it
# cannot be satisfied by the schema's pre-existing, unrelated taskChecks/validationCommands prose.
SUBSET_WINDOW = 400
EXPECT_RED_TOKEN_RE = re.compile(r"expect_red", re.IGNORECASE)
OWN_VALIDATION_COMMANDS_RE = re.compile(r"validation_commands", re.IGNORECASE)
SUBSET_VERB_RE = re.compile(r"\b(must (also )?appear|not (present|found) in|subset)\b", re.IGNORECASE)

# --- Assertion D: harness-check boundary stated + gatingChecks() untouched ---------------------
BOUNDARY_PHRASE_RE = re.compile(
    r"expect_red[^.\n]{0,200}\b(never|cannot|can't)\b[^.\n]{0,120}\b(gates?:true|harness)\b",
    re.IGNORECASE,
)
GATING_CHECKS_FN_RE = re.compile(r"function\s+gatingChecks\s*\(\s*cfg\s*\)\s*\{")
EXPECT_RED_MENTION_RE = re.compile(r"expect[_-]?red", re.IGNORECASE)

# --- Assertion E: generate-tasks.md documents expect_red -----------------------------------------
# Anchored on the `expect_red` field's own heading, not the much-earlier `## Output Format` section
# heading -- that section runs long enough (field-by-field task-shape prose) that the field's actual
# documentation can sit past any window bounded to avoid running past the next top-level heading.
OUTPUT_FORMAT_HEADING_RE = re.compile(r"\*\*`expect_red`\*\*", re.IGNORECASE | re.MULTILINE)
STEP8_HEADING_RE = re.compile(
    r"^\d+\.\s*\*\*Property self-check", re.IGNORECASE | re.MULTILINE
)
# Width of each documentation section scanned for the `expect_red` mention -- generous enough to
# span the Output Format's multi-paragraph field table / the self-check's bullet list, bounded so
# it does not run past the following top-level heading/numbered step.
DOC_SECTION_WINDOW = 6000


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes: list[str] = []

        # Prefixed onto every label so the same assertion run against both engines reports two
        # distinguishable results instead of one ambiguous one.
        self.prefix: str = ""

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        label = f"{self.prefix}{label}"
        if ok:
            self.passes.append(label)
        else:
            self.failures.append(f"{label}: {detail}" if detail else label)


def _read(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def assertion_a(text: str, r: Result) -> None:
    schema_m = ENUMERATE_SCHEMA_RE.search(text)
    if not schema_m:
        r.check("A (taskExpectRed declared with taskId + commands)", False,
                "ENUMERATE_SCHEMA declaration not found")
        return
    prop_m = TASK_EXPECT_RED_PROP_RE.search(text, schema_m.end())
    if not prop_m:
        r.check("A (taskExpectRed declared with taskId + commands)", False,
                "no 'taskExpectRed:' property found in/after ENUMERATE_SCHEMA")
        return
    window = text[prop_m.end(): prop_m.end() + SCHEMA_PROP_WINDOW]
    has_task_id = "taskId" in window
    has_commands = "commands" in window
    r.check("A (taskExpectRed declared with taskId + commands)", has_task_id and has_commands,
             f"taskId present={has_task_id}, commands present={has_commands} within "
             f"{SCHEMA_PROP_WINDOW} chars of the property key")


def assertion_b(text: str, r: Result) -> None:
    pass_matches = list(INVERTED_PASS_RE.finditer(text))
    fail_matches = list(INVERTED_FAIL_RE.finditer(text))
    if not pass_matches:
        r.check("B (inverted-verdict wording: passes on non-zero, fails on exit 0)", False,
                "no 'PASSES ... NON-ZERO'-shaped wording found")
        return
    if not fail_matches:
        r.check("B (inverted-verdict wording: passes on non-zero, fails on exit 0)", False,
                "no 'FAILS ... exit 0'-shaped wording found")
        return
    paired = any(
        abs(pm.start() - fm.start()) <= INVERTED_VERDICT_PAIR_WINDOW
        for pm in pass_matches for fm in fail_matches
    )
    r.check("B (inverted-verdict wording: passes on non-zero, fails on exit 0)", paired,
            "PASS-side and FAIL-side wording exist but are not within "
            f"{INVERTED_VERDICT_PAIR_WINDOW} chars of each other")


def assertion_c(text: str, r: Result) -> None:
    for m in EXPECT_RED_TOKEN_RE.finditer(text):
        window = text[max(0, m.start() - SUBSET_WINDOW): m.end() + SUBSET_WINDOW]
        if OWN_VALIDATION_COMMANDS_RE.search(window) and SUBSET_VERB_RE.search(window):
            r.check("C (subset constraint stated in engine source)", True)
            return
    r.check("C (subset constraint stated in engine source)", False,
            "no 'expect_red' occurrence sits near both 'validation_commands' and a "
            "must-appear/subset verb")


def assertion_d(text: str, r: Result) -> None:
    boundary_ok = bool(BOUNDARY_PHRASE_RE.search(text))
    fn_m = GATING_CHECKS_FN_RE.search(text)
    if not fn_m:
        r.check("D (harness-check boundary stated; gatingChecks() untouched)", False,
                "gatingChecks(cfg) function definition not found")
        return
    # Extract the function body by brace counting from the opening brace already matched.
    start = fn_m.end() - 1  # position of the opening '{'
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        r.check("D (harness-check boundary stated; gatingChecks() untouched)", False,
                "could not locate gatingChecks() function body (unbalanced braces)")
        return
    body = text[start:end]
    fn_untouched = not EXPECT_RED_MENTION_RE.search(body)
    r.check("D (harness-check boundary stated; gatingChecks() untouched)",
            boundary_ok and fn_untouched,
            f"boundary phrase present={boundary_ok}, gatingChecks() body free of "
            f"expect-red mentions={fn_untouched}")


def assertion_e(text: str, r: Result) -> None:
    output_m = OUTPUT_FORMAT_HEADING_RE.search(text)
    step8_m = STEP8_HEADING_RE.search(text)
    if not output_m:
        r.check("E (generate-tasks.md documents expect_red)", False,
                "'**`expect_red`**' field heading not found")
        return
    if not step8_m:
        r.check("E (generate-tasks.md documents expect_red)", False,
                "step 8 'Property self-check' heading not found")
        return
    output_window = text[output_m.end(): output_m.end() + DOC_SECTION_WINDOW]
    step8_window = text[step8_m.end(): step8_m.end() + DOC_SECTION_WINDOW]
    output_ok = bool(EXPECT_RED_TOKEN_RE.search(output_window))
    step8_ok = bool(EXPECT_RED_TOKEN_RE.search(step8_window))
    r.check("E (generate-tasks.md documents expect_red)", output_ok and step8_ok,
            f"Output Format section mentions expect_red={output_ok}, "
            f"step 8 self-check section mentions expect_red={step8_ok}")


def _brace_body(text: str, header_end: int) -> str | None:
    """Body of the block whose opening `{` is the last char of the matched header."""
    start = header_end - 1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def assertion_d_flow(text: str, r: Result) -> None:
    """Assertion D, adapted to sdlc-flow.js's shape.

    The boundary claim is the same -- expect_red is scoped to a task's own validation_commands and
    can never invert or suppress a project-wide `gates: true` harness check. What differs is where
    the harness gating SET is computed: sdlc-task.js has `gatingChecks(cfg)`; sdlc-flow.js filters
    inside `renderCheckList(cfg, { gatingOnly })`. That filter is this engine's equivalent of the
    untouched function, so it is what must stay free of any expect-red mention.
    """
    boundary_ok = bool(BOUNDARY_PHRASE_RE.search(text))
    fn_m = FLOW_CHECKLIST_FN_RE.search(text)
    if not fn_m:
        r.check("D (harness-check boundary stated; gating-set filter untouched)", False,
                "renderCheckList(cfg, { ... }) function definition not found")
        return
    body = _brace_body(text, fn_m.end())
    if body is None:
        r.check("D (harness-check boundary stated; gating-set filter untouched)", False,
                "could not locate renderCheckList() function body (unbalanced braces)")
        return
    filter_ok = bool(FLOW_GATING_FILTER_RE.search(body))
    fn_untouched = not EXPECT_RED_MENTION_RE.search(body)
    r.check("D (harness-check boundary stated; gating-set filter untouched)",
            boundary_ok and filter_ok and fn_untouched,
            f"boundary phrase present={boundary_ok}, gatingOnly filter present={filter_ok}, "
            f"renderCheckList() body free of expect-red mentions={fn_untouched}")


def assertion_f(task_text: str, flow_text: str, r: Result) -> None:
    """Cross-engine parity: the anchored expectRedFor() region is byte-identical in both engines.

    A/B/C/D re-run per engine catch an engine that LOST the feature; this catches the subtler
    case -- both engines still mention expect_red, but one's implementation has drifted from the
    other's, which is how the two halves of a ported rule silently disagree.
    """
    regions = {}
    for name, text in (("sdlc-task.js", task_text), ("sdlc-flow.js", flow_text)):
        open_i = text.find(EXPECT_RED_ANCHOR_OPEN)
        close_i = text.find(EXPECT_RED_ANCHOR_CLOSE)
        if open_i < 0 or close_i < 0 or close_i < open_i:
            r.check("F (expectRedFor region byte-identical across both engines)", False,
                    f"{name}: sync anchors {EXPECT_RED_ANCHOR_OPEN} / "
                    f"{EXPECT_RED_ANCHOR_CLOSE} not found in order")
            return
        regions[name] = text[open_i:close_i + len(EXPECT_RED_ANCHOR_CLOSE)]
    task_region, flow_region = regions["sdlc-task.js"], regions["sdlc-flow.js"]
    # Positive control against a vacuous pass: two empty regions would compare equal.
    if "expectRedFor" not in task_region:
        r.check("F (expectRedFor region byte-identical across both engines)", False,
                "the anchored region does not contain expectRedFor -- anchors bracket the "
                "wrong subject, so equality here would prove nothing")
        return
    r.check("F (expectRedFor region byte-identical across both engines)",
            task_region == flow_region,
            f"the anchored regions differ ({len(task_region)} vs {len(flow_region)} chars) -- "
            "expect_red has been changed in one engine and not the other")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="only print output on failure")
    args = ap.parse_args(argv)

    r = Result()

    r.prefix = "[sdlc-task] "
    engine_text = _read(ENGINE_PATH)
    if engine_text is None:
        r.check("engine file exists", False, f"{ENGINE_PATH} not found")
    else:
        assertion_a(engine_text, r)
        assertion_b(engine_text, r)
        assertion_c(engine_text, r)
        assertion_d(engine_text, r)

    r.prefix = "[sdlc-flow] "
    flow_text = _read(FLOW_ENGINE_PATH)
    if flow_text is None:
        r.check("engine file exists", False, f"{FLOW_ENGINE_PATH} not found")
    else:
        assertion_a(flow_text, r)
        assertion_b(flow_text, r)
        assertion_c(flow_text, r)
        assertion_d_flow(flow_text, r)

    r.prefix = "[both engines] "
    if engine_text is not None and flow_text is not None:
        assertion_f(engine_text, flow_text, r)

    r.prefix = ""
    docs_text = _read(GENERATE_TASKS_PATH)
    if docs_text is None:
        r.check("generate-tasks.md exists", False, f"{GENERATE_TASKS_PATH} not found")
    else:
        assertion_e(docs_text, r)

    if not args.quiet:
        for p in r.passes:
            print(f"PASS  {p}")
    for f in r.failures:
        print(f"FAIL  {f}")

    if r.failures:
        print(f"\n{len(r.failures)} assertion(s) failed, {len(r.passes)} passed.")
        return 1

    if not args.quiet:
        print(f"\nOK -- all {len(r.passes)} assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
