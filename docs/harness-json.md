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
