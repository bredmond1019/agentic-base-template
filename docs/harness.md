---
type: Reference
title: "harness.md: gated-check verdict scoping for fleet-shared data"
description: "The rule for any gated check whose input is fleet-shared state: attribute the gating VERDICT to this repo's own subtree while still REPORTING everything the scan finds."
doc_id: harness-verdict-scoping
layer: [factory]
project: base-template
status: active
keywords: [gated checks, verdict scoping, delta attribution, fleet-shared state, D64, ownership, harness]
related: [harness-json, brain:D64-push-gate-delta-attribution, base-template-docs-index]
---

# Gated-check verdict scoping for fleet-shared data

A rule for anyone writing or reviewing a gated check whose input is data shared across the whole
fleet — a lane registry, a repo lease, a message queue, a live-config census — rather than data
scoped to this repo alone.

## The rule

**A gated check that reads fleet-shared state attributes its gating VERDICT to this repo's own
subtree, while still REPORTING everything the scan finds.**

- The **scan stays fleet-wide.** Read every record, from every repo, the same as before.
- Only the **verdict narrows.** A malformed or stale record belonging to another repo is printed —
  it must still be visible, because surfacing it is how it ever gets fixed — but it does not fail
  this repo's run.
- A malformed or stale record belonging to **this repo** still fails the verdict. A check that fails
  on nothing is not a check.
- **Attribution is by ownership of the record — its own `repo` field — never by path scoping of the
  scan.** Path scoping (only reading records that happen to sit under this repo's own directory)
  would silently narrow what gets reported too, which defeats the point: the whole reason to keep
  scanning fleet-wide is so a foreign break is still caught and reported by *someone's* run, even
  though it does not block that run.

## Why: this is the Test-stage counterpart of D64

[D64](../../docs/decisions/D64-push-gate-delta-attribution.md) (`brain:D64-push-gate-delta-attribution`)
already settled this question for the push gate: `hooks/pre-push` validates the whole corpus, but
blocks only on errors new since this clone's last successful push — "attribution is by delta, never
by path," because deleting a doc can surface the resulting error on a file the push never touched, and
a path-scoped gate would wave that straight through.

The SDLC engines' Test stage never inherited that principle, and every lane's `planning/` is a
symlink into one shared vault, so any gated check can *reach* fleet-wide state whether or not it
should be judged by it. Three checks were found bailing lanes on other lanes' data this way —
`message-schema`, `lane-agent-schema`, and `harness-schema-realpath` — in every case failing a lane
that could not itself fix the record. This document states the fix once, as a pattern, so the next
fleet-reading check inherits it instead of repeating the same measured failure. Full instance-by-
instance evidence: `planning/blocks/BT.ticket.fleet-wide-gates-red-on-another-lanes-data.json`.

## For the next fleet-reading check

If a new gated check reads any file outside this repo's own `planning/`/`docs/` tree — a registry,
a lease, a queue, a cross-repo census, or anything else that another lane's session can write —
implement it this way:

1. Resolve "this repo" once (the check's own repo slug — e.g. via `brain.toml`'s `[[repos]]` table),
   fail closed if it cannot be resolved (never silently treat "unknown" as "not foreign").
2. Keep the scan over the full fleet-shared dataset.
3. Report every finding, foreign or not.
4. Compute the gating exit status from only the findings whose record's own `repo` field matches this
   repo.
5. Test both directions explicitly: a foreign bad record must be reported and non-fatal; an own bad
   record must still be fatal. A test suite that only proves the first direction cannot tell you the
   check still catches anything.

See `scripts/check_lane_agents.py` and `scripts/check_messages.py` for a worked implementation
(`resolve_own_repo`, `is_foreign`), and their test files for the both-directional fixtures.
