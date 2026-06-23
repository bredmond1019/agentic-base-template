---
name: sdlc-run
description: >
  Trigger on '/sdlc-run' or requests to run the SDLC pipeline workflow sequentially on the current branch (implement -> test -> review -> document -> wrap-up).
---

=============================================================================
sdlc-run — SDLC Pipeline Workflow
=============================================================================

Runs the full SDLC pipeline for a spec from the current stage to
completion. Each stage is a separate agent with its own context window;
agents communicate only through report files on disk.

USAGE
  /sdlc-run <spec-slug>                  runs all tasks in the spec
  /sdlc-run <spec-slug> 2                scopes every stage to task 2 only
  /sdlc-run <spec-slug> --from implement  skips scout; starts at the named stage
  /sdlc-run <spec-slug> 2 --from test    task-scoped + skip scout

PIPELINE STAGES (in order)
  Scout      → detect current stage from report files + status.md + log
  Plan       → generate task spec (skipped if spec file already exists)
  Implement  → execute tasks from spec
  Fix        → targeted fixes for FAIL/PARTIAL review (one pass per retry)
  Test       → run the project's validation suite from planning/harness.json (+ universal emoji gate)
  Review     → fresh validation run + acceptance criteria check; verdict gates next
  Document   → surgical patches to docs/ (skipped if verdict is not PASS)
  Wrap-up    → update status.md + log, commit planning files, write report

COMMIT STRATEGY
  Each agent commits its own work immediately after completing it:
    feat: implement <stem>          implement agent (fix: if validation failed)
    fix: fix pass N for <stem>      fix agent — one commit per pass
    docs: update docs for <stem>    document agent
    chore: wrap up <stem>           wrap-up agent (status/log/reports)

  This ensures crash recovery: if the pipeline dies mid-run, all completed
  work is already in git history and visible to future agents via git log.

RESUMPTION
  The scout checks which report files exist to determine where to resume.
  Priority order:
    no spec file      → generate-tasks
    no implement.md   → implement
    no test.md        → test
    no review.md      → review
    review = FAIL     → fix
    no document.md    → document
    document.md exists → wrap-up
  Report files are authoritative; log is a cross-reference sanity check.
  Safe to re-run — the scout will pick up exactly where the pipeline stopped.

RETRY LOOP (max 3 review attempts)
  implement → test → review → [PASS: document] or [FAIL: fix → test → review]
  Each fix pass is a separate commit so the diff from each pass is auditable.

MODEL TIERING (token lever — see the MODEL map below)
  Three tiers, matched to the work: Opus on PLANNING (generate-tasks fallback); Haiku on the
  purely-mechanical stages (scout, start-block, test); Sonnet on the judgment work
  (implement/fix/review/document/wrap-up). Without this map every stage inherits the SESSION
  model — so launching from an Opus session would run scout/test on Opus too. Tune
  one place: the MODEL map.

STAGED MODEL ESCALATION (ESCALATION_MODEL)
  The FINAL fix pass and FINAL review attempt before the loop gives up run on Opus. The cheap
  path stays on Sonnet; a genuinely hard failure that has already failed twice gets one strong
  shot. Set null to disable.

REPORT FILES  (all written to planning/<name>/sdlc/reports/)
  [taskN-]implement.md  implement agent; overwritten by each fix pass
  [taskN-]test.md       test agent
  [taskN-]review.md     review agent
  [taskN-]document.md   document agent
  [taskN-]workflow.md   wrap-up agent (full pipeline run summary)

=============================================================================


## Antigravity Execution Guide

When the user asks you to run `/sdlc-run <spec-slug> [N]`, do NOT try to execute `sdlc-run.js` as a node script. Instead, orchestrate the run yourself by following these steps:

1. **Scout Stage**:
   - Verify if `planning/<spec-slug>/tasks.md` exists. If not, the current stage is `generate-tasks`.
   - List files in `planning/<spec-slug>/sdlc/reports/`.
   - Identify the resumption stage:
     - No spec file -> `generate-tasks`
     - No `implement.md` (or `taskN-implement.md`) -> `implement`
     - No `test.md` (or `taskN-test.md`) -> `test`
     - No `review.md` (or `taskN-review.md`) -> `review`
     - `review.md` has a `FAIL` or `PARTIAL` verdict -> `fix`
     - No `document.md` (or `taskN-document.md`) -> `document`
     - `document.md` exists -> `wrap-up`
2. **Execute Stages sequentially**:
   - For each stage from the resume stage onward, read the corresponding skill (`generate-tasks`, `implement`, `test`, `review-task`, `fix`, `document`, `log-work`) and follow its instructions to perform the stage.
   - Run tests and verify the code is correct at the test/review stages.
   - If review fails, loop back to the fix stage (up to 3 times before failing the workflow run).
   - Write intermediate reports (`implement.md`, `test.md`, `review.md`, etc.) to the reports directory as you complete stages.
   - Commit the changes for each stage with the correct conventional commit message format (e.g. `feat: implement <slug>`, `docs: update docs for <slug>`).
3. **Wrap-up**:
   - Update `status.md` and `log.md`.
   - Write a summary report to `planning/<spec-slug>/sdlc/reports/workflow.md`.
