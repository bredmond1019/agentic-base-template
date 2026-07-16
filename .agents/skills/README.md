# Agent Skills

Custom agent skills for projects scaffolded from `base-template/`. These skills empower your autonomous agents with structured capabilities for planning, SDLC, and codebase management. 

These drive **structured spec work**: a spec lives at `planning/<name>/tasks.md` (prose — Goal,
Acceptance Criteria, Validation Commands) + a companion `planning/<name>/tasks.json` (the task
list itself — see D44/D45/D46 in `planning/decisions/`), and the pipeline takes it through
implement → test → review → document → wrap-up, writing predictably-named reports alongside it.

> **Project-agnostic harness.** The skill set and workflows are fully
> stack-neutral. Validation commands, ports/routes, and the UI-test stage are all driven by
> each project's `planning/harness.json` — the engines carry no stack defaults. Copy a profile
> from `planning/harness.examples.md` to configure your project's stack.

---

## Directory Layout

All skills live in `.agents/skills/` — each skill in its own directory with a `SKILL.md` file.
`sync-global-skills` installs all non-brain skills into `~/.gemini/config/skills/`.

```
.agents/skills/
  README.md                        ← this file
  sync-global-skills               ← skill to sync all skills to ~/.gemini/config/skills/
  sync-brain-skills                ← skill to distribute shared skills to all sub-brain tiers
  sync-global-commands             ← installs .claude/commands/ into ~/.claude/commands/ (Claude Code)

  archive/        capture/       commit/        handoff/
  log-work/       prime/         session-recap/ status/
  wrap-up/         update-state/  next/

  breakdown/      chore/         generate-master-plan/  generate-tasks/
  plan/           ticket/        backlog-ticket/

  close-out/      conditional_docs/  document/      fix/
  implement/      patch/             process-tasks/ review-PR/
  review-task/    review-workflow/   test/          update-docs/
  update-task/

  clean-worktree/  init-worktree/  merge-train/  start-block/

  sdlc-block/  sdlc-flow/  sdlc-run/  sdlc-task/   ← thin doc-comment mirrors of the
                                                       .claude/workflows/*.js engines (JS-driven,
                                                       not prose-instruction skills)
```

### `sync-global-skills`

Use the `sync-global-skills` skill from base-template root to install (or update) all harness skills
into `~/.gemini/config/skills/`. 

---

## SDLC Pipeline

The complete development lifecycle for structured spec work. Each step runs in a fresh agent
context, starts with `prime`, reads the prior step's output file, and writes a
predictably-named output file.

### Phase Table

| SDLC Phase | Skill | Role | Output |
|---|---|---|---|
| Session Start | `session-recap` | Briefing: recent Log entries, where you left off, next step | chat only |
| Session Start | `status` | Check current focus and what's in progress | chat only |
| Session Start | `process-tasks` | Check which specs are eligible to start | chat only |
| Session Start | `next` | Briefing on what's up next, blocked, and recommend next action | chat only |
| Session End | `wrap-up` | Log work + commit; clean close without a handoff file | status.md, log.md, git |
| Session End | `handoff` | Write handoff + log work + commit; hands off to a fresh session | `planning/handoff.md`, status.md, log.md, git |
| Session End | `close-out` | Verify coverage → patch docs → hand off; the quality-close pipeline after sdlc-run/sdlc-flow | status.md, log.md, docs/, git |
| Block Setup | `start-block` | Flip a spec to `In progress` in status.md | status.md |
| **1 — Roadmap** | `generate-master-plan` | Author the full roadmap as canonical block definitions | `planning/master-plan.md` |
| **1 — Plan** | `generate-tasks` | Write the full task spec from a master-plan block, **or** from a standalone block file (`--from`) | `planning/<name>/tasks.md` + `tasks.json` |
| **1 — Plan (ad-hoc)** | `chore` · `ticket` · `plan` | Plan ad-hoc work from a free-text description (not a master-plan block) | `planning/<prefix>-<slug>/{tasks.md+tasks.json, or plan.md}` |
| **1 — Plan (opt.)** | `breakdown` | Decompose spec into atomic, agent-executable sub-steps | `planning/<name>/breakdown.md` |
| **2 — Implement** | `implement` | Execute every task (or task N) in the spec | `planning/<name>/sdlc/reports/[taskN-]implement.md` |
| **2 — Hotfix** | `patch` | Implement → validate → commit for low-risk single-file fixes; skips test/review/document | git history |
| **2 — Fix** | `fix` | Targeted fixes for FAIL/PARTIAL verdict; reads review report; overwrites implement report | `planning/<name>/sdlc/reports/[taskN-]implement.md` |
| **2 — Track** | `update-task` | Mark a step done and/or append a dated note mid-implementation | spec file (in-place) |
| **2 — Commit** | `commit` | Stage + commit with a conventional message | git history |
| **3 — Test** | `test` | Run the project's validation suite; write snapshot | `planning/<name>/sdlc/reports/[taskN-]test.md` |
| **4 — Review** | `review-task` | Verify all criteria; run fresh tests; issue verdict | `planning/<name>/sdlc/reports/[taskN-]review.md` |
| **5 — Document** | `document` | Surgically patch `docs/`; gates on PASS verdict | `planning/<name>/sdlc/reports/[taskN-]document.md` |
| **6 — Wrap-up** | `log-work` | Update status.md + append Log entry + sync company brain | status.md, log.md, brain `docs/projects/<slug>.md`, brain `README.md` |
| **7 — Verify run** | `review-workflow` | Audit pipeline execution: reports, commits, Log, STATUS | `planning/<name>/sdlc/reports/[taskN-]workflow-review.md` |

> **Note:** `/fix` writes to the same `implement.md` slot as `/implement` — it represents the
> current state of Phase 2 work. Git history preserves prior versions.

---

## Session Orientation

### `prime`
Orient to this repo at session start: reads `README.md`, `CLAUDE.md` (or AGENT.md), `planning/context.md`, `planning/status.md`; runs `git ls-files`; summarizes the codebase, layout, focus, and standing rules. Read-only. Embedded in every pipeline command.

### `wrap-up`
Clean session close without a handoff. Runs `log-work` (syncs status.md + appends log entry) then `commit`.

### `handoff`
Session end-of-context handoff. Writes `planning/handoff.md` (what's in flight, completed, remaining, open questions, first command for the next agent), then invokes `log-work` and `commit`. `prime` in the next session detects the handoff file and surfaces it first.

### `close-out`
Quality-close pipeline for the end of a session. Runs four steps in sequence: (1) validation suite; (2) coverage gap scan; (3) `update-docs --patch`; (4) `handoff`.

### `session-recap`
Start-of-session briefing. Read-only summary of where the project left off.

### `status`
Reads only `planning/status.md` and reports the Current focus line, what's In progress, and what's Next. Read-only.

### `process-tasks`
Reads `status.md`, applies sequential eligibility rules, and returns a status table. Read-only.

### `next`
Briefing on what's next, what's blocked, and a recommended next action based on local status and HQ/business/core goals. Read-only.

---

## Pre-planning capture — `capture`

Before something is ready to plan, use `capture` to park rich conversation notes without
losing them. Creates `planning/<slug>/notes.md` with a structured scaffold and adds a
pointer ticket to the brain's `planning/backlog.md`.

| Command | Use for | Writes to |
|---|---|---|
| `capture` | Rich pre-plan notes — detailed enough to need a file, not yet a plan | `planning/<slug>/notes.md` + brain backlog |
