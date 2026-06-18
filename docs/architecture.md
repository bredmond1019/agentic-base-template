---
type: Reference
title: base-template architecture
description: How the two halves work, OKF naming conventions, and the mechanism/policy split.
---

# base-template architecture

## The two halves

Every new project gets exactly two things from this template, copied verbatim:

| Half | Source path | Destination in new project | What it is |
|---|---|---|---|
| **Harness** | `.claude/` | `.claude/` | The SDLC pipeline — commands + workflow engines. Ships *mechanism only*, never project facts. |
| **Scaffold** | `scaffold/` (contents) | project root | Tokenized project docs: `CLAUDE.md`, `README.md`, `log.md`, and a full `planning/` skeleton. |

The template's own `log.md`, `planning/`, `docs/`, `CLAUDE.md`, and `README.md` are **never
copied**. They are the factory's own records and must not pollute a new project's clean start.

## Harness: mechanism only

The `.claude/` tree ships mechanism — the *how* of running a pipeline — and reads all
project-specific *policy* from `planning/harness.json`. This means:

- The engines (`workflows/*.js`) carry zero stack defaults. No npm scripts, no port numbers,
  no framework assumptions.
- Every validation command, route, and UI-test config lives in the project's
  `planning/harness.json`, not in the engine code.
- Universal rules (no emoji in docs, parallel port = `port + taskNumber`) stay hardcoded in
  the engine because they apply to every project, making them mechanism, not policy.

See [harness-json.md](harness-json.md) for the config format and all three stack profiles.

## Scaffold: tokenized project docs

The `scaffold/` directory is a complete starting-state for a new project's documentation:

```
scaffold/
  CLAUDE.md                   ← project-specific agent guide (tokenized)
  README.md                   ← project README (tokenized)
  log.md                      ← project change history (clean start)
  planning/
    context.md                ← orientation doc
    status.md                 ← current focus tracker
    master-plan.md            ← phase/block tracker
    index.md                  ← planning/ navigation
    harness.json              ← neutral stub — fill in for your stack
    harness.examples.md       ← Rust / Python / Next.js profiles to copy from
    decisions/
      D1-initial-okf.md       ← the project's first ADR (bootstrap)
      index.md                ← decisions navigation
```

`/new-project` substitutes tokens (`{{PROJECT_NAME}}`, `{{SLUG}}`, etc.) across all scaffold
files at generation time. See `README.md` for the full token table.

## OKF naming conventions

These names are **load-bearing** — the SDLC engines read them directly. Any rename must move
in lockstep with the workflow code in `.claude/workflows/`.

| Convention | Rule |
|---|---|
| **Lowercase docs** | `status.md`, `master-plan.md`, `context.md`, `log.md`, `index.md` — no uppercase names |
| **Concept-folder model** | Spec work lives at `planning/<concept>/tasks.md`; pipeline machine-state at `planning/<concept>/sdlc/` (`execution-plan.json`, `reports/`) |
| **`index.md` for directories** | Every directory that needs a listing file uses `index.md`, not `README.md` |
| **`sdlc/` reserved** | `planning/<concept>/sdlc/` is exclusively for pipeline-generated state — never author files there manually |

## The mechanism/policy split (harness.json)

Before OKF Phase 2, the engines hardcoded the learn-ai stack (npm scripts, port 3003, pt-BR
parity, etc.). The split introduced `planning/harness.json` as the clean seam:

```
MECHANISM (harness, copied as-is)         POLICY (project, via harness.json)
─────────────────────────────────         ──────────────────────────────────
pipeline ordering                         validation command list
retry loops                               whether a UI-test stage exists
report formats                            dev server command + ready signal
"run the validation suite"                port number and smoke routes
"run the UI smoke check"                  stack label (informational)
emoji gate (universal)
port = port + taskNumber (universal)
```

Config absent → validation falls back to the spec's `## Validation Commands` section;
UI-test stage is disabled. See [harness-json.md](harness-json.md) for the full schema.

## The update loop

When a downstream project reveals something that improves the factory:

1. Make the change **here**, in `base-template`.
2. If it is a keep/drop or behavioral call, add an atomic ADR under `planning/decisions/`.
3. Append a dated entry to `log.md`.
4. Commit. The new commit hash becomes the provenance stamp for the next generated project.

Downstream projects do **not** auto-sync. They pull improvements manually and diverge by
design — this is intentional. Track the propagation effort in the company brain.
