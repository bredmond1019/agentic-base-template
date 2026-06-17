# base-template — the software-factory source

This repo is the **single curated source** that `/new-project` clones to scaffold a new
project. It is not a product and not application code — it is the harness and document
skeleton every new project in the practice starts from. It has its own git history so every
change to the factory records *what* changed and *why*.

> **Tracked by path only.** This repo lives at `agentic-portfolio/base-template/` and is
> gitignored from the company brain (it has its own git). The brain references it by path.

---

## Canonical document names (Phase-2 rename surface)

The scaffold deliberately keeps the **load-bearing names the SDLC workflows depend on**, so a
freshly generated project runs the pipeline on day one:

- `planning/STATUS.md`
- `planning/MASTER_PLAN.md`
- root `DEVLOG.md`
- `planning/tasks/<stem>/`

> ⚠️ These names are the **OKF Phase-2 rename surface**. If/when the practice settles canonical
> names (e.g. UPPERCASE vs the brain's lowercase `status.md`/`log.md`, `README.md` → `index.md`),
> the renames must move in lockstep with the SDLC workflow JS that reads them. Do **not** rename
> them piecemeal here. See the brain's `planning/okf-phase-2/plan.md`.

---

## Layout

```
base-template/
├── .claude/              ← curated, project-agnostic Claude Code harness
│   ├── commands/         ← 22 SDLC + general commands (project-specific ones stripped)
│   └── workflows/        ← sdlc-run / sdlc-task / sdlc-block engines
├── .agents/              ← Gemini/Antigravity skill twins (same pipeline, skill form)
│   ├── skills/
│   └── scripts/          ← compute-waves.ts (backs sdlc-block)
├── scaffold/             ← TOKENIZED project templates — copied into each new project
│   ├── CLAUDE.md  README.md  DEVLOG.md
│   └── planning/         ← CONTEXT, STATUS, MASTER_PLAN, README, decisions/, tasks/
├── planning/
│   └── decisions/        ← THIS template's own harness ADRs (why a skill was kept/dropped)
├── CLAUDE.md             ← agent guide for working *on the template* + the update loop
├── DEVLOG.md             ← the template's own change history
└── README.md            ← this file
```

**Why `scaffold/` is separate from the template's own meta:** the template repo keeps its own
`DEVLOG.md` and `planning/decisions/` (the harness change history). Those must **not** become a
new project's starting DEVLOG/decisions — a fresh project starts with a clean DEVLOG and a
`D1-initial-okf` decision. So the tokenized project docs live under `scaffold/`, and
`/new-project` copies `.claude/`, `.agents/`, and the **contents** of `scaffold/` into the new
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

---

## How a new project is generated

`/new-project` (run from the `agentic-portfolio/` brain root) does the following:

1. Copies `base-template/.claude/` and `base-template/.agents/` into `<slug>/`.
2. Copies the **contents** of `base-template/scaffold/` into `<slug>/` (so `scaffold/planning/`
   becomes `<slug>/planning/`, etc.).
3. Substitutes the tokens above across the copied files.
4. Stamps the `base-template` commit hash as provenance (`planning/.template-version` and the
   first `DEVLOG.md` entry).
5. Onboards the project to the brain (`docs/projects/<slug>.md`, `.gitignore`, `README.md`,
   `docs/index.md`, `docs/projects/index.md`).
6. Optionally `git init`s the new project (its history is independent of this template's).

Downstream projects **do not auto-sync** with this template. Improvements are pulled manually;
projects diverge after generation by design.

---

## The update loop

See `CLAUDE.md` for the discipline. In short: when a discovery improves the harness, change it
**here**, log *why* in `DEVLOG.md` (and add a `planning/decisions/` ADR for keep/drop/behavioral
calls), then commit. The new commit hash becomes the provenance stamp for the next generated
project.
