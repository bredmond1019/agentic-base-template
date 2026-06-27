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

## SDLC pipeline

This project carries the curated SDLC harness. Run `/prime` to orient, then drive structured
work through `/generate-tasks → /implement → /test → /review-task → /document → /log-work`.
See `.claude/commands/README.md` for the full pipeline reference.

> **Stack note:** the SDLC engines carry no stack defaults. Point them at this project's stack
> by filling `planning/harness.json` (validation commands + optional UI-test config). Copy a
> ready-made profile from `planning/harness.examples.md` (Rust / Python / Next.js). Do **not**
> edit the `workflows/*.js` engines for stack reasons — that's what `harness.json` is for.
