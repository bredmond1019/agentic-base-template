---
type: Spec
title: <Concept Name> — Task Spec
description: One-line summary of what this spec delivers.
---

# <Concept Name>

> Format reference for SDLC task specs. A real spec lives at `planning/<concept>/tasks.md` +
> a companion `planning/<concept>/tasks.json`. Replace every `<...>` placeholder; keep the
> section headings — the pipeline reads them.

**Status:** Not started · **Last run:** _never_

## Goal

<What this spec delivers, stated as an outcome. One short paragraph. What does "done" look
like?>

## Context Pointers

- `planning/context.md` — project orientation and standing rules
- `planning/master-plan.md` — where this concept sits in the sequence
- <path/to/relevant/source — the code this spec touches>
- <link to any prior decision in planning/decisions/ that constrains this work>

## Step-by-Step Tasks

The task list is **not** written here — it lives in the companion `tasks.json` (same directory,
same basename). This file just points at it; the pipeline reads `tasks.json` directly, never a
markdown heading. See `planning/<concept>/tasks.json`:

```json
{
  "tasks": [
    { "id": 1, "title": "<Foundational step>", "actions": ["<what to build and where>"], "files": ["<path/to/file>"], "dependsOn": [] },
    { "id": 2, "title": "<Next step>", "actions": ["<what to build and where>"], "files": ["<path/to/file>"], "dependsOn": [1] },
    { "id": 3, "title": "<Next step>", "actions": ["<what to build and where>"], "files": ["<path/to/file>"], "dependsOn": [1] },
    { "id": 4, "title": "Validate", "actions": ["Run the Validation Commands listed below and confirm all pass."], "files": [], "dependsOn": [1, 2, 3] }
  ]
}
```

`id` — 1-indexed, dependency-ordered, no gaps. `title` — short, matches what a heading used to
say. `actions` — the bulleted "what to build and where," one string per bullet. `files` — every
task except the final Validate task must name ≥1 concrete file it creates or modifies (the
dependency analysis and disjoint-ownership guard read this). `dependsOn` — ids this task
requires to run first; the final Validate task depends on every other id.

## Acceptance Criteria

- <Observable, checkable condition — not "works well" but "endpoint returns 200 for X">
- <Each criterion maps to something a reviewer can verify against the diff>
- All tasks ship with tests covering their core functionality.

## Validation Commands

Optional. If `planning/harness.json` exists, the pipeline runs its `validation.checks[]` and
this section is a human reference. If `harness.json` is absent, the pipeline runs the commands
listed here instead.

```bash
# <format check>
# <lint check>
# <test suite — authoritative for the verdict>
# <build>
```

## Notes

<Anything that doesn't fit above: known risks, out-of-scope items, follow-ups, links.>

## Amendment Log

Append-only. When a pipeline stage deviates from this spec (a fix, a scope adjustment, a
substitution), it records one dated line here so the spec stays a living record of how it actually
ran. Do not rewrite history — only append.

_No amendments yet._
