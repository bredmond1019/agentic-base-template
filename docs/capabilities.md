---
type: Reference
title: What this factory can do — the capability catalogue
description: Every capability the base-template harness ships — commands, engines, skills, scripts and gates — with one plain-English line each and how to invoke it.
doc_id: base-template-capabilities
layer: [factory]
project: base-template
status: active
keywords: [capabilities, commands, engines, skills, gates, catalogue]
related: [base-template-docs-index, base-template-workflows-index, base-template-gates, base-template-architecture]
---

# What this factory can do

One page listing everything the harness ships, what it does in one line, and how to run it.
New to the system? Read [`workflows/index.md`](workflows/index.md) first for the vocabulary,
then come back here to find the thing you need.

## What this page is for

`base-template` is the **software factory**: the pipeline (commands, engines, skills, gates)
that every project repo is scaffolded from. This page is the index of *capabilities* — the
things you can actually invoke. It is derived from the files on disk, not from doc titles, so
a capability missing here means it is missing from the repo.

Counts, as of the last regeneration: **57 commands**, **2 engines**, **11 skills**,
**52 gated checks**. If you add one and don't add a row here, this page is wrong.

## Quickstart

Three ways in, depending on what you have:

| You have | Type this | Where |
|---|---|---|
| An idea, no plan | `/plan <description>` | Claude Code |
| A plan, one small change | `/sdlc-task <spec-slug>` | Claude Code |
| A plan, a real feature | `/sdlc-flow <spec-slug>` | Claude Code |
| An ordered list of blocks | `/orchestrate <block-id ...>` | Claude Code |
| No idea where you left off | `/session-recap` | Claude Code |

**Where things are typed matters and is not visible from the page.** A leading `/` means a
**Claude Code slash command** — type it into a Claude Code session. Anything starting `python3`,
`node` or `./scripts/` is a **shell command** — type it into a terminal at the repo root. They
are not interchangeable.

## The two engines

An **engine** is a `.js` pipeline the Workflow harness runs end to end: it implements, tests,
fixes, and commits without you driving each step. There are exactly two.

| Engine | What it does | Invoke | When |
|---|---|---|---|
| [`sdlc-task`](workflows/sdlc-task.md) | implement → fast gating test → triage → fix (≤3 attempts) → commit → terminal reconcile → lean bookkeep. No review, no docs stage, no PR. | `/sdlc-task <spec-slug> [task\|range] [--worktree] [--resume] [--test-depth fast\|full]` | One small unit of behaviour change — a `/ticket` or `/chore`. |
| [`sdlc-flow`](workflows/sdlc-flow.md) | The same per-task test→fix loop, run sequentially over a whole spec on one branch, then **one** consolidated review, a docs patch, and a PR. | `/sdlc-flow <spec-slug> [range] [--auto-merge] [--no-pr] [--worktree] [--resume] [--test-depth fast\|full]` | The default for non-trivial feature work — many moving parts in one spec. |

Both run on a plain branch in the main working tree by default; `--worktree` gives true
isolation. The source of truth for both is `.claude/workflows/sdlc-task.js` and
`.claude/workflows/sdlc-flow.js`; the prose pages linked above are hash-tripwired against them
(see the `engine-docs-sync` row in [gates.md](gates.md)).

## Commands

All 57 are flat — invoke as `/<name>` in Claude Code. Full parameter reference:
[`.claude/commands/README.md`](../.claude/commands/README.md).

### Orient and close a session

| Command | What it does |
|---|---|
| [`/prime`](../.claude/commands/prime.md) | Deep orientation at session start — reads the key docs in order and summarises state. |
| [`/session-recap`](../.claude/commands/session-recap.md) | The light version: recent log entries plus `status.md`, as a tight briefing. |
| [`/next`](../.claude/commands/next.md) | What's up next, what's blocked and by what, plus a recommended next action. |
| [`/log-work`](../.claude/commands/log-work.md) | Appends a log entry, syncs status, regenerates the freshness spine via `mev emit-state`. |
| [`/wrap-up`](../.claude/commands/wrap-up.md) | `/log-work` then `/commit` — a clean close with no handoff file. |
| [`/handoff`](../.claude/commands/handoff.md) | Writes `handoff.md`, logs, commits — hands the in-flight session to a fresh agent. |
| [`/close-out`](../.claude/commands/close-out.md) | Post-implementation close: verify test coverage, patch docs, hand off cleanly. |
| [`/archive`](../.claude/commands/archive.md) | Retires a folder or file into `planning/archive/`, distilling its durable residue first. |
| [`/blocked`](../.claude/commands/blocked.md) | Captures a new blocker on the fly — what is blocked, by what, where, why. |
| [`/capture`](../.claude/commands/capture.md) | Scaffolds `planning/<slug>/notes.md` for pre-plan content too rich for a ticket. |
| [`/backlog-ticket`](../.claude/commands/backlog-ticket.md) | Files a queued idea into the backlog with uniform tags. |

### Before you plan (Phase 0)

Use this ladder when the work sits on an existing system and the right cut is not obvious.
Each stage feeds the next: `/assess` → `/seams` → `/sequence` → **`/plan` or
`/generate-roadmap`**. All three pre-plan stages write `planning/<slug>/`; which successor consumes
them is a **count**, not a judgement — the distinct repos in `sequence.md`'s block table. One repo
goes to `/plan`, which authors into that same directory. Several go to `/generate-roadmap`, which
writes `planning/roadmaps/<slug>/` and relocates the pre-plan to
`planning/roadmaps/<slug>/pre-plan/` (its Step 7b). The invariant: `planning/<slug>/` and
`planning/roadmaps/<slug>/` are **never both populated**.

| Command | What it does |
|---|---|
| [`/initial-research`](../.claude/commands/initial-research.md) | Deep reconnaissance on a topic — codebase or external — reported back as structured findings. |
| [`/assess`](../.claude/commands/assess.md) | Fans out recon agents over an existing codebase, then re-checks the load-bearing claims. Evidence only; may not propose a sequence. |
| [`/seams`](../.claude/commands/seams.md) | Classifies every capability as built / half-built / absent and maps where new work attaches, with a blast radius per seam. |
| [`/sequence`](../.claude/commands/sequence.md) | Cuts the seam map into ordered blocks that each ship something usable the day they land. |
| [`/define-design-system`](../.claude/commands/define-design-system.md) | Greenfield UI: establishes the tokens, components and rules the UI is built from. |
| [`/define-polish-standard`](../.claude/commands/define-polish-standard.md) | Existing UI: writes the document the UI can actually be judged against. |

### Plan (Phase 1)

| Command | What it does |
|---|---|
| [`/plan`](../.claude/commands/plan.md) | Authors an initiative — its narrative plus its block records. |
| [`/ticket`](../.claude/commands/ticket.md) | One small behaviour change, specified with observable acceptance criteria. |
| [`/chore`](../.claude/commands/chore.md) | Plans a maintenance or housekeeping task. |
| [`/generate-tasks`](../.claude/commands/generate-tasks.md) | Generates the task spec for a given phase and block. |
| [`/breakdown`](../.claude/commands/breakdown.md) | Decomposes a task spec into agent-executable sub-steps. |
| [`/update-state`](../.claude/commands/update-state.md) | Safely edits a repo's `planning/state.json` — the authoritative block dependency graph. |
| [`/generate-master-plan`](../.claude/commands/generate-master-plan.md) | **Superseded** by `/plan --founding`; `master-plan.md` is now generated from the block graph. |

### Build, test, review, document

> **The one-off stage commands were retired (2026-08-31).** `/implement`, `/test`, `/fix`,
> `/review-task`, `/document`, `/process-tasks` and `/conditional_docs` are gone. They were a hand-
> driven copy of what the engines already do, they had drifted onto an older data model (they read
> `tasks.md` prose and never learned `tasks.json` or block records), and nobody was running them.
>
> **Run [`/sdlc-task`](workflows/sdlc-task.md) or [`/sdlc-flow`](workflows/sdlc-flow.md) instead** —
> they perform every one of those stages, against the current spec format, with the gates wired in.
> `/update-docs` remains for ad-hoc documentation work outside a run. Full rationale:
> [workflows/prompt-parity.md](workflows/prompt-parity.md).

| Command | What it does |
|---|---|
| [`/review-PR`](../.claude/commands/review-PR.md) | Spec-aware review of a branch-train PR — runs the gating suite, posts a structured verdict. |
| [`/update-task`](../.claude/commands/update-task.md) | Records progress or a deviation in a task spec. |
| [`/update-docs`](../.claude/commands/update-docs.md) | Documentation health sweep — finds stale sections, creates missing coverage. |
| [`/patch`](../.claude/commands/patch.md) | Hotfix ladder: implement → validate → commit, nothing else. |
| [`/commit`](../.claude/commands/commit.md) | Stages and commits with a conventional message. |

### Run work automatically

| Command | What it does |
|---|---|
| [`/orchestrate`](../.claude/commands/orchestrate.md) | Drives an ordered chain of blocks end-to-end through the engines, in one session. |
| [`/generate-roadmap`](../.claude/commands/generate-roadmap.md) | Turns findings and open blocks into a roadmap document plus the per-repo lane files `/begin-orchestration` consumes. |
| [`/begin-orchestration`](../.claude/commands/begin-orchestration.md) | Opens **one lane** of a multi-repo roadmap run, with concurrency, reporting and operator-gate rules enforced. |
| [`/orchestration-commander`](../.claude/commands/orchestration-commander.md) | One stateless drain: re-derives the remainder of a run and reports it. See the two run paths in [orchestration.md](workflows/orchestration.md). |
| [`/roadmap-status`](../.claude/commands/roadmap-status.md) | Read-only mid-run view of one roadmap's lanes across every repo. Writes nothing. |
| [`/consolidate-run`](../.claude/commands/consolidate-run.md) | Gathers findings across the fleet for one roadmap and proposes `carryover[]` entries. Writes no `state.json`. |
| [`/consolidate-fleet`](../.claude/commands/consolidate-fleet.md) | Mines several runs at once — lane logs, run records, commander retros, carryover triage — for the mechanisms behind them; emits one pattern analysis and advances a per-roadmap lane-log watermark. HQ-only. Writes no `state.json`. |
| [`/dispose-run`](../.claude/commands/dispose-run.md) | Files a consolidation's mechanisms into the graph as blocks, carryover entries or operator edges; reports what it withheld for want of evidence. Files rows and stops — never authors a roadmap. HQ-only. |
| [`/begin-session`](../.claude/commands/begin-session.md) | Drives one **operator session** — work an agent cannot do alone (a decision, a credential, a judgement call). |

### Branches and worktrees

| Command | What it does |
|---|---|
| [`/start-block`](../.claude/commands/start-block.md) | Marks a block as in-progress in `status.md`. |
| [`/init-worktree`](../.claude/commands/init-worktree.md) | Creates an isolated git worktree for a spec or task. |
| [`/clean-worktree`](../.claude/commands/clean-worktree.md) | Merges a completed worktree branch into main and removes the worktree. |

### Keep the factory in sync

A change made here reaches nothing until it is pulled. These are the pull paths.

| Command | What it does |
|---|---|
| [`/sync-downstream-harness`](../.claude/commands/sync-downstream-harness.md) | Copies changed `.claude/commands/*.md` + `.claude/workflows/` into every scaffolded repo, then reports what changed per repo. Never commits for you. |
| [`/sync-global-commands`](../.claude/commands/sync-global-commands.md) | Installs the harness commands into `~/.claude/commands/`. |
| [`/sync-global-skills`](../.claude/commands/sync-global-skills.md) | Installs the harness skills into `~/.gemini/config/skills/`. |
| [`/sync-brain-skills`](../.claude/commands/sync-brain-skills.md) | Distributes the shared skills into every sub-brain tier named in `brain.toml`. |
| [`/sync-all`](../.claude/commands/sync-all.md) | Runs all of the above through one Python utility. |

### E2E test templates

These are **templates, not commands that run tests**. Each describes a scenario to adapt.
See [`.claude/commands/e2e-templates-README.md`](../.claude/commands/e2e-templates-README.md).

| Template | Scenario |
|---|---|
| [`test_auth_gate`](../.claude/commands/test_auth_gate.md) | Protected routes reject unauthenticated/unauthorized requests. |
| [`test_crud_api`](../.claude/commands/test_crud_api.md) | Create / read / update / delete against a REST endpoint. |
| [`test_error_handling`](../.claude/commands/test_error_handling.md) | UI and API surface errors without exposing raw internals. |
| [`test_ui_form`](../.claude/commands/test_ui_form.md) | A browser form-submit flow via Playwright. |

### `brain/` — reference only

[`.claude/commands/brain/`](../.claude/commands/brain/) holds 33 company-brain commands
(`/log-decision`, `/weekly-plan`, `/biz-status`, …). They are **not** installed into scaffolded
projects — they exist here as the reference copy the brain repo syncs from.

## Skills

A **skill** is procedural guidance loaded on demand — it teaches an agent how to do a
high-stakes operation without getting it wrong. Consult the relevant one *before* the operation,
not after. Source: [`.claude/skills/`](../.claude/skills/).

| Skill | Load it before |
|---|---|
| [`commit-in-this-fleet`](../.claude/skills/commit-in-this-fleet/SKILL.md) | Any `git add`, `commit`, `stash`, `reset` or `mv` in this fleet. |
| [`derive-state-safely`](../.claude/skills/derive-state-safely/SKILL.md) | `mev emit-state --write`, `set-block-status`, or any other state writer. |
| [`edit-state-json`](../.claude/skills/edit-state-json/SKILL.md) | Hand-editing `state.json` or authoring a `depends_on` / `carryover` entry. |
| [`fleet-push-discipline`](../.claude/skills/fleet-push-discipline/SKILL.md) | Pushing any repo, or debugging a push/CI failure unrelated to your change. |
| [`notify-operator`](../.claude/skills/notify-operator/SKILL.md) | Sending a `bastion notify`, or deciding a lane is blocked. |
| [`ping-agent`](../.claude/skills/ping-agent/SKILL.md) | Sending or triaging a cross-lane message. |
| [`report-to-the-operator`](../.claude/skills/report-to-the-operator/SKILL.md) | Drafting a chat reply, turn output or run report. |
| [`run-the-gates`](../.claude/skills/run-the-gates/SKILL.md) | Running `validate-brain` or the `harness.json` checks. |
| [`stop-or-continue`](../.claude/skills/stop-or-continue/SKILL.md) | Deciding whether a session must restart. (Context size is never a reason.) |
| [`write-okf-markdown`](../.claude/skills/write-okf-markdown/SKILL.md) | Creating or editing any `.md` in this corpus. |
| [`write-repo-doc`](../.claude/skills/write-repo-doc/SKILL.md) | Writing or restructuring any doc under `docs/`. |

## Scripts you run directly

Everything under `scripts/` named `check_*.py` or `test_*.py` is a gate — see
[gates.md](gates.md). These are the ones you invoke yourself, in a **terminal** at the repo root.

| Script | What it does |
|---|---|
| [`scripts/sync_downstream_harness.py`](../scripts/sync_downstream_harness.py) | The mechanical half of `/sync-downstream-harness`. Never deletes a file a repo added itself; stamps `planning/.template-version`. |
| [`scripts/sync_all_skills_commands.py`](../scripts/sync_all_skills_commands.py) | The mechanical half of `/sync-all` — reconciles commands and skills across workspaces, tiers and global configs. |
| [`scripts/sync_claude_md_block.py`](../scripts/sync_claude_md_block.py) | Distributes one named `<!-- BEGIN:x -->…<!-- END:x -->` block into every canonical `CLAUDE.md`. Touches only the named block. |
| [`scripts/fleet_concurrency_check.py`](../scripts/fleet_concurrency_check.py) | Enforces "at most two heavy-gate repos at once" with an advisory lockfile registry. A lane takes a slot before starting and releases it when done. |
| [`scripts/roadmap_status_discovery.py`](../scripts/roadmap_status_discovery.py) | The discovery half of `/roadmap-status` — joins the four scattered artifact families into one view. |
| [`scripts/commander_drain.sh`](../scripts/commander_drain.sh) | **Unattended, no dry-run.** Wakes one `/orchestration-commander` drain via `bastion ask` and writes to the shared lock directory. Prefer the slash command interactively. |
| [`scripts/nextest_artifact_wrapper.py`](../scripts/nextest_artifact_wrapper.py) | Wraps `cargo nextest` so a failure names the corpus *file* it read, not just the test name. |

## Gates

52 checks in `planning/harness.json`, all of them gating. They are what "passing" means in this
repo, and both the engines' Test stage and the push gate read the same file.

```
# terminal, repo root — run one check
python3 scripts/check_block_records.py
```

Full list with one line each: [gates.md](gates.md). Schema and how to configure your own:
[harness-json.md](harness-json.md).

## See also

- [index.md](index.md) — the docs folder map.
- [workflows/index.md](workflows/index.md) — vocabulary, the pipeline ladder, the two engines compared.
- [architecture.md](architecture.md) — why the harness/scaffold split exists.
- [using-the-template.md](using-the-template.md) — generate → configure → first run.
- [`.claude/commands/README.md`](../.claude/commands/README.md) — every command's full parameters.
