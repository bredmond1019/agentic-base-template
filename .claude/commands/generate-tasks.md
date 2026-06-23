# Generate Tasks — Generate a task spec for a specified phase and block.

## Variables

$ARGUMENTS — the spec's `planning/` directory name (its phase-dotted slug),
             e.g. `<spec-slug>` or `2.1-learn-paths-structural-fixes`.
             New master-plan specs follow the `P.N-slug` convention (see
             `planning/index.md` → *Task directory naming convention*); ad-hoc work uses
             `/chore`, `/feature`, or `/plan` instead.
             Required. If omitted, stop and say: "Usage: /generate-tasks <P.N-slug>  (e.g. <spec-slug>)"

## Instructions

1. Run `/prime` to orient to the repo (standing rules, architecture).

2. Parse `$ARGUMENTS` to extract the phase number and block/project identifier
   (e.g. `phase0-blockC` → phase 0, block C).
   - Accept any of these forms: `phase0-blockC`, `phase0blockC`, `0-C`, `Phase 0 Block C`.
   - If the argument cannot be parsed into a phase + block, stop and explain the expected format.

3. Check whether a spec already exists at `planning/phaseN-blockX/tasks.md` (using the
   normalized directory form, e.g. `planning/<spec-slug>/tasks.md`).
   - If it exists, read it and report: "Spec already exists at <path>. Overwrite? (re-run with
     `--force` appended to overwrite, or run `/breakdown <path>` to decompose it instead.)"
   - If `$ARGUMENTS` contains `--force`, proceed and overwrite.

4. Read ONLY the relevant section for the requested block in:
   - `planning/master-plan.md` (the phase/block definition)
   - Do NOT read status.md — the target block is given explicitly.

5. **Clarify gate (only when enabled).** Read `planning/harness.json` → `planning.clarify`. When it is
   `true` **or** `$ARGUMENTS` contains `--clarify`, and the block definition is genuinely ambiguous (its
   scope, deliverables, or task boundaries could be read more than one way), pause and ask the user
   **2–4 targeted clarifying questions** before writing the spec; fold the answers into the tasks. If the
   block is already unambiguous, skip the questions and proceed even when the gate is on. When
   `planning.clarify` is absent/`false` and no `--clarify` flag is present, skip this step entirely and
   behave exactly as before. (`--clarify` is a control flag only — do not treat it as part of the
   phase/block slug when parsing `$ARGUMENTS`.)

6. THINK HARD about correct scope:
   - Do not invent work beyond what the block defines.
   - Size tasks to roughly 21 hours spread across Mon/Wed/Fri sessions.
   - Enforce **the project's standing rules** as written in `CLAUDE.md` — do not assume any stack, locale-parity, or content-layout rule unless written there. Every task must leave the project's gated checks (`planning/harness.json` → `validation.checks[]` with `gates: true`) passing.
   - **Disjoint file ownership (parallel-merge safety).** A block's tasks run as parallel pipelines that merge independently, so two tasks editing the same existing file collide at merge. Decompose so each task **owns a distinct set of files**. When two tasks would touch the same file, either (a) make one `dependsOn` the other so `/sdlc-block` serializes them into different waves, or (b) restrict the shared file to **append-only** edits (the block engine union-merges files declared `additiveFiles`). Name each task's primary files in its step so the dependency analysis can see the boundaries — an undeclared overlap escalates the whole block on a merge conflict.
   - Foundational steps come first; the final step is always Validate.
   - **Use `### N. Title` heading format for every task** — sdlc-block enumerates tasks by
     this pattern (`### N.`) and will abort pre-flight on a spec that has none. Never use
     flat numbered lists (`1. **Title**`) or any other format for the task headings.

7. Create the directory `planning/phaseN-blockX/` if it does not exist, then write the spec to `planning/phaseN-blockX/tasks.md` using the Output Format below.

8. **Property self-check (before committing).** A structurally valid spec can still be substantively
   thin and waste pipeline tokens. Re-read what you just wrote and confirm every required property
   holds; **revise the spec in place** if any fails, then re-check:
   - **Every `### N.` task names ≥1 concrete file** it creates or modifies (so the dependency analysis
     and disjoint-ownership guard can see boundaries). The final Validate step is exempt.
   - **Acceptance Criteria are non-empty and observable** — each criterion can be judged true/false.
   - **Validation Commands are present** (or `planning/harness.json` → `validation.checks[]` supplies
     them as the fallback).
   - **No leftover template sentinels** — no `{{TOKEN}}`, no literal seed strings the Output Format
     ships (`<placeholder>`-style angle stubs left unfilled, empty AC/Validation bullets). Do **not**
     treat legitimate `<...>` in code/prose (e.g. `Vec<T>`, "the `<concept>` folder") or a bare
     `TODO`/`TBD` inside authored content as a sentinel.

9. **Commit the spec.** Leave the working tree clean so a downstream `/sdlc-block` run never trips
   its clean-tree merge guard (an uncommitted `tasks.md` blocks every merge):
   ```bash
   git add planning/phaseN-blockX/
   git commit -m "chore: add spec for phaseN-blockX"
   ```
   (Use the normalized directory slug, e.g. `chore: add spec for <spec-slug>`.)

10. **Decomposition assessment.** Before reporting, evaluate each task you just wrote against the
   coarseness heuristic and recommend which (if any) warrant a `/breakdown` first. The real predictor
   is SEPARABLE STRUCTURE, not raw file count. A task is a breakdown candidate when ANY hold: it bundles
   multiple separable concerns ("implement X AND refactor Y AND add Z"), OR it spans multiple layers
   (data model + API + UI), OR it carries a large acceptance-criteria set over several independently-
   testable units, OR it touches more than `breakdown.complexityThreshold` distinct files
   (`planning/harness.json`; default 3) AND those files are HETEROGENEOUS (different shapes/roles or
   spanning more than one concern/layer). Do NOT flag on file count alone when the many files are the
   same shape serving one concern (e.g. a content path's metadata + N near-identical lesson pairs) —
   decomposition yields little there. List the flagged task numbers with a one-line reason in the report
   (the SDLC engines apply the same heuristic at run time per `breakdown.mode`, so this is the
   authoring-time preview of that decision).

11. **Pipeline recommendation.** After writing the tasks, evaluate which run command fits the block and
   report a clear recommendation with a one-line reason. The two whole-block runners differ only in
   **how implement is scoped** — `/sdlc-run` runs **one** implement agent across all tasks; the lean
   `/sdlc-block` runs **a fresh implement agent per task** (deliberate per-task context windows +
   observability), then does **one** consolidated back-half (test/review/document/wrap-up) just like
   `/sdlc-run`. The block runs tasks **in-place sequentially** by default and only spins worktrees for
   genuinely parallel waves, so its cost is close to `/sdlc-run`'s. Use these signals:

   - **`/sdlc-run`** (default) — small, homogeneous, or sequential blocks, **even past 4 tasks**. When a
     single shared implement context can hold all the tasks without blurring or overflowing, this is the
     cheapest correct choice (one agent, one back-half).
   - **`/sdlc-block`** (lean) — recommend when tasks each benefit from a **fresh implement agent**:
     large or heterogeneous tasks where one shared context would blur or overflow, **or** when ≥2 tasks
     genuinely share a wave (disjoint file ownership from step 6, no `dependsOn` between them → true
     parallelism). Count the independent tasks per wave, not just the total.
   - **`/sdlc-task <N>`** — Not a strategy for running all tasks; name it only when the right move is
     one specific task in an isolated worktree (e.g. a high-risk surgical change, or resuming after a
     block failure on task N). If naming it, also say which task number and why isolation matters.

   **Per-task review depth (only when recommending `/sdlc-block`).** The lean block defaults to
   `--verify-depth consolidated` (per-task review **off** — one review at the end over the integrated
   tree). Reuse the step-10 decomposition signal: when tasks are large / complex / heterogeneous enough
   that a single end-of-run review would struggle to localize **which task** caused a finding, recommend
   `--verify-depth consolidated+review` (a per-task review pass that acts as a localization map). State
   the tradeoff: it adds roughly **38k output tokens × N tasks**, and a per-task review validates a slice
   **in isolation** — the consolidated review stays authoritative for cross-task integration. For small
   homogeneous blocks, leave it off.

   If `breakdown.mode` is `auto` and any tasks were flagged in step 10, note that breakdown must run
   first and the pipeline recommendation applies to each resulting sub-spec, not this spec directly.

12. **Author the execution plan (only when recommending a block runner; D22).** If step 11 recommends
    `/sdlc-block` (or it is a plausible choice), write the dependency graph you already derived in step 6
    (each task's files + disjoint-ownership boundaries) to `planning/<spec-slug>/sdlc/execution-plan.json`
    so the block's Analyze stage can LOAD it instead of re-deriving it on an Opus agent. Follow
    `.claude/workflows/execution-plan.schema.json`:
    - `blockId` = the spec slug; `tasks` = an object keyed by task number ("1", "2", …), one entry per
      `### N.` heading, each with `num`, `title`, `dependsOn` (task numbers whose output it consumes),
      `filesCreated`, `filesModified` (existing shared files), and an `evidence` quote for each
      dependency edge. Carry over each task's `recommendBreakdown`/`breakdownReason` from step 10.
    - `additiveFiles` = shared files every touching task only APPENDS to (barrels/index re-exports,
      registries/manifests, auto-generated reference docs) — safe to union-merge.
    - **Omit `waves`** — the engine computes them deterministically from the graph.
    Then commit it with the spec (or in a follow-up commit if the spec was already committed in step 9):
    ```bash
    git add planning/<spec-slug>/sdlc/execution-plan.json
    git commit -m "chore: add execution plan for <spec-slug>"
    ```
    Skip this step entirely when the recommendation is `/sdlc-run` or `/sdlc-task` (no block, no plan
    needed). The block validates the plan on load and falls back to its own Opus analyzer if the plan is
    absent, malformed, or stale (tasks.md edited afterward), so a skipped plan is always safe.

13. Report the path written and suggest the next step:
    "Spec written and committed to planning/phaseN-blockX/tasks.md. Run `/breakdown planning/phaseN-blockX/tasks.md` to decompose into atomic sub-steps."

## Context / Files to Read

- `planning/master-plan.md` (target block section only)
- `CLAUDE.md` (the project's standing rules)
- `planning/harness.json` (the project's validation checks)

## Output Format

```md
# Task Spec — Phase <N>, <Block/Project> <X>

**Status:** Not started · **Last run:** never

## Goal
<one sentence, taken directly from the plan>

## Context Pointers
<which plan sections are relevant + which repo files / CLAUDE.md sections apply>

## Step-by-Step Tasks

### 1. <Foundational step>
- <bulleted actions>

### 2. <Next step>
- <bulleted actions>

<!-- ... continue; last step is always validation -->

### N. Validate
- Run the Validation Commands listed below and confirm all pass.

## Acceptance Criteria
- <specific, measurable condition>
- <specific, measurable condition>

## Validation Commands
```
<the project's validation commands — see `planning/harness.json` (`validation.checks[]`) or CLAUDE.md; one command per line, in order>
```
<!-- Add any spec-specific checks above the standard project checks. -->

## Notes
<filled in as work happens>

## Amendment Log
<!-- Append-only. Pipeline stages append one dated line here when they deviate from the spec. -->
_No amendments yet._
```

## Report

Output the path to the file created, the decomposition assessment, the pipeline recommendation, and the next-step options:
```
planning/<spec-slug>/tasks.md

Decomposition assessment:
  <"All tasks appropriately scoped." OR a list like:>
  - Task 3 — touches 6 files across model + API + UI; recommend /breakdown
  - Task 5 — bundles two separable concerns; recommend /breakdown

Pipeline recommendation:
  <one of:>
  /sdlc-run <spec-slug>          — <N> tasks, small/homogeneous/sequential; one shared implement context is sufficient
  /sdlc-block <spec-slug>        — <N> tasks; fresh implement agent each (<reason: heterogeneous/large, or <M> parallel across <W> waves>)
  /sdlc-block <spec-slug> --verify-depth consolidated+review
                                 — as above, plus per-task review for localization (<reason; +~38k tok × N>)
  /sdlc-task <spec-slug> <N>     — run task <N> in isolation; <reason isolation matters here>

Next (optional — decompose first):
  /breakdown planning/<spec-slug>/tasks.md

Next (run directly):
  /<recommended-command> <spec-slug>
```
