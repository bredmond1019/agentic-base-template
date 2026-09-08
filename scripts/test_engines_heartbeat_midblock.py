#!/usr/bin/env python3
"""Structural completeness fixture: both SDLC engines re-stamp the holding lane's heartbeat from
inside their per-task test-stage gate (BT.ticket.lane-heartbeat-goes-stale-mid-block, task 4).

WHY THIS EXISTS
----------------
A long block previously only re-stamped its claim+lease heartbeat at block boundaries (the
release-and-re-take /orchestrate rule 10 already performs), which lets a claim/lease go stale
mid-block on a long-running task. Task 4 wires `scripts/lane_heartbeat.py` into the per-task test
stage -- each engine's `test-${taskNum}-${attempt}` gate, rendered by `runTests()` -- so a long
block re-stamps between tasks too. A bare reference to `scripts/lane_heartbeat.py` ANYWHERE in an
engine file is not enough: it must actually sit on the path from `runTests()` (the function that
IS that gate) to `renderTestPrompt()` (the function that builds the prompt actually SENT to the
test agent), or a later refactor could compute it and silently drop it, or move it to a helper
never reached, and this suite would still pass. Modelled on scripts/test_engines_pass_agent.py's
region-scoped assertion shape: locate the relevant function bodies structurally (brace-depth
counting, not a fixed line-count slice) and assert properties of what is inside each, rather than
grepping the whole file.

WHAT THIS ASSERTS, per engine (sdlc-task.js and sdlc-flow.js):
  1. `runTests()` calls the `renderLaneHeartbeatRecipe()` helper AND threads its result
     (`heartbeatRecipe`) into the SAME `renderTestPrompt(...)` call that builds the prompt sent to
     the test agent -- computing it without passing it through would never reach the agent.
  2. `renderTestPrompt()` interpolates `${heartbeatRecipe...}` into its OWN returned template --
     accepting the parameter without using it would make step 1's plumbing a dead argument.
  3. `renderLaneHeartbeatRecipe()` itself invokes `scripts/lane_heartbeat.py`, threads an --agent
     identity via `agentFlag` on that exact invocation line, suffixes it `|| true` (non-fatal --
     a lane with no live claim/lease must not fail the task because of this), and resolves that
     identity via `await renderAgentFlag()` -- the SAME resolver these engines already use for
     `mev emit-state --write`'s `--agent` flag (see scripts/test_engines_pass_agent.py), never a
     second, invented identity source.

This is a GATING check (registered in planning/harness.json by this same task, per its
validation_commands).

Usage:
    python3 scripts/test_engines_heartbeat_midblock.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"
FLOW_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"

HEARTBEAT_SCRIPT = "scripts/lane_heartbeat.py"
HELPER_NAME = "renderLaneHeartbeatRecipe"


def extract_function_region(text: str, decl_re: str, label: str) -> str:
    """Return the full source of the first function whose declaration matches `decl_re` (which
    must match through the OPENING `(` of the parameter list, e.g. `r"async function foo\\("`),
    located by depth-counting parens (to skip the parameter list, which may itself contain
    destructuring braces and nested calls like `new Set()`) and then depth-counting braces (to
    find the matching function body close). A fixed line-count slice, or a regex that assumes the
    parameter list contains no parentheses of its own, would silently stop covering the function
    the moment it grows, shrinks, or gains a nested call in its default params."""
    m = re.search(decl_re, text)
    if not m:
        raise AssertionError(f"{label}: no function found matching {decl_re!r}")
    paren_start = m.end() - 1
    depth = 0
    i = paren_start
    for i in range(paren_start, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
    else:
        raise AssertionError(f"{label}: unbalanced parens scanning params from offset {m.start()}")
    brace_start = text.index("{", i)
    depth = 0
    for j in range(brace_start, len(text)):
        ch = text[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[m.start() : j + 1]
    raise AssertionError(f"{label}: unbalanced braces scanning body from offset {brace_start}")


def check_engine(path: Path) -> list[str]:
    failures: list[str] = []
    text = path.read_text()
    rel = path.relative_to(REPO_ROOT)

    # --- 1. runTests() -- the function that IS the per-task test-stage gate -----------------
    try:
        run_tests_region = extract_function_region(
            text, r"async function runTests\(", str(rel)
        )
    except AssertionError as exc:
        return [str(exc)]

    if f"{HELPER_NAME}(" not in run_tests_region:
        failures.append(
            f"{rel}: runTests() does not call {HELPER_NAME}() -- the heartbeat re-stamp is not "
            "wired into the per-task test-stage gate"
        )

    render_call_match = re.search(r"renderTestPrompt\(\{.*?\}\)", run_tests_region, re.S)
    if not render_call_match:
        failures.append(f"{rel}: runTests() has no renderTestPrompt({{...}}) call")
    elif "heartbeatRecipe" not in render_call_match.group(0):
        failures.append(
            f"{rel}: the renderTestPrompt(...) call inside runTests() does not pass "
            "heartbeatRecipe -- computing it without threading it into the prompt call never "
            "reaches the test agent"
        )

    # --- 2. renderTestPrompt() -- the function that builds the prompt sent to the test agent -
    try:
        render_test_prompt_region = extract_function_region(
            text, r"function renderTestPrompt\(", str(rel)
        )
    except AssertionError as exc:
        failures.append(str(exc))
        render_test_prompt_region = ""
    if render_test_prompt_region and "heartbeatRecipe" not in render_test_prompt_region:
        failures.append(
            f"{rel}: renderTestPrompt() does not interpolate heartbeatRecipe into its returned "
            "prompt text -- the value is accepted but never reaches the test agent"
        )

    # --- 3. renderLaneHeartbeatRecipe() -- the helper that actually invokes the script --------
    try:
        helper_region = extract_function_region(
            text, rf"async function {HELPER_NAME}\(", str(rel)
        )
    except AssertionError as exc:
        return failures + [str(exc)]

    if HEARTBEAT_SCRIPT not in helper_region:
        failures.append(f"{rel}: {HELPER_NAME}() does not reference {HEARTBEAT_SCRIPT}")
    else:
        invocation_line_match = re.search(
            rf"^.*{re.escape(HEARTBEAT_SCRIPT)}.*$", helper_region, re.M
        )
        assert invocation_line_match, "unreachable -- membership already checked above"
        line = invocation_line_match.group(0)
        if "agentFlag" not in line:
            failures.append(
                f"{rel}: the {HEARTBEAT_SCRIPT} invocation line does not thread `agentFlag` -- "
                f"got: {line.strip()!r}"
            )
        if "|| true" not in line:
            failures.append(
                f"{rel}: the {HEARTBEAT_SCRIPT} invocation is not suffixed `|| true` (non-fatal) "
                f"-- a lane with no live claim/lease would bail the task. got: {line.strip()!r}"
            )

    if "await renderAgentFlag()" not in helper_region:
        failures.append(
            f"{rel}: {HELPER_NAME}() does not resolve identity via `await renderAgentFlag()` -- "
            "a second, invented identity source may have been used instead of the resolver these "
            "engines already thread to `mev emit-state --write`"
        )

    return failures


def main() -> int:
    failures: list[str] = []
    for path in (TASK_JS, FLOW_JS):
        failures.extend(check_engine(path))

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print(
        "OK: both engines wire scripts/lane_heartbeat.py into their per-task test-stage gate, "
        "threading --agent identity via renderAgentFlag(), non-fatally"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
