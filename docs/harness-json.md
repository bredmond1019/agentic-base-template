---
type: Reference
title: harness.json — configuration reference
description: Complete reference for planning/harness.json — the policy file the SDLC engines read for validation commands and UI-test configuration.
doc_id: harness-json
layer: [factory]
project: base-template
status: active
keywords: [harness.json, validation, pipeline config, checks, UI-test, stack profiles]
related: [base-template-architecture, D5-okf-phase-2-adopted, D6-harness-richer-checks, D62-harness-schema-realpath-resolution, D64-ungateable-criteria-must-be-declared]
---

# harness.json — configuration reference

`planning/harness.json` is the **policy** seam between a project and the SDLC harness. The
engine code (`.claude/workflows/*.js`) carries the *mechanism* (pipeline ordering, retry loops,
report formats) and ships **no stack defaults**. This file is where a project names its real
validation commands and decides whether a UI-test stage exists.

## Scope: the gates are in-repo and in-language, by design

Every check a `harness.json` can declare — `command`, `baseline-diff`, `count-delta`,
`warning-scan`, `forbidden-pattern-scan`, `skip-count-regression` — runs a shell command against
**this repo's working tree**, in **this repo's language toolchain**. For `base-template` that is
`node --check` over four engines plus a set of Python scripts; for a Rust project it is
`cargo fmt`/`clippy`/`nextest`/`build`. That scope is deliberate, not an oversight — it is what
makes a check fast, hermetic, and reproducible in a worktree. But it means these checks
**structurally cannot observe** four classes of evidence, ever, regardless of which stack profile
a project picks:

1. **Another process** — an external CLI the code shells out to (`gh`, `git` against a second
   repo). The command's own exit code can be checked, but *what that process actually did* (did a
   PR really get created?) is outside any in-repo check's view.
2. **Another repo** — a sibling git index in a particular state. `harness.json` has no field for
   "assert this about a different repository's tree."
3. **A generated artifact** — a file emitted by a separate tool run, such as `status.md` or the
   boards `mev emit-state` writes across the fleet. A unit test can prove the generator's logic is
   correct without proving the artifact it emits into production reflects that logic.
4. **An installed artefact** — the compiled binary or distributed copy the fleet actually runs, as
   opposed to the source tree the gates compile against. Measured instance: `mev` on `PATH` was
   built Aug 9 12:57 against source HEAD Aug 9 23:22, and `bastion` embeds `mev` as a path library
   (`core/bastion/Cargo.toml:36`) built Jul 31 against source HEAD Aug 6 — every gate in both repos
   passed against current source while the deployed binaries ran stale code. Nothing in
   `harness.json` asks "is what's deployed what we built?"; that question is closed only by a
   project's own distribution step — `/sync-downstream-harness` for this repo's engines,
   `cargo install --path core/mev` (or `core/bastion`) for the Rust binaries on `PATH`. Until that
   step runs, source-tree correctness and installed behavior can diverge silently.

An acceptance criterion whose evidence lives in any of the four classes above is **un-gateable by
construction** — no `harness.json` check, however creatively written, can gate it directly. What
*is* gateable is whether the spec **admits** the gap and pairs the criterion with fixture evidence
instead of a bare command; `/ticket` and `/generate-tasks` enforce that declaration (see
[D64](../planning/decisions/D64-ungateable-criteria-must-be-declared.md) for the full diagnostic,
the observed instances, and why the trigger is a mechanical evidence-location test rather than a
judgment call). A green `harness.json` suite is evidence of **gate agreement**, not correctness —
it proves the checks that exist all passed, not that the criteria resting outside their reach are
true.

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

### Why the `$schema` path resolves from two different physical parents

In every generated project, `planning/` is a **symlink** into the company-brain vault
(`core/_planning/<repo>/`, `_planning/<repo>/`, and sibling vault roots per tier). A
`../`-relative `$schema` string is therefore read from two different physical parents
depending on how the reader gets there:

- **Lexical / textual-normalisation face** — a pure string join (`os.path.normpath`,
  `path.resolve`, most editor `$ref` autocomplete) collapsing `<repo>/planning/..` lands on
  `<repo>/.claude/workflows/harness.schema.json`, which exists in every synced repo. This
  reading resolves.
- **Physical / `realpath`-canonicalized face** — the file's real, symlink-resolved location is
  `core/_planning/<repo>/harness.json` (or the sibling vault root); its `../` is
  `core/_planning/`, which has no `.claude/` of its own. Any reader that actually calls
  `open()`/`stat()` on the joined path — including a naive lexical resolver, once the OS walks
  the symlink — hits this and fails, not just realpath-canonicalizing tools.

The fix (see [D62](../planning/decisions/D62-harness-schema-realpath-resolution.md)) is a
`.claude/workflows/harness.schema.json` **symlink** placed at each vault root, pointing at
base-template's canonical schema. That makes a real file exist at the join point on both faces,
so the existing `"../.claude/workflows/harness.schema.json"` string resolves everywhere with
zero edits to any project's `harness.json`. `scripts/test_harness_schema_realpath.py` is the
fleet audit that pins both faces resolving for every live config (registered in this repo's own
`planning/harness.json` as the `harness-schema-realpath` gating check).

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
| `flow` | object | No | `/sdlc-flow` engine policy (absent → CLI flag defaults apply) |

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

`kind` defaults to `"command"` (a plain exit-code gate — the table above). Five richer kinds let a
suite express more than "run a command" while keeping every stack-specific command/pattern in this
file (the engine only carries the interpretation). ¹`command` is required for every kind except
`forbidden-pattern-scan` (which uses `rules[]` instead).

| `kind` | Extra fields | What it does |
|---|---|---|
| `baseline-diff` | `baselineCommand`, `compareKeys[]` | Snapshots a baseline at worktree creation; at test time diffs current output and fails **only on net-new items** (pre-existing ones never gate). Both commands must emit the same JSON-array format. |
| `count-delta` | `countPattern`, `failOn` | Extracts an integer (first number on the line matching `countPattern`) and fails when it regresses vs the previous task. `failOn`: `decrease` or `zero-or-decrease`. Task 1 → SKIPPED. |
| `warning-scan` | `warningPatterns[]` | Runs `command` (its **exit code gates**), then records matches of the patterns in its output — advisory WARN when `gates:false`, also-failing when `gates:true`. |
| `forbidden-pattern-scan` | `rules[]` of `{id, pattern, paths?, allowlistPattern?}` | Source greps that must find nothing; any match is a violation. |
| `skip-count-regression` | `command`, `baselineCommand`, `reasonCommand?` | Captures a baseline skip count at worktree creation (`baselineCommand`, bare integer); at gate time re-runs `command` and fails only when the current skip count **exceeds** the baseline. `reasonCommand` (optional) runs only when the check is about to fail, to surface the dominant skip reason in the failure message. Supported identically (no degradation) in both `/sdlc-task` and `/sdlc-flow`. |

> **`count-delta` caveat:** this check degrades to a plain exit-code gate in both `/sdlc-task`
> and `/sdlc-flow`. The cross-task regression comparison (`failOn: decrease`/`zero-or-decrease`)
> no longer fires under either engine — only the command's exit code is evaluated.

See `planning/harness.examples.md` (the Python "rich checks" profile) for a worked example of all
five, and [D6](../planning/decisions/D6-harness-richer-checks.md) for the rationale.

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
| `recommend` (default) | Log a recommendation and proceed — no file is written. `/sdlc-task` logs it before implementing; `/sdlc-flow` logs it before its first task. |
| `auto` | Generate `breakdown.md` sub-steps for the flagged tasks first, then implement follows the sub-steps. |
| `off` | Skip the assessment entirely. |

The per-task engine (`/sdlc-flow` or `/sdlc-task`) assesses coarseness when it starts and
logs/applies per `mode`. `/generate-tasks` previews the same recommendation at authoring time.
See [D10](../planning/decisions/D10-breakdown-assessment.md).

### `planning` object

Optional. Controls planning-phase behavior of the authoring commands (`/plan`, `/generate-tasks`).
Absent → all fields default to today's zero-touch behavior.

| Field | Type | Required | Description |
|---|---|---|---|
| `clarify` | boolean | No | `false` (default) · `true` |

When `clarify: true`, the authoring commands surface **2–4 targeted clarifying questions** for an
ambiguous prompt *before* writing the spec — the deliberate counter to the "model guesses intent →
median results" anti-pattern. Default `false` preserves the zero-touch flow (write immediately). A
user can always force the behavior for a single invocation by appending **`--clarify`**, regardless
of this setting. See [D20](../planning/decisions/D20-clarify-before-generate.md).

### `flow` object

Optional. Policy for the **`/sdlc-flow`** engine — the default for non-trivial feature work. It
runs one spec sequentially in a single shared worktree, with a per-task test-fix loop, one
consolidated end-review, a docs patch, and a PR as the terminal step. Only `/sdlc-flow` reads this
block; `/sdlc-task` ignores it. Absent → CLI flag defaults apply.

| Field | Type | Required | Description |
|---|---|---|---|
| `autoMerge` | boolean | No | Default for `--auto-merge`. `false` (default): stop after opening the PR and let a human merge. `true`: merge the PR and tear down the worktree on a clean PASS (non-draft PR only — never merges on bail). CLI `--auto-merge` overrides per run. |
| `testDepth` | string | No | `"fast"` (default) or `"full"`. Per-task validation depth. `fast` runs only `gates:true` checks as a cheap tripwire; `full` runs the whole suite per task. The end-review always runs the full suite regardless of this setting. CLI `--test-depth` overrides per run. |
| `prBase` | string | No | Base branch for `gh pr create --base` (default: `"main"`). Set to `"develop"` or another branch if the project uses a non-main integration target. |
| `bailReasons` | string[] | No | Extra project-specific immediate-bail reasons appended to the five universal ones (missing dependency, spec contradiction, env failure, out-of-scope action, stuck/structural). Triage checks the full combined list. Format: plain-English sentences. |

**The five universal bail reasons** are hardcoded in the engine (mechanism, not policy) and always
active regardless of this config. `bailReasons[]` only **adds** project-specific reasons on top of
them.

**CLI flag resolution order:** `--flag` (per run) > `flow.*` key (per project) > engine fallback.

```jsonc
// example flow block — adjust to project needs
"flow": {
  "autoMerge": false,          // keep false; require human to merge the PR
  "testDepth": "fast",         // "full" if per-task integration breaks are common
  "prBase": "main",            // or "develop" for gitflow projects
  "bailReasons": []            // add project-specific triggers here
}
```

See [D30](../planning/decisions/D30-sdlc-flow-engine.md) (engine design),
[D32](../planning/decisions/D32-triage-gated-bail.md) (bail set), and
[D33](../planning/decisions/D33-pr-based-wrap-up.md) (PR wrap-up) for the rationale behind each
key.

---

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
      { "name": "clippy", "command": "cargo clippy --all-targets -- -D warnings", "fastCommand": "cargo clippy -- -D warnings", "purpose": "Lint gate — end-of-flow review sees test/bench targets too", "gates": true },
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
| **No emoji in docs** | Universal harness rule — every project applies it. **Diff-scoped**: the gate parses `git diff -U0` and judges only lines *added* in the run's range (`+++`/`---` diff headers are never treated as content, a pure rename has no added lines and passes, a brand-new file's added lines are its whole content). A file with pre-existing emoji outside the diff never fails a change that didn't touch those lines — this is what lets the gate ratchet instead of blocking on legacy footprint. See `.claude/commands/test.md`, `.claude/workflows/sdlc-task.js`, `.claude/workflows/sdlc-flow.js`, and `.claude/commands/close-out.md` for the four sites (all four also exempt the literal `Generated with Claude Code` PR-footer). |
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
