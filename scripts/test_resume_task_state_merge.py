#!/usr/bin/env python3
"""Fixture check: does sdlc-task.js's resume merge RULE keep every previously-passed
task in the committed `tasks` map, across one resume and across a second consecutive
resume -- and does the pre-fix rule (start `tasks` empty every invocation) actually
lose that history, proving this suite can fail?

WHY THIS RE-IMPLEMENTS THE MERGE RULE IN PYTHON RATHER THAN CALLING THE ENGINE
-------------------------------------------------------------------------------
`.claude/workflows/sdlc-task.js` runs under the Workflow harness runtime (agent
turns, Bash tool calls, a live model) and cannot be executed in-process from a
plain Python/CI check. So this suite mirrors the MERGE RULE the engine now
implements -- described in its own comment at the resume state-read call site
("seeds the in-memory `state.tasks` with the FULL prior tasks object ... before
the per-task loop below only ever populates `state.tasks[N]` for tasks it
actually runs") -- over fixture state files, and separately asserts the live
source actually declares the `tasksJson` field the rule depends on, so the
mirror cannot silently drift into testing a rule no engine implements.

UN-GATEABLE PART, STATED HONESTLY (D64)
----------------------------------------
That a REAL `/sdlc-task --resume` invocation writes the merged map to disk is
not something any in-repo check can observe: the engine executes under the
Workflow runtime and, per base-template CLAUDE.md standing rule 10, from a
launch-time snapshot taken when the session started. A green run of this suite
is evidence about the RULE (and that the shipped engine source declares the
field the rule needs), not evidence that a live resume, right now, in this
process, writes it. The live claim is evidenced only by a one-off manual
reproduction from a FRESH session, recorded in the run notes -- never by this
suite, and never by observing the run that is executing this very fix (the
self-modification hazard the ticket names explicitly).

WHAT THIS DOES
--------------
1. Mirrors the POST-FIX merge rule: state.tasks is seeded from the prior
   state file's full `tasks` object before the per-task loop runs, so a write
   after any invocation contains every task ever passed, not just this
   invocation's.
2. Mirrors the PRE-FIX rule: `tasks` starts `{}` fresh every invocation (the
   documented pre-fix defect) and shows it losing history on the very case the
   post-fix rule keeps -- if the "negative" case does not fail here, the
   diagnosis this ticket is built on is wrong.
3. Runs a first-invocation case (4 tasks pass), a single-resume case (task 5
   added), and the case that actually causes damage: bail, resume, bail again,
   resume again -- and asserts every invocation's write still carries the
   very first invocation's passed tasks forward.
4. Asserts `started_at` survives every merge unchanged, across both a normal
   write and a bail write.
5. Asserts `.claude/workflows/sdlc-task.js` mentions `tasksJson`, binding this
   mirror to the actual implementation rather than to an invented rule.

This is a GATING check (see `planning/harness.json`, `resume-task-state-merge-tests`).
"""

from __future__ import annotations

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


# --- the two candidate merge rules, mirrored from the engine's own comment --

def merge_rule_post_fix(prior_tasks: dict, prior_started_at: str | None,
                         this_invocation_tasks: dict) -> tuple[dict, str]:
    """The FIXED rule: seed state.tasks from the prior file's full tasks object,
    then let this invocation's per-task loop overwrite/extend individual keys.
    Mirrors sdlc-task.js: `Object.assign(state.tasks, priorTasks)` executed
    BEFORE the per-task loop populates state.tasks[N] for tasks it runs.
    """
    merged = dict(prior_tasks)
    merged.update(this_invocation_tasks)
    started_at = prior_started_at if prior_started_at else "NOW"
    return merged, started_at


def merge_rule_pre_fix(prior_tasks: dict, prior_started_at: str | None,
                        this_invocation_tasks: dict) -> tuple[dict, str]:
    """The DOCUMENTED PRE-FIX defect: `tasks: {}` initialized fresh every
    invocation (sdlc-task.js used to do this, unconditionally, regardless of
    --resume), so only tasks touched by THIS invocation's loop ever appear.
    started_at preservation is a separate code path and is unaffected by this
    particular defect, so it is mirrored identically here.
    """
    merged = dict(this_invocation_tasks)  # prior_tasks is NEVER consulted -- the bug
    started_at = prior_started_at if prior_started_at else "NOW"
    return merged, started_at


def passed_task_ids(tasks: dict) -> set[int]:
    return {int(k) for k, v in tasks.items() if v.get("status") == "passed"}


def make_task(status: str) -> dict:
    return {"status": status}


# --- case (a): first invocation, tasks 1-4 pass ------------------------------

def check_first_invocation() -> dict:
    """Simulates invocation 1: no prior state file exists, tasks 1-4 all run and
    pass. Returns the resulting `tasks` map (the on-disk state after this
    invocation) for use as the prior state of the next case.
    """
    prior_tasks: dict = {}
    prior_started_at = None
    this_run = {str(n): make_task("passed") for n in range(1, 5)}

    merged, started_at = merge_rule_post_fix(prior_tasks, prior_started_at, this_run)

    check(
        "(a) first invocation: tasks 1-4 all recorded passed",
        passed_task_ids(merged) == {1, 2, 3, 4},
        f"got {sorted(passed_task_ids(merged))}",
    )
    check(
        "(a) first invocation: started_at stamped (no prior to preserve)",
        started_at == "NOW",
    )
    return merged


# --- case (b): resume runs task 5, must NOT lose 1-4 -------------------------

def check_single_resume(prior_tasks_after_invocation_1: dict) -> dict:
    prior_started_at = "2026-08-01T00:00:00Z"
    this_run = {"5": make_task("passed")}

    merged, started_at = merge_rule_post_fix(
        prior_tasks_after_invocation_1, prior_started_at, this_run
    )

    check(
        "(b) resume: tasks map contains 1,2,3,4 AND 5, not just 5",
        passed_task_ids(merged) == {1, 2, 3, 4, 5},
        f"got {sorted(passed_task_ids(merged))}",
    )
    check(
        "(b) resume: started_at preserved from prior file, not restamped",
        started_at == prior_started_at,
        f"got {started_at!r}",
    )
    return merged


# --- case (c): the damaging one -- bail, resume, bail again, resume again ---

def check_second_resume_chain(prior_tasks_after_invocation_1: dict) -> None:
    """Invocation 2: runs task 5, then BAILS on task 6 (a MAJOR-class bail writes
    state too, per renderBailStateWriteRecipe -- the merge must apply there
    exactly as it does on a passing write). Invocation 3: resumes at task 6,
    which finally passes. Assert invocation 3's final map still carries
    invocation 1's tasks 1-4 -- this is the case a single-resume fixture does
    not exercise, and it is the one that actually causes re-run damage: a
    third invocation deciding what to skip from a map that dropped history at
    invocation 2 would re-run already-landed work.
    """
    started_at = "2026-08-01T00:00:00Z"

    # Invocation 2: resume from invocation-1's file, run task 5 (passes), then
    # bail on task 6. The bail write happens with state.tasks already seeded
    # from invocation 1 (mirrors the engine: the seed happens once at resume
    # time, before either the per-task loop or a mid-loop bail write).
    invocation_2_this_run = {
        "5": make_task("passed"),
        "6": make_task("running"),  # bail leaves the in-progress task un-passed
    }
    invocation_2_write, sa2 = merge_rule_post_fix(
        prior_tasks_after_invocation_1, started_at, invocation_2_this_run
    )

    check(
        "(c) invocation 2 (mid-chain bail write): 1-4 still present alongside 5",
        {1, 2, 3, 4, 5}.issubset(passed_task_ids(invocation_2_write)),
        f"got {sorted(passed_task_ids(invocation_2_write))}",
    )

    # Invocation 3: resume again, reading invocation 2's file (which itself
    # only reflects invocation 1 + task 5 + a running task 6). Task 6 now runs
    # and passes.
    invocation_3_this_run = {"6": make_task("passed")}
    final_merged, sa3 = merge_rule_post_fix(invocation_2_write, sa2, invocation_3_this_run)

    check(
        "(c) SECOND resume (the damaging case): invocation 1's tasks 1-4 survive two resumes later",
        {1, 2, 3, 4}.issubset(passed_task_ids(final_merged)),
        f"got {sorted(passed_task_ids(final_merged))}",
    )
    check(
        "(c) second resume: all of 1-6 present in the final map",
        passed_task_ids(final_merged) == {1, 2, 3, 4, 5, 6},
        f"got {sorted(passed_task_ids(final_merged))}",
    )
    check(
        "(c) second resume: started_at threaded through three invocations unchanged",
        sa3 == started_at,
        f"got {sa3!r}",
    )


# --- case (d): started_at preserved through a BAIL write specifically -------

def check_started_at_preserved_through_bail() -> None:
    prior_tasks = {"1": make_task("passed"), "2": make_task("passed")}
    prior_started_at = "2026-07-15T12:00:00Z"
    # A bail write: the in-flight task is recorded as failed/running, not passed.
    this_run = {"3": make_task("running")}

    merged, started_at = merge_rule_post_fix(prior_tasks, prior_started_at, this_run)

    check(
        "(d) started_at preserved across a bail write, not restamped to NOW",
        started_at == prior_started_at,
        f"got {started_at!r}",
    )
    check(
        "(d) bail write still carries prior passed tasks forward",
        {1, 2}.issubset(passed_task_ids(merged)),
        f"got {sorted(passed_task_ids(merged))}",
    )


# --- case (e): the pre-fix rule must LOSE case (b) ---------------------------

def check_pre_fix_rule_loses(prior_tasks_after_invocation_1: dict) -> None:
    """Proves the suite is capable of failing: apply the DOCUMENTED PRE-FIX rule
    (tasks: {} fresh every invocation) to the exact same resume scenario as
    case (b), and assert it drops tasks 1-4 -- i.e. the pre-fix rule FAILS the
    assertion case (b) makes. If this rule did NOT lose history, the ticket's
    diagnosis of the original defect would be wrong.
    """
    prior_started_at = "2026-08-01T00:00:00Z"
    this_run = {"5": make_task("passed")}

    pre_fix_merged, _ = merge_rule_pre_fix(
        prior_tasks_after_invocation_1, prior_started_at, this_run
    )

    check(
        "(e) pre-fix rule LOSES tasks 1-4 on the same resume case (b) keeps -- proves the defect was real",
        passed_task_ids(pre_fix_merged) == {5},
        f"got {sorted(passed_task_ids(pre_fix_merged))} (expected ONLY {{5}} under the buggy rule)",
    )
    check(
        "(e) pre-fix rule: the post-fix rule on the identical inputs does NOT lose them (contrast)",
        passed_task_ids(
            merge_rule_post_fix(prior_tasks_after_invocation_1, prior_started_at, this_run)[0]
        )
        == {1, 2, 3, 4, 5},
    )


# --- binding the mirror to the real implementation ---------------------------

def check_engine_declares_tasks_json() -> None:
    check(
        "sdlc-task.js exists",
        SDLC_TASK_JS.is_file(),
        f"not found at {SDLC_TASK_JS}",
    )
    if not SDLC_TASK_JS.is_file():
        return
    text = SDLC_TASK_JS.read_text(encoding="utf-8")
    check(
        "sdlc-task.js's resume state-read schema declares a tasksJson field",
        "tasksJson" in text,
        "no occurrence of 'tasksJson' found -- the mirrored merge rule above tests "
        "a rule the engine does not implement",
    )
    check(
        "sdlc-task.js seeds state.tasks from the prior tasks object (Object.assign carry-forward)",
        "Object.assign(state.tasks, priorTasks)" in text,
        "expected the carry-forward seed line copied from sdlc-flow.js's shape; "
        "not found verbatim -- re-check the implementation still matches this mirror",
    )


def main() -> int:
    invocation_1_tasks = check_first_invocation()
    invocation_2_tasks = check_single_resume(invocation_1_tasks)
    check_second_resume_chain(invocation_1_tasks)
    check_started_at_preserved_through_bail()
    check_pre_fix_rule_loses(invocation_1_tasks)
    check_engine_declares_tasks_json()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- resume tasks-map merge rule holds, second-resume chain preserves "
          "invocation-1 history, pre-fix rule demonstrably loses it, and sdlc-task.js "
          "implements the field this mirror depends on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
