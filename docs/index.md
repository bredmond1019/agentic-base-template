---
type: Index
title: docs/ — base-template documentation
description: Navigation guide for the base-template documentation folder, grouped by what you are trying to do.
doc_id: base-template-docs-index
layer: [factory]
project: base-template
status: active
keywords: [docs, documentation, navigation, architecture, workflows, harness]
related: [base-template-capabilities, base-template-architecture, using-the-template, harness-json, base-template-workflows-index, base-template-gates, base-template-ci]
---

# docs/ — base-template documentation

How to use and extend the `base-template` software factory. For how the repo is *structured*,
read `README.md` and `CLAUDE.md` instead.

## Start here

| Page | Read it when |
|---|---|
| [capabilities.md](capabilities.md) | You want the list of everything you can run, and how to invoke it |
| [workflows/index.md](workflows/index.md) | You need the vocabulary and the pipeline ladder |
| [using-the-template.md](using-the-template.md) | You are creating a new project, or pulling harness updates into one |

## Running work

| Page | Covers |
|---|---|
| [workflows/orchestration-runbook.md](workflows/orchestration-runbook.md) | The whole orchestration system — one lane, several lanes, monitoring, troubleshooting |
| [workflows/orchestration.md](workflows/orchestration.md) | The lane lifecycle, its mandatory artifacts, and the traps |
| [workflows/sdlc-task.md](workflows/sdlc-task.md) | The lean engine: implement → test → fix → commit |
| [workflows/sdlc-flow.md](workflows/sdlc-flow.md) | The feature engine: sequential tasks, one review, a PR |
| [workflows/commands.md](workflows/commands.md) | Driving the same pipeline by hand, stage by stage |
| [workflows/lane-coordination.md](workflows/lane-coordination.md) | The layer under a lane: registry, leases, message queue, commander |
| [workflows/roadmap-sweep.md](workflows/roadmap-sweep.md) | The scripted mid-run check that wakes an agent only on real change |

## Configuring a project

| Page | Covers |
|---|---|
| [harness-json.md](harness-json.md) | `planning/harness.json` — validation commands, the UI-test stage, all three stack profiles |
| [gates.md](gates.md) | The 52 checks base-template runs on itself, and what each protects |
| [harness.md](harness.md) | Writing a check over fleet-shared data: scan wide, report wide, fail narrow |
| [ci.md](ci.md) | Hosted CI for public repos — the four reusable workflows and the `actionlint` → `act` → push loop |
| [rust-sdlc-iteration-speed.md](rust-sdlc-iteration-speed.md) | A Rust pipeline gone slow: measure the link/test ratio, then four fixes |

## Extending the factory

| Page | Covers |
|---|---|
| [architecture.md](architecture.md) | The harness/scaffold split, the OKF conventions, mechanism vs policy |
| [data-contract.md](data-contract.md) | The three terminal `status` values a run-state consumer must handle |
| `.claude/skills/write-repo-doc/SKILL.md` | The standard every page in this folder is written to |

## Quick pointers

- **Every command's full parameters:** [`.claude/commands/README.md`](../.claude/commands/README.md)
- **Architectural decisions:** `planning/decisions/` — the append-only ADR log
- **Change history:** `log.md`
- **Why the mechanism/policy split exists:** D5 (`planning/decisions/D5-okf-phase-2-adopted.md`)
