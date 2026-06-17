# Plan — Create a plan for a task, scaled to its complexity.

## Variables

$ARGUMENTS — description of the task to plan.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the task.
2. THINK HARD about task type and complexity before writing anything:
   - `task_type`: `chore` | `feature` | `refactor` | `fix` | `enhancement` | `content`
   - `complexity`: `simple` | `medium` | `complex`
   - Simple tasks (chores, targeted fixes, single-post content edits): focus on specific changes and validation.
   - Complex tasks (features, refactors, multi-page content arcs): include design rationale, implementation phases, and testing strategy.
3. Research the codebase: read `CLAUDE.md`, then files directly relevant to the task.
4. Create a plan using the Plan Format below, omitting sections marked as conditional when they don't apply.
5. Choose a short descriptive slug (e.g. `fix-claude-sdk-package-name`, `refactor-content-loader`, `add-build-cache`).
6. Create the directory `planning/tasks/plan-{descriptive-name}/` if it does not exist, then save the plan to `planning/tasks/plan-{descriptive-name}/plan.md`.
7. Return only the path to the file created.

## Codebase Structure

- `CLAUDE.md` — standing rules, the SDLC pipeline, build/test/validate commands (start here)
- `planning/CONTEXT.md` — why the revamp exists + audit findings; `planning/STATUS.md` — progress
- `app/[locale]/` — locale-routed pages and layouts (every page is defined ONCE here)
- `app/api/` — Next.js route handlers
- `components/` — React components
- `lib/services/` — service logic; `lib/content/`, `lib/core/`, `lib/translations/`, `lib/utils/` — supporting libraries
- `content/` — bilingual MDX/JSON content (`blog/`, `learn/`, `projects/`, `resume/`, `socials/`)
- `__tests__/` — jest unit/integration tests; `__mocks__/` — test mocks
- `scripts/validate-content.ts` — content correctness validator (run via `npm run validate:content`)
- `middleware.ts`, `next.config.mjs` — locale routing + build config (architecture-level; touch with care)
- `planning/tasks/` — task specs and plan files (one directory per task)

## Standing rules to respect (from CLAUDE.md)

- **EN/pt-BR parity:** any `content/` change ships both locales, or records an explicit deferral in `## Notes`.
- **Public-narrative rule:** in anything public-facing, Brandon and his work are the subject; never name or criticize a former employer.
- **No fabricated metrics:** every number must be verifiable.
- `npm run validate:content` and `npm run build` must stay green.

## Plan Format

```md
# Plan: <task name>

## Metadata
prompt: `{$ARGUMENTS}`
task_type: <chore|feature|refactor|fix|enhancement|content>
complexity: <simple|medium|complex>

## Task Description
<describe the task in detail based on the prompt>

## Objective
<one sentence: what will be true when this plan is fully executed>

<!-- Include for feature/refactor/complex tasks: -->
## Problem Statement
<the specific problem or opportunity this task addresses>

## Solution Approach
<the proposed solution and why it fits the site's patterns (App Router, locale routing, service layer, content pipeline)>
<!-- end conditional -->

## Relevant Files
<list files relevant to the task with bullet points explaining why each is needed>

### New Files
<list any new files to be created, if applicable — include the pt-BR mirror for any new content>

<!-- Include for medium/complex tasks: -->
## Implementation Phases
### Phase 1: Foundation
<any foundational work that must land first>

### Phase 2: Core Implementation
<the main body of work>

### Phase 3: Integration & Validation
<integration with existing pages/services, tests, final checks>
<!-- end conditional -->

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. <First Task Name>
- <specific action>
- <specific action>

### 2. <Second Task Name>
- <specific action>

### N. Validate
- Run the Validation Commands listed below and confirm all pass.

<!-- Include for feature/complex tasks: -->
## Testing Strategy
<jest tests needed under `__tests__/`; edge cases to cover; any integration test requirements>
<!-- end conditional -->

## Acceptance Criteria
<list specific, measurable conditions that must be true for this task to be done>

## Validation Commands
```
npm run lint
npx tsc --noEmit
npm run validate:content
npm test
npm run build
```
<add any task-specific checks above the five standard lines (e.g. a bilingual-parity check if `content/` is touched)>

## Notes
<optional: dependencies, new packages needed (`npm install <pkg>`), bilingual deferrals, constraints, follow-ups>
```

## Report

Output the path to the plan file created and the next-step options:
```
planning/tasks/plan-{name}/plan.md

Next (optional — decompose into atomic sub-steps):
  /breakdown planning/tasks/plan-{name}/plan.md

Next (skip breakdown — implement directly):
  /implement planning/tasks/plan-{name}/plan.md
```
