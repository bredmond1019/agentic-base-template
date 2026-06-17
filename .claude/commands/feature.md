# Feature — Create a comprehensive plan to implement a new feature.

## Variables

$ARGUMENTS — description of the feature to plan.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the feature.
2. THINK HARD about the feature's scope, design, and how it fits the existing site before writing anything.
3. Research the codebase: read `CLAUDE.md` and the relevant docs in `docs/` (e.g. `docs/OPERATIONS.md`, `docs/agentic-workflows/`), then any files directly relevant to the feature.
4. Create a plan using the Plan Format below.
5. Choose a short descriptive slug (e.g. `add-rss-feed`, `add-search`, `add-newsletter-signup`).
6. Create the directory `planning/tasks/feature-{descriptive-name}/` if it does not exist, then save the plan to `planning/tasks/feature-{descriptive-name}/tasks.md`.
7. Return only the path to the file created.

## Codebase Structure

- `CLAUDE.md` — standing rules, the SDLC pipeline, build/test/validate commands (start here)
- `docs/OPERATIONS.md`, `docs/DEPLOYMENT.md`, `docs/agentic-workflows/` — operational + workflow reference
- `planning/CONTEXT.md` — why the revamp exists + audit findings; `planning/STATUS.md` — progress
- `app/[locale]/` — locale-routed pages and layouts (every page is defined ONCE here)
- `app/api/` — Next.js route handlers
- `components/` — React components (build new UI here)
- `lib/services/` — service logic (content loaders, translation, dev.to, etc.)
- `lib/content/`, `lib/core/`, `lib/translations/`, `lib/types/`, `lib/utils/` — supporting libraries
- `content/` — bilingual MDX/JSON content (`blog/`, `learn/`, `projects/`, `resume/`, `socials/`)
- `__tests__/` — jest unit/integration tests; `__mocks__/` — test mocks
- `scripts/validate-content.ts` — content correctness validator (run via `npm run validate:content`)
- `middleware.ts`, `next.config.mjs` — locale routing + build config (architecture-level; touch with care)
- `types/` — shared TypeScript types
- `planning/tasks/` — task specs and plan files (one directory per task)

## Standing rules to respect (from CLAUDE.md)

- **EN/pt-BR parity:** new pages and content ship in both locales; routes live under `app/[locale]/`, content under both the EN path and its `pt-BR/` mirror, or record an explicit deferral in `## Notes`.
- **Public-narrative rule:** in anything public-facing, Brandon and his work are the subject; never name or criticize a former employer.
- **No fabricated metrics:** every number must be verifiable. Verify any model id / package name via the `claude-api` skill, not memory.
- **MDX/content pipeline:** content additions must pass `npm run validate:content` and render in `npm run build`.

## Plan Format

```md
# Feature: <feature name>

## Metadata
prompt: `{$ARGUMENTS}`

## Feature Description
<describe the feature in detail — what it does, why it's needed, who/what benefits>

## User Story
As a <type of visitor or site component>
I want to <action or goal>
So that <benefit or outcome>

## Problem Statement
<the specific problem or gap this feature addresses>

## Solution Statement
<the proposed approach and why it fits this site's patterns (App Router, locale routing, service layer)>

## Relevant Files
<list files relevant to the feature with bullet points explaining why each is needed>

### New Files
<list all new files to be created with a one-line description of each — include the pt-BR mirror for any new content>

## Implementation Plan

### Phase 1: Foundation
<types, shared utilities, service-layer changes, content scaffolding — anything that must land first>

### Phase 2: Core Implementation
<the components, page routes under app/[locale]/, service logic, and main business logic>

### Phase 3: Integration
<wiring into navigation/layout, API routes, locale + content hookup, end-to-end behavior>

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.
Include writing tests throughout — do not leave them to the end.

### 1. <First Task Name>
- <specific action>
- <specific action>

### 2. <Second Task Name>
- <specific action>

### N. Validate
- Run the Validation Commands listed below and confirm all pass.

## Testing Strategy

### Unit Tests
<list the jest tests to write under `__tests__/` and what each should cover>

### Edge Cases
<list edge cases that must be tested — empty content, missing locale, malformed frontmatter, etc.>

## Acceptance Criteria
<list specific, measurable conditions that must be true for the feature to be done>

## Validation Commands
```
npm run lint
npx tsc --noEmit
npm run validate:content
npm test
npm run build
```
<add any feature-specific end-to-end or integration checks above the five standard lines>

## Notes
<dependencies, new packages needed (`npm install <pkg>`), bilingual deferrals, future considerations, known constraints>
```

## Report

Output the path to the plan file created and the next-step options:
```
planning/tasks/feature-{name}/tasks.md

Next (optional — decompose into atomic sub-steps):
  /breakdown planning/tasks/feature-{name}/tasks.md

Next (skip breakdown — implement directly):
  /implement planning/tasks/feature-{name}/tasks.md
```
