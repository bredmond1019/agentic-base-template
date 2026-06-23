---
type: Reference
title: harness.json — configuration reference
description: Complete reference for planning/harness.json — the policy file the SDLC engines read for validation commands and UI-test configuration.
---

# harness.json — configuration reference

`planning/harness.json` is the **policy** seam between a project and the SDLC harness. The
engine code (`.claude/workflows/*.js`) carries the *mechanism* (pipeline ordering, retry loops,
report formats) and ships **no stack defaults**. This file is where a project names its real
validation commands and decides whether a UI-test stage exists.

## Location and schema

```
planning/harness.json          ← in each generated project
.claude/workflows/harness.schema.json   ← the JSON Schema (editor validation + living docs)
```

Point your editor at the schema via the `$schema` field and it will validate inline:

```jsonc
{
  "$schema": "../.claude/workflows/harness.schema.json",
  ...
}
```

## Config-absent behavior

If `planning/harness.json` is **absent**:

- The `/test` and `/review-task` stages fall back to the spec's `## Validation Commands`
  section (a plain markdown list in the task spec).
- The UI-test stage is disabled — no dev server is started, verdict is SKIPPED.
- The breakdown assessment defaults to `recommend` (advisory; threshold 3) — coarse tasks are
  logged but nothing is auto-generated.
- The clarify-before-generate gate is off — the authoring commands write the spec immediately
  (unless the user passes `--clarify`).

This is acceptable for a quick start but is less reliable than a `harness.json`.

## Full schema

### Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `$schema` | string | No | Path to the schema for editor validation |
| `stack` | string | No | Informational label only (`rust`, `python-fastapi`, `nextjs`, etc.) — not consumed by engine logic |
| `_comment` | string | No | Free-form note for humans — ignored by engines |
| `validation` | object | **Yes** | The always-run validation suite |
| `uiTest` | object | **Yes** | UI smoke-test stage config |
| `breakdown` | object | No | Task-decomposition policy (absent → `mode: recommend`, `complexityThreshold: 3`) |
| `planning` | object | No | Planning-phase policy for the authoring commands (absent → `clarify: false`) |

### `validation.checks[]`

An ordered array of checks run top-to-bottom in the Test stage. Each check:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | **Yes** | Short identifier (`fmt`, `clippy`, `test`, `build`) |
| `command` | string | Yes¹ | Shell command to run (`cargo test`, `pytest`, etc.) |
| `purpose` | string | **Yes** | One-line description of what the check gates |
| `gates` | boolean | **Yes** | Whether failure blocks the review verdict |
| `kind` | string | No | `command` (default) or a richer kind — see below |

`gates: true` on your test command makes it authoritative — a failing test blocks a PASS
verdict. Use `gates: false` for advisory checks you want to run but not block on.

#### Check `kind`s

`kind` defaults to `"command"` (a plain exit-code gate — the table above). Four richer kinds let a
suite express more than "run a command" while keeping every stack-specific command/pattern in this
file (the engine only carries the interpretation). ¹`command` is required for every kind except
`forbidden-pattern-scan` (which uses `rules[]` instead).

| `kind` | Extra fields | What it does |
|---|---|---|
| `baseline-diff` | `baselineCommand`, `compareKeys[]` | Snapshots a baseline at worktree creation; at test time diffs current output and fails **only on net-new items** (pre-existing ones never gate). Both commands must emit the same JSON-array format. |
| `count-delta` | `countPattern`, `failOn` | Extracts an integer (first number on the line matching `countPattern`) and fails when it regresses vs the previous task. `failOn`: `decrease` or `zero-or-decrease`. Task 1 → SKIPPED. |
| `warning-scan` | `warningPatterns[]` | Runs `command` (its **exit code gates**), then records matches of the patterns in its output — advisory WARN when `gates:false`, also-failing when `gates:true`. |
| `forbidden-pattern-scan` | `rules[]` of `{id, pattern, paths?, allowlistPattern?}` | Source greps that must find nothing; any match is a violation. |

See `planning/harness.examples.md` (the Python "rich checks" profile) for a worked example of all
four, and [D6](../planning/decisions/D6-harness-richer-checks.md) for the rationale.

### `uiTest` object

| Field | Type | Required | Description |
|---|---|---|---|
| `enabled` | boolean | **Yes** | `false` = whole UI stage is a no-op (verdict SKIPPED) |
| `devServerCommand` | string | When enabled | Command that starts the dev server |
| `readySignal` | string | When enabled | Substring in dev-server output that signals readiness |
| `port` | integer | When enabled | Base port. In parallel task runs the engine uses `port + taskNumber` (hardcoded behavior) |
| `routes` | string[] | When enabled | Routes to smoke-check once the server is ready |

### `breakdown` object

Optional. Controls whether the engines assess each task for **decomposition** (a `/breakdown` into
atomic sub-steps) once the spec exists. The coarseness heuristic is universal **mechanism** in the
engines; this object only sets the **policy** of what to do with the result.

| Field | Type | Required | Description |
|---|---|---|---|
| `mode` | string | No | `recommend` (default) · `auto` · `off` |
| `complexityThreshold` | integer | No | File-count signal: a task touching more than this many distinct files is a candidate **only when those files are heterogeneous** (default `3`). Multi-concern / multi-layer tasks are flagged regardless of count |

A task is a **breakdown candidate** when ANY hold: it bundles multiple separable concerns; OR it spans
multiple layers (data model + API + UI); OR it carries a large acceptance-criteria set over several
independently-testable units; OR it touches more than `complexityThreshold` distinct files **and those
files are heterogeneous** (different shapes/roles or spanning more than one concern/layer). File count
is a contributing signal, not a trigger on its own — a homogeneous many-file task (e.g. a content
path's metadata + N near-identical lesson pairs) is **not** flagged on count alone, since
decomposition yields little there. Raise `complexityThreshold` if a project's tasks routinely run wide
but cohesive.

| `mode` | What happens when a task is flagged |
|---|---|
| `recommend` (default) | Log a recommendation and proceed — no file is written. `/sdlc-block` lists the coarse tasks before the waves; a standalone `/sdlc-task` logs it before implementing. |
| `auto` | Generate `breakdown.md` sub-steps for the flagged tasks first. `/sdlc-block` writes + commits them on **main before the waves** (so every parallel worktree inherits the same file — no merge conflict); a standalone `/sdlc-task` writes them in its own worktree. Implement then follows the sub-steps. |
| `off` | Skip the assessment entirely. |

`/sdlc-block` assesses **once** in its Analyze stage (folded into the existing dependency-graph pass,
near-zero added cost) and passes `--under-block` to each `/sdlc-task` so the per-task engine does not
re-assess. `/generate-tasks` previews the same recommendation at authoring time. See
[D10](../planning/decisions/D10-breakdown-assessment.md).

### `planning` object

Optional. Controls planning-phase behavior of the authoring commands (`/plan`, `/feature`,
`/generate-tasks`). Absent → all fields default to today's zero-touch behavior.

| Field | Type | Required | Description |
|---|---|---|---|
| `clarify` | boolean | No | `false` (default) · `true` |

When `clarify: true`, the authoring commands surface **2–4 targeted clarifying questions** for an
ambiguous prompt *before* writing the spec — the deliberate counter to the "model guesses intent →
median results" anti-pattern. Default `false` preserves the zero-touch flow (write immediately). A
user can always force the behavior for a single invocation by appending **`--clarify`**, regardless
of this setting. See [D20](../planning/decisions/D20-clarify-before-generate.md).

## Stack profiles

Copy the profile that matches your stack into `planning/harness.json`.

### Rust (CLI / TUI / library)

```json
{
  "$schema": "../.claude/workflows/harness.schema.json",
  "stack": "rust",
  "validation": {
    "checks": [
      { "name": "fmt",    "command": "cargo fmt --check",           "purpose": "Format gate", "gates": true },
      { "name": "clippy", "command": "cargo clippy -- -D warnings", "purpose": "Lint gate",   "gates": true },
      { "name": "test",   "command": "cargo test",                  "purpose": "Test suite — AUTHORITATIVE for verdict", "gates": true },
      { "name": "build",  "command": "cargo build --release",       "purpose": "Build gate",  "gates": true }
    ]
  },
  "uiTest": { "enabled": false }
}
```

### Python / FastAPI + pydantic

```json
{
  "$schema": "../.claude/workflows/harness.schema.json",
  "stack": "python-fastapi",
  "validation": {
    "checks": [
      { "name": "ruff",  "command": "ruff check .",  "purpose": "Lint gate",  "gates": true },
      { "name": "mypy",  "command": "mypy .",        "purpose": "Type gate",  "gates": true },
      { "name": "test",  "command": "pytest",        "purpose": "Test suite — AUTHORITATIVE for verdict", "gates": true }
    ]
  },
  "uiTest": { "enabled": false }
}
```

### Next.js (web) — with UI smoke tests

The only profile that exercises the `uiTest` fields. `port` is the base port; in parallel task
runs the engine uses `port + taskNumber` automatically.

```json
{
  "$schema": "../.claude/workflows/harness.schema.json",
  "stack": "nextjs",
  "validation": {
    "checks": [
      { "name": "lint",   "command": "npm run lint",      "purpose": "Lint gate",  "gates": true },
      { "name": "types",  "command": "npx tsc --noEmit",  "purpose": "Type gate",  "gates": true },
      { "name": "test",   "command": "npm test",          "purpose": "Test suite — AUTHORITATIVE for verdict", "gates": true },
      { "name": "build",  "command": "npm run build",     "purpose": "Build gate", "gates": true }
    ]
  },
  "uiTest": {
    "enabled": true,
    "devServerCommand": "npm run dev",
    "readySignal": "Ready in",
    "port": 3000,
    "routes": ["/", "/about"]
  }
}
```

### Optional stub / not-implemented scan

A gating companion to the implement/fix completeness self-check ([D8](../planning/decisions/D8-implement-completeness-self-check.md)):
a `forbidden-pattern-scan` check that hard-fails if unimplemented placeholders
(`todo!()`/`unimplemented!()`, `raise NotImplementedError`, `throw new Error('not implemented')`)
remain on shipped paths. Ready-to-paste Rust / Python / TypeScript blocks — with the false-positive
caveats (Rust `unreachable!()` excluded; Python ABCs allowlisted) — live in the scaffold's
`planning/harness.examples.md` so generated projects can opt in per stack. The self-check (engine,
agnostic) always runs; this scan (config, per-project) is the optional hard backstop.

## Extending the suite (what goes where)

Arriving in a project and wanting "more checks" or "more criteria"? First decide *which layer* you
mean — they are three different files with three different jobs:

| You want to add… | Lives in | Read by | Needs an engine change? |
|---|---|---|---|
| A **validation check** (a command/scan that gates the verdict) | `planning/harness.json` → `validation.checks[]` | Test + review stages | No — pure config |
| An **acceptance criterion** for one task | the spec, `planning/<concept>/tasks.md` → `## Acceptance Criteria` | Review stage (per task) | No — authored via `/generate-tasks` |
| A project-wide **standing rule** (always applies) | `CLAUDE.md` standing rules, optionally backed by a `forbidden-pattern-scan` check | Review stage + Test stage | No — config + prose |

`harness.json` holds **checks, not acceptance criteria.** Criteria are per-task and live in the spec;
checks are the always-run gate. Conflating them is the common first mistake.

**The extensibility boundary — config vs engine:**

- **More of an existing shape → `harness.json` (config, per-project, no ADR).** Append as many
  `checks[]` as you like; mix plain `command` checks with the four richer kinds freely (`kind` defaults
  to `command`). The engine runs whatever's there — no engine edit. This is the [D5](../planning/decisions/D5-okf-phase-2-adopted.md)
  mechanism/policy split working as intended.
- **A new *shape* of check → `base-template` engine + ADR (mechanism, propagates to all projects).**
  The schema is **strict** (`additionalProperties: false`, and `kind` is a fixed enum of the five
  values above) — you **cannot** invent new fields or a new `kind` in a project's `harness.json`; they
  would fail validation or be ignored. A genuinely new gating mechanism (e.g. "fail if coverage < 80%"
  as a first-class kind) is an engine change made *here*, with an ADR, that then flows to every project
  via the update loop. Until then, model it as a plain `command` check that exits non-zero.

> Rule of thumb: **more of an existing kind → config; a new kind of check → engine + ADR.** If a real
> project needs a check the five kinds can't express, that's the signal to bring it back to
> `base-template` as a mechanism change — not to fork the engine in the project.

## Hardcoded engine behaviors (not config fields)

These behaviors are intentionally hardcoded in the engine — they are universal mechanism, not
project policy, so they are not config fields in the current schema:

| Behavior | Why hardcoded |
|---|---|
| **No emoji in docs** | Universal harness rule — every project applies it |
| **Parallel port = `port + taskNumber`** | One valid behavior; a knob with one value is noise |

## Deferred fields (not yet built)

These fields are defined in `harness.schema.json` as intentional future slots but not yet wired
into the engine. Do not add them to your `harness.json` — they will be ignored. Add a field
only when a real project needs it and the corresponding engine logic is written:

- `validation.conditionalChecks[]` — glob-triggered checks (only run when specific paths change)
- `validation.globalGates.noEmoji.scopeGlobs` — configurable emoji-check scope
- `uiTest.parallelPortStrategy` — alternative port-assignment strategies
- `uiTest.framework` — explicit framework label (e.g. `playwright`)
- `uiTest.triggerPaths` — only run UI-test when these paths change
- `uiTest.smokeRoutes{}` — per-route smoke config (currently `routes[]` covers this)
- `exampleSpecPath` — path to an example spec (currently `.claude/workflows/templates/spec-template.md` covers this)
