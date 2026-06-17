# Agent Skills

Custom Gemini Agent Skills for projects scaffolded from `base-template/`. These skills follow
the [Agent Skills](https://agentskills.io) open standard. The Gemini Antigravity CLI loads them
from `.agents/skills/<name>/SKILL.md` at the start of a session.

These skills drive **structured spec work**: a spec lives at `planning/tasks/<name>/tasks.md`,
and the pipeline takes it through:
**Plan → Implement → Test → Review → Document → Wrap-up** (writing predictably-named reports
alongside it).

> **Project-agnostic harness.** This skill set was curated down to the stack-neutral SDLC core
> (the `.claude/commands/` twin documents the same pipeline). The skill bodies and the
> `sdlc-block` / `sdlc-task` engines were seeded from a Next.js project and still carry some
> stack-specific assumptions (npm validation scripts, content/bilingual gates). Generalizing
> them is **deferred to OKF Phase 2** — see the template `DEVLOG.md` and `planning/decisions/`.

---

## SDLC Pipeline

The complete development lifecycle for structured spec work. Each step runs in the session
context, starts with the **prime** skill, reads the prior step's output file, and writes a
predictably-named output file.

### Phase Table

| SDLC Phase | Skill | Role | Output |
|---|---|---|---|
| Session Start | `session-recap` | Briefing: recent DEVLOG entries, where you left off, next step | chat only |
| Session Start | `status` | Check current focus and what's in progress | chat only |
| Session Start | `process-tasks` | Check which specs are eligible to start | chat only |
| Block Setup | `start-block [name]` | Flip a spec to `In progress` in STATUS.md | STATUS.md |
| **1 — Plan** | `generate-tasks <name>` | Write the full task spec from the master plan | `planning/tasks/<name>/tasks.md` |
| **1 — Plan (ad-hoc)** | `chore` · `feature` · `plan <desc>` | Plan ad-hoc work from a free-text description | `planning/tasks/<prefix>-<slug>/{tasks,plan}.md` |
| **1 — Plan (opt.)** | `breakdown <spec>` | Decompose spec into atomic, agent-executable sub-steps | `planning/tasks/<name>/breakdown.md` |
| **2 — Implement** | `implement <spec> [N]` | Execute every task (or task N) in the spec | `planning/tasks/<name>/reports/[taskN-]implement.md` |
| **2 — Fix** | `fix <spec> [N]` | Targeted fixes for FAIL/PARTIAL verdict; reads review report | `planning/tasks/<name>/reports/[taskN-]implement.md` |
| **2 — Track** | `update-task [name] <step> [note]` | Mark a step done and/or append a dated note | spec file (in-place) |
| **2 — Commit** | `commit [hint]` | Stage + commit with a conventional message | git history |
| **3 — Test** | `test <spec> [N]` | Run the project's validation suite; write snapshot | `planning/tasks/<name>/reports/[taskN-]test.md` |
| **4 — Review** | `review-task <spec> [N]` | Verify all criteria; run fresh tests; issue verdict | `planning/tasks/<name>/reports/[taskN-]review.md` |
| **5 — Document** | `document <spec> [N]` | Surgically patch `docs/`; gates on PASS verdict | `planning/tasks/<name>/reports/[taskN-]document.md` |
| **6 — Wrap-up** | `log-work [notes]` | Update STATUS.md + append DEVLOG entry + sync company brain | STATUS.md, DEVLOG.md, brain `docs/projects/<slug>.md` |
| **7 — Verify run** | `review-workflow <name> [N]` | Audit pipeline execution: reports, commits, DEVLOG, STATUS | `planning/tasks/<name>/reports/[taskN-]workflow-review.md` |

### Pipeline Flow

```
SESSION START
  status                          → read-only: current focus and what's next
  process-tasks                   → read-only: which specs are eligible

BLOCK SETUP
  start-block <spec>              → STATUS.md

PHASE 1 — PLAN
  generate-tasks <spec>           → planning/tasks/<spec>/tasks.md
        ↓  (optional)
  breakdown planning/tasks/<spec>/tasks.md  → planning/tasks/<spec>/breakdown.md

PHASE 2 — IMPLEMENT
  implement planning/tasks/<spec>/tasks.md [N]
        → planning/tasks/<spec>/reports/[taskN-]implement.md
  (update-task and commit can be called any number of times during this phase)

PHASE 3 — TEST
  test planning/tasks/<spec>/tasks.md [N]
        → planning/tasks/<spec>/reports/[taskN-]test.md

PHASE 4 — REVIEW                  ← runs fresh tests; verdict gates next step
  review-task planning/tasks/<spec>/tasks.md [N]
        → planning/tasks/<spec>/reports/[taskN-]review.md

        if PASS → continue to PHASE 5 — DOCUMENT
        if FAIL/PARTIAL → PHASE 2 — FIX:
  fix planning/tasks/<spec>/tasks.md [N]
        → planning/tasks/<spec>/reports/[taskN-]implement.md  (overwritten)
  then repeat: test [N] → review-task [N] until PASS

PHASE 5 — DOCUMENT                ← gates on PASS verdict
  document planning/tasks/<spec>/tasks.md [N]
        → planning/tasks/<spec>/reports/[taskN-]document.md

PHASE 6 — WRAP-UP
  log-work [notes]                → STATUS.md, DEVLOG.md

(OPTIONAL) PHASE 7 — VERIFY RUN
  review-workflow <spec> [N]      → planning/tasks/<spec>/reports/[taskN-]workflow-review.md
```

### Argument Convention

Every step from Phase 2 onward takes the same input format: `planning/tasks/<name>/tasks.md [N]`.
Trailing number `N` represents the target task number (scopes work and reports to that task
only). No number implies the full spec.

---

## Skills Catalog

### Session Orientation
*   **[prime](file://./prime/SKILL.md)**: Orient to this repo at the start of a session. Read-only.
*   **[status](file://./status/SKILL.md)**: Report the current focus and sequence status from `STATUS.md`. Read-only.
*   **[session-recap](file://./session-recap/SKILL.md)**: Start-of-session briefing: what was done recently, where we left off. Read-only.
*   **[process-tasks](file://./process-tasks/SKILL.md)**: Analyze sequential spec prerequisites to report which tasks are eligible. Read-only.

### Phase 1 — Plan
*   **[generate-tasks](file://./generate-tasks/SKILL.md)**: Write a full task spec (`tasks.md`) from a master-plan block.
*   **[breakdown](file://./breakdown/SKILL.md)**: Decompose a task spec into granular, executable sub-steps (`breakdown.md`).
*   **[chore](file://./chore/SKILL.md)**: Plan ad-hoc maintenance or housekeeping work.
*   **[feature](file://./feature/SKILL.md)**: Plan a new capability (design, stories, strategy).
*   **[plan](file://./plan/SKILL.md)**: General-purpose planner for other tasks scaled to complexity.

### Phase 2 — Implement & Track
*   **[implement](file://./implement/SKILL.md)**: Execute a plan file against the codebase and write an implement report.
*   **[fix](file://./fix/SKILL.md)**: Targeted fixes addressing failures identified in a review report.
*   **[update-task](file://./update-task/SKILL.md)**: Record progress inside a task spec during implementation.
*   **[commit](file://./commit/SKILL.md)**: Stage and commit code/docs with a clean conventional commit message.

### Phase 3 — Test
*   **[test](file://./test/SKILL.md)**: Run the validation suite and generate a test report. *(Stack-specific gates — adapt to your project.)*

### Phase 4 — Review
*   **[review-task](file://./review-task/SKILL.md)**: Authoritative review of completed code/tests against spec criteria and rules.

### Phase 5 — Document
*   **[document](file://./document/SKILL.md)**: Surgically update `docs/` Markdown files based on the implement report.

### Phase 6 — Wrap-up
*   **[log-work](file://./log-work/SKILL.md)**: Mark specs done in `STATUS.md`, append `DEVLOG.md` entry, sync the company brain.

### Phase 7 — Verify Run
*   **[review-workflow](file://./review-workflow/SKILL.md)**: Audit pipeline execution and verify correct stages/rules were followed.

### Orchestration Engines
*   **[sdlc-task](file://./sdlc-task/SKILL.md)**: Run the full pipeline for a single task in an isolated worktree (parallel-safe).
*   **[sdlc-block](file://./sdlc-block/SKILL.md)**: Drive a whole spec as dependency-ordered waves of parallel `sdlc-task` runs, merging each wave.

### Worktree Management
*   **[init-worktree](file://./init-worktree/SKILL.md)**: Initialize an isolated Git worktree for spec/task isolation.
*   **[clean-worktree](file://./clean-worktree/SKILL.md)**: Merge completed worktree branches back into `main` and clean them up.

### Standalone Utilities
*   **[update-docs](file://./update-docs/SKILL.md)**: Ad-hoc utility to synchronize `docs/` with recent code changes based on a git diff.

---

## Company Brain Integration

`log-work` automatically mirrors status updates to the parent `agentic-portfolio/` company
brain: `docs/projects/<slug>.md` and `README.md` (status synchronization).
