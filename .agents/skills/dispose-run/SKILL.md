---
name: dispose-run
description: >
  Reads a pattern analysis and its disposal.json and files each row as a block, a carryover entry, an operator edge, or explicitly nothing. Refuses rows the evidence does not support and reports them. Files rows and stops; it never authors a roadmap.
---

# Dispose Run — turn an analysis into rows in the graph

`/consolidate-fleet` produces mechanisms. Until they are filed they gate nothing, sort nowhere and
appear on no board — the "prose gates nothing" failure, one level up from the findings it analyses.
**This command is the disposal half.** It reads `disposal.json`, files each row, and stops.

**Where it stops is as important as what it does.** It files rows. It does **not** author a
roadmap — `/generate-roadmap --from <analysis>` does that when there are enough blocks to need
lanes, and running both produces two schedulers over one body of findings.

## Run it in a FRESH Opus session — not the one that wrote the analysis

**A different session from `/consolidate-fleet`'s, deliberately.** Step 2 below says to ask the
analysis's author *"if that session is reachable"*, and that sentence only makes sense because
disposal normally runs somewhere else.

The reason is `ungrounded[]`. It is the analysis's own list of fields it could not support, and it
is a real contract only when a different reader picks it up. **The author who just wrote the
analysis will fill those gaps from memory without noticing they are doing it** — which is the
confident invention Step 2 forbids, and it multiplies through every downstream task. A second reader
either finds the evidence in the sidecar or cannot, and that is the signal.

There is a second reason: `disposal.json` exists so the handoff does not depend on prose or on one
session's context. Disposing in the authoring session never tests whether the sidecar is actually
sufficient — you find that out weeks later, when someone else tries.

**Opus, not Sonnet.** This is routing under judgement, not transcription: Step 3 may route a row to
*explicitly nothing*, which is the verdict needing the most judgement; Step 2 requires **refusing**
a row the evidence does not support and reporting the refusal rather than filing something
plausible; Step 4 writes `state.json` and re-runs `emit-state`, whose blast radius is corpus-wide.

**Always `--dry-run` first.** It resolves, validates and reports every row while writing nothing.

```
# Claude Code, in a fresh Opus session at the brain root — NOT a terminal
/dispose-run <path-to-analysis.md> --dry-run
/dispose-run <path-to-analysis.md>
```

**If the authoring session is still open, use it — Step 2 asks you to.** Just do not *be* it.

## Variables

```
Usage: /dispose-run <analysis-path-or-disposal-json> [--rows M1,M2] [--dry-run] [--no-epic-check]
```

| Flag | Default | What it does |
|---|---|---|
| `<path>` | **required** | The analysis `.md` (its `disposal.json` sibling is used) or the JSON directly. |
| `--rows <ids>` | all | File only these mechanisms. Use to land the P0s first. |
| `--dry-run` | off | Resolve, validate and report every row; write nothing. |
| `--no-epic-check` | off | Skip step 5's epic reconciliation. |

## Step 1 — Read the disposal, and the analysis behind it

Load `disposal.json`. **If it is absent, stop** and say so: an analysis written before the sidecar
existed must be backfilled by whoever wrote it, because only that reader knows which evidence backs
which row. Do not parse the prose table as a substitute — heading-shaped parsing is what the
sidecar exists to replace.

Then read the analysis itself for the rows you will file. The sidecar carries routing; the
mechanism sections carry the evidence a block record needs.

## Step 2 — The plan-quality floor, and who answers it

**`ungrounded[]` is the contract.** Every field named there is one the analysis could not support.
For each:

- **Ask the analysis's author if that session is reachable.** They read the records; you have a
  summary. Every question is also a defect in the analysis — record it so the document can be
  patched and the next reader need not ask.
- **If it is not reachable, stop and ask the operator, naming exactly what is missing.** An honest
  "I need X to state the `why` for M4" beats a confident invention that multiplies through every
  downstream task.
- **Never fill a required field by inference to make a row filable.** A row withheld for missing
  evidence is a result, not a failure.

## Step 3 — Route each row

| `route` | How |
|---|---|
| `block` / `chore` | `mev create-block --from <payload.json>` — one invocation per row; there is no batch mode |
| `carryover` | Load **`write-carryover-entry`** and follow it. Do not restate its rules here |
| `operator` | An `operator` edge in the `depends_on` of the block(s) it gates |
| `none` | File nothing, and **report it as a decision** — a silent skip is indistinguishable from an omission |

**Four rules that were each learned by getting them wrong on 2026-09-02's first disposal:**

1. **A block carries neither `finding_id` nor `needs`.** `block.schema.json` is
   `additionalProperties: false` and declares neither; `mev create-block` does not
   `deny_unknown_fields`, so both are **silently dropped**. Provenance goes in
   `origin: {"type": "mechanism", "slug": "<finding_id>"}`; `needs` stays in `disposal.json`.
2. **An operator edge must gate a block.** If a proposed operator item gates none of the rows you
   filed, **do not file it** — inventing a gate to hold it is worse than leaving it. Check first
   whether the gate already exists elsewhere; two of four proposed on that run already did. Zero
   filed can be the right answer.
3. **A `carryover[]` predicate must be verified UNMET before you commit it.** An entry that lands
   in CLEARED on the day it is written retires itself while the finding is live. Positive-control
   it — run the identical predicate somewhere a match is known to exist.
4. **Recount every total the disposal states.** That run's table said "8 blocks — base-template 6,
   mev 3", which is nine. A summary line that does not sum is the self-report failure the analysis
   audits in other documents.

**Order by leverage, not by row number.** File the P0s first, and within them the mechanism others
depend on. Say what order you chose and why.

## Step 4 — Emitting is not optional, so check freshness immediately before

**`mev create-block --write` chains `mev emit-state --write` unconditionally.** Filing anything at
all means emitting the whole corpus. Therefore:

```bash
mev conformance --check toolchain-freshness > /tmp/tf.txt 2>&1; echo "exit=$?"
```

Run it **immediately before the first write**, never from a reading taken earlier in the session —
a stale reading reported as current is what made "file these but do not emit" an instruction
nothing could obey. If it is red, stop and report; a stale binary rewrites derived boards in an old
format.

**Snapshot any file another lane has dirty** before the emit, and verify it byte-identical
afterwards. The emit rewrites the whole corpus, not your repo.

## Step 5 — Reconcile the epic (unless `--no-epic-check`)

If the rows join an `epics[]` entry, check that entry's `status` against what you just filed. On
2026-09-02 nine blocks were filed into `fleet-integrity`, whose status is `complete` — leaving a
completed epic with four open members. Load the **`epic`** skill and resolve it: resume the epic,
or give the rows their own. A board showing complete-with-open-members is a defect either way.

## Step 6 — Write boundary

Writes: block records and their `state.json` registrations (via `mev create-block`), `carryover[]`
entries, operator edges, and whatever the emit that `create-block` chains produces. Nothing else.

- **Never bulk-backfill `finding_id`** across existing entries. A false merge destroys durable
  knowledge the way a false `cleared` does; a shared id is authored by a human who confirmed the
  match.
- **Never re-file or amend rows a previous disposal already filed.** Re-running is safe only
  because `create-block` refuses an existing id — respect the refusal rather than routing around it.
- Explicit pathspec on every commit; one git repo backs every `planning/`.

## Report

**<= 10 lines.** See `report-to-the-operator`.

```
<n> rows: <f> filed (<b> blocks, <c> carryover, <o> operator), <w> withheld, <s> none
- <the withheld rows and what each was missing — this is the real output>
- <anything the disposal asked for that the evidence does not support>
Epic: <reconciled / no change needed>. Commits: <shas>.
```

**The withheld list is the deliverable, not the filed count.** A disposal that files everything it
was handed has not checked anything.
