# Chore — Plan a maintenance or housekeeping task.

## Variables

$ARGUMENTS — description of the chore to plan.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the chore.
2. Research the codebase: read `CLAUDE.md`, then any files directly relevant to the chore.
3. Create a plan using the Plan Format below.
4. Choose a short descriptive slug for the chore (e.g. `remove-k8s-secret`, `fix-devin-typos`, `update-stale-handles`).
5. Create the directory `planning/tasks/chore-{descriptive-name}/` if it does not exist, then save the plan to `planning/tasks/chore-{descriptive-name}/tasks.md`.
6. Return only the path to the file created.

## Codebase Structure

- `CLAUDE.md` — standing rules, the SDLC pipeline, build/test/validate commands (start here)
- `planning/CONTEXT.md` — why the revamp exists + audit findings; `planning/STATUS.md` — progress
- `app/[locale]/` — locale-routed pages and layouts (every page is defined ONCE here)
- `app/api/` — Next.js route handlers
- `components/` — React components
- `lib/services/` — service logic (content loaders, translation, dev.to, etc.)
- `lib/content/`, `lib/core/`, `lib/translations/`, `lib/utils/` — supporting libraries
- `content/` — bilingual MDX/JSON content (`blog/`, `learn/`, `projects/`, `resume/`, `socials/`)
- `__tests__/` — jest unit/integration tests; `__mocks__/` — test mocks
- `scripts/validate-content.ts` — content correctness validator (run via `npm run validate:content`)
- `middleware.ts`, `next.config.mjs` — locale routing + build config (architecture-level; touch with care)
- `planning/tasks/` — task specs (plan files live here, one directory per task)

## Standing rules to respect (from CLAUDE.md)

- **EN/pt-BR parity:** any `content/` change ships both locales, or records an explicit deferral in `## Notes`.
- **Public-narrative rule:** in anything public-facing, Brandon and his work are the subject; never name or criticize a former employer.
- **No fabricated metrics:** every number must be verifiable.
- `npm run validate:content` and `npm run build` must stay green.

## Plan Format

```md
# Chore: <chore name>

## Metadata
prompt: `{$ARGUMENTS}`

## Chore Description
<describe the chore in detail — what it is, why it matters, any known constraints>

## Relevant Files
<list files relevant to the chore with bullet points explaining why each is needed>

### New Files
<list any new files that will be created, if applicable>

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. <First Task Name>
- <specific action>
- <specific action>

### 2. <Second Task Name>
- <specific action>

### N. Validate
- Run the Validation Commands listed below and confirm all pass.

## Validation Commands
```
npm run lint
npx tsc --noEmit
npm run validate:content
npm test
npm run build
```
<add any chore-specific checks above the five standard lines (e.g. a bilingual-parity check if `content/` is touched)>

## Notes
<optional context, edge cases, or gotchas>
```

## Report

Output the path to the plan file created and the next-step options:
```
planning/tasks/chore-{name}/tasks.md

Next (optional — decompose into atomic sub-steps):
  /breakdown planning/tasks/chore-{name}/tasks.md

Next (skip breakdown — implement directly):
  /implement planning/tasks/chore-{name}/tasks.md
```
