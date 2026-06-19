---
type: Reference
title: harness.json — copy-paste profiles
description: Ready-made planning/harness.json profiles (Rust, Python/FastAPI, Next.js) for adapting the SDLC pipeline to this project's stack.
---

# `harness.json` profiles

`planning/harness.json` is the **policy** the SDLC engines read: the validation commands and
whether a UI-test stage exists. The engine code (`.claude/workflows/*.js`) carries the
**mechanism** and ships no stack defaults — so this file is where a project names its real
commands.

Pick the profile that matches this project's stack, paste it into `planning/harness.json`, and
edit the commands to match. Validation `checks[]` run **top-to-bottom**; a check with
`gates: true` blocks the review verdict on failure. Set `uiTest.enabled: true` only for web
projects that have a dev server to smoke-test.

> If `planning/harness.json` is absent, the engines fall back to the spec's
> `## Validation Commands` section and skip the UI-test stage entirely. The file is the
> recommended path, not a hard requirement.

---

## Rust (CLI / TUI / library) — no web server

```json
{
  "$schema": "../.claude/workflows/harness.schema.json",
  "stack": "rust",
  "validation": {
    "checks": [
      { "name": "fmt",    "command": "cargo fmt --check",            "purpose": "Format gate", "gates": true },
      { "name": "clippy", "command": "cargo clippy -- -D warnings",  "purpose": "Lint gate",   "gates": true },
      { "name": "test",   "command": "cargo test",                   "purpose": "Test suite — AUTHORITATIVE for verdict", "gates": true },
      { "name": "build",  "command": "cargo build --release",        "purpose": "Build gate",  "gates": true }
    ]
  },
  "uiTest": { "enabled": false }
}
```

## Python / FastAPI + pydantic — no web UI to smoke-test

```json
{
  "$schema": "../.claude/workflows/harness.schema.json",
  "stack": "python-fastapi",
  "validation": {
    "checks": [
      { "name": "ruff",  "command": "ruff check .",  "purpose": "Lint gate",   "gates": true },
      { "name": "mypy",  "command": "mypy .",        "purpose": "Type gate",   "gates": true },
      { "name": "test",  "command": "pytest",        "purpose": "Test suite — AUTHORITATIVE for verdict", "gates": true }
    ]
  },
  "uiTest": { "enabled": false }
}
```

## Python — rich checks (baseline-diff lint, test-count delta, import warnings, standing-rule scan)

The profile above treats every check as a plain command. A maturing project often wants more: gate
on **net-new** lint only (not pre-existing debt), fail when the **test count regresses**, surface
import-time **warnings** without failing, and scan source for **standing-rule violations**. Those are
the four richer `kind`s. Each still keeps all stack-specific commands and patterns here — the engine
only carries the interpretation. `kind` defaults to `"command"`, so mix plain and rich checks freely.

```json
{
  "$schema": "../.claude/workflows/harness.schema.json",
  "stack": "python-fastapi",
  "validation": {
    "checks": [
      {
        "kind": "forbidden-pattern-scan",
        "name": "standing-rules",
        "purpose": "CLAUDE.md standing-rule scan (non-waivable) — these are rules, not pre-existing debt",
        "gates": true,
        "rules": [
          { "id": "f-string-in-logging", "pattern": "logging\\.[a-z]+\\(.*f[\"']", "paths": "--include=*.py app/" },
          { "id": "open-without-encoding", "pattern": "open\\(", "paths": "--include=*.py app/", "allowlistPattern": "encoding=|#" },
          { "id": "param-named-id", "pattern": "def [a-zA-Z_]+\\([^)]*\\bid\\b", "paths": "--include=*.py app/", "allowlistPattern": "obj_id|record_id|node_id|workflow_id|task_id|invalid" }
        ]
      },
      {
        "name": "no-raise-without-from",
        "purpose": "In except blocks, raise ... from e (context-sensitive — runs as a plain inverted grep)",
        "gates": true,
        "command": "m=$(grep -rnE --include=*.py -A1 'except .* as e:' app/ | grep -E 'raise ' | grep -v 'from e' || true); if [ -n \"$m\" ]; then echo \"VIOLATION raise-without-from-e:\"; echo \"$m\"; exit 1; fi; echo clean"
      },
      {
        "kind": "warning-scan",
        "name": "app-import",
        "purpose": "App imports cleanly; surface Pydantic field-shadow warnings (advisory)",
        "gates": false,
        "command": "cd app && uv run python -c 'import main'",
        "warningPatterns": ["UserWarning", "shadows an attribute", "field.*shadow"]
      },
      {
        "kind": "warning-scan",
        "name": "worker-import",
        "purpose": "Worker config imports cleanly; surface Pydantic field-shadow warnings (advisory)",
        "gates": false,
        "command": "cd app && uv run python -c 'import worker.config'",
        "warningPatterns": ["UserWarning", "shadows an attribute", "field.*shadow"]
      },
      { "name": "db-session-import",    "command": "cd app && uv run python -c 'import database.session'",    "purpose": "Database session imports", "gates": true },
      { "name": "db-repository-import", "command": "cd app && uv run python -c 'import database.repository'", "purpose": "Repository imports",        "gates": true },
      {
        "kind": "baseline-diff",
        "name": "net-new-lint",
        "purpose": "Ruff — fail only on violations this task introduced (diff vs worktree-creation baseline)",
        "gates": true,
        "baselineCommand": "uv run ruff check app/ --output-format=json",
        "command": "uv run ruff check app/ --output-format=json",
        "compareKeys": ["filename", "code", "message"]
      },
      { "name": "pylint", "command": "uv run pylint app/", "purpose": "Pylint", "gates": true },
      {
        "kind": "count-delta",
        "name": "pytest-count",
        "purpose": "Pytest collection count must not drop vs the previous task (catches silently-removed tests)",
        "gates": true,
        "command": "uv run pytest --collect-only -q",
        "countPattern": "[0-9]+ tests? collected",
        "failOn": "decrease"
      },
      { "name": "pytest", "command": "uv run pytest", "purpose": "Full test suite — AUTHORITATIVE for verdict", "gates": true }
    ]
  },
  "uiTest": { "enabled": false }
}
```

**How each rich kind runs:**

- **`forbidden-pattern-scan`** — each `rule.pattern` is a `grep -rnE` over `rule.paths` (defaults to the
  whole tree), minus `rule.allowlistPattern`. Any match is a violation; the check fails if any rule matches.
- **`baseline-diff`** — `baselineCommand` runs once at **worktree creation** and is stored as an
  artifact; at test time `command` runs again and the engine fails only on result items whose
  `compareKeys` tuple is absent from the baseline. Pre-existing violations never gate. (Both commands
  must emit the same JSON-array format.)
- **`count-delta`** — `command` runs, the first integer on the line matching `countPattern` is the
  count, and it is compared against the previous task's recorded count. `failOn: "decrease"` fails on a
  drop; `"zero-or-decrease"` also fails when it does not grow. Task 1 (no prior count) is SKIPPED.
- **`warning-scan`** — `command` runs and its **exit code gates as usual**; additionally every
  `warningPatterns` match is recorded. With `gates: false` matches are advisory WARNs; with
  `gates: true` a match also fails the check.

---

## Next.js (web) — UI-test stage enabled

The only profile that exercises the `uiTest` fields. `port` is the base port; in parallel task
runs the engine uses `port + taskNumber` automatically. `routes[]` are smoke-checked once
`readySignal` appears in the dev-server output.

```json
{
  "$schema": "../.claude/workflows/harness.schema.json",
  "stack": "nextjs",
  "validation": {
    "checks": [
      { "name": "lint",   "command": "npm run lint",        "purpose": "Lint gate",  "gates": true },
      { "name": "types",  "command": "npx tsc --noEmit",    "purpose": "Type gate",  "gates": true },
      { "name": "test",   "command": "npm test",            "purpose": "Test suite — AUTHORITATIVE for verdict", "gates": true },
      { "name": "build",  "command": "npm run build",       "purpose": "Build gate", "gates": true }
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

---

*The harness carries the mechanism; this file carries the policy. Keep stack facts here, never
in `.claude/workflows/*.js`.*
