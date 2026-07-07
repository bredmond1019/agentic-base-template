---
type: Index
title: base-template — software factory source
description: Entry point for the base-template factory repo — canonical document names, harness structure, scaffold layout, and how /new-project uses this template.
doc_id: base-template-readme
layer: [factory]
project: base-template
status: active
keywords: [software factory, new-project, scaffold, harness, OKF conventions, base-template]
related: [base-template-architecture, base-template-docs-index, base-template-planning-index]
---

# base-template — the software-factory source

This repo is the **single curated source** that `/new-project` clones to scaffold a new
project. It is not a product and not application code — it is the harness and document
skeleton every new project in the practice starts from. It has its own git history so every
change to the factory records *what* changed and *why*.

> **Tracked by path only.** This repo lives at `agentic-portfolio/base-template/` and is
> gitignored from the company brain (it has its own git). The brain references it by path.

---

## Canonical document names (OKF Phase-2 conventions — settled)

The scaffold ships the **load-bearing names the SDLC workflows depend on**, so a freshly generated
project runs the pipeline on day one. As of OKF Phase 2 ([D5](planning/decisions/D5-okf-phase-2-adopted.md))
these are the settled lowercase / concept-folder conventions:

- `planning/status.md`, `planning/master-plan.md`, `planning/context.md`
- scaffold `log.md` (the project's change history; the *template's own* root `log.md` keeps the same name)
- `planning/<concept>/` concept folders, with pipeline machine-state under a reserved
  `planning/<concept>/sdlc/` (`execution-plan.json`, `reports/`)
- `index.md` for directory-listing files; root `README.md` keeps its name
- `planning/harness.json` — the per-project pipeline config the engines read (validation commands +
  optional UI-test config). The scaffold ships a neutral stub + `planning/harness.examples.md`
  (Rust / Python / Next.js profiles); the engines carry no stack defaults of their own.

> These names are read by the SDLC engine JS. Any future rename must move in **lockstep** with the
> workflow code in `.claude/workflows/`, not piecemeal. See [D5](planning/decisions/D5-okf-phase-2-adopted.md).

---

## Layout

```
base-template/
├── .claude/              ← curated, project-agnostic Claude Code harness (mechanism only)
│   ├── commands/         ← global SDLC + general commands (installed to ~/.claude/commands/ via
│   │                       /session:sync-global-commands; see commands/README.md)
│   └── workflows/        ← sdlc-run / sdlc-task / sdlc-block engines + harness.schema.json
│                           + templates/spec-template.md
├── scaffold/             ← TOKENIZED project templates — copied into each new project
│   ├── CLAUDE.md  README.md  log.md
│   └── planning/         ← context, status, master-plan, index, decisions/,
│                           harness.json (neutral stub) + harness.examples.md
├── docs/                 ← documentation for using and maintaining the template
│   ├── index.md          ← navigation guide
│   ├── architecture.md   ← how the two halves work + OKF conventions
│   ├── using-the-template.md  ← step-by-step: generate → configure → run pipeline
│   └── harness-json.md   ← harness.json config reference + all stack profiles
├── planning/             ← THIS template's own meta (context, status, decisions/)
│   ├── decisions/        ← harness ADRs (D1–D5; D5 = Phase-2 adoption)
│   └── harness.json      ← the template's OWN pipeline config (non-web: node --check the engines)
├── CLAUDE.md             ← agent guide for working *on the template* + the update loop
├── log.md                ← the template's own change history
└── README.md             ← this file
```

**Why `scaffold/` is separate from the template's own meta:** the template repo keeps its own
`log.md` and `planning/decisions/` (the harness change history). Those must **not** become a
new project's starting log/decisions — a fresh project starts with a clean log and a
`D1-initial-okf` decision. So the tokenized project docs live under `scaffold/`, and
`/new-project` copies `.claude/` and the **contents** of `scaffold/` into the new
project (never the template's own root meta or `.git`). See `planning/decisions/D2-scaffold-split.md`.

---

## Tokens

The `scaffold/` files use placeholder tokens, substituted by `/new-project` at generation time:

| Token | Replaced with |
|---|---|
| `{{PROJECT_NAME}}` | Human-readable project name |
| `{{SLUG}}` | kebab-case directory/identifier slug |
| `{{DESCRIPTION}}` | One-sentence description |
| `{{PROJECT_TYPE}}` | `personal` · `client` · `infrastructure` |
| `{{DATE}}` | Generation date (YYYY-MM-DD) |
| `{{TEMPLATE_COMMIT}}` | The `base-template` commit hash the project was generated from (provenance) |
| `{{VERIFIED_HANDLES}}` | The project's authoritative identities/handles/URLs (or `none` if not applicable) |

---

## How a new project is generated

`/new-project` (run from the `agentic-portfolio/` brain root) does the following:

1. Copies `base-template/.claude/workflows/` into `<slug>/.claude/workflows/` — the SDLC
   engine JS files only. Commands are **not** copied by default; they come from
   `~/.claude/commands/` (global), which is installed from base-template via
   `/session:sync-global-commands`. Use `--include-commands` (Block C) to opt into a full local
   copy for portable/offline/shareable projects.
2. Copies the **contents** of `base-template/scaffold/` into `<slug>/` (so `scaffold/planning/`
   becomes `<slug>/planning/`, etc.).
3. Substitutes the tokens above across the copied files.
4. Stamps the `base-template` commit hash as provenance (`planning/.template-version` and the
   first `log.md` entry).
5. Onboards the project to the brain (`docs/projects/<slug>.md`, `.gitignore`, `README.md`,
   `docs/index.md`, `docs/projects/index.md`).
6. Optionally `git init`s the new project (its history is independent of this template's).

> See `docs/using-the-template.md` for the complete generation + configuration guide.

Downstream projects **do not auto-sync** with this template. Improvements are pulled manually;
projects diverge after generation by design.

---

## The update loop

See `CLAUDE.md` for the discipline. In short: when a discovery improves the harness, change it
**here**, log *why* in `log.md` (and add a `planning/decisions/` ADR for keep/drop/behavioral
calls), then commit. The new commit hash becomes the provenance stamp for the next generated
project.

## Roadmap / Known limitations

- **SDLC Task Wrap-up:** The lightweight `/sdlc-task` workflow engine does not automatically call `/log-work` at the end of a run, which can leave `state.json` open until manually closed.
- **Decision Propagation:** A formal strategy for propagating architectural decisions (ADRs) to downstream generated projects after generation is a planned enhancement.
