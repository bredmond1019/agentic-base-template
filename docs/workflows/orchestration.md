---
type: Guide
title: Orchestration lifecycle — driving a lane end to end
description: How to open, run and close one lane of a multi-repo roadmap — quickstart first, then the phase table, the mandatory artifacts, and the traps that have cost real runs.
doc_id: base-template-orchestration-guide
layer: [factory]
project: base-template
status: active
keywords: [orchestration, lane, begin-orchestration, lane-log, run record, commander]
related: [base-template-workflows-index, sdlc-task, sdlc-flow, D57-orchestration-run-artifact-contract, plan-lane-coordination]
---

# Orchestration lifecycle — driving a lane end to end

**One repo, one session, one chain of blocks from one roadmap.** That is a lane. This page is how
to run one.

- **Flag-level reference:** [`.claude/commands/README.md`](../../.claude/commands/README.md).
- **The layer underneath** (registry, leases, messages, commander):
  [`lane-coordination.md`](lane-coordination.md).
- **Where this page and a command file disagree, the command wins.**

---

## Quickstart

```bash
# 1. Open the lane. --roadmap is required and never inferred.
/begin-orchestration --roadmap planning/roadmaps/<slug>/roadmap.md --lane <name>

# 2. Read the dry-run it prints. Confirm, or fix the chain and re-run.

# 3. It hands off to /orchestrate, which drives every block.
```

That is the whole happy path. Everything below is what the dry run is telling you and what to do
when it is not happy.

**Before you run it, you need:** a roadmap at `planning/roadmaps/<slug>/roadmap.md`, and a lane
record at `<roadmap-dir>/lane-<name>.json` naming this repo in its `blocks[]`.

**No lane record?** Use `--blocks <id> <id> ...` instead and skip the file.

---

## The run at a glance

| # | Phase | Who acts | Detail |
|---|---|---|---|
| 1 | Resolve | command | [↓](#1-resolve) |
| 2 | Isolation | command | [↓](#2-isolation) |
| 3 | Concurrency | command | [↓](#3-concurrency) |
| 4 | Confirm | **you** | [↓](#4-confirm) |
| 5 | Per block ×N | agent | [↓](#5-per-block) |
| 6 | Lane close | agent | [↓](#6-lane-close) |

You are only in the loop at step 4 — and at any operator gate step 5 surfaces.

---

## 1. Resolve

Resolves in this order: `BRAIN_ROOT` → repo → roadmap → `run_record_dir` → chain.

- **Repo** comes from `state.json`; `--repo` overrides.
- **Roadmap** is never inferred. A missing `--roadmap` prints usage and stops.
- **`run_record_dir`** is `planning/orchestration-run/<roadmap-slug>/` in this repo.
- **Chain** is the lane record's `blocks[]` in array order, filtered to this repo — or `--blocks`
  verbatim.
- **Cross-check:** the lane record's own `roadmap` field must match the resolved roadmap. A
  mismatch stops the run.

## 2. Isolation

| Repo | Isolation | Why |
|---|---|---|
| `base-template` | **always `--worktree`** | A chain here edits the engines running it. |
| brain root (HQ) | **always `--no-worktree`** | A worktree's `brain.toml` mis-resolves the gitignored sub-repos. |
| everything else | `--no-worktree` | Opt into `--worktree` when a block deserves quarantine. |

**Re-verify before relying on this table.** It is a measurement, not policy, and it can go stale.

## 3. Concurrency

Heavy-gate repos (browser-automation, native-build) register a slot before the chain and release
it after — on success, failure, *or* abandonment.

```bash
python3 scripts/fleet_concurrency_check.py is-heavy --repo-path <repo>   # exit 0 = heavy
python3 scripts/fleet_concurrency_check.py register --repo <name> --category <cat>
python3 scripts/fleet_concurrency_check.py release  --repo <name>
```

Exit `3` on register means that category's pool is full. Wait, or run a cheap-gate block instead.
Cheap-gate repos skip this entirely.

## 4. Confirm

The dry run prints: repo · roadmap · lane record · chain order · isolation · per-block engine and
spec status · readiness against the live graph · operator gates · log path.

**Read the readiness and gate lines.** They are the two that stop a run later if ignored.
`--execute` skips this stop.

## 5. Per block

Per block, in order: **spec → engine → integrate → verify → report.**

1. **Spec** — resolve the block ID to a slug; run `/generate-tasks` (or `--from <plan>`) if
   `tasks.json` is missing. Since D65 the spec is `planning/blocks/<BlockID>.json` +
   `planning/<BlockID>/tasks.json`; `tasks.md` is a legacy fallback.
2. **Engine** — `/sdlc-task` or `/sdlc-flow`, as a background workflow. Spec prep for later blocks
   may overlap; **engine runs are strictly serial** — one repo, one engine at a time.
3. **Integrate** — merge/clean the worktree; resolve conflicts toward the incoming block's intent.
4. **Verify the state write** — engine status bookkeeping is known-unreliable. Check `state.json`
   and `status.md` yourself; do not trust the engine's report.
5. **Log** — one line to `<roadmap_dir>/lane-log.jsonl`, committed.
6. **Notes** — append to `notes.md`.

Repeat until the chain is done or stopped.

## 6. Lane close

- Write the terminal `review.md`.
- Promote every `OPEN` item in `notes.md` to a durable home. **Never copy it into a successor
  file** — D57 keeps one record per `(repo, roadmap)`, addressed rather than rotated.
- Release the repo lease and registry claim.
- Run `/close-out`.

---

## Artifacts

| Artifact | Scope | Written |
|---|---|---|
| `<roadmap_dir>/lane-log.jsonl` | **Cross-lane.** One line per block, append-only. Sibling lanes read this. | Per block |
| `planning/orchestration-run/<slug>/notes.md` | **Local.** Everything the log line can't carry: defects found in passing, decisions and why, traps re-confirmed. | Per block, append-only |
| `planning/orchestration-run/<slug>/review.md` | **Terminal.** Plain-English summary + hand-verification recipes. Every recipe must have been **run** before the file is written. | Once, at close |

Frontmatter, the `doc_id` rule, `lifecycle`, and the ledger's `origin_roadmap` column are specified
in `planning/decisions/D57-orchestration-run-artifact-contract.md`. Cited, not restated.

---

## Traps

- **A piped command's exit code is the pipe's.** `mev conformance | tail` reports success while
  `mev conformance` exits 1. Redirect to a file, then check `$?`.
- **`validate-brain`'s flags do not compose.** First flag wins (if/else-if chain). One per invocation.
- **Every `planning/` is a symlink.** `rg`/`find` need `-L`. **At the brain root also pass `-uu`** —
  every sub-repo is gitignored there, so `-L` alone reports a false clean over the whole fleet.
- **Command and engine files are launch-time snapshots.** Editing `.claude/commands/*.md` or
  `.claude/workflows/*.js` mid-session does not change what the running session executes. A re-run
  against a stale snapshot proves nothing.
- **A lane record reads as a chain but behaves as a queue of one.** Its value is the `depends_on`
  edges, not array order. Never start a `blocked` block — pull the next `open` one and say what the
  blocked one waits on.

---

## The commander

A **stateless drain**: one `bastion ask` turn that reads the queue and fleet state from disk, routes
what it finds, re-derives generated surfaces, commits what it can prove is derived, and reports the
rest. Context never grows — nothing carries between drains except what is on disk.

```bash
./scripts/commander_drain.sh [--repo NAME] [--lane NAME]
```

- Defaults: this repo's basename, and `main`.
- Knobs: `COMMANDER_DRAIN_TIMEOUT_SECS` (900, deliberately not `bastion ask`'s 180),
  `COMMANDER_LAUNCH_CMD` (Sonnet), `FLEET_LOCK_DIR`.
- **The one rule:** the commander **re-derives, it never detects.** It does not scan `git status`
  for files that look derived — it runs the derivation and commits exactly the paths reported back.
  Anything dirty outside that manifest is an authored orphan: reported, never committed.

**Nothing schedules it yet.** Kind-triggered drains need no scheduler (a lane sends `RENDEZVOUS` or
`LEASE_RELEASE` and drains at its block boundary), but the 20–30 minute heartbeat has no invoker —
cron on the Mac Mini is blocked behind `HQ.8.A`. Until then, a drain happens when someone runs the
wrapper.

Full procedure: [`.claude/commands/orchestration-commander.md`](../../.claude/commands/orchestration-commander.md).

---

## See also

- [`.claude/commands/README.md`](../../.claude/commands/README.md) — flag reference.
- [`lane-coordination.md`](lane-coordination.md) — registry, leases, messages, commander setup.
- [`index.md`](index.md) — the two SDLC engines this drives per block.
- `planning/decisions/D57-orchestration-run-artifact-contract.md` — the run-record contract.
- `planning/decisions/D43-cross-domain-priority-graph.md` — priority ordering at lane close.
