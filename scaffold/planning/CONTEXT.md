---
type: LocalContext
title: {{PROJECT_NAME}} Project Context
description: Core context, governing principles, and documentation router for {{PROJECT_NAME}}.
---

# CONTEXT — {{PROJECT_NAME}}

> **Read this first.** Stable orientation for {{PROJECT_NAME}}: *why* this body of work
> exists, the rules that govern how it is built, and a router to the rest of `planning/`.
> This file orients; it does not track. For state, open `STATUS.md`. For why choices were
> made, open `decisions/`.

## What This Project Is

{{DESCRIPTION}}

<!-- Expand: 1–2 paragraphs on what it does and the destination/outcome it builds toward. -->

## Who Is Building It

<!-- The builder's background, the through-line, and the relevant experience that makes this
     project a credible thing for them to build. -->

## The Document Set

| File | Role | Volatility | Read it when… |
|---|---|---|---|
| **CONTEXT.md** | Orientation + router (read first) | Stable | You need to understand the project or find the right file |
| **STATUS.md** | Current progress | Volatile | You need to know what's done / what's next |
| **MASTER_PLAN.md** | Strategy + phase specifications | Semi-stable | You need to understand the sequence of work |
| **decisions/** | Architectural decisions (atomic, append-only) | Append-only | You want to check a prior architectural choice |
| **README.md** | Navigation index for `planning/` | Stable | You need a map of the planning folder |
| **DEVLOG.md** (root) | Dated narrative of work completed | Append-only | You want the chronological dev history |

## The Project Sequence at a Glance

<!-- Phase names only, one line each. The sequence is load-bearing; details live in
     MASTER_PLAN.md. -->

- **Phase 0 — Foundation**
- **Phase 1 — Core**
- **Phase 2 — Depth / Hardening**
- **Phase 3+ — Differentiating Build**

## Governing Principles

<!-- 6–8 numbered rules that govern how this project is built. At minimum keep the first
     three; add project-specific architectural rules. -->

1. **Tests ship with every block.** No block is "done" until its core functionality is
   covered by automated tests.
2. **Just-in-time scope.** Build what the current block needs, not a speculative future.
3. **Sequence, not calendar.** Work is ordered by dependency and competence, not by dates.
4. <!-- project-specific rule -->
5. <!-- project-specific rule -->

## Fast Facts

- **Destination:** <!-- the named product / outcome this builds toward -->
- **Type:** {{PROJECT_TYPE}}
- **Tech stack:** <!-- languages, frameworks, datastores -->
- **Key constraints:** <!-- time/capacity, hard requirements -->
- **Started:** {{DATE}}

---

*This file orients; it does not track. For state, open STATUS.md. For why choices were made,
open decisions/.*
