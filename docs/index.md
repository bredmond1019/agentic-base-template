---
type: Index
title: docs/ — base-template documentation
description: Navigation guide for the base-template documentation folder.
---

# docs/ — base-template documentation

User-facing documentation for the `base-template` software factory. Read these when you want
to understand how to use the template, not when you want to know how it is structured (that's
`README.md` + `CLAUDE.md`).

| File | What it covers | Read it when… |
|---|---|---|
| [architecture.md](architecture.md) | How the two halves work, the OKF conventions, the mechanism/policy split | You want to understand *why* the template is designed the way it is |
| [using-the-template.md](using-the-template.md) | Generate → configure → first pipeline run, step by step | You are creating a new project or setting up an existing one |
| [harness-json.md](harness-json.md) | `planning/harness.json` config reference + all three stack profiles | You are configuring validation commands or the UI-test stage |

## Quick pointers

- **Commands reference:** `.claude/commands/README.md` — all 22 commands, the pipeline
  flow, the `sdlc-block` orchestrator.
- **Architectural decisions:** `planning/decisions/` — the append-only ADR log (D1–D5).
- **Change history:** `log.md` — dated entries for every factory change.
- **Why OKF Phase 2 happened:** `planning/decisions/D5-okf-phase-2-adopted.md` — the
  mechanism/policy split, schema, and MVP scope calls.
