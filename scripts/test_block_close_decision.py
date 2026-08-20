#!/usr/bin/env python3
"""Fixture check: does sdlc-task.js's block-close RULE close the block exactly
when every task in the spec has passed -- across a resume that lands the last
task, a genuine subset run that leaves tasks outstanding, and a bail -- and do
the OLD rule (fullRun proxy) and the NAIVE repair (un-AND fullRun but compare
against taskList) each actually lose one of those cases, proving this suite
can fail?

WHY THIS RE-IMPLEMENTS THE CLOSE RULE IN PYTHON RATHER THAN CALLING THE ENGINE
-------------------------------------------------------------------------------
`.claude/workflows/sdlc-task.js` runs under the Workflow harness runtime (agent
turns, Bash tool calls, a live model) and cannot be executed in-process from a
plain Python/CI check. So this suite mirrors the CLOSE RULE the engine now
implements -- described in its own comment beside `blockDone` ("the honest
close condition is computed over the FULL SPEC (allTasks), never from taskList
... comparing against allTasks makes the condition honest on its own") -- over
fixture run-states, and separately asserts the live source actually computes
the condition over `allTasks` and carries no `fullRun`-style selection proxy
in it, so the mirror cannot silently drift into testing a rule no engine
implements.

UN-GATEABLE PART, STATED HONESTLY (D64)
----------------------------------------
That a REAL `/sdlc-task --resume` invocation flips `state.json` to `closed` on
disk is not something any in-repo check can observe: the engine executes under
the Workflow runtime and, per base-template CLAUDE.md standing rule 10, from a
launch-time snapshot taken when the session started. A green run of this suite
is evidence about the RULE (and that the shipped engine source implements the
rule this mirror depends on), not evidence that a live resume, right now, in
this process, writes the closed status. The live claim is evidenced only by a
one-off manual reproduction from a FRESH session, recorded in the run notes --
never by this suite, and never by observing the run executing this very fix
(the self-modification hazard the ticket names explicitly).

WHAT THIS DOES
--------------
1. Mirrors the FIXED rule: blockDone = not bailed and not reconcileFailed and
   passedAll.length == allTasks.length, where passedAll is filtered against
   allTasks (the full enumerated spec), never against taskList (the selected
   subset).
2. Case 1 -- a resume that lands the final outstanding task (6-task spec,
   tasks 1-5 already passed, this invocation resumes and passes task 6):
   the fixed rule CLOSES the block.
3. Case 2 -- a genuine subset run that leaves tasks outstanding (6-task spec,
   only task 3 has ever passed, this invocation runs --tasks 3 alone and it
   passes again): the fixed rule does NOT close the block. This is the real
   risk of the fix, not a nice-to-have case.
4. Case 3 -- a bail never closes the block, regardless of how many tasks have
   passed (even if every task happens to already show passed=True elsewhere,
   a bailed run must not close).
5. Case 4 -- the OLD rule (fullRun = !selectedTasks, gating the close
   unconditionally) is mirrored explicitly and shown to LOSE case 1: a
   completed resume names a selection, so fullRun is False and the old rule
   declines to close a spec that has, in fact, fully passed.
6. Case 5 -- the NAIVE repair (drop fullRun, but keep comparing
   passedTasks.length == taskList.length where taskList is the SELECTED
   subset) is mirrored explicitly and shown to LOSE case 2: on a subset run
   taskList IS the selection, so the comparison is trivially true and the
   naive repair closes a block that still has outstanding tasks -- the exact
   regression the ticket exists to prevent.
7. Asserts `.claude/workflows/sdlc-task.js` computes `blockDone` over
   `allTasks` (via a `passedAll` filtered against `allTasks`) and that the
   `blockDone` line itself carries no `fullRun` reference, binding this mirror
   to the actual implementation rather than to an invented rule.

This is a GATING check (see `planning/harness.json`, `block-close-decision-tests`).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SDLC_TASK_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"

# --- FAIL accounting ---------------------------------------------------------

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


# --- the three candidate close rules -----------------------------------------

def fixed_rule(all_tasks: list[int], task_list: list[int], passed_this_run: set[int],
               passed_from_prior: set[int], bailed: bool, reconcile_failed: bool) -> bool:
    """THE FIX (task 1 of this ticket): close iff every task in the FULL SPEC
    (allTasks) has passed -- either this run or a prior one -- and the run
    neither bailed nor failed reconciliation. No selection proxy involved.
    """
    passed_all = {n for n in all_tasks if n in passed_this_run or n in passed_from_prior}
    return (not bailed) and (not reconcile_failed) and len(passed_all) == len(all_tasks)


def old_rule(all_tasks: list[int], task_list: list[int], selected_tasks: set[int] | None,
             passed_this_run: set[int], passed_from_prior: set[int],
             bailed: bool, reconcile_failed: bool) -> bool:
    """THE OLD (pre-fix) rule: fullRun = !selectedTasks gates the close
    unconditionally, regardless of whether every task actually passed.
    passedTasks is filtered against taskList (the selected list), matching
    the pre-fix source at sdlc-task.js:1848-1849 before this ticket.
    """
    full_run = selected_tasks is None
    passed_tasks = {n for n in task_list if n in passed_this_run or n in passed_from_prior}
    return (not bailed) and (not reconcile_failed) and full_run and len(passed_tasks) == len(task_list)


def naive_repair_rule(all_tasks: list[int], task_list: list[int], passed_this_run: set[int],
                       passed_from_prior: set[int], bailed: bool, reconcile_failed: bool) -> bool:
    """THE NAIVE REPAIR the ticket explicitly warns against: drop the fullRun
    guard but leave the comparison scoped to taskList (the SELECTED subset,
    not the full spec). On a subset run taskList IS the selection, so the
    comparison is trivially true and this rule wrongly closes.
    """
    passed_tasks = {n for n in task_list if n in passed_this_run or n in passed_from_prior}
    return (not bailed) and (not reconcile_failed) and len(passed_tasks) == len(task_list)


# --- case 1: resume lands the final outstanding task -------------------------

def check_case_1_resume_completes_spec() -> None:
    """6-task spec. Tasks 1-5 already passed in a prior invocation. This
    invocation resumes with a selection of just task 6, which passes.
    """
    all_tasks = [1, 2, 3, 4, 5, 6]
    selected_tasks = {6}
    task_list = [6]
    passed_this_run = {6}
    passed_from_prior = {1, 2, 3, 4, 5}
    bailed = False
    reconcile_failed = False

    result = fixed_rule(all_tasks, task_list, passed_this_run, passed_from_prior, bailed, reconcile_failed)
    check(
        "(1) fixed rule: a resume landing the final outstanding task CLOSES the block",
        result is True,
        f"got {result}",
    )


# --- case 2: genuine subset run leaves tasks outstanding ----------------------

def check_case_2_subset_run_leaves_outstanding() -> None:
    """6-task spec. Only task 3 has ever passed (in this run). Tasks 1,2,4,5,6
    remain outstanding -- a deliberate one-off re-run of task 3, not a resume
    finishing the spec.
    """
    all_tasks = [1, 2, 3, 4, 5, 6]
    selected_tasks = {3}
    task_list = [3]
    passed_this_run = {3}
    passed_from_prior: set[int] = set()
    bailed = False
    reconcile_failed = False

    result = fixed_rule(all_tasks, task_list, passed_this_run, passed_from_prior, bailed, reconcile_failed)
    check(
        "(2) fixed rule: a subset run leaving tasks outstanding does NOT close the block",
        result is False,
        f"got {result}",
    )


# --- case 3: a bail never closes, regardless of counts -----------------------

def check_case_3_bail_never_closes() -> None:
    """Even if every task in the spec shows passed somewhere, a bailed run
    must not close the block -- bailed/reconcile_failed are hard gates.
    """
    all_tasks = [1, 2, 3]
    task_list = [1, 2, 3]
    passed_this_run = {1, 2, 3}
    passed_from_prior: set[int] = set()

    result_bailed = fixed_rule(all_tasks, task_list, passed_this_run, passed_from_prior, True, False)
    check(
        "(3a) fixed rule: bailed=True never closes, even with every task passed",
        result_bailed is False,
        f"got {result_bailed}",
    )

    result_reconcile_failed = fixed_rule(all_tasks, task_list, passed_this_run, passed_from_prior, False, True)
    check(
        "(3b) fixed rule: reconcile_failed=True never closes, even with every task passed",
        result_reconcile_failed is False,
        f"got {result_reconcile_failed}",
    )


# --- case 4: the OLD rule loses case 1 ----------------------------------------

def check_case_4_old_rule_loses_case_1() -> None:
    """Apply the pre-fix rule (fullRun = !selectedTasks) to the exact scenario
    of case 1 -- a resume that lands the last outstanding task. The old rule
    must decline to close, because a selection was passed (fullRun is False)
    -- this is the diagnosed defect itself. If the old rule did NOT lose this
    case, the ticket's diagnosis would be wrong.
    """
    all_tasks = [1, 2, 3, 4, 5, 6]
    selected_tasks = {6}
    task_list = [6]
    passed_this_run = {6}
    passed_from_prior = {1, 2, 3, 4, 5}

    result = old_rule(all_tasks, task_list, selected_tasks, passed_this_run, passed_from_prior, False, False)
    check(
        "(4) OLD rule (fullRun proxy) LOSES case 1 -- declines to close a fully-passed resume",
        result is False,
        f"got {result} (expected False under the pre-fix rule)",
    )
    check(
        "(4) contrast: the fixed rule on the identical inputs DOES close",
        fixed_rule(all_tasks, task_list, passed_this_run, passed_from_prior, False, False) is True,
    )


# --- case 5: the NAIVE repair loses case 2 ------------------------------------

def check_case_5_naive_repair_loses_case_2() -> None:
    """Apply the naive repair (drop fullRun, compare against taskList, the
    SELECTED subset) to the exact scenario of case 2 -- a deliberate one-off
    re-run of a single task with others outstanding. Because taskList IS the
    selection {3}, passedTasks.length == taskList.length is trivially true and
    the naive repair wrongly closes -- the exact regression the ticket warns
    against ("a two-character change that silently makes every partial run
    close its block").
    """
    all_tasks = [1, 2, 3, 4, 5, 6]
    task_list = [3]
    passed_this_run = {3}
    passed_from_prior: set[int] = set()

    result = naive_repair_rule(all_tasks, task_list, passed_this_run, passed_from_prior, False, False)
    check(
        "(5) NAIVE repair (un-AND fullRun, compare against taskList) LOSES case 2 -- "
        "wrongly closes a subset run with tasks still outstanding",
        result is True,
        f"got {result} (expected True under the naive repair -- proving it regresses)",
    )
    check(
        "(5) contrast: the fixed rule on the identical inputs does NOT close",
        fixed_rule(all_tasks, task_list, passed_this_run, passed_from_prior, False, False) is False,
    )


# --- binding the mirror to the real implementation ---------------------------

def check_engine_implements_fixed_rule() -> None:
    check(
        "sdlc-task.js exists",
        SDLC_TASK_JS.is_file(),
        f"not found at {SDLC_TASK_JS}",
    )
    if not SDLC_TASK_JS.is_file():
        return
    text = SDLC_TASK_JS.read_text(encoding="utf-8")

    check(
        "sdlc-task.js computes a passedAll set filtered against allTasks",
        bool(re.search(r"passedAll\s*=\s*allTasks\.filter", text)),
        "no `passedAll = allTasks.filter(...)` found -- the mirrored fixed rule above "
        "tests a rule the engine does not implement",
    )

    m = re.search(r"const\s+blockDone\s*=\s*([^\n;]+);?", text)
    check(
        "sdlc-task.js declares a blockDone condition",
        m is not None,
        "no `const blockDone = ...` line found",
    )
    if m:
        blockdone_expr = m.group(1)
        check(
            "blockDone is computed against passedAll/allTasks (the full spec), not taskList",
            "passedAll" in blockdone_expr and "allTasks" in blockdone_expr,
            f"got: {blockdone_expr!r}",
        )
        check(
            "blockDone no longer references fullRun (the selection proxy)",
            "fullRun" not in blockdone_expr,
            f"got: {blockdone_expr!r} -- fullRun must not gate the close",
        )

    check(
        "sdlc-task.js still reports the close decision in terminal output (Block done:)",
        "Block done:" in text,
        "expected an explicit reported close decision line",
    )
    check(
        "sdlc-task.js names outstanding tasks when the block does not close",
        "outstandingTasks" in text or "outstanding" in text,
        "expected the engine to name which tasks are still outstanding",
    )


def main() -> int:
    check_case_1_resume_completes_spec()
    check_case_2_subset_run_leaves_outstanding()
    check_case_3_bail_never_closes()
    check_case_4_old_rule_loses_case_1()
    check_case_5_naive_repair_loses_case_2()
    check_engine_implements_fixed_rule()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- block-close rule closes exactly when every task in the full spec has "
          "passed, a resume completing the spec closes, a genuine subset run does not, a "
          "bail never closes, the old fullRun-proxy rule demonstrably loses the resume "
          "case, the naive un-guarded repair demonstrably loses the subset case, and "
          "sdlc-task.js implements the rule this mirror depends on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
