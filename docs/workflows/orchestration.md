---
type: Guide
title: Orchestration lifecycle — driving a lane end to end
description: How-to for opening, running and closing one lane of a multi-repo roadmap — the lane model, the phases from /begin-orchestration through the terminal review.md, the mandatory artifacts, and the traps that have cost real runs.
doc_id: base-template-orchestration-guide
layer: [factory]
project: base-template
status: active
keywords: [orchestration, lane, begin-orchestration, orchestrate, lane-log, notes.md, review.md, D57, D43, commander]
related: [base-template-workflows-index, sdlc-task, sdlc-flow, D57-orchestration-run-artifact-contract, plan-lane-coordination]
---

# Orchestration lifecycle — driving a lane end to end

A how-to for the piece of the pipeline the reference pages don't cover: what a **lane** is, which
command opens one, what order its phases run in, which artifacts are mandatory, and what to watch
for. For the flag-level reference on `/orchestrate` and `/begin-orchestration`, see
[`.claude/commands/README.md`](../../.claude/commands/README.md) — this page is the narrative,
that page is the lookup table. Where this page and a command file disagree, **the command wins**;
this page describes `.claude/commands/begin-orchestration.md` and `.claude/commands/orchestrate.md`
as they stand, not as remembered from an older reading.

---

## What a lane is

A **lane** is one repo, one session, one chain of blocks drawn from one roadmap. That's the whole
model — everything else follows from it.

- **One repo per session, one engine run at a time.** Both SDLC engines take the repo's branch or
  working tree; a lane never launches a second engine in the same repo before the first has
  completed and integrated (`orchestrate.md` standing rule 3).
- **Several repos run concurrently — as separate sessions.** That concurrency is the lane model:
  each lane is independent, and lanes interact only through cross-repo `depends_on` edges in
  `state.json`, never by sharing a working tree or a session.
- A lane runs one engine at a time per block — `/orchestrate` chooses `/sdlc-task` or `/sdlc-flow`
  per block, and every block in the chain runs strictly one after another.

---

## The phases, in order

### 1. Resolve

`/begin-orchestration --roadmap <path|slug> (--lane <name> | --blocks <id...>)` resolves, in order:
`BRAIN_ROOT` → the repo (from `state.json`, or `--repo`) → the roadmap (never inferred — a missing
`--roadmap` stops and prints usage) → `run_record_dir` (`planning/orchestration-run/<roadmap-
slug>/` in this repo) → the chain (the lane record's `blocks[]` in array order, filtered to this
repo, or the `--blocks` list verbatim). A lane record's top-level `roadmap` field is cross-checked
against the resolved roadmap; a mismatch stops the run rather than proceeding against the wrong
lane.

### 2. Isolation policy

`base-template` always runs `--worktree` (a chain here edits the engines that are running it); the
brain root (HQ) always runs `--no-worktree` (a worktree's own `brain.toml` resolves the gitignored
sub-repos incorrectly); every other repo defaults to `--no-worktree` and opts into `--worktree`
only when a block deserves quarantine. Re-verify the measurement behind this table before relying
on it — it is a measured fact, not policy handed down once, and it can go stale.

### 3. Concurrency registration

Heavy-gate repos (browser-automation, native-build) register a slot with
`scripts/fleet_concurrency_check.py` before the chain starts and release it when the chain ends —
success, failure, or abandonment. Cheap-gate repos skip this step.

### 4. Confirm

Print the resolved repo, roadmap, lane record, chain order, isolation, per-block engine/spec
status, readiness against the live graph, and any operator gates — then stop for confirmation
unless `--execute`. Before the first block launches, this step also claims the lane's identity in
the registry and takes the repo lease (both released at lane close).

### 5. Per block: spec → engine → integrate → verify → report

For each block in the resolved chain:

1. **Spec** — resolve the block ID to a spec slug and run `/generate-tasks` (or `--from <plan>`)
   if `tasks.json` is missing. Since D65 the spec is the block record at
   `planning/blocks/<BlockID>.json` plus `planning/<BlockID>/tasks.json`; `tasks.md` is a legacy
   path the engines still fall back to when no block record exists.
2. **Engine** — launch `/sdlc-task` or `/sdlc-flow` per `/generate-tasks`' recommendation, as a
   background workflow. Spec preparation for the next blocks overlaps the running engine; the
   engine runs themselves are strictly serial (one repo, one engine run at a time).
3. **Integrate** — merge/clean the worktree, resolve any merge conflict toward the incoming
   block's intent.
4. **Verify the state write** — the engines' status bookkeeping is known-unreliable; check
   `state.json`'s block status and `status.md` directly rather than
   trusting the engine's own report.
5. **One lane-log line** — append to `<roadmap_dir>/lane-log.jsonl` and commit it.
6. **Append to `notes.md`** — this repo's local record (see Artifacts below).

Repeat until the chain is done or stopped.

### 6. Lane close

- Write the terminal `review.md`.
- Promote any `notes.md` item still `OPEN` into a durable home — never copy it into a successor
  file (D57 keeps one record per `(repo, roadmap)` pair, addressed rather than rotated).
- Release the repo lease and registry claim.
- Close with a terminal `/close-out`.

---

## Artifacts

| Artifact | Scope | Written | Cite |
|---|---|---|---|
| `<roadmap_dir>/lane-log.jsonl` | **Cross-lane.** One line per integrated block, append-only — the channel sibling lanes read. | Per block | — |
| `planning/orchestration-run/<roadmap-slug>/notes.md` | **Local to this repo.** Everything the lane log's one line can't carry: defects found in passing, deferred fixes, decisions taken and why, traps re-confirmed. | Per block (append-only) | D57 |
| `planning/orchestration-run/<roadmap-slug>/review.md` | **Terminal.** A plain-English summary plus hand-verification recipes; every recipe must have been **executed** by this lane before the file is written. | Once, at lane close | D57 |

Frontmatter, the `doc_id` rule, `lifecycle`, and the ledger's `origin_roadmap` column are specified
once, in `planning/decisions/D57-orchestration-run-artifact-contract.md` — cited here as the
deciding authority, not restated.

---

## Traps

- **A piped command's exit code is the pipe's, not the command's** — `mev conformance | tail`
  reports success while `mev conformance` itself exits 1. Redirect to a file, then check `$?`.
- **`validate-brain`'s flags do not compose** — `main.rs` is an if/else-if chain, first flag wins.
  One invocation per flag, never combined.
- **Every `planning/` is a symlink into a `_planning/` vault** — `rg`/`find` are symlink-blind by
  default, so an exhaustive sweep needs `-L`. **At the brain root, also pass `-uu`** — every
  sub-repo is gitignored there, so `-L` alone still skips them all, and a sweep missing `-uu`
  reports a false clean over the whole fleet.
- **Command and engine files are launch-time snapshots** — editing `.claude/commands/*.md` or
  `.claude/workflows/*.js` mid-session does not change what the running session executes. A re-run
  against a stale snapshot proves nothing about a fix; verify the snapshot (or fix somewhere that
  takes effect immediately) before concluding an engine change did or didn't work.
- **A lane record reads as a chain but usually behaves as a queue of one** — its value is the
  `depends_on` edges, not the array order. Never start a block showing `blocked`; pull the next
  `open` block instead, and say plainly what it's waiting on.

---

## The commander

`BT.6.D` landed on 2026-08-22. The commander is a **stateless drain**: one `bastion ask` turn that
reads the queue and fleet state from disk, routes what it finds, re-derives the fleet's generated
surfaces and commits exactly what it can prove is derived, then reports the remainder. Its context
never grows, because nothing is carried between drains except what is on disk.

Run one by hand:

```bash
./scripts/commander_drain.sh [--repo NAME] [--lane NAME]
```

`--repo`/`--lane` default to this repo's basename and `main`. Knobs, all with defaults:
`COMMANDER_DRAIN_TIMEOUT_SECS` (900 — deliberately not `bastion ask`'s 180s default),
`COMMANDER_LAUNCH_CMD` (Sonnet), `FLEET_LOCK_DIR`.

**Nothing schedules it yet.** Kind-triggered drains need no scheduler — a lane sends `RENDEZVOUS`
or `LEASE_RELEASE` and drains at its own block boundary — but the 20–30 minute heartbeat has no
invoker, and cron on the Mac Mini is blocked behind `HQ.8.A`. Until then a drain happens when
someone runs the wrapper. The full procedure is
[`.claude/commands/orchestration-commander.md`](../../.claude/commands/orchestration-commander.md);
the design and what was deliberately cut are in
[`planning/lane-coordination/plan.md`](../../planning/lane-coordination/plan.md).

The one rule worth knowing before you run it: **the commander re-derives, it never detects.** It
does not scan `git status` for files that look derived — it runs the derivation and commits exactly
the paths that reports back. Anything dirty outside that manifest is an authored orphan: reported,
never committed.

---

## See also

- [`.claude/commands/README.md`](../../.claude/commands/README.md) — flag-level reference for
  `/orchestrate` and `/begin-orchestration`.
- [`workflows/index.md`](index.md) — the two SDLC engines this lifecycle drives per block.
- `planning/decisions/D57-orchestration-run-artifact-contract.md` — the run-record contract.
- `planning/decisions/D43-cross-domain-priority-graph.md` — priority ordering for lingering items
  at lane close.
