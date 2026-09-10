---
type: Reference
title: sdlc-state status vocabulary
description: The closed, gated enum of status values sdlc-task-state.json and sdlc-flow-state.json's top-level `status` field may carry, and the mapping from each terminal sdlc-state status to the state.json block status it should produce.
doc_id: sdlc-state-vocabulary
layer: [factory]
project: base-template
status: active
keywords: [sdlc-state, status vocabulary, sdlc-task, sdlc-flow, state.json, gate, D86]
related: [base-template-workflows-index, sdlc-task, sdlc-flow, D86-sdlc-state-status-is-a-closed-enforced-vocabulary]
---

# sdlc-state status vocabulary

`state.json` block status is already a closed, gated enum — `mev`'s `VALID_TRACK_BLOCK_STATUSES`,
enforced by `mev set-block-status` at write time and `validate-brain` at commit/push time. The
`status` field on the engines' own committed run state (`sdlc-task-state.json` /
`sdlc-flow-state.json`) had no such enforcement — a fleet audit (2026-09-10) found `completed`
hand-written in several repos' planning folders even though neither current engine emits it, a
dead/legacy value nothing had ever caught. This page is the documented vocabulary; the machine copy
is [`sdlc-state-vocab.json`](../../.claude/workflows/sdlc-state-vocab.json), read by
[`scripts/check_sdlc_state_vocab.py`](../../scripts/check_sdlc_state_vocab.py) to gate every
`sdlc-*-state.json` reachable from `planning/`.

## The ten values

There are two families on the top-level `status` field: the run-level status written on
`sdlc-task-state.json` / `sdlc-flow-state.json` itself, and the per-task status written into that
same file's `tasks["<N>"].status`. Both live in one enum because both are values the `status` key
can hold somewhere in the file.

| Value | Meaning | Emitted by |
|---|---|---|
| `running` | The engine has started this run and is actively working through tasks — the initial status written when state is first created. | `sdlc-task`, `sdlc-flow` |
| `passed` | A single task's implement→test loop finished clean. **Per-task status**, not the top-level run status. | `sdlc-task`, `sdlc-flow` |
| `failed` | A single task's implement→test loop did not finish clean after its retry budget. **Per-task status**, not the top-level run status. | `sdlc-task`, `sdlc-flow` |
| `blocked` | The run bailed before reaching a terminal outcome — a task failed and triage judged it stuck, or another stop condition fired. Top-level run status. | `sdlc-task`, `sdlc-flow` |
| `done` | The run completed cleanly: every task passed, and (`sdlc-task` only) the terminal reconcile and acceptance-criteria verdict did not refuse the close. Top-level run status. | `sdlc-task`, `sdlc-flow` |
| `criteria_refused` | `sdlc-task` only. Every task passed and reconcile succeeded, but the acceptance-criteria verdict stage refused a clean close — replaces a would-be `done`. | `sdlc-task` |
| `reconcile_failed` | `sdlc-task` only. Every task passed its own fast per-task tripwire, but the terminal authoritative reconcile (D56) — re-running checks the fast path had substituted or skipped — failed. | `sdlc-task` |
| `review` | `sdlc-flow` only. The task loop is finished and the run is in the end-of-flow review stage over the integrated tree. | `sdlc-flow` |
| `docs` | `sdlc-flow` only. Review passed and the run is now in the documentation-patch stage. | `sdlc-flow` |
| `wrapup` | `sdlc-flow` only. Docs are patched and the run is in its final wrap-up/PR stage. | `sdlc-flow` |

## Terminal status → state.json block status mapping

Only a **terminal** run status (one that ends the run) ever has an opinion about `state.json`'s
block status. `running`, `review`, `docs`, and `wrapup` are all mid-run markers — none of them is
terminal, so none of them appears below. `passed`/`failed` are per-task, not run-level, so they are
also out of scope for this table.

| Terminal sdlc-state status | state.json block status | Why |
|---|---|---|
| `done` | → `closed` | The run finished cleanly; this is the only sdlc-state status that closes a block. |
| `blocked` | *(no forced transition — stays whatever `state.json` already said)* | A bail is a stop, not a verdict on the block; it neither closes nor reopens anything. |
| `criteria_refused` | *(stays `open`/`in_progress`, not `closed`)* | The run explicitly refused to call the work clean; forcing `closed` here would launder a refused verdict into a false "done". |
| `reconcile_failed` | *(stays `open`/`in_progress`, not `closed`)* | Same shape as `criteria_refused` — the authoritative re-check failed, so the block is not reported done. |

## Related

- [`sdlc-state-vocab.json`](../../.claude/workflows/sdlc-state-vocab.json) — the machine-readable
  enum this page documents in prose.
- [`scripts/check_sdlc_state_vocab.py`](../../scripts/check_sdlc_state_vocab.py) — the gate that
  enforces it against every `sdlc-*-state.json` under `planning/`.
- [sdlc-task.md](sdlc-task.md), [sdlc-flow.md](sdlc-flow.md) — the two engines that emit these
  values.
- [index.md](index.md) — the workflows reference hub.
