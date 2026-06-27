---
type: ProjectStatus
title: {{PROJECT_NAME}} Status
description: Current state and progress tracker for {{PROJECT_NAME}}.
doc_id: status
layer: [factory]
status: active
timestamp: "{{DATE}}"
now: "Phase 0, Block A — Foundation setup"
next: "Define Phase 0 tasks via /generate-tasks"
blocked: []
keywords: [status, progress tracker, current focus, blocks]
related: [context, master-plan, planning-index, knowledge, memory]
---

# STATUS — Current State & Progress

**Last updated:** {{DATE}} — Project initialized
**Current focus:** Phase 0, Block A — Foundation setup

---

## How to Read / Update This File

- Status values: `Not started` · `In progress` · `Done` · `Blocked` · `Skipped`
- Keep `Current focus` and `Last updated` accurate; update as work happens.
- This file is **state only**. For what the work means, see `master-plan.md`.
- The **now/next/blocked** frontmatter scalars mirror the `## Momentum` headlines below;
  `/log-work` keeps them in sync. See `agentic-portfolio/docs/planning-conventions.md` (D30).

---

## Momentum

> Working board — keep all five queues live. **Never end a meaningful session with every queue
> empty.** The headlines of **now / next / blocked** mirror the frontmatter scalars above.

- **now** — Phase 0, Block A — Foundation setup
- **next** — Define Phase 0 tasks (`/generate-tasks`)
- **blocked** — _nothing yet — each entry names its blocker and the smallest missing answer_
- **improve** — _self-improvement backlog: eval gaps, flaky workflows, repeated failures, missing skills, stale assumptions_
- **recurring** — _schedules, monitors, sweeps, automations_

---

## Metrics

> Cheap, hand-maintained signals (leading + lagging). Do **not** push these into frontmatter —
> they are multi-valued and volatile.

- tasks completed / verified this period; intervention rate; retry rate; regression rate
- reusable assets created since last milestone
- days since last eval improvement; days since last new skill/workflow
- % of runs ending with an explicit next action

---

## Progress Table

### Phase 0 — Foundation
| Block | What | Status | Notes |
|---|---|---|---|
| Block A | Foundation setup | Not started | Initialize codebase and planning infrastructure |

<!-- Add one sub-table per phase as the plan is fleshed out. -->

---

## Decisions & Deviations Log

*Record deviations from the plan and notable in-flight choices here. Promote durable ones to
`decisions/` via `/log-work`.*

---

## Quick Self-Check

- Is `Current focus` accurate?
- Any `In progress` rows that are actually `Done`?
- Anything `Blocked` that needs surfacing?

---

*State only. For what things mean, see master-plan.md. For orientation, see context.md.*
