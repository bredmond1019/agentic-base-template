# CLAUDE.md — working on `base-template`

This repo is the **software-factory source**: the curated harness + tokenized document
scaffold that `/new-project` clones. You are not building a product here — you are curating the
thing every new project starts from. Read `README.md` first for the layout and the
generation flow.

## Before you change anything

- **Active work:** `planning/index.md` → currently **OKF Phase 2** (`planning/okf-phase-2/plan.md`),
  a self-contained plan to converge the harness/scaffold to lowercase names, the concept-folder
  `planning/` model, and the `sdlc/` pipeline-state convention. If you're here to do that work,
  read the plan first — it supersedes standing rule #3 below (which still describes the pre-Phase-2
  names) and closes the D3 engine-generalization deferral.
- **What this is + layout:** `README.md`
- **Why the harness looks the way it does:** `planning/decisions/` (keep/drop ADRs, the
  scaffold-split decision)
- **What changed and when:** `DEVLOG.md`

## The two halves — don't mix them

| Half | Path | Purpose | Goes into new projects? |
|---|---|---|---|
| **Harness** | `.claude/`, `.agents/` | The SDLC pipeline (commands/skills + engines) | Yes — copied as-is |
| **Scaffold** | `scaffold/` | Tokenized project docs (CLAUDE, README, DEVLOG, planning/) | Yes — copied + token-substituted |
| **Template meta** | `CLAUDE.md`, `README.md`, `DEVLOG.md`, `planning/decisions/` | The template's *own* docs and change history | **No** — never copied into a project |

A new project must start with a **clean** DEVLOG and a `D1-initial-okf` decision — so the
template's own `DEVLOG.md` / `planning/decisions/` (this repo's harness history) stay at the
root and out of `scaffold/`.

## The update loop (how to evolve the harness)

When a discovery in a downstream project improves the harness:

1. Make the change **here**, in `base-template` — not only in the project where you found it.
2. If it's a keep/drop or behavioral call, add an atomic ADR under `planning/decisions/`
   explaining *why*.
3. Append a dated `DEVLOG.md` entry describing *what* changed.
4. Commit. The new commit hash becomes the provenance stamp for the next generated project.

Downstream projects **do not auto-sync**. They pull improvements manually and diverge by
design — so keep changes here additive and well-documented.

## Standing rules

1. **Keep the harness project-agnostic.** No project-specific skills, paths, or stack
   assumptions in `.claude/` / `.agents/`. (Residual stack assumptions in the SDLC engines are
   tracked as Phase-2 work — see `DEVLOG.md` and `planning/decisions/`.)
2. **Tokenize, don't hardcode** in `scaffold/`. Use the tokens in `README.md`; never bake a
   real project name/slug/date into a scaffold file.
3. **Preserve the load-bearing names** (`STATUS.md`, `MASTER_PLAN.md`, root `DEVLOG.md`,
   `planning/tasks/<stem>/`). Renames are an OKF Phase-2, lockstep-with-the-workflows change.
4. **Never edit a settled decision** — supersede it with a new atomic ADR and link back.
