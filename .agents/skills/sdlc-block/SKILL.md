---
name: sdlc-block
description: >
  >
---

=============================================================================
 sdlc-block — Block-level roadmap orchestrator (a branch train of /sdlc-flow runs)
 =============================================================================

 Drives a whole ROADMAP (a master-plan-format file) to completion by fanning out ONE /sdlc-flow per
 independent BLOCK over dependency-ordered waves, producing a branch train of reviewable PRs. This
 REPLACES the legacy task-level wave machine (which ran task-level waves WITHIN a single spec and
 "almost always hit an inter-task merge conflict", D30): blocks in a wave are independent BY
 CONSTRUCTION (the master-plan's per-block Files + Out-of-scope contract), and the proven /sdlc-flow
 engine — one shared worktree, per-task test→fix loop, one end review, a PR — is the inner unit.

 USAGE
   /sdlc-block                              orchestrate planning/master-plan.md (every block)
   /sdlc-block <plan-file>                  orchestrate a /plan output (planning/plan-<slug>/plan.md)
   /sdlc-block <plan-file> --blocks 0-1     scope to a phase/wave selection (see --blocks)
   /sdlc-block --auto-merge                 merge each block into the base in dependency order
   /sdlc-block --no-pr                      produce the branch train only (no PRs)
   /sdlc-block --base develop               branch/merge against a base other than main
   /sdlc-block --resume                     re-read block-orchestration-state.json and continue

   ARGS
     [planFileOrSlug]        optional 1st positional — a path to a master-plan-format file, OR a slug
                             resolved to planning/<slug>/plan.md. Default: planning/master-plan.md.
     --base <branch>         the base branch the train forks from / merges into (default: main).
     --auto-merge            merge each completed block branch into <base> in dependency order
                             (resolving conflicts); the train IS the base. Default off.
     --no-pr                 child flows produce branches only — no PRs anywhere.
     --max-parallel-blocks N max /sdlc-flow runs in flight per wave (default 3).
     --blocks <sel>          phase selection (e.g. 0, 0-1, 0,2) — only those phases' blocks run.
     --resume                load block-orchestration-state.json, skip done blocks, continue.

 MODEL
   sonnet : pre-flight, enumerate-blocks, merge, report   |   opus : per-block generate-tasks (planning)
   haiku  : state-writer   |   the inner /sdlc-flow carries its OWN model tiering per stage.

 BRANCH TRAIN
   The orchestrator keeps a "train" branch checked out at the MAIN repo root; every wave's child
   /sdlc-flow worktrees fork off it (sdlc-flow's worktree-setup branches off HEAD), so a Phase-N block
   sees the Phase-0..N-1 work its dependencies produced. After a wave, each successful block branch is
   merged into the train in dependency order; the next wave forks off the advanced train.
     - default  : train = `<planSlug>-train` (off <base>); each child flow opens its OWN PR (PR per
                  block); the orchestrator records merge_order for /merge-train; <base> is untouched.
     - --auto-merge : train = <base>; each block branch is merged straight into <base> in dependency
                  order as waves complete (no PRs).
     - --no-pr  : train = `<planSlug>-train`; branches only, no PRs.

   PR-base caveat (default mode): /sdlc-flow PRs target its own prBase (planning/harness.json
   flow.prBase, default main) — there is no per-PR base override (that would require changing
   sdlc-flow, out of scope here). A Phase-N block forked off the advanced train therefore opens a
   "fat" PR whose diff includes its ancestors' work. /merge-train (Phase 1 B) merges the train
   bottom-up in recorded dependency order, which is the intended review→merge path.

 STATE (committed authoritative index — block-orchestration-state.json under planning/<planSlug>/sdlc/)
   Per-block status + branch + PR + verdict + the child flow's token total, plus a TWO-LEVEL token
   roll-up: this engine's own orchestration stages + each child /sdlc-flow's tokens.total. Written by
   a cheap Haiku state-writer after each wave (the committed child commits/PRs remain the authoritative
   resume signal; state is the at-a-glance index + review artifact).

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
2. **Enumerate**: parse the plan's `## Phase N` sections into blocks + a dependency graph (explicit
   `- **Depends on:**` lines plus the phase-sequential default), then compute block-level waves in
   code. Blocks are headed either by the canonical `### <Prefix>.<PhaseNumber>.<BlockLetter>` id (no
   "Block" word) or the legacy `### Block X` form; the canonical id (constructed from the repo's
   `brain.toml` prefix for a legacy heading) is used to sync each block's authored status in
   `planning/state.json`, when the repo has one — `open` → `in_progress` at wave start, → `closed` on
   an `--auto-merge` landing.
3. **Per wave**: ensure each block has a committed `planning/<slug>/tasks.md` (generate it from the
   block's plan section if missing), then fan out one `/sdlc-flow <slug> --no-pr` per block, up to the
   parallel cap.
4. **Gap-check + PR/merge**: for each passed block, run the close-out gap-check in its worktree
   (diffing the whole block against the train); in PR mode open its PR, otherwise leave the branch for
   the merge step. Merge passed block branches into the train in dependency order.
5. **Report + final close-out**: write `block-orchestration.md` + the committed state, then run
   `/close-out --gap-check-only` over the full train branch. Surface PRs, merge order, and escalations.








