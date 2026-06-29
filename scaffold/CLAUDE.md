# CLAUDE.md — {{PROJECT_NAME}}

{{DESCRIPTION}}

## Before you start

- **Strategic context:** `planning/context.md` (read first) → `planning/status.md` (current state)
- **Plan:** `planning/master-plan.md` — the phase/block sequence
- **Pipeline config:** `planning/harness.json` — the validation commands + UI-test config the
  SDLC engines run (see `planning/harness.examples.md` for ready-made stack profiles)
- **Decisions log:** `planning/decisions/` (start at `planning/decisions/index.md`) — check
  before relitigating any settled choice

## Standing rules

1. **Every block/task ships with tests** covering its core functionality. No exceptions.
2. **Every new `.md` under `docs/` or `planning/` must open with OKF YAML frontmatter.**
   Required fields: `type` (e.g. Decision, Index, Reference, Plan, Log, ProjectStatus, LocalContext,
   Guide); `title` (human-readable); `description` (one-line summary for embedding).
   Optional but strongly encouraged: `doc_id` (kebab-case stable id, defaults to filename stem);
   `layer` (list from closed vocab: `factory` · `brain` · `engine` · `console` · `surface` ·
   `infra` · `business` · `content` · `meta`); `project` (the project's own slug — see
   `docs/okf-frontmatter.md` in the company brain for the controlled vocabulary); `status`
   (`active` · `draft` · `deprecated` · `superseded` · `archived`); `keywords` (3–7 topic
   terms); `related` (list of doc_ids). Canonical guide: `agentic-portfolio/docs/okf-frontmatter.md`
   (governed by brain decision D27).
   Adding a file to a directory requires updating that directory's `index.md` — propagate up
   the chain as needed.
3. **Sequence, not calendar** — work the order in `master-plan.md`; pick up where you left off.
4. **Decisions are append-only** — never edit a settled decision; supersede it with a new
   atomic file in `planning/decisions/` and link back.
5. **Verified identity / handles:** {{VERIFIED_HANDLES}} — treat these as the only authoritative
   identities/URLs; flag any other handle or profile link as unverified before publishing it.
6. <!-- Add project-specific standing rules here (prompt handling, registries, deployment
   boundaries, code style, etc.). -->

## Known bugs

None known at initialization.

## Build / test / run

```bash
# Replace with this project's actual commands.
# <install>
# <build>
# <test>
# <run>
```

> The SDLC pipeline reads its validation suite from `planning/harness.json` (not from this
> block). Keep the `<test>`/`<build>` commands here in sync with that file's
> `validation.checks[]` so humans and the pipeline run the same thing.

## Directory map

```
{{SLUG}}/
├── .claude/        ← Claude Code commands + SDLC workflow engines
├── planning/       ← context, status (+Momentum/Metrics), master-plan, knowledge, memory,
│                     artifacts/, harness.json, decisions/, <concept>/
└── <source dirs>   ← add as the project grows
```

## What NOT to touch

<!-- Reference-only code, generated files, migration history, etc. List them as they appear. -->

---

## Available Commands

All harness commands are installed globally in `~/.claude/commands/` via `/session:sync-global-commands`
(run from base-template). Invoke them with the `<dir>:<name>` format shown below. Project-specific
commands (if any) live in `.claude/commands/` and take precedence over global commands on name conflict.

### Session

| Command | What it does |
|---|---|
| `/session:prime` (global) | Deep session start — reads key docs and summarizes state |
| `/session:session-recap` (global) | Start-of-session briefing: recent log, current focus, next action |
| `/session:handoff` (global) | Write handoff.md + log work + commit; hands off to a fresh agent |
| `/session:wrap-up` (global) | Log work + commit; clean session close without a handoff file |
| `/session:status` (global) | Quick status snapshot of current focus and momentum |
| `/session:log-work` (global) | Log a completed work session and update status.md |
| `/session:archive` (global) | Retire a folder/file — distill durable residue first (D35 gate) |
| `/session:capture` (global) | Scaffold planning/<slug>/notes.md for pre-plan ideas; adds backlog ticket to brain |

### Planning

| Command | What it does |
|---|---|
| `/planning:plan` (global) | Author a mini-roadmap (phases/blocks) into planning/plan-<slug>/plan.md |
| `/planning:ticket` (global) | Single-block behavior-change spec with observable AC + testing strategy |
| `/planning:chore` (global) | Plan a maintenance or housekeeping task |
| `/planning:breakdown` (global) | Decompose a task spec into agent-executable sub-steps |
| `/planning:generate-tasks` (global) | Generate a task spec for a specified phase and block |
| `/planning:generate-master-plan` (global) | Author the project roadmap as canonical block definitions |

### SDLC

| Command | What it does |
|---|---|
| `/sdlc:implement` (global) | Execute a plan file against the codebase |
| `/sdlc:test` (global) | Application validation test suite |
| `/sdlc:fix` (global) | Make targeted fixes for a FAIL or PARTIAL review verdict |
| `/sdlc:patch` (global) | Hotfix ladder: small targeted fix routed to lean /sdlc-task |
| `/sdlc:document` (global) | Update docs to reflect a completed, reviewed implementation |
| `/sdlc:update-docs` (global) | Documentation health sweep: find stale sections and create missing coverage |
| `/sdlc:conditional_docs` (global) | Task-type documentation router |
| `/sdlc:process-tasks` (global) | Process a task list sequentially |
| `/sdlc:update-task` (global) | Update a task spec after a deviation or completion |
| `/sdlc:review-task` (global) | Verify a completed task against its spec and acceptance criteria |
| `/sdlc:review-workflow` (global) | Verify that a completed pipeline executed correctly |
| `/sdlc:review-PR` (global) | Review a PR against its block spec; post structured verdict |
| `/sdlc:close-out` (global) | Verify test coverage, patch docs, and hand off cleanly |

### Git

| Command | What it does |
|---|---|
| `/git:commit` (global) | Stage and commit changes with a conventional message |
| `/git:init-worktree` (global) | Initialize a new git worktree for isolated work |
| `/git:clean-worktree` (global) | Merge a completed worktree branch into main and remove it |
| `/git:start-block` (global) | Start a new spec block: branch, initial commit, worktree setup |
| `/git:merge-train` (global) | Merge all approved block PRs in dependency order |

### E2E

| Command | What it does |
|---|---|
| `/e2e:test_auth_gate` (global) | E2E test template: authentication gate |
| `/e2e:test_crud_api` (global) | E2E test template: CRUD API |
| `/e2e:test_error_handling` (global) | E2E test template: error handling |
| `/e2e:test_ui_form` (global) | E2E test template: UI form |

> `/session:sync-global-commands` (global) is available in base-template only — it syncs
> these commands to `~/.claude/commands/` and aborts if run outside the base-template root.

## SDLC pipeline

This project carries the curated SDLC harness. Run `/session:prime` to orient, then drive
structured work through:
`/planning:generate-tasks → /sdlc:implement → /sdlc:test → /sdlc:review-task → /sdlc:document → /session:log-work`.

> **Stack note:** the SDLC engines carry no stack defaults. Point them at this project's stack
> by filling `planning/harness.json` (validation commands + optional UI-test config). Copy a
> ready-made profile from `planning/harness.examples.md` (Rust / Python / Next.js). Do **not**
> edit the `workflows/*.js` engines for stack reasons — that's what `harness.json` is for.
