# CLAUDE.md — working on `base-template`

This repo is the **software-factory source**: the curated harness + tokenized document
scaffold that `/new-project` clones. You are not building a product here — you are curating the
thing every new project starts from. Read `README.md` first for the layout and the
generation flow.

## Before you change anything

- **Orientation + current state:** `planning/context.md` (why this repo exists + governing rules)
  → `planning/status.md` (current focus + progress). Or run `/prime`.
- **Symlink warning:** the `planning/` directory is actually a local symlink pointing to the company brain repo's `_planning/` vault (e.g. `_planning/base-template/`). The brain repo is responsible for tracking all planning files under Git. Do not track `planning/` in this project's public Git repository (it is gitignored).
- **What this is + layout:** `README.md`
- **How to use it:** `docs/using-the-template.md`
- **Why the harness looks the way it does:** `planning/decisions/` (keep/drop ADRs + the
  Phase-2 adoption record D5).
- **What changed and when:** `log.md`

## The two halves — don't mix them

| Half | Path | Purpose | Goes into new projects? |
|---|---|---|---|
| **Harness** | `.claude/` | The SDLC pipeline (commands + engines) — ships *mechanism* only | Yes — copied as-is |
| **Scaffold** | `scaffold/` | Tokenized project docs (CLAUDE, README, log, planning/ incl. `harness.json` stub) | Yes — copied + token-substituted |
| **Template meta** | `CLAUDE.md`, `README.md`, `log.md`, `planning/`, `docs/` | The template's *own* docs, change history, and pipeline config | **No** — never copied into a project |

A new project must start with a **clean** log and a `D1-initial-okf` decision — so the template's
own `log.md` / `planning/` (this repo's harness history, decisions, and `harness.json`) stay at
the root and out of `scaffold/`.

## The update loop (how to evolve the harness)

When a discovery in a downstream project improves the harness:

1. Make the change **here**, in `base-template` — not only in the project where you found it.
2. If it's a keep/drop or behavioral call, add an atomic ADR under `planning/decisions/`
   explaining *why*.
3. Append a dated `log.md` entry describing *what* changed.
4. Commit. The new commit hash becomes the provenance stamp for the next generated project.
5. **Run `/sync-downstream-harness`** (dry-run first, then `--apply`) to pull the change into every
   already-scaffolded repo — see `planning/decisions/D48-downstream-harness-sync-script.md`. This
   is not optional busywork: a fix that lives only here isn't fixed anywhere real work happens. If
   the change touched `sdlc-flow.js` or the `tasks.json` contract specifically, also check
   `core/orchestrator`'s `SDLC_FLOW` workflow (`app/schemas/sdlc_schema.py`) — it's a second,
   independently-implemented consumer of the same contract (see
   `core/orchestrator/docs/sdlc-flow-workflow.md`) that this script does not touch.

Downstream projects **do not auto-sync** — pulling is still a deliberate, reviewed step (the
script never commits for you) — but it is no longer a fully manual copy-paste; `/sync-downstream-
harness` does steps 5's mechanical part. Repos still diverge by design after the pull (their own
customizations are never touched) — keep changes here additive and well-documented.

## Standing rules

1. **Keep the harness project-agnostic — `.claude/` ships mechanism, never project facts.** No
   project-specific skills, paths, or stack assumptions in the engines. Stack *policy* (validation
   commands, ports/routes, whether a UI-test stage exists) lives in each project's
   `planning/harness.json`; the engines read it and ship **no stack defaults** (config absent →
   fall back to the spec's `## Validation Commands` + disable the UI-test stage). See
   [D5](planning/decisions/D5-okf-phase-2-adopted.md). Universal rules (e.g. no emoji in docs,
   parallel port = `port + taskNumber`) stay hardcoded — they are mechanism, not facts.
2. **Tokenize, don't hardcode** in `scaffold/`. Use the tokens in `README.md`; never bake a
   real project name/slug/date into a scaffold file.
3. **Preserve the load-bearing names** the SDLC engines depend on — the settled OKF conventions:
   lowercase docs (`status.md`, `master-plan.md`, `context.md`, scaffold `log.md`), the
   concept-folder `planning/<concept>/` model with pipeline state under a reserved
   `planning/<concept>/sdlc/`, and `index.md` for directory listings. Renames are a
   lockstep-with-the-workflows change, not piecemeal. (The template's *own* root `README.md`
   keeps its name by design.)
4. **Never edit a settled decision** — supersede it with a new atomic ADR and link back.
5. **Every new `.md` under `docs/` or `planning/` must open with OKF YAML frontmatter.**
   Required fields: `type` (e.g. Decision, Index, Reference, Plan, Log, ProjectStatus, LocalContext,
   Guide, Handoff); `title` (human-readable); `description` (one-line summary for embedding).
   Optional but strongly encouraged: `doc_id` (kebab-case stable id, defaults to filename stem);
   `layer` (list from closed vocab: `factory` · `brain` · `engine` · `console` · `surface` ·
   `infra` · `business` · `content` · `meta`); `project` (`base-template` for this repo's own
   docs; omit for scaffold/ files); `status` (`active` · `draft` · `deprecated` · `superseded` ·
   `archived`); `keywords` (3–7 topic terms); `related` (list of doc_ids). Canonical guide:
   `agentic-portfolio/docs/okf-frontmatter.md` (governed by brain decision D27).
   Adding a file to a directory requires updating that directory's `index.md` — propagate up
   the chain as needed (e.g. a new `docs/workflows/` file → update `docs/workflows/index.md`
   and `docs/index.md` if the scope changes).
