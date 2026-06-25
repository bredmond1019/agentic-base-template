---
name: sdlc-block
description: >
  Trigger on '/sdlc-block' or requests to orchestrate a whole master-plan roadmap as a branch train: one /sdlc-flow per independent block, in dependency-ordered waves, each block a reviewable PR.
---

=============================================================================
sdlc-block — Block-level roadmap orchestrator (a branch train of /sdlc-flow runs)
=============================================================================

Drives a whole ROADMAP (a master-plan-format file) to completion by fanning out ONE /sdlc-flow per
independent BLOCK over dependency-ordered waves, producing a branch train of reviewable PRs. This
REPLACES the legacy task-level wave machine: blocks in a wave are independent BY CONSTRUCTION (the
master-plan's per-block Files + Out-of-scope contract), and the proven /sdlc-flow engine — one shared
worktree, per-task test→fix loop, one end review, a PR — is the inner unit.

USAGE
  /sdlc-block                              orchestrate planning/master-plan.md (every block)
  /sdlc-block <plan-file>                  orchestrate a /plan output (planning/plan-<slug>/plan.md)
  /sdlc-block <plan-file> --blocks 0-1     scope to a phase/wave selection
  /sdlc-block --auto-merge                 merge each block into the base in dependency order (no PRs)
  /sdlc-block --no-pr                      produce the branch train only (no PRs)
  /sdlc-block --base develop               branch/merge against a base other than main
  /sdlc-block --resume                     re-read block-orchestration-state.json and continue

  ARGS
    [planFileOrSlug]        optional 1st positional — a path to a master-plan-format file, OR a slug
                            resolved to planning/<slug>/plan.md. Default: planning/master-plan.md.
    --base <branch>         the base branch the train forks from / merges into (default: main).
    --auto-merge            merge each completed block branch into <base> in dependency order; no PRs.
    --no-pr                 child flows produce branches only — no PRs anywhere.
    --max-parallel-blocks N max /sdlc-flow runs in flight per wave (default 3; harness.json
                            block.maxParallelBlocks supplies the default when the flag is absent).
    --blocks <sel>          phase selection (e.g. 0, 0-1, 0,2) — only those phases' blocks run.
    --resume                load block-orchestration-state.json, skip done blocks, continue.

MODEL
  sonnet : pre-flight, enumerate-blocks, merge, report   |   opus : per-block generate-tasks (planning)
  haiku  : state-writer   |   the inner /sdlc-flow carries its OWN model tiering per stage.

BRANCH TRAIN
  The orchestrator keeps a "train" branch checked out at the MAIN repo root; every wave's child
  /sdlc-flow worktrees fork off it, so a Phase-N block sees the Phase-0..N-1 work its dependencies
  produced. After a wave, each successful block branch is merged into the train in dependency order;
  the next wave forks off the advanced train.
    - default     : train = `<planSlug>-train` (off <base>); each child flow's branch gets its OWN PR
                    (opened by the orchestrator after a per-block gap-check); merge_order recorded for
                    /merge-train; <base> is untouched.
    - --auto-merge : train = <base>; each block branch is gap-checked, then merged straight into
                    <base> in dependency order as waves complete (no PRs).
    - --no-pr     : train = `<planSlug>-train`; branches only, no PRs.

  Each child /sdlc-flow is invoked with --no-pr so the orchestrator can run a per-block close-out
  gap-check (validation suite + coverage scan + docs patch, scoped to `<train>...HEAD` — the whole
  block) BEFORE opening the PR (default mode) or merging (auto-merge). A final /close-out
  --gap-check-only runs over the full train branch after the report.

STATE (committed authoritative index — block-orchestration-state.json under planning/<planSlug>/sdlc/)
  Per-block status + branch + PR + verdict + the child flow's token total, plus a TWO-LEVEL token
  roll-up: this engine's own orchestration stages + each child /sdlc-flow's tokens.total. Written by a
  cheap Haiku state-writer after each wave. Keys consumed by /review-PR + /merge-train: base_branch,
  train_branch, merge_order, blocks{slug:{status,branch,pr,verdict}}, mode.

RESUMPTION
  Re-run with --resume: the orchestrator re-reads block-orchestration-state.json, skips blocks already
  'done'/'merged', and continues from the first incomplete wave. Escalated blocks (a child flow bailed
  or a merge conflicted) poison their dependent subtree for that run; fix the blocker and re-run.

  Validation is downstream only (e.g. bella) — never run an SDLC workflow against base-template.

=============================================================================


## Antigravity Execution Guide

When the user asks you to run `/sdlc-block [plan-file] [flags]`, perform the roadmap orchestration:

1. **Pre-flight**: ensure the main tree is clean and the plan file is committed; check out (or create)
   the train branch off the base.
2. **Enumerate**: parse the plan's `## Phase N` / `### Block X` sections into blocks + a dependency
   graph (explicit `- **Depends on:**` lines plus the phase-sequential default), then compute
   block-level waves in code.
3. **Per wave**: ensure each block has a committed `planning/<slug>/tasks.md` (generate it from the
   block's plan section if missing), then fan out one `/sdlc-flow <slug> --no-pr` per block, up to the
   parallel cap.
4. **Gap-check + PR/merge**: for each passed block, run the close-out gap-check in its worktree
   (diffing the whole block against the train); in PR mode open its PR, otherwise leave the branch for
   the merge step. Merge passed block branches into the train in dependency order.
5. **Report + final close-out**: write `block-orchestration.md` + the committed state, then run
   `/close-out --gap-check-only` over the full train branch. Surface PRs, merge order, and escalations.
