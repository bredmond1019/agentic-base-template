---
type: Index
title: {{PROJECT_NAME}} — Planning Docs
description: Navigation index for the {{PROJECT_NAME}} planning folder.
---

# {{PROJECT_NAME}} — Planning Docs

The strategy, state, and decision record for {{PROJECT_NAME}}. Code lives elsewhere; this
folder is the map.

## Files

| File | What it is | Open it when… |
|---|---|---|
| `CONTEXT.md` | Orientation + governing principles (read first) | You need to understand the project |
| `STATUS.md` | Current progress tracker | You need to know what's done / next |
| `MASTER_PLAN.md` | Strategy + phase specifications | You need the sequence of work |
| `decisions/` | Atomic, append-only architectural decisions | You want to check a prior choice |
| `tasks/` | Per-spec task specs + pipeline reports | You're running the SDLC pipeline |

## Read Order for a Newcomer

1. `CONTEXT.md` — what this is and the rules of the road
2. `STATUS.md` — where things stand right now
3. The relevant phase section of `MASTER_PLAN.md`

## What's NOT Here

- Application code (lives in the source tree, not `planning/`)
- Generated task specs (those live under `tasks/<name>/`)

---

*The map, not the territory. For the chronological narrative, see the root `DEVLOG.md`.*
