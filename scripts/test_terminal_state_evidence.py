#!/usr/bin/env python3
"""Fixture for BT.ticket.engine-terminal-state-needs-evidence, task 1.

D68: this fixture is written and run FIRST, against the UNMODIFIED `.claude/workflows/sdlc-task.js`
and `.claude/workflows/sdlc-flow.js`, and is expected to FAIL -- a fixture first observed passing
proves nothing. This repo cannot execute either engine (D64 -- they are Workflow-tool scripts); every
assertion below is a source-text check, in the established style of `test_expect_red_contract.py`
and `test_step2_reverify_rules.py`. Every region is located by SYMBOL or heading marker, never by
line number -- the line numbers quoted in the block record are already a stale snapshot and this
block's own edits (tasks 2-3) shift every one of them.

Five named, independent assertions (A-E), each printed ok/FAIL per engine file so a regression names
WHICH engine drifted:

  A. `emitStateRan` is CONSISTENT per engine: either absent from the file entirely, or -- if
     retained -- assigned onto the object that is actually JSON.stringify'd to the on-disk state
     file (`state.emitStateRan = ...` / `state['emitStateRan'] = ...`, or the `snapshot` clone of
     it), not merely declared in a StructuredOutput schema or mentioned in a log line. Measured
     2026-09-03: the token is retained in both engines (sdlc-task.js 7 lines / 8 occurrences,
     sdlc-flow.js 11 lines / 14 occurrences) but assigned onto the persisted state object in
     NEITHER -- it is a key in 0 of the corpus's 150 sdlc-*state.json files. This assertion counts
     and reports the exact per-file site/occurrence numbers at runtime rather than asserting the
     hardcoded figures above, so a future recount is not silently trusted against a stale docstring.

  B. the terminal RUN status (`state.status = ... 'done'`/`'passed'`) is never written from inside
     the per-task loop body (`for (const taskNum of taskList) { ... }`, brace-matched from that
     exact anchor). The per-task slots -- `t.status = ...`, `snapshot.tasks[...] = { ..., status:
     'passed' }`, `snapshot.status = 'blocked'` inside the `buildPassPayload`/`buildBailPayload`
     helpers -- are per-task and legitimate; this assertion must NOT flag them, and does not, because
     those helper function BODIES sit textually outside the loop's brace-matched region (they are
     defined once, above the loop, and only CALLED by name from inside it).

  C. `renderWorkAssertion` is defined AND actually invoked (not merely threaded through as a
     parameter) in both engines, AND the terminal state-write region (the "LEAN BOOKKEEP CLOSE-OUT"
     heading in sdlc-task.js / the "PHASE 5: WRAP-UP" heading in sdlc-flow.js, through end of file)
     references its outcome. Today it does not -- `renderWorkAssertion`'s files[]-vs-diff check is
     invoked only as PROSE inside the implement prompt's step 7a (BT.ticket.a-run-must-prove-its-
     commits-contain-the-work, closed, owns that half); nothing carries its result as a structured
     field into the terminal write. This is the assertion task 3 is expected to turn green.

  D. REGRESSION GUARD (AC 4, amended 2026-09-03): no operator-attributed verdict code path exists in
     either engine -- the incident named in the block's `why` was agent behaviour in a learn-ai
     content run, not engine code, so this asserts continued ABSENCE, not a removal. Uses the same
     pattern the block record's AC quotes verbatim: `operator[- ]?(sign|verdict|approv|attribut)|
     signed off|sign-off`, case-insensitive.

     Self-test (recorded here per the task's AC): this suite verified, AT RUN TIME, that assertion D
     is actually capable of failing -- not just vacuously true because the pattern is unreachable --
     by taking an in-memory COPY of each engine's text, injecting the literal string
     "operator sign-off" into it, re-running the same regex against the copy, and asserting that
     match trips. See `assertion_d_self_test()` below; its own result is folded into this script's
     exit code, so a change that breaks the self-test (e.g. a typo'd pattern) fails the run visibly
     rather than the demonstration silently going stale.

  E. POSITIVE CONTROL, must pass before and after A-D: both engine files were located, are
     non-empty, `renderWorkAssertion`'s definition was found, and each engine's terminal-write
     heading anchor was found. If a region slice comes back empty this fails, so A-D failing can
     never be mistaken for a bad slice.

TRAP: a piped command's exit code is the pipe's, not this script's -- redirect, then check `$?`
separately (never `python3 scripts/test_terminal_state_evidence.py | tail`).
TRAP: `node --check` is BLIND to a stray backtick placed after a top-level `export` in this Node
(measured 2026-09-03, see the run record) -- it is not used anywhere in this suite as a structural
control; `scripts/check_prompt_templates.py` is the check that actually detects that class of break,
and it is a separate validation command, not reimplemented here.

Registered in planning/harness.json (task 5) as `terminal-state-evidence` --
run directly: python3 scripts/test_terminal_state_evidence.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TASK_ENGINE_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"
FLOW_ENGINE_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"

# --- Assertion A: emitStateRan consistency -------------------------------------------------------
EMIT_STATE_RAN_TOKEN_RE = re.compile(r"\bemitStateRan\b")
# The object that is actually serialized to the on-disk state file is `state` (or its deep clone,
# `snapshot`) -- see `JSON.stringify(state, ...)` / `JSON.parse(JSON.stringify(state))` in both
# engines. A schema declaration or a log-line interpolation of `bookkeepResult.emitStateRan` /
# `wrapupResult.emitStateRan` does NOT put the key on disk; only an assignment onto `state.` or
# `snapshot.` does.
EMIT_STATE_RAN_PERSISTED_RE = re.compile(
    r"(?:state|snapshot)(?:\.emitStateRan\s*=|\[['\"]emitStateRan['\"]\]\s*=)"
)

# --- Assertion B: terminal RUN status never written inside the per-task loop ---------------------
PER_TASK_LOOP_ANCHOR_RE = re.compile(r"for\s*\(\s*const\s+taskNum\s+of\s+taskList\s*\)\s*\{")
# Forbidden: the top-level `state.status` (never `t.status`/`snapshot.tasks[...]`) assigned a
# 'done'/'passed' literal from inside the per-task loop body.
FORBIDDEN_TERMINAL_STATUS_RE = re.compile(
    r"\bstate\.status\s*=\s*[^;\n]*?(?:'done'|\"done\"|'passed'|\"passed\")"
)

# --- Assertion C: work assertion invoked + terminal write references its outcome -----------------
WORK_ASSERTION_DEF_RE = re.compile(r"function\s+renderWorkAssertion\s*\(")
# An actual call (not just being threaded through as a parameter name) -- `renderWorkAssertion(`
# followed by an argument list, distinct from the bare identifier passed around in destructured
# params/object literals.
WORK_ASSERTION_CALL_RE = re.compile(r"renderWorkAssertion\(\s*['\"a-zA-Z]")
TASK_TERMINAL_HEADING_RE = re.compile(r"LEAN BOOKKEEP CLOSE-OUT")
FLOW_TERMINAL_HEADING_RE = re.compile(r"PHASE 5: WRAP-UP")
WORK_ASSERTION_OUTCOME_TOKEN_RE = re.compile(r"workAssertion", re.IGNORECASE)

# --- Assertion D: regression guard -- no operator-attributed verdict path ------------------------
# The exact pattern the block record's AC 4 quotes, reused verbatim so the fixture and the AC can
# never silently drift apart.
OPERATOR_VERDICT_RE = re.compile(
    r"operator[- ]?(sign|verdict|approv|attribut)|signed off|sign-off", re.IGNORECASE
)
SELF_TEST_INJECTION = "operator sign-off"

# --- Assertion E: positive control -----------------------------------------------------------------


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


def _brace_body(text: str, open_brace_index: int) -> str | None:
    """Body of the block whose opening `{` sits at `open_brace_index` (index of the `{` itself)."""
    depth = 0
    for i in range(open_brace_index, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_index:i + 1]
    return None


def assertion_a(text: str, r: Result) -> None:
    occurrences = EMIT_STATE_RAN_TOKEN_RE.findall(text)
    occurrence_count = len(occurrences)
    line_count = sum(1 for line in text.splitlines() if EMIT_STATE_RAN_TOKEN_RE.search(line))
    if occurrence_count == 0:
        r.check("A (emitStateRan consistent: absent)", True,
                "absent from this engine -- consistent by omission")
        return
    persisted = bool(EMIT_STATE_RAN_PERSISTED_RE.search(text))
    r.check(
        "A (emitStateRan consistent: retained AND persisted to the state object)",
        persisted,
        f"retained ({line_count} line(s) / {occurrence_count} occurrence(s)) but never assigned "
        "onto `state.emitStateRan` / `snapshot.emitStateRan` -- schema declarations and log-line "
        "interpolations do not put the key on disk",
    )


def assertion_b(text: str, r: Result) -> None:
    anchor_m = PER_TASK_LOOP_ANCHOR_RE.search(text)
    if not anchor_m:
        r.check("B (terminal status never written inside the per-task loop)", False,
                "per-task loop anchor `for (const taskNum of taskList) {` not found")
        return
    loop_body = _brace_body(text, anchor_m.end() - 1)
    if loop_body is None:
        r.check("B (terminal status never written inside the per-task loop)", False,
                "could not brace-match the per-task loop body (unbalanced braces)")
        return
    violation = FORBIDDEN_TERMINAL_STATUS_RE.search(loop_body)
    r.check(
        "B (terminal status never written inside the per-task loop)",
        violation is None,
        "found `state.status = ... 'done'/'passed'` inside the per-task loop body -- terminal "
        "status must be stamped only from the terminal node"
        if violation else "",
    )


def assertion_c(text: str, r: Result, terminal_heading_re: re.Pattern[str]) -> None:
    def_ok = bool(WORK_ASSERTION_DEF_RE.search(text))
    call_ok = bool(WORK_ASSERTION_CALL_RE.search(text))
    heading_m = terminal_heading_re.search(text)
    if not heading_m:
        r.check("C (work assertion invoked and terminal write references its outcome)", False,
                f"def found={def_ok}, called={call_ok}, terminal-write heading not found")
        return
    terminal_region = text[heading_m.end():]
    outcome_referenced = bool(WORK_ASSERTION_OUTCOME_TOKEN_RE.search(terminal_region))
    ok = def_ok and call_ok and outcome_referenced
    r.check(
        "C (work assertion invoked and terminal write references its outcome)",
        ok,
        f"def found={def_ok}, called={call_ok}, terminal-write region references its outcome="
        f"{outcome_referenced} -- renderWorkAssertion is invoked only as prose in the implement "
        "prompt's step 7a; no structured field carries its result into the terminal write",
    )


def assertion_d(text: str, r: Result) -> None:
    m = OPERATOR_VERDICT_RE.search(text)
    r.check(
        "D (regression guard: no operator-attributed verdict path)",
        m is None,
        f"matched {m.group(0)!r} at offset {m.start()} -- an operator-sign-off-shaped construction "
        "was introduced" if m else "",
    )


def assertion_d_self_test(text: str, r: Result) -> None:
    """Demonstrate assertion D is capable of failing (task's own AC), not vacuously true.

    Takes an in-memory copy of the engine text -- never a file on disk, this suite writes nothing --
    injects the literal string "operator sign-off" partway through it, and asserts the SAME regex
    used by assertion_d() trips on the copy. If it did not, assertion D would be silently unable to
    ever catch a real regression.
    """
    midpoint = len(text) // 2
    injected = text[:midpoint] + f"\n// {SELF_TEST_INJECTION}\n" + text[midpoint:]
    tripped = OPERATOR_VERDICT_RE.search(injected) is not None
    r.check(
        "D self-test (regex demonstrably trips on an injected operator-verdict string)",
        tripped,
        f"injecting {SELF_TEST_INJECTION!r} into a copy of this engine's text did NOT trip "
        "OPERATOR_VERDICT_RE -- assertion D would never catch a real regression",
    )


def assertion_e(text: str, r: Result, terminal_heading_re: re.Pattern[str], engine_name: str) -> None:
    non_empty = len(text) > 0
    def_ok = bool(WORK_ASSERTION_DEF_RE.search(text))
    heading_ok = bool(terminal_heading_re.search(text))
    r.check(
        "E (positive control: file located, non-empty, renderWorkAssertion + terminal heading found)",
        non_empty and def_ok and heading_ok,
        f"{engine_name}: non_empty={non_empty}, renderWorkAssertion def found={def_ok}, "
        f"terminal-write heading found={heading_ok}",
    )


def run_engine(name: str, text: str | None, path: Path, r: Result,
               terminal_heading_re: re.Pattern[str]) -> None:
    r.prefix = f"[{name}] "
    if text is None:
        r.check("engine file exists", False, f"{path} not found")
        r.check("E (positive control)", False, f"{path} not found -- cannot be a bad-slice false "
                 "negative, the file itself is missing")
        return
    assertion_a(text, r)
    assertion_b(text, r)
    assertion_c(text, r, terminal_heading_re)
    assertion_d(text, r)
    assertion_d_self_test(text, r)
    assertion_e(text, r, terminal_heading_re, name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="only print output on failure")
    args = ap.parse_args(argv)

    r = Result()

    task_text = _read(TASK_ENGINE_PATH)
    run_engine("sdlc-task", task_text, TASK_ENGINE_PATH, r, TASK_TERMINAL_HEADING_RE)

    flow_text = _read(FLOW_ENGINE_PATH)
    run_engine("sdlc-flow", flow_text, FLOW_ENGINE_PATH, r, FLOW_TERMINAL_HEADING_RE)

    r.prefix = ""
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
