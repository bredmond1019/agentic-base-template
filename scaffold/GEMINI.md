# GEMINI.md — {{PROJECT_NAME}}

{{DESCRIPTION}}

## Before you start

- **Strategic context:** `planning/context.md` (read first) → `planning/status.md` (current state)
- **Symlink warning:** the `planning/` directory is actually a local symlink pointing to the company brain repo's `_planning/` vault (e.g. `<tier>/_planning/<slug>/`). The brain repo is responsible for tracking all planning files under Git. Do not track `planning/` in this project's public Git repository (it is gitignored).
- **Plan:** `planning/master-plan.md` — the phase/block sequence
- **Pipeline config:** `planning/harness.json` — the validation skills + UI-test config the
  SDLC engines run (see `planning/harness.examples.md` for ready-made stack profiles)
- **Decisions log:** `planning/decisions/` (start at `planning/decisions/index.md`) — check
  before relitigating any settled choice

## Standing rules

1. **Every new function, module, or behaviour change ships with tests.** No exceptions — this applies to ad-hoc fixes and one-off changes just as much as formal blocks/tasks. If you add or change code, add or update the tests that cover it.
2. **OKF frontmatter is required on every new `.md` file** under `docs/` and `planning/`.
   Every new file must open with a YAML frontmatter block. Three fields are **required**:
   `type`, `title`, `description`. Six fields are **optional but strongly encouraged**:
   - `doc_id` — kebab-case stable id (defaults to filename stem if omitted)
   - `layer` — list from closed vocab: `brain` · `engine` · `factory` · `console` · `surface` · `infra` · `business` · `content` · `meta`
   - `project` — controlled slug (this repo: `{{SLUG}}`; omit for genuinely cross-cutting docs)
   - `status` — one of: `active` · `draft` · `deprecated` · `superseded` · `archived`
   - `keywords` — 3–7 free-form topic terms; never exceed 7
   - `related` — list of `doc_id` values from other real docs in the repo
   Canonical guide: `docs/okf-frontmatter.md` in the company-brain repo; governing decision: D27.
   **Adding a file to a directory also requires updating that directory's `index.md`** — propagate
   up the chain if the parent directory's scope changes.
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
> block). Keep the `<test>`/`<build>` skills here in sync with that file's
> `validation.checks[]` so humans and the pipeline run the same thing.

## Directory map

```
{{SLUG}}/
├── .claude/        ← Gemini skills + SDLC workflow engines
├── planning/       ← context, status (+Momentum/Metrics), master-plan, knowledge, memory,
│                     artifacts/, harness.json, decisions/, <concept>/
└── <source dirs>   ← add as the project grows
```

## What NOT to touch

<!-- Reference-only code, generated files, migration history, etc. List them as they appear. -->

---

## Available Skills

All harness skills are installed globally in `~/.agents/skills/` via `/sync-global-commands`
(run from base-template). Invoke them with `/<name>` directly. Project-specific skills (if any)
live in `.agents/skills/` and take precedence over global skills on name conflict.

### Session

| Skill/Command | What it does |
|---|---|
| `/prime` (global) | Deep session start — reads key docs and summarizes state |
| `/session-recap` (global) | Start-of-session briefing: recent log, current focus, next action |
| `/next` (global) | Briefing on what's next, what's blocked, and recommend next action |
| `/handoff` (global) | Write handoff.md + log work + commit; hands off to a fresh agent |
| `/wrap-up` (global) | Log work + commit; clean session close without a handoff file |
| `/status` (global) | Quick status snapshot of current focus and momentum |
| `/log-work` (global) | Log a completed work session and update status.md |
| `/archive` (global) | Retire a folder/file — distill durable residue first (D35 gate) |
| `/capture` (global) | Scaffold planning/<slug>/notes.md for pre-plan ideas; adds backlog ticket to brain |

### Planning

| Skill/Command | What it does |
|---|---|
| `/plan` (global) | Author a mini-roadmap (phases/blocks) into planning/plan-<slug>/plan.md |
| `/ticket` (global) | Single-block behavior-change spec with observable AC + testing strategy |
| `/chore` (global) | Plan a maintenance or housekeeping task |
| `/breakdown` (global) | Decompose a task spec into agent-executable sub-steps |
| `/generate-tasks` (global) | Generate a task spec for a specified phase and block |
| `/generate-master-plan` (global) | Author the project roadmap as canonical block definitions |

### SDLC

| Skill/Command | What it does |
|---|---|
| `/implement` (global) | Execute a plan file against the codebase |
| `/test` (global) | Application validation test suite |
| `/fix` (global) | Make targeted fixes for a FAIL or PARTIAL review verdict |
| `/patch` (global) | Hotfix ladder: small targeted fix routed to lean /sdlc-task |
| `/document` (global) | Update docs to reflect a completed, reviewed implementation |
| `/update-docs` (global) | Documentation health sweep: find stale sections and create missing coverage |
| `/conditional_docs` (global) | Task-type documentation router |
| `/process-tasks` (global) | Process a task list sequentially |
| `/update-task` (global) | Update a task spec after a deviation or completion |
| `/review-task` (global) | Verify a completed task against its spec and acceptance criteria |
| `/review-workflow` (global) | Verify that a completed pipeline executed correctly |
| `/review-PR` (global) | Review a PR against its block spec; post structured verdict |
| `/close-out` (global) | Verify test coverage, patch docs, and hand off cleanly |

### Git

| Skill/Command | What it does |
|---|---|
| `/commit` (global) | Stage and commit changes with a conventional message |
| `/init-worktree` (global) | Initialize a new git worktree for isolated work |
| `/clean-worktree` (global) | Merge a completed worktree branch into main and remove it |
| `/start-block` (global) | Start a new spec block: branch, initial commit, worktree setup |
| `/merge-train` (global) | Merge all approved block PRs in dependency order |

### E2E

| Skill/Command | What it does |
|---|---|
| `/test_auth_gate` (global) | E2E test template: authentication gate |
| `/test_crud_api` (global) | E2E test template: CRUD API |
| `/test_error_handling` (global) | E2E test template: error handling |
| `/test_ui_form` (global) | E2E test template: UI form |

> `/sync-global-commands` (global) is available in base-template only — it syncs
> these commands to `~/.agents/skills/` and aborts if run outside the base-template root.

## SDLC pipeline

This project carries the curated SDLC harness. Run `/prime` to orient, then drive
structured work through:
`/generate-tasks → /implement → /test → /review-task → /document → /log-work`.

> **Stack note:** the SDLC engines carry no stack defaults. Point them at this project's stack
> by filling `planning/harness.json` (validation skills + optional UI-test config). Copy a
> ready-made profile from `planning/harness.examples.md` (Rust / Python / Next.js). Do **not**
> edit the `workflows/*.js` engines for stack reasons — that's what `harness.json` is for.

<!-- BEGIN:response-style -->
## Response Style

Optimize every reply for an operator scanning several concurrent agent sessions. Default to the
shortest response that fully answers. Long prose is the failure mode, not thoroughness.

**Shape**

1. **First line = the outcome.** What happened, and did it work. No preamble, no restating the ask.
2. **Then the specifics, if any** — bullets, one line each, max ~6. Facts, not narration.
3. **Last line = the ask, if any** — one question the user can answer in a word.

Ceiling for a normal turn: **~150 words / ~15 lines**. Only depth the user explicitly asked for
(a review, a design rationale, a plan document) may exceed it.

**Cut**

- Reasoning narration — how you got there, what you considered, what you almost did. Report
  conclusions; the transcript already holds the steps.
- Justifying decisions that worked out. Explain only what was non-obvious or that the user may
  want to reverse.
- Unasked-for "what's next", roadmaps, option menus, and status recaps.
- Tables or headings for fewer than ~4 rows/sections — a sentence or bullets is faster to read.
- Self-assessment and stage direction: "the finding that reframes everything", "worth your
  attention", "one thing I want to flag", praise, hedging, apology.
- Re-explaining anything already in a file you just wrote. Link the path instead.

**Keep — these earn their space**

- Failures, blocks, and anything not matching what was asked: say it first, plainly, with the
  real error text.
- Assumptions the user might reject, and decisions that need their call.
- Security, data-loss, or money implications.
- Exact identifiers where they *are* the content: `src/serve/handlers/attention.rs:101`, a
  version, an error code. Never a paragraph describing what a one-line reference would say.

**Register**

Plain English for status, decisions, and trade-offs. Technical depth only where it changes what
the user does next. One idea per sentence; no stacked em-dash asides.
<!-- END:response-style -->
