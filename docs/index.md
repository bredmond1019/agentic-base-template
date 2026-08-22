---
type: Index
title: docs/ — base-template documentation
description: Navigation guide for the base-template documentation folder.
doc_id: base-template-docs-index
layer: [factory]
project: base-template
status: active
keywords: [docs, documentation, navigation, architecture, workflows, harness]
related: [base-template-architecture, using-the-template, harness-json, base-template-workflows-index, base-template-ci]
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
| [rust-sdlc-iteration-speed.md](rust-sdlc-iteration-speed.md) | Why agent-driven Rust pipelines get slow (linking, not testing) and the four measured fixes — one integration-test binary, nextest, no sccache, `[profile.dev]` — plus per-task `validation_commands` | An SDLC run in a Rust repo is taking tens of minutes, or you are setting up a new Rust project |
| [ci.md](ci.md) | Hosted CI for public repos — the four reusable gate workflows, how a repo opts in, the `actionlint` → `act` → push loop, and the Deviations table | You are wiring up or debugging a public repo's `.github/workflows/ci.yml` |
| [workflows/](workflows/index.md) | The SDLC engines (`/sdlc-task`, `/sdlc-flow`) + the manual command lifecycle — parameters, flags, mermaid flow diagrams, gates, token usage | You want to understand or run any SDLC pipeline |
| [data-contract.md](data-contract.md) | The complete, enumerable vocabulary of terminal `status` values the SDLC engines write into their committed run-state files (`done`, `blocked`, `reconcile_failed`) — what each means and what a consumer must not fold it into | You are building or auditing a consumer (dashboard, `mev emit-state`, `bastion` status/serve surface) that reads an SDLC run-state file's `status` field |

## SDLC workflow reference

The [`workflows/`](workflows/index.md) subfolder is the canonical reference for the automated pipelines
— authored and evolved here, copied verbatim into every generated project:

| Page | Covers |
|---|---|
| [workflows/index.md](workflows/index.md) | Hub: the two engines compared, shared concepts (reports, gates, model tiering), token overview |
| [workflows/sdlc-task.md](workflows/sdlc-task.md) | Lean single-unit engine (D38) — implement→test→fix→commit, in-place or `--worktree`, pairs with `/chore`/`/ticket` |
| [workflows/sdlc-flow.md](workflows/sdlc-flow.md) | Shared-worktree feature engine (D30–D33) — sequential tasks, per-task test→fix, one end review, PR wrap-up |
| [workflows/commands.md](workflows/commands.md) | The manual Phase 1–7 command lifecycle the engines automate |
| [workflows/orchestration.md](workflows/orchestration.md) | The lane lifecycle — what a lane is, the phases from `/begin-orchestration` through the terminal `review.md`, the mandatory artifacts, and the traps |

## Quick pointers

- **Commands reference:** `.claude/commands/README.md` — all commands, the pipeline
  flow, `/orchestrate`.
- **Architectural decisions:** `planning/decisions/` — the append-only ADR log (D1–D70).
- **Change history:** `log.md` — dated entries for every factory change.
- **Why OKF Phase 2 happened:** `planning/decisions/D5-okf-phase-2-adopted.md` — the
  mechanism/policy split, schema, and MVP scope calls.
