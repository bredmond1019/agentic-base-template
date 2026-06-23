---
name: sdlc-task
description: >
  Trigger on '/sdlc-task' or requests to run the SDLC pipeline for a single task in an isolated git worktree.
---

=============================================================================
sdlc-task — Parallel-Safe SDLC Pipeline with Auto-Managed Worktree
=============================================================================

A parallel-safe variant of sdlc-run that:
  1. Auto-creates a git worktree for this specific task
  2. Runs the full SDLC pipeline inside that worktree
  3. Defers status.md / log.md updates to a task log file
     (applied at merge time via /clean-worktree)

This lets multiple tasks run simultaneously with zero shared file writes,
eliminating merge conflicts. sdlc-run.js is unchanged and still available
for sequential use.

USAGE
  /sdlc-task <spec-slug> 2                  runs task 2 in an isolated worktree (full pipeline)
  /sdlc-task <spec-slug> 2 --implement-only  worktree implement only, then STOP (lean /sdlc-block
                                             width-≥2 path; add --review for one localization-map
                                             review pass). No test/document/wrap-up/merge.

  Task number is REQUIRED. For full-spec runs use /sdlc-run instead.

PIPELINE STAGES (in order)
  Worktree   → auto-create (or suffix-increment) isolated git worktree (also reports spec-exists +
               block status, so a fresh non-resume run can skip the Scout stage entirely)
  Scout      → detect current stage from report files (RESUME runs only; a fresh run's start stage
               is deterministic — generate-tasks if the spec is missing, else implement)
  Plan       → generate task spec (if missing) + breakdown assessment (standalone runs; recommend/auto/off
               per planning/harness.json breakdown.mode — skipped under /sdlc-block, which assesses once)
  Implement  → execute the task from spec
  Fix        → targeted fixes for FAIL/PARTIAL review (up to 3 attempts)
  Test       → run the project's validation suite from planning/harness.json (+ universal emoji gate)
  Review     → fresh validation run + acceptance criteria; verdict gates next stage
  Document   → surgical patches to docs/ (gates on PASS verdict)
  Wrap-up    → write task log + workflow report, commit all reports (status/log deferred to merge
               time). task-log and finalize were merged into one Haiku agent — see D14.

WHAT RUNS IN THE WORKTREE vs. MAIN
  Worktree branch: all code, content, doc, and report changes
  Main (at merge): status.md + log.md updates (applied by /clean-worktree)

MERGE FLOW
  After pipeline completes:
    /clean-worktree <branchName>
  This: merges the branch → applies the task log → updates status/log →
        commits → removes worktree → deletes branch.

WORKTREE PATH CONVENTION
  trees/<specSlug-lowercased>-task<N>   e.g. trees/<spec-slug>-task2
  If that name is taken, auto-increments: trees/...-task2-2, -3, etc.
  The actual branch name is always reported in the pipeline output and task log.

RESUMPTION
  Same as sdlc-run: the scout checks which report files exist.
  If the worktree already exists at setup time, a new suffixed worktree is
  created rather than resuming the old one. This ensures clean state for retries.

COMMIT STRATEGY (same as sdlc-run)
  feat: implement <stem>         implement agent
  fix: fix pass N for <stem>     fix agent (one per pass)
  docs: update docs for <stem>   document agent
  chore: wrap up <stem>          finalize agent (reports + task log)

MODEL TIERING (token lever — see the MODEL map below)
  Three tiers: Opus earns its cost on PLANNING (generate-tasks fallback); Haiku handles the
  purely-mechanical stages (scout, test, wrap-up — fixed procedures, no judgment); Sonnet
  handles everything in between (implement/fix/review/document/task-log). Tune one place: the
  MODEL map. Real planning happens upstream in the /generate-tasks and /breakdown skills — run
  those on Opus. This matters most under /sdlc-block, which fans this pipeline out across many tasks.

STAGED MODEL ESCALATION (ESCALATION_MODEL)
  The FINAL fix pass and FINAL review attempt before the loop gives up run on Opus.
  The cheap Sonnet path covers the common case; a genuinely hard failure that has
  already failed twice gets one strong shot before the task escalates. Set null to off.

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
