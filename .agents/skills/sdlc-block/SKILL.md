---
name: sdlc-block
description: >
  Trigger on '/sdlc-block' or requests to orchestrate a full spec through dependency-ordered waves of parallel task executions and ordered merges.
---

=============================================================================
sdlc-block — Lean Spec-Level SDLC Orchestration ("a more powerful /sdlc-run")
=============================================================================

Drives an ENTIRE spec to completion with a FRESH implement agent per task (deliberate per-task
context windows + observability — the one thing /sdlc-run lacks, since it implements all tasks in
one context) and ONE consolidated back-half over the integrated result. Setup is shared once per
block; per task runs lean (implement, + an optional localization review). Genuinely parallel waves
(≥2 independent tasks) use worktrees; the common sequential case runs in-place on the integration
branch. See decisions/D23 + D24. Generic: every path derives from the spec slug.

USAGE
  /sdlc-block <spec-slug>                       run every task in the spec
  /sdlc-block <spec-slug> 1-7                   run only tasks 1–7 (range/list selection)
  /sdlc-block <spec-slug> --tasks 1,3,5-7       same selection via explicit flag
  /sdlc-block <spec-slug> --verify-depth consolidated+review   per-task review on (default: off)
  /sdlc-block <spec-slug> --max-retries 2 --max-wave-width 4

  ARGS
    <specSlug>          required — the planning/<specSlug>/ directory name
    [range]             optional 2nd positional, or --tasks — e.g. 1-7, 1,3,5, 1-3,7. Default: all.
    --max-retries N     total implement attempts per task before escalation (default 2)
    --max-wave-width W   max worktree implements run concurrently per parallel batch (default 3)
    --verify-depth D    consolidated (default) | consolidated+review — per-task verification depth;
                        overrides planning/harness.json block.verify (D24)

DESIGN
  0. Pre-flight — guarantee a clean integration tree with the spec committed (generate/commit it;
       abort fast on unrelated dirt; D16/D19 structure + thin-spec guards) before any task runs.
  1. Analyze — resume-scout; load planning/<specSlug>/sdlc/execution-plan.json if present & valid
       (D22; authored by /generate-tasks), else an Opus agent emits the dependency graph and CODE
       computes the dependency-ordered waves. SHARED SETUP ONCE (D23): harness config loaded once,
       baseline snapshot captured once (only when a D6 baseline-diff check needs it).
  2. Per wave (lean — implement only, + an optional localization review; D23):
       - width-1 wave  -> run the task IN PLACE on the integration branch (no worktree, no merge).
         The pre-task HEAD is captured; a failed implement is `git reset --hard`'d back before retry.
       - width-≥2 wave -> isolate each task in a worktree via /sdlc-task --implement-only, then merge
         passing branches in task order (additive-union only; else escalate). True concurrent writers.
       - RETRY + TRIAGE per task: RETRYABLE -> clean-slate retry; MAJOR/exhausted -> ESCALATE.
         Escalation poisons ONLY the dependent subtree; independent tasks keep running.
  3. Consolidated back-half (D24) — ONLY when the block is complete (no escalations/skips): seed a
       spec-level implement report from the per-task reports, then run ONE
       test -> review -> fix -> (ui-test) -> document -> wrap-up over the integrated tree via
       workflow('sdlc-run', '<slug> --from test'). Its wrap-up owns status.md / log.md / the spec
       Amendment Log (D18). The consolidated review is AUTHORITATIVE; any per-task review is only a
       localization map. Replaces the old per-task back-half (~113k tokens × N -> 1×).
  4. Report — write the block-level report (per-task outcomes + escalations + breakdown assessment +
       token roll-up + back-half verdict). It does NOT touch status/log (the back-half owns those).

  block.verify (planning/harness.json) / --verify-depth:
    consolidated         (default) — per task: implement + the D8 completeness self-check only.
    consolidated+review            — per task: + one review pass (a localization map; non-gating).

RESUMPTION
  Re-run /sdlc-block <specSlug>. A task's implement commit on the integration branch (its
  taskN-implement.md) marks it landed -> skipped on re-run. Escalated tasks are retried after you fix
  the blocker (or edit execution-plan.json). The consolidated back-half re-runs once every task has
  landed. Leftover worktrees from a parallel wave are reconciled by the Analyze resume-scout.

NOTE — the consolidated back-half runs on the integration branch. When that branch is `main`, the
  universal emoji gate (which diffs `main..HEAD`) has no diff base and no-ops; the per-stage gating
  checks still run. Running the block on a dedicated integration branch off main restores emoji
  gating end-to-end and is the documented follow-up (D23/D24 "Reconsider if").

=============================================================================


## Antigravity Execution Guide

When the user asks you to run `/sdlc-block <spec-slug> [range]`, perform the spec-level orchestration:

1. **Pre-flight & Analyze**:
   - Ensure the tree is clean and the spec is committed.
   - Read `planning/<spec-slug>/sdlc/execution-plan.json` if it exists. If not, analyze the spec and create a dependency-ordered task plan.
2. **Execute Waves**:
   - Group independent tasks into execution waves.
   - For each wave:
     - If wave has 1 task: Run the task in-place on the integration branch.
     - If wave has multiple parallel tasks: Spawn parallel sub-agents (using `invoke_subagent` running `/sdlc-task`) to implement each task in its own worktree.
     - Wait for tasks to complete, then merge their branches/worktrees back to the integration branch.
3. **Consolidated Back-half**:
   - Once all tasks are merged, run a single consolidated pass of `test` -> `review` -> `fix` -> `document` -> `wrap-up` on the integrated branch to finalize the block.
