# Generate Tasks — Generate a task spec for a specified phase and block.

## Variables

$ARGUMENTS — the spec's `planning/tasks/` directory name (its phase-dotted slug),
             e.g. `1.3-projects-add-current` or `2.1-learn-paths-structural-fixes`.
             New master-plan specs follow the `P.N-slug` convention (see
             `planning/README.md` → *Task directory naming convention*); ad-hoc work uses
             `/chore`, `/feature`, or `/plan` instead.
             Required. If omitted, stop and say: "Usage: /generate-tasks <P.N-slug>  (e.g. 1.3-projects-add-current)"

## Instructions

1. Run `/prime` to orient to the repo (standing rules, architecture).

2. Parse `$ARGUMENTS` to extract the phase number and block/project identifier
   (e.g. `phase0-blockC` → phase 0, block C).
   - Accept any of these forms: `phase0-blockC`, `phase0blockC`, `0-C`, `Phase 0 Block C`.
   - If the argument cannot be parsed into a phase + block, stop and explain the expected format.

3. Check whether a spec already exists at `planning/tasks/phaseN-blockX/tasks.md` (using the
   normalized directory form, e.g. `planning/tasks/1.1-site-credibility-fixes/tasks.md`).
   - If it exists, read it and report: "Spec already exists at <path>. Overwrite? (re-run with
     `--force` appended to overwrite, or run `/breakdown <path>` to decompose it instead.)"
   - If `$ARGUMENTS` contains `--force`, proceed and overwrite.

4. Read ONLY the relevant section for the requested block in:
   - `planning/MASTER_PLAN.md` (the phase/block definition)
   - Do NOT read STATUS.md — the target block is given explicitly.

5. THINK HARD about correct scope:
   - Do not invent work beyond what the block defines.
   - Size tasks to roughly 21 hours spread across Mon/Wed/Fri sessions.
   - Every content task must ship EN + pt-BR in parallel (or record an explicit deferral in `## Notes / deviations`), and must leave `npm run validate:content` and `npm run build` passing (standing rules from CLAUDE.md).
   - Foundational steps come first; the final step is always Validate.

6. Create the directory `planning/tasks/phaseN-blockX/` if it does not exist, then write the spec to `planning/tasks/phaseN-blockX/tasks.md` using the Output Format below.

7. **Commit the spec.** Leave the working tree clean so a downstream `/sdlc-block` run never trips
   its clean-tree merge guard (an uncommitted `tasks.md` blocks every merge):
   ```bash
   git add planning/tasks/phaseN-blockX/
   git commit -m "chore: add spec for phaseN-blockX"
   ```
   (Use the normalized directory slug, e.g. `chore: add spec for 1.3-projects-add-current`.)

8. Report the path written and suggest the next step:
   "Spec written and committed to planning/tasks/phaseN-blockX/tasks.md. Run `/breakdown planning/tasks/phaseN-blockX/tasks.md` to decompose into atomic sub-steps."

## Context / Files to Read

- `planning/MASTER_PLAN.md` (target block section only)
- `CLAUDE.md` (standing rules — bilingual parity, public-narrative rule, no fabricated metrics, validate:content + build must pass)

## Output Format

```md
# Task Spec — Phase <N>, <Block/Project> <X>

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
npm run lint
npx tsc --noEmit
npm run validate:content
npm test
npm run build
```
<!-- Add any spec-specific checks (e.g. bilingual-parity diff) above the standard lines. -->

## Notes
<filled in as work happens>
```

## Report

Output the path to the file created and the next-step options:
```
planning/tasks/1.1-site-credibility-fixes/tasks.md

Next (optional — decompose into atomic sub-steps):
  /breakdown planning/tasks/1.1-site-credibility-fixes/tasks.md

Next (skip breakdown — implement directly):
  /implement planning/tasks/1.1-site-credibility-fixes/tasks.md
```
