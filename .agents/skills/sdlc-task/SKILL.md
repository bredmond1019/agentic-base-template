---
name: sdlc-task
description: >
  Custom skill: sdlc-task
---

=============================================================================
 sdlc-task — the LEAN small-work engine (implement → test → fix → commit)
 =============================================================================

 The cheap rung of the pipeline ladder, for one small unit of behaviour-changing
 work (a /ticket or /chore). Runs a spec's task(s) through a tight per-task loop —
   implement → fast gating-test → triage → fix (≤3 attempts, Opus on the last)
   → commit → lean bookkeep close-out
 and nothing else. No scout, no separate review, no document stage, no ui-test, no
 PR. The bookkeep close-out is deliberately lean: on a passing full run it flips the
 authored status markers (tasks.md task status, the status.md Progress row, the
 state.json block status) and — in place, on main — runs `mev emit-state --write`; it
 does NOT write a log.md narrative, a D18 amendment log, or run review/docs/PR. Run
 /log-work for the narrative. When you need a consolidated review + docs + a PR, use
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
     → per-task loop → lean bookkeep close-out (on pass) → final state commit

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
   chore: sdlc-task bookkeep — <…>  bookkeep close-out (on a passing run)

 MODEL TIERING (the token lever — see the MODEL map below)
   haiku : setup, enumerate, state-load, test, state-writer, bookkeep
   sonnet: implement, fix, triage
   opus  : ESCALATION on the FINAL per-task fix pass

 IMPLEMENTATION RULE: engines are self-contained — lift, don't import. No cross-engine
 require. Validation is downstream only; never run this against base-template itself.
 =============================================================================

## Antigravity Execution Guide

When the user asks you to run `/sdlc-task <spec-slug> [taskNumber]` and you cannot invoke
`sdlc-task.js` directly, replicate the lean engine (do NOT substitute `sdlc-run` — this is the cheap
rung, not the full pipeline):

1. **Isolation**:
   - Default is IN PLACE on the current branch. Only create a worktree if the user passed `--worktree`
     (path `trees/<spec-slug>-task<taskNumber>`, branch `sdlc/<spec-slug>/task<taskNumber>`).
2. **Per-task loop** (implement → fast gating-test → triage → fix ≤3, Opus on the last → commit).
3. **Lean bookkeep close-out** (on a passing run only — skip on a bail):
   - Mark the passed tasks done in `planning/<spec>/tasks.md`.
   - On a full passing run, flip the spec's `planning/status.md` Progress row to "Done" and flip the
     matching block in `planning/state.json` `tracks[].blocks[].status` to `"closed"` (resolve the
     canonical block id from the status.md row; do not fabricate a block; skip if there is no
     `state.json`). On a task subset, keep the spec "In progress" and do NOT close the block.
   - In place (on main), run `mev emit-state --write` to regenerate derived surfaces (skip silently
     if `mev`/`brain.toml` is absent). In a worktree, skip emit-state — it regenerates on merge.
   - Commit these as `chore: sdlc-task bookkeep — <spec-slug>`. Do NOT write a `log.md` narrative or a
     D18 amendment log — recommend the user run `/log-work` for that.
4. **Finish**: report the branch (and worktree path under `--worktree`), and remind the user to run
   `/log-work` for the narrative log entry.






























