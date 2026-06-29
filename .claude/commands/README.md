# Slash Commands

Custom Claude Code commands for projects scaffolded from `base-template/`. Invoke with
`/category:command-name` in the prompt (Claude Code exposes subdirectory commands as
`<dir>:<name>` — e.g. `/session:prime`, `/planning:plan`, `/sdlc:implement`).

These drive **structured spec work**: a spec lives at `planning/<name>/tasks.md`, and
the pipeline takes it through implement → test → review → document → wrap-up, writing
predictably-named reports alongside it.

> **Project-agnostic harness.** The command set and `workflows/*.js` engines are fully
> stack-neutral. Validation commands, ports/routes, and the UI-test stage are all driven by
> each project's `planning/harness.json` — the engines carry no stack defaults. Copy a profile
> from `planning/harness.examples.md` to configure your project's stack.
> See `planning/decisions/D5-okf-phase-2-adopted.md` for the adoption record.

---

## Directory Layout

Commands are organized into category subdirectories. `sync-global-commands` installs all
non-brain commands into `~/.claude/commands/` and is invoked from this repo (base-template).

```
.claude/commands/
  README.md                        ← this file
  sync-global-commands.md          ← syncs all non-brain commands to ~/.claude/commands/

  session/           (8 commands)  — session lifecycle
  planning/          (6 commands)  — planning, specs, and roadmaps
  sdlc/             (13 commands)  — SDLC pipeline phases 2–7
  git/               (5 commands)  — git + worktree management
  e2e/               (5 commands)  — end-to-end test runners

  brain/                           ← reference only; NEVER synced to ~/.claude/commands/
    shared/                        ← commands available in HQ + all sub-brains
      session/   (7 files)
      planning/  (2 files)
      projects/  (3 files)
    hq/                            ← HQ (agentic-portfolio) only; never in sub-brains
      projects/  (3 files)
      business/  (9 files)
      content/   (4 files)
```

### Category Summary

| Directory | Count | Commands |
|---|---|---|
| `session/` | 8 | `prime`, `session-recap`, `handoff`, `wrap-up`, `status`, `log-work`, `archive`, `capture` |
| `planning/` | 6 | `plan`, `ticket`, `chore`, `breakdown`, `generate-tasks`, `generate-master-plan` |
| `sdlc/` | 13 | `implement`, `test`, `fix`, `patch`, `document`, `update-docs`, `conditional_docs`, `process-tasks`, `update-task`, `review-task`, `review-workflow`, `review-PR`, `close-out` |
| `git/` | 5 | `commit`, `init-worktree`, `clean-worktree`, `start-block`, `merge-train` |
| `e2e/` | 5 | `test_auth_gate`, `test_crud_api`, `test_error_handling`, `test_ui_form` + README |

### Naming Convention

Subdirectory commands are invoked as `/<dir>:<name>`:

| Old flat name | New name |
|---|---|
| `/prime` | `/session:prime` |
| `/session-recap` | `/session:session-recap` |
| `/handoff` | `/session:handoff` |
| `/wrap-up` | `/session:wrap-up` |
| `/log-work` | `/session:log-work` |
| `/status` | `/session:status` |
| `/archive` | `/session:archive` |
| `/capture` | `/session:capture` |
| `/plan` | `/planning:plan` |
| `/ticket` | `/planning:ticket` |
| `/chore` | `/planning:chore` |
| `/breakdown` | `/planning:breakdown` |
| `/generate-tasks` | `/planning:generate-tasks` |
| `/generate-master-plan` | `/planning:generate-master-plan` |
| `/implement` | `/sdlc:implement` |
| `/test` | `/sdlc:test` |
| `/fix` | `/sdlc:fix` |
| `/patch` | `/sdlc:patch` |
| `/document` | `/sdlc:document` |
| `/update-docs` | `/sdlc:update-docs` |
| `/conditional_docs` | `/sdlc:conditional_docs` |
| `/process-tasks` | `/sdlc:process-tasks` |
| `/update-task` | `/sdlc:update-task` |
| `/review-task` | `/sdlc:review-task` |
| `/review-workflow` | `/sdlc:review-workflow` |
| `/review-PR` | `/sdlc:review-PR` |
| `/close-out` | `/sdlc:close-out` |
| `/commit` | `/git:commit` |
| `/init-worktree` | `/git:init-worktree` |
| `/clean-worktree` | `/git:clean-worktree` |
| `/start-block` | `/git:start-block` |
| `/merge-train` | `/git:merge-train` |

### `brain/` — Reference Only

`brain/` contains a reference copy of all brain-level commands organized by distribution scope.
It is **never** synced to `~/.claude/commands/` (the `--exclude='brain/'` flag in
`sync-global-commands` enforces this). Brain commands are managed by the brain repo's own
`sync-brain-commands` command. See `brain/README.md` for the full layout.

### `sync-global-commands`

Run `/sync-global-commands` from base-template root to install (or update) all harness commands
into `~/.claude/commands/`. The command:
- Guards that it is running from the base-template root.
- Runs `rsync -av --delete --exclude='brain/' .claude/commands/ ~/.claude/commands/`.
- Verifies with a dry-run that nothing remains to sync.
- Reports file counts before and after and confirms `brain/` is absent from global.

---

## SDLC Pipeline

The complete development lifecycle for structured spec work. Each step runs in a fresh agent
context, starts with `/session:prime`, reads the prior step's output file, and writes a
predictably-named output file.

### Phase Table

| SDLC Phase | Command | Role | Output |
|---|---|---|---|
| Session Start | `/session:session-recap` | Briefing: recent Log entries, where you left off, next step | chat only |
| Session Start | `/session:status` | Check current focus and what's in progress | chat only |
| Session Start | `/sdlc:process-tasks` | Check which specs are eligible to start | chat only |
| Session End | `/session:wrap-up [note]` | Log work + commit; clean close without a handoff file | status.md, log.md, git |
| Session End | `/session:handoff [note]` | Write handoff + log work + commit; hands off to a fresh session | `planning/handoff.md`, status.md, log.md, git |
| Session End | `/sdlc:close-out [--skip-coverage] [note]` | Verify coverage → patch docs → hand off; the quality-close pipeline after sdlc-run/sdlc-flow | status.md, log.md, docs/, git |
| Block Setup | `/git:start-block [name]` | Flip a spec to `In progress` in status.md | status.md |
| **1 — Roadmap** | `/planning:generate-master-plan [desc]` | Author the full roadmap as canonical block definitions | `planning/master-plan.md` |
| **1 — Plan** | `/planning:generate-tasks <name>` · `/planning:generate-tasks --from <path>` | Write the full task spec from a master-plan block, **or** from a standalone block file (`--from`) | `planning/<name>/tasks.md` |
| **1 — Plan (ad-hoc)** | `/planning:chore` · `/planning:ticket` · `/planning:plan <desc>` | Plan ad-hoc work from a free-text description (not a master-plan block) | `planning/<prefix>-<slug>/{tasks,plan}.md` |
| **1 — Plan (opt.)** | `/planning:breakdown <spec>` | Decompose spec into atomic, agent-executable sub-steps | `planning/<name>/breakdown.md` |
| **2 — Implement** | `/sdlc:implement <spec> [N]` | Execute every task (or task N) in the spec | `planning/<name>/sdlc/reports/[taskN-]implement.md` |
| **2 — Hotfix** | `/sdlc:patch` | Implement → validate → commit for low-risk single-file fixes; skips test/review/document | git history |
| **2 — Fix** | `/sdlc:fix <spec> [N]` | Targeted fixes for FAIL/PARTIAL verdict; reads review report; overwrites implement report | `planning/<name>/sdlc/reports/[taskN-]implement.md` |
| **2 — Track** | `/sdlc:update-task [name] <step> [note]` | Mark a step done and/or append a dated note mid-implementation | spec file (in-place) |
| **2 — Commit** | `/git:commit [hint]` | Stage + commit with a conventional message | git history |
| **3 — Test** | `/sdlc:test <spec> [N]` | Run the project's validation suite; write snapshot | `planning/<name>/sdlc/reports/[taskN-]test.md` |
| **4 — Review** | `/sdlc:review-task <spec> [N]` | Verify all criteria; run fresh tests; issue verdict | `planning/<name>/sdlc/reports/[taskN-]review.md` |
| **5 — Document** | `/sdlc:document <spec> [N]` | Surgically patch `docs/`; gates on PASS verdict | `planning/<name>/sdlc/reports/[taskN-]document.md` |
| **6 — Wrap-up** | `/session:log-work [notes]` | Update status.md + append Log entry + sync company brain | status.md, log.md, brain `docs/projects/<slug>.md`, brain `README.md` |
| **7 — Verify run** | `/sdlc:review-workflow <name> [N]` | Audit pipeline execution: reports, commits, Log, STATUS | `planning/<name>/sdlc/reports/[taskN-]workflow-review.md` |

### Pipeline Flow

```
SESSION START
  /session:status                  → read-only: current focus and what's next
  /sdlc:process-tasks              → read-only: which specs are eligible

BLOCK SETUP
  /git:start-block <spec>          → status.md

PHASE 1 — PLAN
  /planning:generate-tasks <spec>           → planning/<spec>/tasks.md
        ↓  (optional)
  /planning:breakdown planning/<spec>/tasks.md   → planning/<spec>/breakdown.md

PHASE 2 — IMPLEMENT
  /sdlc:implement planning/<spec>/tasks.md [N]
        → planning/<spec>/sdlc/reports/[taskN-]implement.md
  (/sdlc:update-task and /git:commit can be called any number of times during this phase)

PHASE 3 — TEST
  /sdlc:test planning/<spec>/tasks.md [N]
        → planning/<spec>/sdlc/reports/[taskN-]test.md

PHASE 4 — REVIEW                   ← runs fresh tests; verdict gates next step
  /sdlc:review-task planning/<spec>/tasks.md [N]
        → planning/<spec>/sdlc/reports/[taskN-]review.md

        if PASS → continue to PHASE 5 — DOCUMENT
        if FAIL/PARTIAL → PHASE 2 — FIX:
  /sdlc:fix planning/<spec>/tasks.md [N]
        → planning/<spec>/sdlc/reports/[taskN-]implement.md  (overwritten)
  then repeat: /sdlc:test [N] → /sdlc:review-task [N] until PASS

PHASE 5 — DOCUMENT                 ← gates on PASS verdict
  /sdlc:document planning/<spec>/tasks.md [N]
        → planning/<spec>/sdlc/reports/[taskN-]document.md

PHASE 6 — WRAP-UP
  /session:log-work [notes]        → status.md, log.md

(OPTIONAL) PHASE 7 — VERIFY RUN
  /sdlc:review-workflow <spec> [N] → planning/<spec>/sdlc/reports/[taskN-]workflow-review.md
```

### Argument Convention

Every step from Phase 2 onward takes the same form: `planning/<name>/tasks.md [N]`

Split on the last space. Trailing number = task N (scope to that task only). No number = full
spec. Use the **same `N`** throughout the pipeline — it determines all report filenames at
every step.

### Directory Layout

Each spec gets its own directory under `planning/`. All reports live in a `reports/`
subdirectory alongside the spec:

```
planning/
  <spec>/
    tasks.md          ← spec (written by /planning:generate-tasks)
    breakdown.md      ← optional (written by /planning:breakdown)
    sdlc/
      reports/
        implement.md         ← or task3-implement.md for task-scoped
        test.md              ← or task3-test.md
        review.md            ← or task3-review.md
        document.md          ← or task3-document.md
        workflow.md          ← or task3-workflow.md (written by /sdlc-run)
        workflow-review.md   ← or task3-workflow-review.md (written by /sdlc:review-workflow)
```

### Report File Naming

Pattern: `[taskN-]{step}.md` inside `planning/<name>/sdlc/reports/`

| Step | Full-spec | Task-scoped |
|---|---|---|
| implement | `implement.md` | `task3-implement.md` |
| fix | *(overwrites implement slot)* | *(overwrites implement slot)* |
| test | `test.md` | `task3-test.md` |
| review | `review.md` | `task3-review.md` |
| document | `document.md` | `task3-document.md` |
| workflow (sdlc-run) | `workflow.md` | `task3-workflow.md` |
| workflow-review | `workflow-review.md` | `task3-workflow-review.md` |

> **Note:** `/sdlc:fix` writes to the same `implement.md` slot as `/sdlc:implement` — it represents the
> current state of Phase 2 work. Git history preserves prior versions.

---

## Automated & Orchestrated Pipelines

The manual Phase 1 → 7 commands above can be run end-to-end by automated workflows
(`workflows/*.js`). Invoke them like slash commands. Each runs the same pipeline stages, but
unattended.

| Workflow | Scope | Isolation |
|---|---|---|
| `/sdlc-run <name> [N]` | one task or a **full spec**, sequential | none — runs on the current branch, updates STATUS/Log directly |
| `/sdlc-task <name> N` | **one** task, parallel-safe | own git worktree; defers STATUS/Log to merge time |
| `/sdlc-flow <name> [range]` | a **full spec** as one shared worktree, per-task test→fix loop, one end review, a PR | own worktree; terminates in a PR |
| `/sdlc-block [plan-file]` | a **whole roadmap** (master-plan) as a branch train — one `/sdlc-flow` per independent block, in dependency-ordered waves | each block its own worktree + PR; orchestrator owns the train branch and merges in dependency order |

> **Full reference with mermaid diagrams, per-stage detail, and token usage:**
> [`docs/workflows/`](../../docs/workflows/index.md) — one page per engine plus the manual lifecycle.

### `/sdlc-block` — roadmap orchestration (branch train)

**Drive a whole master-plan roadmap to completion in one invocation.** Fans out **one `/sdlc-flow` per
independent block** over dependency-ordered waves, producing a **branch train of reviewable PRs**.
Blocks in a wave are independent *by construction* (the master-plan's per-block **Files** + **Out of
scope** contract). A **pre-flight** guarantees a clean tree with the plan committed and sets up the train
branch off the base; **enumerate** parses the `## Phase N` / `### Block X` sections into blocks + a
dependency graph. Per wave it ensures each block's `tasks.md`, fans out the child flows (each `--no-pr`),
runs a **per-block close-out gap-check** (scoped to the whole block, `<train>...HEAD`), then opens the PR
(default) or merges into the base (`--auto-merge`), advancing the train in dependency order. A final
`/sdlc:close-out --gap-check-only` runs over the full train. See
[D34](../../planning/decisions/D34-adhoc-planning-seam.md).

| Arg | Meaning | Default |
|---|---|---|
| `[plan-file]` | Optional 1st positional — a master-plan-format path, or a slug → `planning/<slug>/plan.md`. | `planning/master-plan.md` |
| `--base <branch>` | Base branch the train forks from / merges into. | `main` |
| `--auto-merge` | Merge each block into `<base>` in dependency order (no PRs). | off |
| `--no-pr` | Branch train only — no PRs anywhere. | off |
| `--max-parallel-blocks N` | Max `/sdlc-flow` runs in flight per wave (default from `harness.json` `block.maxParallelBlocks`). | `3` |
| `--blocks <sel>` | Phase selection: `0`, `0-1`, `0,2` — only those phases' blocks run. | all phases |
| `--resume` | Re-read `block-orchestration-state.json`, skip done blocks, continue. | — |

After the train is built, review each PR with **`/sdlc:review-PR <PR#>`** and land them bottom-up with
**`/git:merge-train`** (below).

### `/sdlc:review-PR <PR#> [plan-slug]`
Spec-aware review for a branch-train PR. Locates the block's `block-orchestration-state.json`, checks
out the PR, runs the project's gating suite (from `harness.json`, falling back to the spec's
`## Validation Commands`) + the emoji gate (merge-base scoped), reviews the diff against the block's
Acceptance Criteria, and posts an APPROVE / REQUEST_CHANGES / COMMENT verdict via `gh pr review`. Restores
the original branch when done.

### `/git:merge-train [plan-slug]`
Merges the block-train PRs into the base in the recorded `merge_order` (dependency order), halting on the
first unresolved conflict. Pre-flights a clean tree + synced base, classifies each block
(ready / already-merged / needs-approval / has-conflicts / escalated), stops before any merge if any PR
is `CONFLICTING`, confirms with you, then merges each via `gh pr merge --merge --delete-branch`. Exits
early for `--auto-merge` / `--no-pr` runs. Resume-safe — already-merged blocks are auto-detected on re-run.

---

## Session Orientation

### `/session:wrap-up [note]`
Clean session close without a handoff. Runs `/session:log-work` (syncs status.md + appends log entry)
then `/git:commit`. Use this when you're done with a piece of work and don't need to hand off
to a fresh agent.

### `/session:handoff [note]`
Session end-of-context handoff. Writes `planning/handoff.md` (what's in flight, completed,
remaining, open questions, first command for the next agent), then invokes `/session:log-work` and
`/git:commit`. `/session:prime` in the next session detects the handoff file and surfaces it first.
Delete `planning/handoff.md` once the new session has consumed it.

### `/sdlc:close-out [--gap-check-only] [--skip-coverage] [note]`
Quality-close pipeline for the end of an `sdlc-run` or `sdlc-flow` session. Runs four
steps in sequence: **(1)** the full validation suite from `planning/harness.json` — stops
immediately if any gating check fails; **(2)** coverage gap scan — reads changed source
files, classifies gaps as adequate/non-blocking/blocking, writes minimal targeted tests for
blocking gaps and re-runs the suite to confirm; **(3)** `/sdlc:update-docs --patch`; **(4)**
`/session:handoff` with the provided note. Pass `--skip-coverage` to skip step 2 when coverage was
already verified by a prior `/sdlc:review-task`. Pass `--gap-check-only` to skip step 4 (the
handoff) — used by `/sdlc-block` for automated per-block gap-checks mid-run. Non-blocking
gaps are noted in the handoff rather than blocking it.

### `/session:session-recap`
Start-of-session briefing: reads the three most recent Log entries, status.md, the current
spec's `tasks.md`, and the `reports/` directory listing; outputs a concise briefing (under 300
words) and the exact next command. Read-only.

### `/sdlc:conditional_docs [task-type]`
Routes the agent to the documentation most relevant to the current task type (feature, bug/fix,
api/endpoint, test/testing, docs/documentation). Reduces CLAUDE.md overload by surfacing only
the files needed for the task at hand. Takes an optional argument; defaults to reading
`planning/context.md` + `planning/status.md` + `planning/harness.json`.

### `/session:prime`
Orient to this repo at session start: reads `README.md`, `CLAUDE.md`, `planning/context.md`,
`planning/status.md`; runs `git ls-files`; summarizes the codebase, layout, focus, and standing
rules. Read-only. Embedded in every pipeline command.

### `/session:status`
Reads only `planning/status.md` and reports the Current focus line, what's In progress, and
what's Next. Read-only.

### `/sdlc:process-tasks`
Reads `status.md`, applies sequential eligibility rules (a spec is ready only if all specs above
it are `Done`), and returns a status table. Read-only.

---

## Phase 1 — Plan

### `/planning:generate-master-plan`
Authors (or revises) `planning/master-plan.md` — the roadmap source of truth — as a sequence of
canonical **block definitions** (`## Phase N` → `### Block X`, each with What / Why / Build notes /
Acceptance criteria) whose phase/block headers `/planning:generate-tasks` can parse directly. Turns a
free-form planning session into the structure the rest of Phase 1 expects. `/new-project` should call
this as its post-scaffold roadmap step. See `planning/decisions/D34-adhoc-planning-seam.md`.

### `/planning:generate-tasks`
Reads the relevant section of `planning/master-plan.md`, writes a full task spec to
`planning/<name>/tasks.md`, and **commits it** (clean tree for downstream `/sdlc-block`).
Each spec carries a **Validation Commands** block and ends with a Validate task.

**`--from <path>` mode** decomposes a single **standalone block file** (e.g. a `/planning:plan` output)
instead of a master-plan block — for ad-hoc / experimental features kept out of the roadmap. It
derives the slug from the file's parent directory and writes `tasks.md` beside the source, then runs
the identical decomposition / pipeline-recommendation logic. The default master-plan slug mode is
unchanged.

### `/planning:breakdown`
Reads a task spec and the source files each step touches, then writes a granular
`breakdown.md` — every sub-step atomic (one file, one change, one command). Both `/sdlc:implement`
and `/sdlc:fix` auto-detect this file and use the matching `### Step N:` section as the primary
execution guide (HOW); `tasks.md` stays authoritative for scope (WHAT).

### Pre-planning capture — `/session:capture`

Before something is ready to plan, use `/session:capture` to park rich conversation notes without
losing them. Creates `planning/<slug>/notes.md` with a structured scaffold and adds a
pointer ticket to the brain's `planning/backlog.md`.

| Command | Use for | Writes to |
|---|---|---|
| `/session:capture <title>` | Rich pre-plan notes — detailed enough to need a file, not yet a plan | `planning/<slug>/notes.md` + brain backlog |

The notes file sections (What & Why · Context & Background · Key Information · Open Questions ·
Rough Scope) are designed as direct input to the planning commands below — paste conversation
content in, then promote with `/planning:plan`, `/planning:chore`, or `/planning:generate-master-plan` when ready.

### Ad-hoc planners — `/planning:chore`, `/planning:ticket`, `/planning:plan`

Entry points into Phase 1 for work that **isn't** a master-plan block. Each takes a free-text
description, researches the codebase, and writes a spec into its own `planning/<dir>/` directory.
Output feeds the rest of the pipeline unchanged.

| Command | Use for | Writes to |
|---|---|---|
| `/planning:chore <description>` | Maintenance / housekeeping (no behavior change) | `planning/chore-<slug>/tasks.md` |
| `/planning:ticket <description>` | Bug fix or targeted enhancement that requires tests + observable AC | `planning/ticket-<slug>/tasks.md` |
| `/planning:plan <description>` | Any ad-hoc or experimental feature — mini-roadmap format | `planning/plan-<slug>/plan.md` |

`/planning:chore` and `/planning:ticket` write a runnable `tasks.md` **directly** and route to lean `/sdlc-task`
(the fast path). `/planning:plan` writes a `plan.md` in the **master-plan format** (phases/blocks/Quick
Reference table), so `/sdlc-block` can orchestrate it as a branch train or `/planning:generate-tasks --from
planning/plan-<slug>/plan.md` can decompose a single block into a `tasks.md` → `/sdlc-flow`, all
**without** touching `master-plan.md`. See `planning/decisions/D34-adhoc-planning-seam.md`.

---

## Phase 2 — Implement

### `/sdlc:implement`
Runs `/session:prime`, reads the plan file, executes every step (or task N) following CLAUDE.md
conventions, runs the relevant Validation Commands, and writes
`planning/<name>/sdlc/reports/[taskN-]implement.md`.

### `/sdlc:fix`
Reads the review report to extract every failing criterion, orients via `/session:prime`, and applies
targeted changes addressing only the failures. Overwrites the `implement.md` slot. Hard-errors
if the review report is absent; soft-stops if the verdict is already PASS.

### `/sdlc:update-task`
Optionally marks a step done (prepends `[done]`) and/or appends a dated note to the spec's `## Notes`
section. Auto-detects the current spec from status.md if not given. Does not touch status.md.

### `/git:commit`
Inspects `git status`/`git diff --stat`, chooses a commit strategy (code-only, docs-only, or
both → two commits), drafts a conventional message, and confirms before committing. Never
pushes, never `--no-verify`, never `git add -A`.

---

## Phase 3 — Test

### `/sdlc:test`
Runs `/session:prime`, then the project's validation suite (lint, type-check, tests, build, and any
project-specific gates), returning results as a JSON array sorted failed-first. With a spec path,
also writes `planning/<name>/sdlc/reports/[taskN-]test.md`.

> **Stack note:** the test stage runs the checks defined in `planning/harness.json`
> (`validation.checks[]`). The harness ships no stack defaults — define your project's actual
> validation commands there (copy a profile from `planning/harness.examples.md`). If the config
> is absent, the stage falls back to the spec's `## Validation Commands` section.

---

## Phase 4 — Review

### `/sdlc:review-task`
Runs `/session:prime`, reads the `implement.md`/`test.md` reports as context, then runs a **fresh test
suite** as authoritative verification. Verdict is PASS only if all criteria are MET **and** the
fresh tests pass. Writes a review report.

---

## Phase 5 — Document

### `/sdlc:document`
Gates strictly on the review verdict being PASS. Reads the implement report's **Files Created
or Modified** table to scope updates, then surgically patches only affected sections of
`docs/*.md`. Flags architecture-level changes as `NEEDS_REVIEW`. Never touches `planning/`,
`log.md`, `status.md`, or `CLAUDE.md`.

---

## Phase 6 — Wrap-up

### `/session:log-work`
Reads `status.md`, the current spec, and `log.md`; runs `git diff --stat`. Updates
`status.md` and appends a `log.md` entry. Prompts you to add settled choices to
`planning/decisions/` — never edits decisions directly. Also syncs the company brain
(`docs/projects/<slug>.md`, `README.md`) to match the new status.

---

## Phase 7 — Verify Run (Optional)

### `/sdlc:review-workflow`
Audits a completed `/sdlc-run` pipeline execution — not the implementation, but the mechanics:
report files present and well-formed, the Test stage ran the suite, commits follow conventional
format, Log/STATUS reflect the outcome. Issues PASS/PARTIAL/FAIL and writes
`workflow-review.md`. Does **not** re-run tests — use `/sdlc:review-task` for that.

---

## Block Setup & Worktree Management

### `/git:start-block`
Finds the target spec (defaulting to the first non-done spec), checks that all preceding specs
are `Done`, then flips it to `In progress` and updates Current focus + Last updated.

### `/git:init-worktree` · `/git:clean-worktree`
Manual entry points for the isolated-worktree lifecycle that `/sdlc-task` and `/sdlc-block`
automate. `/git:init-worktree` derives a branch/worktree from the spec slug and creates an isolated
sparse checkout; `/git:clean-worktree` **merges before delete** — fast-forward-merges the branch
into `main`, applies deferred STATUS/Log updates, then removes the worktree. Do **not** run
`/git:clean-worktree` for `/sdlc-block` tasks — that orchestrator merges each wave for you.

### `/sdlc:update-docs [--patch] [--since <ref>]`
Documentation health sweep — audits all `docs/` files and `.claude/commands/README.md` against
the current codebase (commands, engine flags, schema fields, new decisions) and recent git
history. Produces a structured gap report: **STALE** sections, **MISSING** coverage, **NO-DOC**
(intentionally undocumented), and **CURRENT** (confirmed). Add `--patch` to apply surgical
fixes for clear-cut stale sections; without it the command is read-only. The un-gated complement
to `/sdlc:document` — use for periodic doc health checks outside the pipeline.

---

## Company Brain Integration

`/session:log-work` automatically mirrors status updates to the parent `agentic-portfolio/` company
brain (`docs/projects/<slug>.md`, `README.md`). To run brain-level commands (briefing,
sync-status, log-decision, add-project, log-correspondence), open Claude Code in the
`agentic-portfolio/` root.
