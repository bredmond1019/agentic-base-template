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

**New here? Read [`index.md`](index.md) first** — it has a diagram of the whole system and a
vocabulary table. This page assumes those words.

## What this page is for

You have a roadmap: a chunk of work spread across several repos. You want the agents to build it.

**A "lane" is how one repo's share of that work gets done.** One repo, one Claude Code session, one
ordered list of blocks. You open a lane per repo, and they run at the same time in separate
sessions.

This page walks through opening a lane, what happens while it runs, and how it closes. It is a
how-to, not a reference — for every flag and argument see
[`.claude/commands/README.md`](../../.claude/commands/README.md).

**If a command file and this page disagree, believe the command file.** It is what actually runs.

## Quickstart

Open a terminal, `cd` into the repo you want the work done in, start Claude Code, and type:

```
/begin-orchestration --roadmap planning/roadmaps/<slug>/roadmap.md --lane <name>
```

That is a **slash command** — you type it into the Claude Code prompt, not into your shell.

It prints a plan and stops. Read it, say go, and it drives every block to completion.

**You need two files to exist first:**

| File | What it is | If it's missing |
|---|---|---|
| `planning/roadmaps/<slug>/roadmap.md` | The roadmap | Nothing to run. Make one with `/generate-roadmap`. |
| `<roadmap-dir>/lane-<name>.json` | This repo's list of blocks | Skip it — pass `--blocks <id> <id> …` instead. |

**`--roadmap` is required and never guessed.** Leave it off and the command prints usage and stops,
on purpose: a lane driven against the wrong roadmap is the hardest mistake here to notice.

---

## The run at a glance

Six phases. You only act in one of them.

| # | Phase | In plain English | Who acts | Detail |
|---|---|---|---|---|
| 1 | Resolve | Work out which repo, which roadmap, and which blocks | command | [↓](#1-resolve) |
| 2 | Isolation | Decide whether to work in a separate copy of the repo | command | [↓](#2-isolation) |
| 3 | Concurrency | Take a slot, so too many expensive lanes don't run at once | command | [↓](#3-concurrency) |
| 4 | Confirm | **Show you the plan and wait** | **you** | [↓](#4-confirm) |
| 5 | Per block ×N | Build each block, one at a time | agent | [↓](#5-per-block) |
| 6 | Lane close | Write the summary, release the locks, tidy up | agent | [↓](#6-lane-close) |

After step 4 it runs on its own until it finishes — or until it hits something only you can decide
(an **operator gate**), which it will stop and tell you about.

---

## 1. Resolve

Before doing anything, the command figures out where it is and what it was asked to do. Nothing is
built in this phase — it is working out the plan it will show you in step 4.

It resolves in this order: `BRAIN_ROOT` → repo → roadmap → `run_record_dir` → chain.

- **Repo** comes from `state.json`; `--repo` overrides.
- **Roadmap** is never inferred. A missing `--roadmap` prints usage and stops.
- **`run_record_dir`** is `planning/orchestration-run/<roadmap-slug>/` in this repo.
- **Chain** is the lane record's `blocks[]` in array order, filtered to this repo — or `--blocks`
  verbatim.
- **Cross-check:** the lane record's own `roadmap` field must match the resolved roadmap. A
  mismatch stops the run.

## 2. Isolation

Some work is safe to do directly in your repo folder. Some is not — if a lane edits the very files
that are running it, it can pull the rug out from under itself. A **worktree** is a second copy of
the repo in a separate folder, used to keep that work quarantined.

The choice is made for you:

| Repo | Isolation | Why |
|---|---|---|
| `base-template` | **always `--worktree`** | A chain here edits the engines running it. |
| brain root (HQ) | **always `--no-worktree`** | A worktree's `brain.toml` mis-resolves the gitignored sub-repos. |
| everything else | `--no-worktree` | Opt into `--worktree` when a block deserves quarantine. |

**Re-verify before relying on this table.** It is a measurement, not policy, and it can go stale.

## 3. Concurrency

Some repos are expensive to test — they launch browsers, or compile Rust from scratch. Running
several of those at once will bury the machine. So those repos take a **slot** before starting and
give it back when done, like a parking space.

Repos with cheap tests skip this entirely and just start.

Heavy repos (browser-automation, native-build) register a slot before the chain and release
it after — on success, failure, *or* abandonment.

```bash
python3 scripts/fleet_concurrency_check.py is-heavy --repo-path <repo>   # exit 0 = heavy
python3 scripts/fleet_concurrency_check.py register --repo <name> --category <cat>
python3 scripts/fleet_concurrency_check.py release  --repo <name>
```

Exit `3` on register means that category's pool is full. Wait, or run a cheap-gate block instead.
Cheap-gate repos skip this entirely.

## 4. Confirm

**This is your step.** The command stops here and prints the plan it just worked out. Nothing has
been built yet, and nothing will be until you say go.

It prints: repo · roadmap · lane record · chain order · isolation · per-block engine and
spec status · readiness against the live graph · operator gates · log path.

**Read the readiness and gate lines.** They are the two that stop a run later if ignored.
`--execute` skips this stop.

## 5. Per block

Now it builds. Each block goes through the same five moves before the next one starts.

**spec → engine → integrate → verify → report**

- **Spec** — write down exactly what to build.
- **Engine** — the automation that writes the code.
- **Integrate** — merge that work back into the main branch.
- **Verify** — check the bookkeeping is actually right.
- **Report** — leave a record for other lanes and for you.

In detail:

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

When the chain is finished, the lane tidies up after itself. This matters more than it sounds: an
unreleased lock blocks the next lane, and an unrecorded loose end is simply lost.

- Write the final `review.md` — a plain-English summary plus the checks you could run by hand.
- Promote every `OPEN` item in `notes.md` to a durable home. **Never copy it into a successor
  file** — D57 keeps one record per `(repo, roadmap)`, addressed rather than rotated.
- Release the repo lease and registry claim.
- Run `/close-out`.

---

## Artifacts

A lane leaves three files behind. They have different jobs, and the difference matters — the first
is how *other lanes* find out what happened, the second and third are for *you*.

| Artifact | Scope | Written |
|---|---|---|
| `<roadmap_dir>/lane-log.jsonl` | **Cross-lane.** One line per block, append-only. Sibling lanes read this. | Per block |
| `planning/orchestration-run/<slug>/notes.md` | **Local.** Everything the log line can't carry: defects found in passing, decisions and why, traps re-confirmed. | Per block, append-only |
| `planning/orchestration-run/<slug>/review.md` | **Terminal.** Plain-English summary + hand-verification recipes. Every recipe must have been **run** before the file is written. | Once, at close |

Frontmatter, the `doc_id` rule, `lifecycle`, and the ledger's `origin_roadmap` column are specified
in `planning/decisions/D57-orchestration-run-artifact-contract.md`. Cited, not restated.

---

## Traps

Things that have genuinely cost real runs. Each one produces a *confident wrong answer* rather than
an error, which is why they are worth knowing in advance.

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

**What it is:** lanes leave each other messages and leave generated files out of date. Something has
to read that pile, act on it, and tell you what is left. That is the commander. One pass over the
pile is called a **drain**.

**There are two ways to run one, and the first is probably the one you want:**

| | How | When to use it |
|---|---|---|
| **Interactive** | Type `/orchestration-commander` in a Claude Code session | You are at the keyboard and want to see what it finds. No setup, no arguments. |
| **Unattended** | `./scripts/commander_drain.sh [--repo NAME] [--lane NAME]` | Cron, or scripting it. It wraps the same slash command and stamps a heartbeat file so you can tell drains have stopped happening. |

They run the same instructions — the script literally reads
[`.claude/commands/orchestration-commander.md`](../../.claude/commands/orchestration-commander.md)
and feeds it to a Claude turn via `bastion ask`. **The slash command is not a second implementation
to keep in sync; it is the original.**

> **The script always writes to the real shared lock directory.** It has no dry-run mode, and
> `FLEET_LOCK_DIR` will not redirect it. If you just want to look, use the slash command.

**Knobs on the script**, all optional: `COMMANDER_DRAIN_TIMEOUT_SECS` (900 — deliberately not
`bastion ask`'s 180s default, because a drain reads a lot), `COMMANDER_LAUNCH_CMD` (which model),
`FLEET_LOCK_DIR`.

**The one rule worth understanding before you run it: the commander re-derives, it never detects.**
Plenty of files in this system are generated rather than hand-written. A naive tool would look at
which files changed and guess which of those were generated. The commander refuses to guess — it
re-runs the generator and commits exactly the files the generator says it wrote. Anything else
that is dirty is treated as something a *human* wrote, and it gets reported to you rather than
committed. **If a drain reports an "authored orphan", that is it working correctly.**

**Nothing runs drains on a schedule yet.** Some messages trigger a drain on their own (a lane
sending `RENDEZVOUS` or `LEASE_RELEASE`), but the every-20-minutes heartbeat has no invoker — cron
on the Mac Mini is blocked behind `HQ.8.A`. Until that lands, a drain happens when you run one.

---

## See also

- [`.claude/commands/README.md`](../../.claude/commands/README.md) — flag reference.
- [`lane-coordination.md`](lane-coordination.md) — registry, leases, messages, commander setup.
- [`index.md`](index.md) — the two SDLC engines this drives per block.
- `planning/decisions/D57-orchestration-run-artifact-contract.md` — the run-record contract.
- `planning/decisions/D43-cross-domain-priority-graph.md` — priority ordering at lane close.
