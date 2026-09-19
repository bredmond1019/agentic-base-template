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
| `running` | The engine has started this run and is actively working through tasks — the initial status written when state is first created. **Also a per-task status** (`tasks["<N>"].status`): a "started" marker the implement agent writes as its own turn's first step, before reading, editing, or committing anything for that task — `tasks["<N>"].start_sha` (HEAD short sha at that moment) and `.marker_at` (UTC ISO timestamp) are written alongside it. The marker is written only on a task's first implement attempt with no `start_sha` recorded yet; a fix attempt never re-stamps it, and a task resumed while already at `running` keeps its original `start_sha`. The happy path fully supersedes the marker with the task's real terminal status (`passed`/`failed`) once it finishes — see "A task stuck at `running`" below. | `sdlc-task`, `sdlc-flow` |
| `passed` | A single task's implement→test loop finished clean. **Per-task status**, not the top-level run status. | `sdlc-task`, `sdlc-flow` |
| `failed` | A single task's implement→test loop did not finish clean after its retry budget. **Per-task status**, not the top-level run status. | `sdlc-task`, `sdlc-flow` |
| `blocked` | The run bailed before reaching a terminal outcome — a task failed and triage judged it stuck, or another stop condition fired. Top-level run status. | `sdlc-task`, `sdlc-flow` |
| `done` | The run completed cleanly: every task passed, and (`sdlc-task` only) the terminal reconcile and acceptance-criteria verdict did not refuse the close. Top-level run status. | `sdlc-task`, `sdlc-flow` |
| `criteria_refused` | `sdlc-task` only. Every task passed and reconcile succeeded, but the acceptance-criteria verdict stage refused a clean close — replaces a would-be `done`. | `sdlc-task` |
| `reconcile_failed` | `sdlc-task` only. Every task passed its own fast per-task tripwire, but the terminal authoritative reconcile (D56) — re-running checks the fast path had substituted or skipped — failed. | `sdlc-task` |
| `review` | `sdlc-flow` only. The task loop is finished and the run is in the end-of-flow review stage over the integrated tree. | `sdlc-flow` |
| `docs` | `sdlc-flow` only. Review passed and the run is now in the documentation-patch stage. | `sdlc-flow` |
| `wrapup` | `sdlc-flow` only. Docs are patched and the run is in its final wrap-up/PR stage. | `sdlc-flow` |

## Verdict vocabularies (not `status` values)

`sdlc-state-vocab.json` also carries a sibling `verdicts` container for the failure-attribution
decision, keyed separately from the ten `status` values above so `load_vocab()`'s status-enum check
never treats them as valid `status` strings:

| Vocabulary | Values | Meaning |
|---|---|---|
| `verdicts.ownership` | `self`, `foreign` | Whether a failing check was introduced by this run (`self`, ordinary fix loop) or was already red at `base_sha` per the gate cache (`foreign`, carried without burning an attempt). |
| `verdicts.failure_class` | `fixable`, `escalate` | Whether an attributed failure is routed into a fix loop (`fixable`) or is a hard stop — in-spec debt never fixed by the task that declared it (`escalate`). |

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

## A task stuck at `running`

If a run's process dies mid-task (a crash, a killed session) after the per-task marker was written
but before the task reached a terminal status, `tasks["<N>"].status` is left at `running` on disk
with a `start_sha` and `marker_at` pointing at the moment the marker was written — this is the
*normal*, expected trace of an interrupted task, not corruption.

**Operator action:** treat a task found at `running` as **unknown**, never as `passed` or `failed`
— the marker only proves the task *started*, not how it ended; the prior attempt may or may not have
committed real work before the crash. Re-launch with `--resume` (or a task-range relaunch covering
that task): the engine re-enters the task at implement attempt 1 (not a fix attempt, and the
attempt counter is not advanced by the crashed attempt), with a note in the implement prompt that a
crashed prior attempt may already have committed the work since `start_sha` — the agent checks for
that commit against the spec before deciding whether new work is needed. `start_sha` also becomes
the work-assertion baseline (`prevSha`) for that resumed attempt on `sdlc-task`, ahead of the
`state.tasks[N-1].commit` / git-history / `base_sha` resolution chain — see
[sdlc-task.md](sdlc-task.md)'s prevSha resolution order. `sdlc-flow` writes the same marker but its
work-assertion range is unchanged (`HEAD~1`, no `prevSha`).

## Related

- [`sdlc-state-vocab.json`](../../.claude/workflows/sdlc-state-vocab.json) — the machine-readable
  enum this page documents in prose.
- [`scripts/check_sdlc_state_vocab.py`](../../scripts/check_sdlc_state_vocab.py) — the gate that
  enforces it against every `sdlc-*-state.json` under `planning/`.
- [sdlc-task.md](sdlc-task.md), [sdlc-flow.md](sdlc-flow.md) — the two engines that emit these
  values.
- [index.md](index.md) — the workflows reference hub.
