---
type: Reference
title: /sdlc-flow — single-branch, PR-terminating SDLC engine
description: The default engine for non-trivial feature work. Runs one spec sequentially on a single branch (in the main tree by default, or an isolated worktree with --worktree) with a per-task test-fix loop, one consolidated end-review, a docs patch, and a PR as the terminal step.
doc_id: sdlc-flow
layer: [factory]
project: base-template
status: active
keywords: [sdlc-flow, branch mode, worktree, PR, test-fix loop, end-review, SDLC engine, planning-vault, D46]
related: [base-template-workflows-index, sdlc-block, D30-sdlc-flow-engine, D31-committed-authoritative-state, D33-pr-based-wrap-up, ticket-vault-aware-state-commits]
---

# `/sdlc-flow` — single-branch, PR-terminating SDLC engine

The default engine for non-trivial feature work. Runs every task in a spec **sequentially on one
shared branch** — so there are no inter-task merge conflicts — with a per-task
`implement → fast-test → fix` loop, **one** consolidated review over the integrated tree at the end,
a surgical docs patch, and a **pull request** as the terminal step.

Compared with `/sdlc-block`, `/sdlc-flow` trades task-level parallelism for reliability: one
shared branch means zero inter-task merge conflicts, one end-review instead of a per-task pile, and
a PR handoff rather than an in-place landing. Compared with `/sdlc-run`, it works on a dedicated
`<spec>-flow` branch and terminates with a PR rather than committing directly to the current branch.

## Isolation mode — branch (default) vs `--worktree`

By **default**, `/sdlc-flow` creates the `<spec>-flow` branch and checks it out **in the main working
tree** — no `trees/` worktree, no sparse-checkout. This keeps a relative `planning/` symlink
(brain-vaulted repos) intact, which a sparse-checkout worktree breaks. `main` stays on the branch
until the PR merges; a fresh run refuses to start on a **dirty** working tree (commit or stash first,
or use `--worktree`).

Pass **`--worktree`** to run in an isolated sparse-checkout worktree under `trees/<spec>-flow/`
instead — the original behavior. Reach for it when you need true isolation: notably `/sdlc-block`,
which fans out concurrent `/sdlc-flow` children and therefore always passes `--worktree` so parallel
blocks don't collide in one working tree.

Everything downstream (the per-task loop, review, docs, wrap-up, PR) is identical in both modes; only
the checkout location differs. In branch mode the "worktree path" the engine reports is simply the
repo root.

Engine: [`.claude/workflows/sdlc-flow.js`](../../.claude/workflows/sdlc-flow.js)

---

## Usage

```
/sdlc-flow <spec-slug>                         run every task in the spec, open a PR, stop
/sdlc-flow <spec-slug> 1-3                     scope to tasks 1 through 3
/sdlc-flow <spec-slug> 1,3,5                   scope to specific tasks
/sdlc-flow <spec-slug> 1-3,7                   range plus an extra task
/sdlc-flow <spec-slug> --tasks 1-7             explicit flag form (same as positional range)
/sdlc-flow <spec-slug> --auto-merge            merge the PR + clean up + emit-state on clean PASS
/sdlc-flow <spec-slug> --no-pr                 stop after wrap-up; do not create a PR
/sdlc-flow <spec-slug> --worktree              run in an isolated worktree (default: plain branch)
/sdlc-flow <spec-slug> --resume                re-attach the branch/worktree; skip already-passed tasks
/sdlc-flow <spec-slug> --test-depth full       run the full gating suite per task (default: fast)
```

| Argument | Meaning | Default |
|---|---|---|
| `<spec-slug>` | **Required.** The spec directory name — drives every `planning/<spec-slug>/…` path. | — |
| `[range]` | Optional task selection as the 2nd positional token or via `--tasks`. Forms: `1-7`, `1,3,5`, `1-3,7`, `5`. | all tasks |
| `--tasks <range>` | Equivalent to the positional range. | — |
| `--auto-merge` | After a clean PASS, merge the PR, delete the branch (tear down the worktree too under `--worktree`), and run `mev emit-state --write` on the base. Only fires on a non-draft PR with a PASS verdict — never on bail. | off |
| `--no-pr` | Stop after wrap-up; leave the branch for a manual PR (or `/close-out --merge-branch`). | off (create PR) |
| `--worktree` | Run in an isolated sparse-checkout worktree under `trees/<spec>-flow/` instead of a plain branch in the main tree. Needed for concurrent runs (e.g. `/sdlc-block` children). | off (plain branch) |
| `--resume` | Re-attach the existing branch/worktree and skip tasks whose `state.json` status is `passed`. | off |
| `--test-depth fast\|full` | Per-task validation depth. `fast` runs only `gates:true` checks (the tripwire); `full` runs the whole suite per task. | `fast` |

> All CLI flags override the corresponding `flow.*` config key in `planning/harness.json`. The config
> sets the per-project default; the flag overrides it for one run.

---

## Pipeline

```mermaid
flowchart TD
    Setup["Setup — branch or --worktree<br/><i>haiku</i>"] --> Enumerate["Enumerate tasks — D16 lint<br/><i>haiku — resume load if --resume</i>"]
    Enumerate --> UpdateTask["update-task (in-progress)<br/><i>haiku</i>"]
    UpdateTask --> Implement["Implement<br/><i>sonnet</i>"]
    Implement --> FastTest["Fast test<br/><i>haiku — gating checks only</i>"]
    FastTest -- "FAIL" --> Triage{"Triage — D32<br/><i>sonnet</i>"}
    Triage -- "RETRYABLE (&lt;3 attempts)" --> Fix["Fix<br/><i>sonnet &rarr; opus on final attempt</i>"]
    Fix --> FastTest
    Triage -- "MAJOR / 3&times; exhausted" --> Review
    FastTest -- "PASS &rarr; next task" --> UpdateTask
    UpdateTask -- "all tasks done" --> Review{"End-review<br/><i>sonnet — full gating suite</i>"}
    Review -- "FAIL/PARTIAL, localized<br/>(&lt;2 passes)" --> ReviewFix["Review fix<br/><i>sonnet &rarr; opus on final</i>"]
    ReviewFix --> Review
    Review -- "PASS" --> Docs["Docs patch<br/><i>sonnet — gated on PASS</i>"]
    Review -- "bail (broad)" --> Wrapup["Wrap-up<br/><i>sonnet — status/log + amendment log</i>"]
    Docs --> Wrapup
    Wrapup --> PR["gh pr create<br/><i>sonnet — draft PR on bail</i>"]

    classDef gate fill:#3b0764,stroke:#a78bfa,color:#e5e7eb;
    class Review,Triage gate;
```

| Stage | Model | What it does |
|---|---|---|
| **Setup** | haiku | Creates (or re-attaches on `--resume`) the `<spec>-flow` branch for the whole spec. **Branch mode (default):** `git checkout -b` in the main tree (aborts on a dirty tree). **`--worktree`:** an isolated git worktree applying the D5/P5 cone-all-tracked-dirs recipe. Checks for unfilled tokens (D19 thin-spec guard) on a fresh run. |
| **Enumerate** | haiku | Reads `tasks.md` for `### N.` task headings (D16 preflight lint — refuses to run if none found). On `--resume`, reads the on-disk (uncommitted) `sdlc-flow-state.json` to identify already-passed tasks and skip them. |
| **update-task** | haiku | Marks the current task in-progress in `tasks.md` (surgical checkbox edit). Disk-only, like the state-writer — neither commits. |
| **Implement** | sonnet | Executes task N against the spec (and `breakdown.md` if present). Runs the D8 completeness self-check before committing `feat:`. |
| **Fast test** | haiku | Runs the `gates:true` checks from `harness.json` (the per-task tripwire). Falls back to the spec's `## Validation Commands` if no config. Also runs the universal emoji gate on changed markdown. |
| **Triage** | sonnet | Classifies a test failure as `RETRYABLE` (transient, or the failure changed — progress is possible) or `MAJOR` (an immediate-bail reason fires, or no progress). See [D32](../../planning/decisions/D32-triage-gated-bail.md). Bail means: break to end-review with `draft` flag. |
| **Fix** | sonnet | Targeted fix for the failing checks only — never a re-implement. Escalates to `opus` on the final attempt (`ESCALATION_MODEL`). |
| **End-review** | sonnet | ONE consolidated review over the integrated tree. Re-runs the **full** gating suite (authoritative). Reads `git diff <prBase>..HEAD` + `tasks.md` acceptance criteria + the on-disk (uncommitted) `state.json` as the localization index. Verdict: `PASS` / `PARTIAL` / `FAIL`. |
| **Review fix** | sonnet | Bounded fix for localized end-review findings. Escalates to `opus` on the final pass. A broad or structural finding bails instead (triage decision). |
| **Docs patch** | sonnet | Surgical `--patch` of affected doc files. **Hard-gated on a PASS verdict.** Skipped entirely on bail. |
| **Wrap-up** | sonnet | Updates `status.md` + appends the `log.md` entry + writes D18 Amendment-Log entries — all **on the flow branch** (so they ride in the PR and merge atomically with the code). On a fully-done block, also flips `planning/state.json`'s block status to `"closed"` on the branch. It does **not** run `mev emit-state --write` in either mode (a worktree refuses it; a plain feature branch is not the base) — derived surfaces regenerate on the base when the branch merges via `/clean-worktree`, `/merge-train`, or `/close-out --merge-branch` ([D50](../../planning/decisions/D50-sdlc-engines-flip-block-status-on-close.md), [D51](../../planning/decisions/D51-sdlc-flow-branch-default.md)). |
| **PR** | sonnet | Pushes the branch and runs `gh pr create --base <prBase>`. Builds the PR body from the on-disk (uncommitted) `state.json` (per-task summary, verdict, open items). Opens a **draft** PR on bail. Degrades gracefully when `gh` is absent — prints the branch name and the exact commands. |

### Per-task retry loop

`update-task → implement → fast-test →` **PASS: next task** or **FAIL: triage →** `RETRYABLE: fix →
fast-test` (up to **3 total attempts**), or `MAJOR: bail to end-review`. The final fix attempt
escalates to `opus`. Exhausting the attempt cap also bails.

### End-review fix loop

`end-review →` **PASS: docs** or **FAIL/PARTIAL (localized): review fix → end-review** (up to
**2 fix passes**, `opus` on the last). A broad or structural finding from triage skips the fix loop
and bails straight to wrap-up (draft PR).

---

## Run-state model — written to disk, deliberately NOT committed

`/sdlc-flow` keeps a compact run-state index instead of the other engines' 5 × N gitignored report
files. Under D46 (`agentic-portfolio/docs/decisions/D46-planning-vault-symlink.md`, a brain-repo
decision — cross-repo, so not linked from here), a brain-vaulted repo's `planning/` is a relative
symlink into the brain, so `git add planning/...` fails with "pathspec is beyond a symbolic link."
Committing run-state was the vector that led an agent recovering from that failure to
checkout/commit inside the brain repo instead. Run-state is read back **only off disk** (never out
of git) by `--resume`, so there is no need to commit it at all. See the "Vaulted planning
directories (D46)" section below for the staging rule this implies for the files that *are* still
committed.

| File | Location | Status | Purpose |
|---|---|---|---|
| `sdlc-flow-state.json` | `planning/<spec>/sdlc/` | written to disk — **not committed** | Authoritative run index. Drives `--resume`, feeds the end-review as a localization map, and lets wrap-up build the PR body. |
| `worklog.md` | `planning/<spec>/sdlc/` | written to disk — **not committed** | Human-readable trail. One short section per task/phase: what completed, issues hit, how resolved, decisions. |

`state.json` keys: `spec_slug`, `branch`, `mode` (`branch|worktree`), `worktree_path` (the repo root in branch mode), `started_at`, `updated_at`,
`status` (`running|review|docs|wrapup|blocked|done`), `current_task`, `tasks` (per-task
`status/attempts/summary/issues/fixes/decisions/files_changed/commit/validated`), `review`
(`verdict/findings/attempts`), `docs` (`changed/created`), `bail_reason`, `pr` (`url/number`),
`tokens` (per-task and per-stage token usage + cumulative `total`).

> **Token roll-up note:** `tokens.total` covers substantive stages (implement, test, fix, review,
> docs, wrap-up). Cheap Haiku helper agents (state writers, enumerate, update-task) are excluded.
> See [D37](../../planning/decisions/D37-unified-committed-state-and-telemetry.md).

A **Haiku state-writer agent** stamps `started_at`/`updated_at` and writes both files to disk with
the Write tool. It runs **no git command at all** — no `git add`, `git commit`, `git checkout`,
`git switch`, or `git branch`. The `tasks.md` checkbox edit (via `update-task`) is likewise disk-only
and uncommitted between task/phase boundaries. This means an uncommitted working tree — beyond the
implement/fix/docs/wrap-up commits themselves — is the **expected steady state** while a run is in
progress, not a sign anything went wrong.

**The state is the index, never a substitute for verification.** The end-review is fed `state.json`
but must still read `git diff <prBase>..HEAD` + `tasks.md` criteria directly and re-run the full
gating suite. State speeds localization; it does not get to assert correctness.

---

## Policy — `flow.*` config keys

The engine ships **no stack defaults**. Per-project defaults live in `planning/harness.json` under
the `flow` block. Every key has a CLI flag that overrides it for a single run.

| `flow` key | Type | CLI override | Default | Meaning |
|---|---|---|---|---|
| `autoMerge` | boolean | `--auto-merge` | `false` | Merge the PR and tear down the worktree on clean PASS (non-draft only). |
| `testDepth` | `"fast"` \| `"full"` | `--test-depth` | `"fast"` | Per-task validation depth. `fast` = gating checks only (tripwire); `full` = whole suite per task. |
| `prBase` | string | — | `"main"` | Base branch for `gh pr create`. |
| `bailReasons` | string[] | — | `[]` | Extra project-specific immediate-bail reasons appended to the universal five. |

**Universal bail reasons** (hardcoded — mechanism, not policy):

1. Missing/undefined upstream dependency or symbol the spec assumes exists.
2. Spec ambiguity/contradiction — intended behavior is genuinely undeterminable.
3. Environment/credential/auth/network failure (not a code defect).
4. Change would require a destructive or out-of-scope action.
5. Same failure twice with no progress (stuck), or a structural design flaw needing a re-plan.

Projects append project-specific reasons via `flow.bailReasons[]`. The triage agent's bias is
**when unsure, bail** — a wasted retry loop costs more than one human glance at a draft PR. See
[D32](../../planning/decisions/D32-triage-gated-bail.md).

---

## Model tiering

> Opus plans · Sonnet judges · Haiku does the mechanics.

| Tier | Stages | Why |
|---|---|---|
| **haiku** | setup, enumerate, state-load, update-task, test, state-writer | Fixed procedures — no judgment required |
| **sonnet** | implement, fix, triage, review, review-fix, docs, wrap-up, PR, merge | Judgment work — reading and writing code/prose |
| **opus (escalation)** | final per-task fix attempt, final review fix pass | Hard tasks that already failed; one strong shot before bail |
| **opus (planning fallback)** | `generate-tasks` if the spec is missing | Spec authoring — the leverage point |

To re-tier a stage, change one value in the `MODEL` map at the top of
`.claude/workflows/sdlc-flow.js`. Nothing else moves.

---

## Commit strategy

All commits land on the `<spec>-flow` branch. The PR body is built from the on-disk (uncommitted)
state. The state-writer and `update-task` no longer commit anything — see "Run-state model" above —
so there is no `chore: flow state` commit in this list.

| Commit | Agent | When |
|---|---|---|
| `chore: init worktree <branch>` | setup | Once, at branch creation — **`--worktree` mode only** (branch mode adds no init commit) |
| `feat: implement <stem> task N` | implement | Per task, attempt 1 |
| `fix: fix pass P for <stem> task N` | fix | Per task, fix attempt P |
| `docs: update docs for <spec>` | docs | After PASS verdict |
| `chore: wrap up <spec>` | wrap-up | Final commit before PR — vault-aware, see below |

---

## Vaulted planning directories (D46)

Under D46, a brain-vaulted sub-repo's `planning/` is a relative symlink into a brain-owned vault
repo (e.g. `planning -> ../_planning/<repo>`), not a real tracked directory. `git add planning/...`
against that path fails with `fatal: pathspec 'planning/...' is beyond a symbolic link` — git refuses
to stage through a symlink boundary. The rule this engine follows wherever it needs to persist a
tracked `planning/`-prefixed file (`planning/status.md`, `planning/state.json` at wrap-up):

- **Never** issue a `git add` (or `git commit`) whose pathspec begins with `planning/`.
- Resolve the symlink first — `fs.lstatSync('planning').isSymbolicLink()` +
  `fs.realpathSync('planning')` — to get the vault's real, absolute path.
- Stage and commit the vaulted files **through that real path**, via `git -C <vault> add <absolute
  path>` and `git -C <vault> commit`, on whatever branch the vault repo is already on.
- **Never** `git checkout`, `git switch`, or `git branch` inside the vault — the wrap-up prompt
  states this prohibition explicitly. The commit lands wherever the vault repo currently sits; the
  engine does not move it there.
- Repo-local files that are not behind the symlink (`log.md`, the spec file) keep committing
  normally, in the invoking repo, on the run's own branch — exactly as before.

When `planning/` is a real tracked directory (non-vaulted repo), none of the above applies and
everything commits together in one commit as it always has.

This is why an uncommitted working tree in a vaulted repo can still show untouched `planning/` bytes
after a run: those bytes were staged and committed in the vault repo, not here.

---

## Resumption

Pass `--resume` after an interruption. The engine re-attaches the existing branch (checks it out in
branch mode; re-attaches the worktree under `--worktree`), reads the on-disk (uncommitted, never
gitignored) `sdlc-flow-state.json`, and skips every task whose status is `passed`. Tasks whose status
is `running` or `failed` are retried from scratch. Resume in the same mode the run started in.

**`--resume` must be passed explicitly** — it is a flag inside `args`, not something the pipeline
infers from how it was invoked. This matters when re-launching via `Workflow({scriptPath,
resumeFromRunId})`: `resumeFromRunId` only replays cached prior `agent()` calls from the Workflow
tool's own journal — it has no effect on `sdlc-flow.js`'s own `resumeMode` flag. If an agent restarts
a failed/interrupted run without adding `--resume` to `args`, the engine has no way to know a prior
attempt exists from that alone.

As a backstop, **Setup refuses to silently start over**: if the exact `<spec>-flow` branch/worktree
name is already taken (evidence of a prior run) and `--resume` wasn't passed, setup aborts with an
explicit `setupError` telling the caller to add `--resume` — rather than quietly falling back to a
`-2` name and orphaning the earlier progress. Only a genuine name collision with something unrelated
still falls through to `-2`/`-3`/etc.

| State | On `--resume` |
|---|---|
| `state.json` absent | Runs all selected tasks fresh |
| Task N status `passed` | Skipped |
| Task N status `running` / `failed` | Retried from implement |
| `bail_reason` set | Logged; end-review proceeds immediately |
| `<spec>-flow` branch/worktree exists, `--resume` NOT passed | Setup aborts (`setupError`) instead of silently forking a `-2` run |

Because `state.json` is durably written to disk after every task/phase (even though it is never
committed), a forced kill never loses progress — the last successful task's state survives on disk
and is read back by `--resume` without depending on git history at all. Resume also re-seeds the
in-memory task history from that on-disk file before the per-task loop runs, so skipped
(already-passed) tasks stay in the record across multiple resumes instead of dropping out of
`state.json` on the next write.

---

## Which engine when

| Engine | Reach for it when |
|---|---|
| `/patch` | Trivial hotfix with no tests needed. |
| `/sdlc-task` | Small tested change — a `/chore` or `/ticket` spec. Fast implement → test → commit. |
| `/sdlc-run` | One task or a full spec on the current branch — no isolation or PR needed. |
| `/sdlc-flow` | **Default for non-trivial feature work** — sequential, conflict-free, terminates in a PR. |
| `/sdlc-block` | A whole roadmap — fans out one `/sdlc-flow` per independent block, branch train of PRs. |

---

## Token usage

| Stage | Model | Typical tokens |
|---|---|---|
| setup | haiku | _TBD_ |
| enumerate | haiku | _TBD_ |
| update-task (per task) | haiku | _TBD_ |
| implement (per task) | sonnet | _TBD_ |
| fast test (per task) | haiku | _TBD_ |
| triage (per failure) | sonnet | _TBD_ |
| fix (per pass) | sonnet | _TBD_ |
| end-review | sonnet | _TBD_ |
| docs | sonnet | _TBD_ |
| wrap-up | sonnet | _TBD_ |
| PR | sonnet | _TBD_ |
| **Full run (5 tasks, PASS first try)** | — | _TBD_ (~30–40 agents) |

Fill these cells from measured runs via the `tracedAgent` telemetry in each run's `worklog.md`.
Levers: a sharp spec + breakdown cuts implement tokens; clean first-try tests avoid the fix loop;
clean end-review avoids the review-fix loop.
