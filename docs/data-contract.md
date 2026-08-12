---
type: Reference
title: "SDLC run-state data contract — terminal status vocabulary"
description: The complete, enumerable vocabulary of terminal `status` values the SDLC engines write into their committed run-state files, and what a Rust/Python consumer must and must not fold each value into.
doc_id: sdlc-run-state-data-contract
layer: [factory]
project: base-template
status: active
keywords: [data contract, run-state, status vocabulary, reconcile_failed, sdlc-task-state, sdlc-flow-state, block-orchestration-state, consumers]
related: [sdlc-task, D56-sdlc-task-authoritative-reconcile]
---

# SDLC run-state data contract — terminal status vocabulary

This is the **pinnable** contract for the top-level `status` field the SDLC engines write into
their committed run-state JSON files. It exists because D56 introduced a new terminal status
(`reconcile_failed`) and stated, only in its Consequences prose, that downstream readers must
treat it as distinct — and nothing could actually depend on that sentence. This page is the
enumerable replacement: a consumer (Rust or Python) reads this table, not a paragraph in an ADR.

**Where the canonical copy lives.** This file, `docs/data-contract.md` in `base-template`, is the
one canonical copy. `scripts/sync_downstream_harness.py` propagates only `.claude/commands/*.md`
and `.claude/workflows/` to downstream repos (verified against the script's own file-selection
logic as of this writing) — **this page does not sync anywhere**. A consumer living in another
repo (`core/mev`, `core/bastion`, or any future one) must either read this file directly from the
`base-template` checkout at a known relative path, or hard-code the vocabulary below at the point
of consumption and note in a comment that it is pinned against this doc — there is no third
mechanism that keeps a downstream copy fresh automatically. If a machine-readable form (e.g. a
JSON schema or enum file consumers can literally `import`) is ever needed instead of a doc table,
it would need its own sync path added to `sync_downstream_harness.py` first; none exists today, so
none is claimed here.

## Run-state files and their `status` field

Three engines write a committed top-level `status` field to a run-state file. (`sdlc-run.js` does
not write its own top-level run-state `status` field — it sequences stages of the other engines
and defers to their state files.)

| Engine | State file | Written under |
|---|---|---|
| `.claude/workflows/sdlc-task.js` | `sdlc-task-state.json` | `planning/<spec>/sdlc/` |
| `.claude/workflows/sdlc-flow.js` | `sdlc-flow-state.json` | `planning/<spec>/sdlc/` |
| `.claude/workflows/sdlc-block.js` | `block-orchestration-state.json` | `planning/<spec>/sdlc/` |

## Terminal vocabulary

A value is **terminal** if it is the `status` an engine's state file is left holding once the run
stops advancing (not a mid-run phase marker such as `"running"`, `"review"`, `"docs"`,
`"wrapup"`, or `sdlc-block.js`'s transient `"paused-budget"`, which is always overwritten by
`"done"`/`"blocked"` before the run actually stops — see `sdlc-block.js` around the Report phase,
where `allClean` folds `state.status !== 'paused-budget'` into its check before the final
assignment).

| Value | Written by | Means success? | A consumer must NOT fold this into |
|---|---|---|---|
| `"done"` | `sdlc-task.js`, `sdlc-flow.js`, `sdlc-block.js` | **Yes.** The run completed and its terminal gate (where one exists) passed. | — |
| `"blocked"` | `sdlc-task.js`, `sdlc-flow.js`, `sdlc-block.js` | **No.** A task/block bailed (exhausted its fix-attempt budget) or an orchestrated block escalated. | `"done"` — a bail is not a completion. |
| `"reconcile_failed"` | `sdlc-task.js` only | **No — and not a bail either.** The per-task fix loop finished and every task individually passed, but the terminal authoritative reconcile (D56) — the one point where checks a per-task `fastCommand` substituted for, or a `perTask: false` check skipped entirely, run in their real form — failed. Bookkeep is skipped entirely: `tasks.md` is not marked done, the `status.md` Progress row is not flipped, and `planning/state.json`'s block status is not flipped to `"closed"`. Per-task commits already made are **not** reverted. | `"done"` (the gate did not pass) **and** ordinary `"blocked"` (there is no single task to attribute the failure to, and no per-task attempt budget was spent retrying it — see D56). This is the category most status enums do not have: *the work finished and the gate did not pass.* Collapsing it into either neighbor is the exact failure this contract exists to prevent. |

That is the complete set as of this writing — grep `state.status = ` (and the block engine's
final assignment) across `.claude/workflows/sdlc-task.js`, `sdlc-flow.js`, and `sdlc-block.js` to
reproduce it; any future engine change that adds a fourth terminal value must add a row here in
the same change (this doc is the "not just a sentence" surface D56's follow-up was missing).

## Practical guidance for a consumer

- **`emit-state` / block-graph consumers** (e.g. `core/mev`): a block whose most recent run's
  `status` is `"reconcile_failed"` must be reported as **not closed** (same open/in-progress
  treatment as an unfinished run) but should be distinguishable in any status text or exit
  reasoning from an ordinary in-progress or `"blocked"` run — the work is done, only the gate
  failed.
- **Status/serve surfaces** (e.g. `core/bastion`): a dashboard or `/status`-style view reading
  this field must render `"reconcile_failed"` as its own state, not silently show it identically
  to `"done"` (the run looks finished at a glance) or identically to `"blocked"` (the run looks
  like ordinary in-progress work, hiding that a terminal gate is the specific thing that failed).

## See also

- [`docs/workflows/sdlc-task.md`](workflows/sdlc-task.md) — the reconcile mechanism itself (why it
  exists, its cost, the recovery path); points here for the vocabulary rather than restating it.
- [D56](../planning/decisions/D56-sdlc-task-authoritative-reconcile.md) — the design rationale for
  the terminal reconcile and the original (prose-only) statement of this follow-up.
