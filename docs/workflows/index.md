---
type: Index
title: SDLC Workflows — reference hub
description: Navigation + shared concepts for the two SDLC orchestration engines (sdlc-flow, sdlc-task) and the manual command lifecycle.
doc_id: base-template-workflows-index
layer: [factory]
project: base-template
status: active
keywords: [SDLC workflows, engines, orchestration, harness, pipeline reference]
related: [base-template-docs-index, sdlc-task, sdlc-flow, sdlc-commands]
---

# SDLC Workflows

This is the canonical reference for the **harness's automated pipelines** — the `.claude/workflows/*.js`
engines that drive a spec from a `tasks.md` to merged, tested, documented code, and the manual
slash-command lifecycle they automate.

> **This lives here on purpose.** These engines are authored and evolved in `base-template` (the
> software-factory source). Downstream projects copy `.claude/` verbatim, so the workflows are
> identical everywhere — documenting them anywhere else would drift. When an engine changes, update the
> matching page here in the same change.

---

## The pipeline ladder

```
/patch          trivial hotfix · no tests · in-place
/sdlc-task      small tested change · implement→test→fix→commit · in-place or --worktree
/sdlc-flow      full spec · sequential · branch (or --worktree) · terminates in PR   ← default for non-trivial work
/orchestrate    roadmap · one /sdlc-flow per block · branch train of PRs
```

## The two engines at a glance

| Engine | Scope | Isolation | Pairs with | You reach for it when… |
|---|---|---|---|---|
| [`/sdlc-task`](sdlc-task.md) | **one small unit** | in-place / `--worktree` | `/chore`, `/ticket` | small tested change — fast implement→test→commit |
| [`/sdlc-flow`](sdlc-flow.md) | **a whole spec**, **sequential** | plain branch in the main tree (one shared for the whole spec), or `--worktree` | `/generate-tasks` | **the default for non-trivial feature work** — sequential, conflict-free, terminates in a PR |

A whole roadmap (master-plan-format file) is driven by `/orchestrate` / `/begin-orchestration`,
which fan out one `/sdlc-flow` per independent block across dependency-ordered waves — see
[`.claude/commands/README.md`](../../.claude/commands/README.md) for that command's reference.

For step-by-step **manual** control (run `/implement`, then inspect, then `/test`, …), see the
[manual command lifecycle](commands.md). The engines automate exactly those commands.

```mermaid
flowchart TD
    plan["planning/&lt;spec&gt;/tasks.md<br/>(written by /generate-tasks)"]
    roadmap["planning/master-plan.md<br/>(written by /generate-master-plan or /plan)"]

    plan --> flow["/sdlc-flow<br/>whole spec, branch (or --worktree), PR"]
    plan --> task["/sdlc-task<br/>small unit, in-place or --worktree"]

    roadmap --> orch["/orchestrate<br/>roadmap → one /sdlc-flow per block"]
    orch --> flow

    flow -. "open PR (default)" .-> pr["PR — /review-PR → /merge-train"]
    orch -. "PR per block" .-> pr

    classDef engine fill:#1f2937,stroke:#60a5fa,color:#e5e7eb;
    class flow,task,orch engine;
```

- `/sdlc-flow` is the **default for non-trivial feature work**: one shared branch eliminates
  inter-task merge conflicts; a single end-review over the integrated tree replaces per-task reviews;
  the terminal step is a PR. Runs on a plain branch in the main tree by default (keeps a relative
  `planning/` symlink intact), or in an isolated worktree with `--worktree`.
- `/orchestrate` is the **roadmap driver**: it fans out one `/sdlc-flow` per independent block
  across dependency-ordered waves, producing a branch train of reviewable PRs.
- `/sdlc-task` is the **fast path** for small work: a real implement→test→fix loop but no
  review/document/wrap-up agents. Pairs with `/chore` and `/ticket`.

### Decomposition differs by engine: disjoint files vs. compilable boundaries

`/generate-tasks` decomposes a block **before** the consuming engine is chosen, so it applies one of
two mutually-exclusive rules depending on which engine will run the spec:

- **`/orchestrate`** runs each block as its own pipeline in parallel worktrees that merge independently
  — so blocks must own **disjoint files**; an undeclared overlap escalates the whole roadmap at merge.
- **`/sdlc-flow` and `/sdlc-task`** run every task sequentially on one branch/worktree with no
  inter-task merge step, but gate the project's checks after **every single task** — so **every task
  boundary must leave the gating suite passing** (for a compiled/type-checked stack, the repo must
  compile at every boundary). A change that cannot be split without an intermediate non-compiling
  task — e.g. a renamed public type and every call site — lands in **one** task instead, even if that
  means merging tasks that would otherwise be file-disjoint.

The full rule, its precedence, and the escape hatches (`additiveFiles`, `dependsOn`) live in
[`generate-tasks.md`](../../.claude/commands/generate-tasks.md) — see its step 6 — rather than being
restated here.

---

## Shared concepts (true for all engines)

### Each stage is its own agent
Every pipeline stage runs as a **separate single-context agent**. Stages never share memory — they
communicate through committed files under `planning/<spec>/sdlc/`. That is what makes the pipeline
crash-recoverable and resumable: the committed files *are* the state.

### Committed state model

Each engine writes a committed JSON state file under `planning/<spec>/sdlc/`:

| Engine | State file | Status |
|---|---|---|
| `/sdlc-task` | `sdlc-task-state.json` | committed — per-task status + token roll-up (D38) |
| `/sdlc-flow` | `sdlc-flow-state.json` | committed — authoritative run index; drives `--resume` (D31) |

`/sdlc-flow` also writes a human-readable `worklog.md` alongside its state file. The other engines
use per-stage report files (see below) as the primary resume signal; their state files are the
at-a-glance index and token accounting artifact.

### State + worklog contract (Phase 2-5 commands invoked by hand)
There is no per-stage prose report file. `/implement`, `/test`, `/fix`, `/review-task`, and
`/document`, invoked by hand, each read and update one shared `planning/<spec>/sdlc/state.json`
(per-task keyed: status, attempts, files changed, commit, validation result) and append a section to
`planning/<spec>/sdlc/worklog.md` — the same D31 shape `/sdlc-flow` uses, adapted for a standalone
run (`mode: "standalone"`). Both files are write-only: never `git add`/`git commit`ed, read back off
disk rather than git history.

| Artifact | Written by | Read by |
|---|---|---|
| `sdlc/state.json` (`tasks["<N>"]` entries) | implement, test, fix, review-task, document — each command only touches the fields/tasks it owns | every later stage on the same spec; `/fix` gates on `review.verdict` |
| `sdlc/worklog.md` (`## Task <N> — <STAGE>` sections; `/fix` appends a `FIX PASS <k>` section per pass rather than overwriting) | implement, test, fix, review-task, document | human-readable run trail for the next stage or a resuming operator |
| `sdlc-flow-state.json` | `/sdlc-flow` state-writer ([D31](../../planning/decisions/D31-committed-authoritative-state.md)) | `--resume`, end-review localization, PR body — **committed** |
| `worklog.md` (flow-scoped) | `/sdlc-flow` state-writer ([D31](../../planning/decisions/D31-committed-authoritative-state.md)) | human-readable run trail — **committed** |

### The two hard gates
1. **Review gates Document** — `/document` refuses to run unless the review verdict is `PASS`.
2. **Fresh tests gate the PASS verdict** — review re-runs the *gating* validation checks itself; a
   failing check forces `FAIL`/`PARTIAL` no matter how clean the code reading was. A sloppy test report
   can never ship a bug.

### `/close-out`'s diff base is resolved, never hard-coded

`/close-out` — the manual quality-close command every engine points to on completion (`sdlc-flow.js`:
"Next: run `/close-out` to verify coverage + patch docs before handing off") — scopes
its universal emoji gate and its source-file coverage sweep to the **same resolved base**, never the
literal string `main`. A hard-coded `main..HEAD` is empty by definition whenever `HEAD` **is** `main`
— the default state after an in-place `/sdlc-task` run, a plain-branch `/sdlc-flow` run (D51), or
right after `--auto-merge`/`--merge-branch` land — which used to report a vacuous "OK" over zero
files instead of "nothing considered."

`/close-out` now resolves the base once, before Step 1, from real evidence: an explicit `--base
<ref>`, else `planning/harness.json`'s `flow.prBase`, else `origin/HEAD`, else a local `main` or
`master`. If the current branch **is** the resolved base, it falls back to the enclosing merge
commit's first parent (`HEAD^1..HEAD`) when one exists (e.g. right after `--auto-merge`); with no
merge commit to scope from, it **refuses to run** rather than proceed with an empty file list. This
mirrors the pattern the engines already use for their own diff scoping — `sdlc-task.js`'s committed
`baseSha`, `sdlc-flow.js`'s configured `${prBase}` —
`/close-out` is the one caller-facing command that previously had none of that context available to
it. Full flag reference: the `/close-out` entry in [`.claude/commands/README.md`](../../.claude/commands/README.md).

### Validation is policy, not mechanism
No engine ships stack defaults. Each project declares its validation commands (and optional UI-test
stage) in [`planning/harness.json`](../harness-json.md). The test/review stages run exactly those
checks; absent a config they fall back to the spec's `## Validation Commands` block and disable the
UI-test stage. **Universal** rules stay hardcoded (no emoji in changed markdown, every change ships with
tests, parallel port = `port + taskNumber`).

### Model tiering — match the model to the work
> **Opus plans · Sonnet judges · Haiku does the mechanics.**

Each stage names its model in a `MODEL` map at the top of its engine. Without the map, every stage would
inherit the *session* model (launch from Opus → scout/test run on Opus too). A sharp spec + breakdown
makes implement/test/review well-scoped enough that Sonnet is reliable, so only spec authoring needs
Opus and the purely-procedural stages drop to Haiku.

| Tier | Stages | Why |
|---|---|---|
| **Opus** | `generate-tasks` (fallback), `enumerate-blocks` | planning / dependency-graph derivation — the leverage point |
| **Sonnet** | `implement`, `fix`, `triage`, `review`, `ui-test`, `document`, `wrap-up`, `pre-flight`, `PR` | judgment work |
| **Haiku** | `scout`, `setup`, `test`, `update-task`, `state-writers` | fixed procedures, no judgment |

**Staged escalation:** inside `/sdlc-task` and `/sdlc-flow`, the *final* fix pass and
*final* review attempt run on `ESCALATION_MODEL` (`opus`). A hard task that has already failed gets one
strong shot before the pipeline wraps up `FAIL`. Set `ESCALATION_MODEL = null` to disable.

The real planning leverage is **upstream**: `/generate-tasks` and `/breakdown` run on your *session*
model, so author specs on an Opus session, then let the pipeline grind on Sonnet.

### The retry loop (max 3 attempts)
`implement → test → review →` `PASS: document` **or** `FAIL/PARTIAL: fix → test → review`.
`/sdlc-flow` and `/sdlc-task` use a triage-gated bail instead of a
simple counter: triage classifies each failure as `RETRYABLE` or stuck, and stops early on stuck. Each
fix pass is its own commit, so the diff from each pass is auditable. After max failures the pipeline
wraps up `FAIL`.

---

## Token usage

Costs are dominated by stage count × model tier × spec size. Per-run token totals are recorded in
each engine's committed state file — check the state JSON for real figures from past runs.

| Workflow | Typical agents per run | Notes |
|---|---|---|
| `/sdlc-task` (one task, PASS first try) | ~4–6 | scout + implement + test + commit |
| `/sdlc-flow` (5-task spec, PASS first try) | ~30–40 | setup + per-task update/implement/test + end-review + docs + wrap-up + PR |
| `/orchestrate` (5-block roadmap) | N × `/sdlc-flow` + orchestration | dominated by child flow costs |

> **Token roll-up note:** all engines record **substantive-stages-only** totals — cheap Haiku helper
> agents (state writers, enumerate, update-task) are excluded. See
> [D37](../../planning/decisions/D37-unified-committed-state-and-telemetry.md).

---

## Pages

- **[sdlc-flow.md](sdlc-flow.md)** — the default for non-trivial feature work (D30). Shared worktree,
  per-task test-fix loop, triage-gated bail (D32), committed state model (D31), PR wrap-up (D33).
- **[sdlc-task.md](sdlc-task.md)** — lean single-unit engine (D38). In-place or `--worktree`, implement→test→fix→commit, pairs with `/chore`/`/ticket`.
- **[commands.md](commands.md)** — the manual command lifecycle the engines automate (Phase 1 → 7).

> A whole roadmap is driven by `/orchestrate` / `/begin-orchestration` (one `/sdlc-flow` per block,
> branch train of PRs, `/review-PR` → `/merge-train`) — see
> [`.claude/commands/README.md`](../../.claude/commands/README.md); block-level roadmap orchestration
> no longer has a dedicated engine of its own (D39 superseded).

## Related

- [harness-json.md](../harness-json.md) — the `planning/harness.json` config the engines read.
- [`.claude/commands/README.md`](../../.claude/commands/README.md) — the command catalog.
- [`planning/decisions/`](../../planning/decisions/index.md) — the ADRs behind each behavior (D6–D43).
