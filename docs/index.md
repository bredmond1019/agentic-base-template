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
| [workflows/](workflows/index.md) | The SDLC engines (`/sdlc-run`, `/sdlc-task`, `/sdlc-block`) + the manual command lifecycle — parameters, flags, mermaid flow diagrams, gates, token usage | You want to understand or run any SDLC pipeline |

## SDLC workflow reference

The [`workflows/`](workflows/index.md) subfolder is the canonical reference for the automated pipelines
— authored and evolved here, copied verbatim into every generated project:

| Page | Covers |
|---|---|
| [workflows/index.md](workflows/index.md) | Hub: the three engines compared, shared concepts (reports, gates, model tiering), token overview |
| [workflows/sdlc-run.md](workflows/sdlc-run.md) | Sequential engine — `--from`, stages, resumption |
| [workflows/sdlc-task.md](workflows/sdlc-task.md) | Parallel-safe single-task engine — worktrees, `--resume`, `--implement-only`, merge flow |
| [workflows/sdlc-block.md](workflows/sdlc-block.md) | Lean spec orchestrator (D22–D28) — pre-flight, Analyze, in-place vs worktree waves, consolidated back-half |
| [workflows/commands.md](workflows/commands.md) | The manual Phase 1–7 command lifecycle the engines automate |

## Quick pointers

- **Commands reference:** `.claude/commands/README.md` — all commands, the pipeline
  flow, the `sdlc-block` orchestrator.
- **Architectural decisions:** `planning/decisions/` — the append-only ADR log (D1–D28).
- **Change history:** `log.md` — dated entries for every factory change.
- **Why OKF Phase 2 happened:** `planning/decisions/D5-okf-phase-2-adopted.md` — the
  mechanism/policy split, schema, and MVP scope calls.
