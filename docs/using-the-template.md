---
type: Guide
title: Using the template — generate, configure, run
description: Step-by-step guide for generating a new project from base-template and running the first pipeline.
doc_id: using-the-template
layer: [factory]
project: base-template
status: active
keywords: [new-project, scaffold, configure, harness.json, pipeline run, getting started]
related: [base-template-architecture, base-template-docs-index, harness-json]
---

# Using the template — generate, configure, run

## 1. Generate a new project

Run `/new-project` from the `agentic-portfolio/` brain root. It will prompt for:

- **Project name** — human-readable (e.g. `My Rust CLI`)
- **Slug** — kebab-case identifier (e.g. `my-rust-cli`)
- **Description** — one sentence
- **Project type** — `personal`, `client`, or `infrastructure`

`/new-project` then:

1. Copies `.claude/workflows/` (the JS engines) from `base-template` into `<slug>/.claude/workflows/`.
   Command files are **not** copied — they live globally in `~/.claude/commands/` and are available
   automatically to every project. Pass `--include-commands` (Block C) to opt into a full local copy
   for portable, offline, or shareable projects.
2. Copies the **contents** of `scaffold/` into `<slug>/` (so `scaffold/planning/` becomes
   `<slug>/planning/`, etc.) and substitutes all `{{TOKENS}}`.
3. Stamps the `base-template` commit hash as provenance in `planning/.template-version` and
   the first `log.md` entry.
4. Registers the project in the brain (`docs/projects/<slug>.md`, `README.md`, etc.).
5. Optionally `git init`s the new directory.

After generation the project has a complete `planning/` skeleton and the full SDLC harness,
but **no application code and no configured validation commands yet**.

### What a new project inherits

- **Global commands** — all harness slash commands from `~/.claude/commands/` are available
  immediately (installed via `/session:sync-global-commands` from base-template). Invoke them using
  the subdirectory namespace: `/session:prime`, `/planning:plan`, `/sdlc:implement`, etc.
- **Workflow engines** — `.claude/workflows/*.js` ship per-project so they can read the local
  `planning/harness.json` for stack-specific config.
- **Project-specific commands** — if your project needs custom commands, place them in
  `.claude/commands/`. Project-level commands take precedence over global commands on name conflict.

## 2. Configure harness.json for your stack

Before you can run `/test` or any pipeline phase past `/implement`, the engines need to know
your validation commands. Open `planning/harness.json` in the new project — it ships as a
neutral stub:

```jsonc
{
  "$schema": "../.claude/workflows/harness.schema.json",
  "stack": "fill-me-in",
  "validation": {
    "checks": [
      // copy a profile from planning/harness.examples.md
    ]
  },
  "uiTest": {
    "enabled": false
  }
}
```

Open `planning/harness.examples.md` and copy the profile for your stack (Rust, Python, or
Next.js). For a web project that needs UI smoke tests, set `uiTest.enabled: true` and fill
in the enabled-only fields (`devServerCommand`, `readySignal`, `port`, `routes`).

See [harness-json.md](harness-json.md) for the full schema reference.

**Config absent behavior:** if you skip this step, the `/test` stage falls back to the
spec's `## Validation Commands` section (a plain markdown list in the task spec). This is
fine for a quick start but is less reliable than a `harness.json`.

## 3. Fill in planning/context.md and planning/master-plan.md

The scaffold ships tokenized stubs. Replace the tokens with real project content:

- `planning/context.md` — fill in the "What This Is", "Who Maintains It", and "Fast Facts"
  sections.
- `planning/master-plan.md` — define your phases and blocks. The SDLC pipeline reads this to
  generate task specs via `/generate-tasks`. Rather than hand-writing it, run
  **`/generate-master-plan`** with your planning notes — it authors the roadmap as canonical
  `## Phase N` → `### Block X` definitions whose headers `/generate-tasks <phaseN-blockX>` parses
  directly, so the structure is right the first time.

## 4. Start your first session

```
/session:prime                 # orient the agent: reads README, CLAUDE.md, context.md, status.md
/session:status                # confirm current focus
/sdlc:process-tasks            # check which specs are eligible
```

## 5. Run a spec through the pipeline

The typical flow for one spec (here `my-feature`):

```
/planning:generate-tasks my-feature     # write planning/my-feature/tasks.md

/sdlc:implement planning/my-feature/tasks.md
/sdlc:test      planning/my-feature/tasks.md
/sdlc:review-task planning/my-feature/tasks.md

# if FAIL or PARTIAL:
/sdlc:fix       planning/my-feature/tasks.md
/sdlc:test      planning/my-feature/tasks.md
/sdlc:review-task planning/my-feature/tasks.md

# once PASS:
/sdlc:document  planning/my-feature/tasks.md
/session:log-work
```

Or run it all unattended:

```
/sdlc-run my-feature           # single sequential run
/sdlc-block my-feature         # parallel waves with retries and auto-merge
```

### Experimental features (kept out of the roadmap)

For a small feature you want to try on a branch *before* committing it to `master-plan.md`:

```
/planning:plan add-rate-limiter                              # writes planning/plan-add-rate-limiter/plan.md
/planning:generate-tasks --from planning/plan-add-rate-limiter/plan.md   # → planning/plan-add-rate-limiter/tasks.md
/sdlc-flow plan-add-rate-limiter                    # run it on a feature branch, terminates in a PR
```

This gets the experimental work the same decomposition rigor as a roadmap block (disjoint-ownership
analysis, pipeline recommendation) without polluting the roadmap. See
`planning/decisions/D34-adhoc-planning-seam.md`.

See `scaffold/CLAUDE.md` → "Available Commands" for the full list of global harness commands,
invocation format, and category descriptions. See `.claude/commands/README.md` (if present in your
project) for project-level command conventions.

## 6. The update loop (pulling harness improvements later)

When `base-template` ships a harness improvement you want to pull into an existing project, run
`/sync-downstream-harness` from `base-template`'s root (dry-run first, then `--apply`) — it copies
every changed `.claude/commands/*.md` + `.claude/workflows/` file into every scaffolded repo at
once, never deletes a project's own customizations, and stamps `planning/.template-version` for
you. See `planning/decisions/D48-downstream-harness-sync-script.md`.

The fully manual version (useful for a single targeted pull, or if the repo isn't registered in
`brain.toml`):

1. Check `base-template/log.md` to see what changed and which files were affected.
2. Copy the changed files from `base-template/.claude/` into your project's `.claude/`.
3. If `planning/harness.json` schema changed (new fields), consult
   `base-template/docs/harness-json.md` and update your project's config.
4. Append a note to your project's `log.md` recording the pull and the base-template commit hash.

Downstream projects diverge by design after generation — pull selectively and verify. Either way,
this doesn't commit for you — review the diff in each project and commit there.
