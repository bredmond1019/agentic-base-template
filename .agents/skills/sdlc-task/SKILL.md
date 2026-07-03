---
name: sdlc-task
description: >
  >
---

=============================================================================
 sdlc-task — the LEAN small-work engine (implement → test → fix → commit)
 =============================================================================

 The cheap rung of the pipeline ladder, for one small unit of behaviour-changing
 work (a /ticket or /chore). Runs a spec's task(s) through a tight per-task loop —
   implement → fast gating-test → triage → fix (≤3 attempts, Opus on the last)
   → commit
 and nothing else. No scout, no separate review, no document stage, no ui-test,
 no wrap-up agent, no PR. When you need a consolidated review + docs + a PR, use
 /sdlc-flow; for a whole spec in place, /sdlc-run; for a roadmap, /sdlc-block.

 ISOLATION
   Default: IN PLACE on the current branch (no worktree) — cheapest, like /sdlc-run.
   --worktree: run in an isolated git worktree on its own branch (you integrate the
   branch yourself when ready). Opt-in only.

 USAGE
   /sdlc-task <spec-slug>                 run every task in the spec, in place
   /sdlc-task <spec-slug> 2               run only task 2
   /sdlc-task <spec-slug> 1-3             run a task range (1-3, 1,3,5, 5)
   /sdlc-task <spec-slug> 2 --worktree    run task 2 in an isolated worktree/branch
   /sdlc-task <spec-slug> --resume        resume from the committed state file
   /sdlc-task <spec-slug> --test-depth full  full gating suite per task (default: fast)

 PIPELINE
   setup (locate repo / create worktree) → enumerate (D16 lint) → [resume load]
     → per-task loop → final state commit

   Per-task loop (sequential):
     implement → fast-test → (triage → fix/bail) ×≤3 → one state write per task
   A triage MAJOR / immediate-bail reason breaks straight out (does NOT burn the
   remaining attempts); the run stops and reports for human pickup.

 STATE (committed — NOT gitignored — at planning/<spec>/sdlc/)
   sdlc-task-state.json   the authoritative run index (per-task summary/issues/
                          fixes/commit + the Block-A `tokens` block). Committed in the
                          worktree under --worktree; in place it is written uncommitted
                          each task (cat-visible for crash inspection) and swept into
                          ONE final `chore:` commit at the end.

 COMMIT STRATEGY
   feat: implement <stem>         implement agent (per task)
   fix:  fix pass P for <stem>    fix agent (per pass)
   chore: sdlc-task state — <…>   state-writer (committed writes)

 MODEL TIERING (the token lever — see the MODEL map below)
   haiku : setup, enumerate, state-load, test, state-writer
   sonnet: implement, fix, triage
   opus  : ESCALATION on the FINAL per-task fix pass

 IMPLEMENTATION RULE: engines are self-contained — lift, don't import. No cross-engine
 require. Validation is downstream only; never run this against base-template itself.
 =============================================================================

## Antigravity Execution Guide

When the user asks you to run `/sdlc-task <spec-slug> <taskNumber>`, do NOT run `sdlc-task.js`. Instead, perform the task isolation yourself:

1. **Worktree Setup**:
   - Determine the worktree path: `trees/<spec-slug>-task<taskNumber>`.
   - Create a git worktree and check out a dedicated branch:
     `git worktree add -b sdlc/<spec-slug>/task<taskNumber> trees/<spec-slug>-task<taskNumber>`
2. **Execute SDLC Run**:
   - Inside the worktree directory, execute the `sdlc-run` workflow (Scout -> Plan -> Implement -> Test -> Review -> Document -> Wrap-up) scoped to task `taskNumber`.
   - Write all reports and commits inside the worktree repository.
   - Do NOT update the main branch's `status.md` or `log.md` files; write a task log file in the reports directory instead.
3. **Finish**:
   - Report the worktree path and branch name to the user.








