---
type: Command
title: consolidate-fleet — mine several runs at once for the mechanisms behind them
description: Reads every unconsolidated lane-log line and run record across a set of roadmaps, plus the commander's retros and carryover triage, and produces one mechanism-level pattern analysis for improving the orchestration system itself. Advances a per-roadmap watermark. Writes no state.json.
doc_id: consolidate-fleet
layer: [factory]
project: base-template
status: active
keywords: [consolidation, patterns, mechanisms, lane-log, watermark, orchestration, carryover]
related: [consolidate-run, roadmap-status, D57-orchestration-run-artifact-contract, block-registration]
---

# Consolidate Fleet — what the runs, together, say about the system

> **HQ-only by nature, not by target.** `scripts/sync_downstream_harness.py` deliberately drops
> this file from every downstream repo via `EXCLUDED_COMMAND_FILENAMES` (line 241, comment:
> "HQ-only by nature, not by target") — that exclusion means **globally installed only**, not
> unreachable. This command reaches an agent ONLY through `/sync-global-commands`, which rsyncs it
> into `~/.claude/commands/`. Misreading the exclusion as "unreachable" is exactly what left this
> command runnable only by opening the file for a day (BT.chore.consolidate-fleet-not-globally-installed).
> Drift signal: `scripts/check_global_commands_fresh.py`.

`/consolidate-run` answers *"what did this roadmap turn up?"* and proposes `carryover[]` entries for
it. This command answers a different question: **"across every run since the last time we looked,
what is wrong with our orchestration system, our engines, and the way we file findings?"**

They are two artifacts, and both already exist on disk, written by hand:
`planning/roadmaps/<slug>/consolidated-review*.md` (per roadmap) and
`$BRAIN_ROOT/planning/open-work/orchestration-runs/retros/pattern-analysis-*.md` (across runs). This command
automates the second. It **calls** `/consolidate-run` for the first rather than reimplementing it.

**Run from a fresh Opus session at the brain root.** It reads across every repo and holds the whole
corpus in view; that is the job. Extraction fans out to Sonnet subagents (Step 3) — the synthesis in
Step 4 does not.

**Do not `/prime` first.** This command assembles its own input set in Step 2 from explicit paths, so
priming spends a large part of the window on orientation it will not use — and Step 4's cross-repo
synthesis is what needs that room. The one exception is `planning/handoff.md`: read that single file
if it exists.

**The disposal half runs in yet another fresh session.** `/dispose-run` deliberately does not run
here — its `ungrounded[]` contract only works when a reader who did **not** write the analysis picks
it up, because this session will fill those gaps from memory without noticing. See
[`/dispose-run`](dispose-run.md)'s session note. Stay reachable while it runs: its Step 2 asks the
analysis's author when a field is unsupported, and that author is you.


**Before writing down anything that is wrong, follow
[`.claude/workflows/finding-discipline.md`](../workflows/finding-discipline.md).** Evidence travels
with the finding or the finding does not exist; one occurrence is an instance, not a pattern; and an
odd-but-unexplained thing is recorded as an **observation** rather than inflated into a defect. The
cut list is part of the report — a pass that files everything it noticed has not filtered. Measured:
three independent audits found 32%/32%/26% of filed carryover already dead.

## Not these

- **Not `/consolidate-run`** — that is one roadmap, and its output is proposed `carryover[]` entries.
  This is many roadmaps, and its output is named mechanisms. This command invokes it.
- **Not `/roadmap-status`** — that is a live projection of one roadmap mid-run. This is retrospective.
- **Not `/attention`** — that triages stale items against `brain.toml` thresholds. This finds why
  they keep appearing.
- **Not `/triage-carryover`** (HQ) — that *works* the carryover backlog: one fan-out round of
  read-only per-repo audits, applied by a single writer, evidence written into the repo. This
  command **reads the evidence it leaves** (`planning/carryover-triage-*/`) and asks what the rot
  rate across rounds says about authoring. Do not audit entries here, and never dispose of one:
  `/triage-carryover` owns that, and bans bulk `--dispose` for reasons this command must not
  second-guess.

## Variables

```
Usage: /consolidate-fleet [<roadmap-slug>...] [--since-watermark] [--all]
                          [--no-per-roadmap] [--dry-run] [--out <path>]
```

| Flag | Default | What it does |
|---|---|---|
| `<roadmap-slug>...` | — | Roadmaps to consolidate. Repeatable and positional. |
| `--since-watermark` | — | Select every roadmap whose `lane-log.jsonl` has lines past its watermark. The normal invocation. |
| `--all` | — | Every roadmap with a `lane-log.jsonl`, watermark ignored. Use for a first run or a deliberate re-read. |
| `--also-per-roadmap` | off | **Additionally** invoke `/consolidate-run` per roadmap for its own `consolidated-review.md` and `carryover[]` proposals. Off by default — this command is the harvest (Step 6), and it promotes the verification ledgers itself (Step 5c). |
| `--since <YYYY-MM-DD>` | — | Select by lane-log activity date rather than by roadmap. A roadmap is not a run: one run spans several roadmaps and one roadmap spans months, so a slug list cannot express "the run of 2026-09-02". Composes with the selectors above; narrows, never widens. |
| `--dry-run` | off | Do everything except write the analysis and advance the watermarks. |
| `--out <path>` | `$BRAIN_ROOT/planning/open-work/orchestration-runs/retros/pattern-analysis-<YYYY-MM-DD>.md` | Where the analysis lands. |

No selector at all (no slugs, no `--since-watermark`, no `--all`) → print the watermark status table
and stop. That is the cheap "what would this read?" call.

---

## Step 1 — Scope, and the watermark

```bash
python3 <path-to-base-template>/scripts/lane_log_watermark.py status --root "$BRAIN_ROOT"
```

`--since-watermark` selects every roadmap the table reports with `N new` where N > 0.

`verify` prints `0 watermark(s) checked, 0 drifted` both when five roadmaps are clean and when five
have never been consolidated. Read the `status` table, not `verify`, to tell those apart.

**A `DRIFTED` row stops this command for that roadmap.** Drift means `lane-log.jsonl` was rewritten
or truncated, so its line numbers no longer mean what the watermark thinks — resuming would skip
real run data and report a clean pass over it. Report the roadmap, exclude it, and continue with the
others; never re-base it automatically. The operator resolves it with an explicit `--to-line`.

**Malformed lines are carried, not dropped.** The status table names them by index. Measured
2026-09-02: 9 of the corpus's 421 lane-log lines do not parse, all in `demand-ready`, each truncated
mid-`note` at 533 bytes. They still describe real blocks. Report the count in the analysis; never
let a parse failure silently shrink the input.

## Step 2 — Assemble the input set, by path

Everything below is read-only. **Resolve run records at their vault paths.** A record reached
through `core/<repo>/planning/...` or under any `trees/` directory is a worktree duplicate of the
same file; including both double-counts every finding.

```bash
find -L "$BRAIN_ROOT" -path '*_planning/*/orchestration-run/*' \
     \( -name notes.md -o -name review.md -o -name verification-ledger.json \) | grep -v '/trees/'
```

**`verification-ledger.json` is in that list deliberately.** `notes.md` and `review.md` say what went
wrong; the ledger says what now works and how to check it, and it is the input to the test-catalogue
pass below. It was missing from this sweep until 2026-09-05, by which point nine ledgers holding 152
entries had accumulated across six repos, none consolidated.

**The `grep -v '/trees/'` matters more for the ledgers than for the records.** Measured 2026-09-05: a
`find -L` for `verification-ledger.*` returns **144 paths that are 18 distinct files**, one okf-core
ledger reachable by **25** separate worktree chains. Dedup by inode or realpath, never by path
string.

Filter to records whose frontmatter `roadmap:` matches a selected slug **and** whose `lifecycle:` is
**not** `consolidated` — that stamp is `/consolidate-run`'s own resume mechanism and this command
honours it rather than adding a second one for the same files.

| Input | Where | Why |
|---|---|---|
| Lane-log lines | `lane_log_watermark.py pending --roadmap <slug> --json` | The per-block narrative; the `note` field carries the real signal |
| Run records | the `find` above | Decisions, findings, traps re-confirmed |
| Verification ledgers | the same `find` | What each run shipped and how to verify it — the input to the catalogue pass |
| Test catalogue | `docs/sandbox/test-catalogue.json` | What is already covered, so a capability is promoted once and merged thereafter |
| Carryover state | `mev carryover --json --allow-exec` | Clusters, suggested duplicates, single-repo `finding_id` warnings, broken-predicate diagnostics, misfiled-operator warnings |
| Commander retros | `$BRAIN_ROOT/planning/open-work/orchestration-runs/retros/*.md` | Instrument failures; the highest-transfer material there is |
| Commander chronology | `$BRAIN_ROOT/planning/open-work/orchestration-runs/retros/commander-retro-*.md` and `liaison-retro-*.md` | Drain-by-drain timeline. (Was `run-log-*.md`, retired 2026-09-07 — the chronology now lives with the retros.) |
| **The open-work board** | `$BRAIN_ROOT/planning/open-work/orchestration-runs/new-work-log.md` | **Every finding a drain surfaced and left open.** The one input that was missing: `orchestration-commander` writes every finding here and closes a row only "when a human resolves it or a later drain observes it gone", and until 2026-09-07 nothing read it — so findings accumulated with no promotion path. Measured that day: 60 findings, exactly **one** marked CLOSED. Treat each open row as a candidate for Step 4's disposal rows. |
| Carryover triage | `planning/carryover-triage-*/` (per-repo files + `evidence/`) | Per-repo rot rates and their causes |
| Prior analyses | `retros/pattern-analysis-*.md`, `roadmaps/*/consolidated-review*.md` | So a known mechanism is reported as another instance, not rediscovered |

**Read the prior analyses first.** The commander's own retro records the cost of skipping this: a
finding written to a board at 05:45Z was re-diagnosed from first principles five hours later by a
different role that never read the board.

**`mev carryover` is the deriver; this command is a projector.** Consume its `clusters`,
`suggestions`, `single_repo_finding_ids`, broken-predicate diagnostics and misfiled-operator
warnings; never reimplement similarity, ranking or staleness.

Three flags matter and one is a trap:

- **`--allow-exec`** — without it 38 entries sit one flag short of a verdict (ACTIONABLE 54 → 83).
- **Never `--repo`** here. It hides cross-repo-scoped entries, measured at 47 of them, and this
  command's whole subject is what recurs *across* repos.
- **Never `--dispose`, not even with `--would-block`.** Disposal is `/triage-carryover`'s call.

**Treat the tools as a hypothesis, not an answer** — the discipline `/triage-carryover` step 0d
establishes, applied here to your own reading. Every disagreement between what an extraction agent
read in a record and what `mev` reports is a **first-class deliverable**, not a discrepancy to
reconcile quietly. And if a tool failure this command warns about cannot be reproduced, **say so** —
that means it got fixed, and the warning should come out.

## Step 3 — Extraction (Sonnet, one agent per record pair)

One agent per `(repo × roadmap)` record pair. Give each agent **explicit absolute paths** and the
warnings below; an agent that has to work out where things live will read a `trees/` copy.

**The unit is uneven and that is accepted, not fixed.** Measured: nine agents, nine returns, ~570
findings; jynx's 2,014-line record took ~9 minutes and seven tool calls against the others' two.
Splitting a record across agents would split a `CORRECTION` from what it corrects (rule 2), which
costs more than the wall-clock. Launch the largest record first so it is not the tail.

Each agent returns a strict JSON array, one object per finding:

```json
{"repo": "", "roadmap": "", "block": "", "claim": "", "owner_repo": "", "severity": "P0|P1|P2|P3",
 "status": "OPEN|DONE|HELD|WONTFIX", "disposition": "carryover|block|escalation|none|unstated",
 "needs": "code|docs|state|operator|dedupe|unstated",
 "carryover_slug": "", "evidence": "file:line or command", "provenance": "verified|assumed|relayed",
 "superseded": false, "quote": ""}
```

Tell every agent, verbatim, all five:

1. **Read the vault path given. Never a `trees/` path.**
2. **A `CORRECTION:` section supersedes earlier text in the same file, and nothing marks the
   superseded passage.** Extract the corrected claim and set `superseded: true` on the one it
   replaces. A naive read yields both the wrong and the right cause of one finding as two findings.
3. **Record shape varies, and more than you expect.** Measured over nine records: **nine different
   section sets**, `## ` counts ranging from **2 to 28**, and at least **six** status vocabularies —
   one record declares a vocabulary in a legend then uses four words outside it, another declares
   `WONTFIX` and never uses it. Extract what is there and **say what was absent**; never infer a
   field to fill the envelope. (An earlier draft named `engine-updates-and-fixes` as the thin
   example. It is not thin — 14 sections — and the claim was wrong; there is no reliable thin
   example, which is the point.)
4. **`provenance` is not optional.** `verified` = the record shows the command and its output;
   `relayed` = another lane told this one; `assumed` = the record asserts it. The prior analysis was
   useful precisely because every claim carried this tag.
5. **Do not invent a `finding_id` at extraction time.** Some carryover entries in the corpus already
   carry one (run `mev carryover --json --allow-exec` and check the `finding_id` field to see how
   many, as of when you run it) — but a raw extraction record is not a carryover entry, and minting
   an id per-record here, before clustering, cannot cluster anything. Minting is Step 4's job, after
   clustering.
6. **`needs` answers "what kind of work closes this", not "why does it exist".** `kind` (defect ·
   deferred · drift · env) already carries the why; `needs` (code · docs · state · operator ·
   dedupe, okf-core's field) is what lets the analysis route findings by executor instead of by
   repo. It is optional on disk and **most entries will not have it** — record `unstated` rather
   than guessing, and report the coverage, because an inferred `needs` is worse than an absent one.

## Step 4 — The mechanism pass (Opus, in this session)

Cluster the extracted findings into **mechanisms**: one underlying cause, however many repos worded
it differently. This is the command's actual output and it does not delegate.

Name each `M<n>` with a severity and a **breadth count**, following the shape already used in
`consolidated-review-5.md` — `M2 — --auto-merge does not merge (P1, measured 6-for-6)`. Breadth is
the number of independent repos or lanes that hit it, counted from the extraction, never estimated.

**Mint one `finding_id` per mechanism** and attach it to every contributing finding. This is what
`mev`'s `cluster_by_finding_id` groups on.

**The gap is cross-repo, not absence — this file's first draft claimed the latter and was wrong.**
Run `mev carryover --json --allow-exec` and look at `total`, the count of entries with a
`finding_id`, `clusters`, and `suggestions`: the ids exist, clusters render, and the mechanism
works — do not re-derive that from a frozen count here, because it will already have moved by the
time you read this. The load-bearing question is narrower than "do ids exist": **how many of the
rendered `clusters` span more than one `repo` among their members?** Count it fresh each run — as
of 2026-09-03 it was 3, against dozens of `single_repo_finding_ids` and a much larger set of
`suggestions` that never got confirmed across a repo boundary. Every id in the fleet is minted
inside one repo, by an author who cannot see another repo saying the same thing — that structural
fact, not any specific count, is the gap this command's vantage point closes, and it is a stronger
argument than "nothing writes them," which was false.

Cross-check against `mev carryover`'s `suggestions`, and **never auto-merge**. A false merge
destroys durable knowledge exactly the way a false `cleared` does. Two entries join only when a
human confirms it by authoring the shared id.

**Four analytic traps, each measured, each of which produces a confident wrong answer:**

- **Not-evaluable ≠ stale.** learn-ai's pool was 16/16 not-evaluable and was predicted "mostly
  stale". Wrong: 5 of 9 live entries could carry a typed predicate that day. The pool was
  *undescribed*, not blocked.
- **A young pool and a healthy pool look identical in the retire rate.** mev and engine-rs measured
  16–19% dead — low because 22 of engine-rs's 42 entries were five days old, not because the pool is
  healthy. Report retire rate only beside pool age.
- **Predicates fail in three directions, not two.** An already-satisfied `clears_when` retires a live
  finding at authoring; a brain-relative one never fires and reports live forever; and — the round-3
  class, `/triage-carryover` pattern 9, seen in 3 repos — one **becomes** satisfied *after* authoring
  through unrelated work, while the finding stays live. The third is the nastiest because the entry
  is well-formed, typed, and genuinely passing: none of the broken-predicate classes catch it. Count
  all three; they are one mechanism with three signs.
- **Self-reported counts are unreliable.** A prior analysis recounted a liaison retro's "6 sends" and
  found 8. Recount every number a record asserts about itself, mechanically, and report the delta.

## Step 4b — The open-work board's rows

**Every open row on `$BRAIN_ROOT/planning/open-work/orchestration-runs/new-work-log.md` is a candidate for a
disposal row, and this is the only step that gives them an exit.**

`orchestration-commander` writes every finding a drain surfaces to that board and, by its step 5,
closes a row only "when a human resolves it or a later drain observes it gone". Until 2026-09-07
nothing read the board, so there was no path from a row to `state.json`: measured that day, **60
findings, exactly one marked CLOSED**, some carried across 40+ drains. Rows accumulate; nothing
promotes them. That is the gap this step closes.

For each open `##` row:

1. **Skip the telemetry.** A row that only records a drain's own state — "quiet", "no change since
   <ts>", "all leases cleared" — is not a finding. It is already recorded structurally in
   `planning/roadmaps/<slug>/drain-log.jsonl`. Do not file it and do not count it.
2. **Give it a `finding_id`** — reuse the row's own slug where it has one, so `mev`'s cross-repo
   correlation joins it to any `carryover[]` entry already carrying that id. A row citing
   `instance N of <row>` is the SAME finding as its parent, not a new one: one `finding_id`, and
   the instance count goes in `breadth.instances`.
3. **Route it** with the same vocabulary as every other row — `block` / `chore` / `carryover` /
   `operator` / `none`. `route: "none"` is a real answer for a row that turned out to be a
   one-off, and saying so is what lets the next pass stop re-reading it.
4. **Evidence is the board line**: `$BRAIN_ROOT/planning/open-work/orchestration-runs/new-work-log.md:<line>`,
   plus whatever the row itself cites. A row whose evidence is only "a drain said so" is
   `route: "none"` with that stated — see `.claude/workflows/finding-discipline.md`.

**Do not delete or rewrite rows here.** This command writes no `state.json` (see Write boundary)
and it must not be the thing that drops a finding either — `/dispose-run` files the rows, and Step
6 marks what was consumed.

## Step 5 — Write the analysis

Write to `--out`. OKF frontmatter (`type: Log`, `layer: [meta]`, `project: brain`), a row in the
retros `index.md` (standing rule 7), and these sections:

| Section | Content |
|---|---|
| Scope | Roadmaps, watermark ranges consumed (`<slug> lines N–M`), records read, records skipped and why. **Recount every total you state** — a per-repo breakdown that does not sum to the headline is the self-report failure this document audits in others |
| Mechanisms | `M1..Mn`, each: claim · severity · breadth · owning repo · `finding_id` · the contributing findings with their provenance tags |
| Instrument failures | Their own section. Every command that returned a plausible wrong answer, with the correct form. The single most transferable output a run produces |
| Carryover health | Read from `/triage-carryover`'s evidence, never re-audited here: per-repo rot rate **beside pool age**, machine-checkable share, broken-predicate counts in all three directions, `needs` coverage, retired-kind survivors (`known_issue`/`constraint` on disk mark entries nobody has re-read since August) |
| Self-report audit | Every number a record asserted about itself, recounted, with the delta |
| Already known | Mechanisms matching a prior analysis — reported as another instance, with the instance count |
| Coverage and docs debt | What the verification ledgers say the fleet can now do, and where that is unwatched — see below |
| Proposed disposal | A **pointer to `disposal.json`** (below) plus the same rows rendered for a human reader. The JSON is the contract; the table is the courtesy copy |
| What needs the operator | Only what genuinely cannot be decided by an agent |

**The Coverage and docs debt section** is the cross-run *shape* of the catalogue, written after
Step 5c has done the per-entry promotion. Step 5c decides each entry; this section counts what the
catalogue now holds:

- **Unwired seams.** Entries with `finding: true` — a capability shipped with no production caller.
  Count them, name the repo, and say whether they cluster: measured on the first pass, **7 of 152**,
  five of them in a single repo, which is a fact about that repo's lane and not about the fleet.
- **Untestable tests.** Entries carrying `recipe_status` — `missing` (no recipe at all) or
  `not-cold-runnable`. **27 of 257 on the first pass.** A catalogue whose recipes cannot be run reads
  as coverage while providing none, so this number is the honest measure of how much of the catalogue
  is real.
- **Docs owed.** Entries whose `docs.state` is `missing` or `stale`. New functionality that no doc
  describes is how a capability becomes folklore — the person who shipped it is the only one who
  knows, and this command runs precisely when that person's session is long gone.
- **Never-run tests.** Catalogue ids with no row in **any** `docs/sandbox/results/*.json`. These have
  never been checked anywhere, in any environment, which is different from having failed.

Report these as counts with named examples, not as a full listing — the catalogue is the listing.

Every claim carries a provenance tag. A section that reports nothing says so as a claim
("no instrument failures found in 6 records") so a reader can tell it ran.

### `disposal.json` — the machine-readable half, written beside the analysis

**Write `disposal.json` next to `--out`, and treat it as the deliverable the prose table describes.**
A downstream command that parses the markdown table by column heading breaks the first time an
analysis words its section differently — and record-shape variance is measured at nine section sets
across nine records. Depending on prose for a machine handoff is the same mistake `finding_id`
exists to fix, one level up. This file is also the port surface: when disposal moves into
`engine-rs`, it consumes this, not a heading.

```json
{"analysis": "<path to the .md>", "generated": "<ISO8601>", "roadmaps": ["..."],
 "backfilled": false,
 "conventions": {"ungrounded_excludes": ["id","title","description","why","created","updated"]},
 "rows": [
   {"finding_id": "gates-that-cannot-fail", "mechanism": "M1",
    "route": "block|chore|carryover|operator|none",
    "owner_repo": "base-template", "needs": "code|docs|state|operator|dedupe",
    "severity": "P0", "breadth": {"repos": 7, "instances": 17},
    "evidence": ["<analysis>.md:<line of the mechanism section>", "<record path>[:<line>]", "..."],
    "payload": {},
    "ungrounded": ["files.new", "acceptance_criteria"],
    "rationale": "one line: why this route"}
 ]}
```

- **`payload`** carries only fields the analysis can GROUND against `block.schema.json`. Leave a
  field out rather than inventing it. **Set `payload.origin` to
  `{"type": "mechanism", "slug": "<this row's finding_id>"}` on every `route: "block"` row.**
- **`ungrounded[]` is required and is the point.** It names every required field the evidence does
  not support, so the filing agent knows exactly what to ask rather than guessing. A row with an
  empty `payload` and an honest `ungrounded[]` is more useful than a full one that guesses.
- **`route: "none"` is a real value.** A mechanism the analysis decided to file nothing for says so
  here, so the filer reports it as a decision rather than an omission.

**Five rules the first hand-written `disposal.json` needed and this shape did not give it** (all
measured on the 2026-09-02 backfill, `retros/disposal-2026-09-02.json` — 11 rows, 10 with a
non-empty `ungrounded[]`):

1. **`ungrounded[]` needs a stated exclusion set, or it becomes a constant.** Six required fields —
   `id`, `title`, `description`, `why`, `created`, `updated` — are mechanically derivable from the
   mechanism itself and were underived on *every* row. Listing them eleven times destroys the
   signal the field exists to carry. Declare them once in `conventions.ungrounded_excludes` and omit
   them from rows. **`spec_dir` is NOT excluded**: it is conventional but it encodes a directory the
   filer chooses, and it was chosen wrong once.
2. **`needs` is a single enum and analyses propose pairs.** Two of eleven rows were proposed as
   "docs + code". Record the dominant value and name the other half in `rationale`; never invent an
   array the consumer will not read.
3. **`evidence[]`'s first element is the analysis section anchor**, `<analysis>.md:<line>`. The
   `path:line` form is right for a record the row can point at precisely, but a mechanism spans many
   records and the per-finding line refs die with the extraction agents' returns. **A bare record
   path is a valid element** — it is honest, and a fabricated line number is not.
4. **`payload` is route-shaped, not always block-shaped.** `route: "carryover"` carries the carryover
   entry's fields (`container`, `repo`, `slug`, `finding_id`, `kind`, `needs`) — note that a
   carryover entry *does* carry `finding_id` and `needs`, unlike a block. `route: "operator"` and
   `route: "none"` carry `{}`, and their `ungrounded[]` says why: an adjudication has no filable
   payload.
5. **`breadth.instances` is `null` when the mechanism heading gives repos only** — five of eleven
   did. Null is the honest value; a guess here is exactly the self-report error the analysis's own
   recount section exists to catch.

**`ungrounded[]` entries may be finer or coarser than a schema field.** `files.new` (the modified
paths were readable, the new ones invented) and free text naming a gap the schema has no field for
("the third of the three counts — the analysis names two") were both more useful than `files`.

**A backfilled file must say so.** Set `"backfilled": true` and a `backfill_note` giving the reason
and the date, so a reader takes the payloads as *what was filed* rather than as current proposals.

**A block carries neither `finding_id` nor `needs`, and that is correct — do not try.**
`block.schema.json` is `additionalProperties: false` and declares neither; `mev create-block`'s
payload does not `deny_unknown_fields`, so writing them is **silently dropped** (measured
2026-09-02 on the first disposal, when they were written into `notes` prose instead). The reason is
not an oversight in the schema:

- **`needs` is a routing key**, consumed the moment a finding becomes work. It is open while
  something is a `carryover[]` finding; a block already answers it with `sdlc_workflow`, `files[]`
  and `what`. It belongs in `disposal.json` and on the carryover entry, and nowhere after that.
- **Clustering is a carryover concern.** Carryover entries already carry `finding_id` and `mev`
  clusters on it. A block does not need to join that cluster — it needs to *point at* the mechanism
  that produced it, which is what `origin` is for:
  `{"type": "mechanism", "slug": "<the mechanism's finding_id>"}`.

So a block row's `payload` sets `origin.type = "mechanism"` and `origin.slug` to the `finding_id`,
and `disposal.json` keeps `needs` for the routing decision itself.

**Disposal has machinery now; propose against it rather than inventing a shape.** A block is filed
with `mev create-block --from <payload.json>` (`block.schema.json`'s 15 required fields arrive as a
JSON payload, never per-field flags). **`create-block --write` chains `emit-state --write`
unconditionally**, so filing anything at all means emitting: check
`mev conformance --check toolchain-freshness` immediately before, not from a reading taken earlier
in the session, and snapshot any file another lane has dirty so the emit can be shown not to have
altered it. "File these but do not emit" is an instruction nothing can obey. A `carryover[]` entry is authored per the
**`write-carryover-entry`** skill — load it before proposing one, and do not restate its rules here.
This command still **proposes only**; see the write boundary.

## Step 5c — Promote the verification ledgers, per roadmap

**This runs on every invocation. It is not behind a flag, and it is not optional.**

`/consolidate-run` Step 5b is the authority for *how* to make each call — the merge-not-overwrite
rule for an id already present, the never-rename-an-id rule, judging whether a recipe is cold-runnable,
the `docs: {page, state}` verdict, and the fact that a ledger's `status`/`last_verified` are results
that belong in `docs/sandbox/results/<env>.json` and are rejected by the catalogue's own checker.
**Read that step and follow it; it is cited here, not restated.**

What this command adds is *when*: once per roadmap in scope, over the ledgers Step 2 already
collected, **before Step 6 stamps anything**.

**Why it moved here.** `/consolidate-fleet` is the entry point; `/consolidate-run` is not expected to
be invoked separately any more. A per-roadmap step that only ran under a command nobody runs is a
step that does not run. MEASURED 2026-09-07: a fleet pass stamped `carryover-cleanup` and
`sandbox-findings` `lifecycle: consolidated` and advanced both watermarks while **82 ledger entries
across 8 ledgers reached neither catalogue** — 57 of them the whole fleet-wide `carryover-cleanup`
run. Worse than late: `/consolidate-run`'s own selection filter is `lifecycle != consolidated`, so
the stamp made those entries **unreachable by the only path that promotes them**. The control that
proves this is a skipped step and not broken machinery: 111 entries across 8 other roadmaps are
fully promoted.

The routing decision, restated here only because it is the one part a reader must not have to
follow a link to make:

| `scope` | The entry describes | Goes to |
|---|---|---|
| `fleet` | a durable surface — a registered `harness.json` check, a CLI verb or flag, a schema another repo reads, an engine behaviour, a documented instruction agents follow, a guard against a recurring mistake | [`docs/sandbox/test-catalogue.json`](../../../docs/sandbox/test-catalogue.json) |
| `run-local` | a one-time state change — a data migration, a repair of one record, documentation prose with no code seam, or proof that one specific bug is fixed | [`test-catalogue-run-local.json`](../../../docs/sandbox/test-catalogue-run-local.json), with the reason |

**The test for `fleet`: if this broke silently in six weeks, would anyone want to know?**

**A `call_site: NONE` is not one verdict.** NONE because the entry is documentation is `run-local`.
NONE because a real seam shipped with **no production caller** is a `fleet` entry *and a finding* —
set `finding: true`, say why, and carry it into Step 5's disposal table like any other finding rather
than leaving it only in the catalogue.

**Validate before Step 6:** `python3 scripts/check_test_catalogue.py` from `BRAIN_ROOT`, exit 0. It is
`gates: true` in HQ's `harness.json`, so a malformed write here red-gates every lane in the fleet.

**A roadmap whose ledger promotion failed or was skipped does not get stamped in Step 6** — same rule
as a record Step 3 failed to extract from, and for the same reason: an unstamped record is recoverable,
a wrongly-stamped one is invisible.

## Step 6 — Stamp what you consumed: this command IS the harvest

**A record this command read is harvested.** Its findings are in the mechanisms; re-reading it in a
later pass re-proposes work that is already filed. So stamp `lifecycle: consolidated` on every run
record Step 2 selected and Step 3 actually extracted from, naming this analysis in the record's
`consolidated_by:` field.

This is a deliberate reversal of the first draft, which delegated the stamp to `/consolidate-run`.
Measured on the first real run: the operator asked for mechanisms, Step 6 was skipped, and five
roadmaps were left with their records `lane-complete` and no `consolidated-review*.md` — neither
harvested nor consolidated, and nothing on disk said which. **A pass that reads a record and does
not stamp it leaves the corpus ambiguous**, and the ambiguity is invisible.

**Do not stamp a record Step 3 failed to extract from** — a fan-out that errored, or a record the
selection reached but no agent read. Those stay unstamped and are named in the report.

**Stamp only after Step 5c.** A record whose ledger entries have not been promoted is not
harvested, however thoroughly its prose was read — the ledger is half of what the record carries.

**Stamp the board's rows the same way, and this is the only thing that ever closes one.** For every
`new-work-log.md` row Step 4b turned into a disposal row, append a marker line to that row:

```
> PROMOTED 2026-09-07 — finding_id `<id>`, route `<route>`, in `retros/disposal-<date>.json`.
```

A marked row is done and later drains skip it; an unmarked row is still open and step 1.0 will
keep surfacing it. **Do not delete the row.** `orchestration-commander` step 5's rule — an item
closes only when a human resolves it or a later drain observes it gone, never because a drain
forgot to relist it — is what keeps findings from evaporating, and deleting here would reintroduce
exactly that. The marker gives a row an exit without giving any single pass the power to drop one.

A row you routed `none` gets the same marker with `route: none`; that is a decision, and recording
it is what stops the next pass re-reading it. **Rows skipped as telemetry get no marker** — they
age out under the file's own retention rule instead.

`--also-per-roadmap` additionally invokes `/consolidate-run <slug>` per roadmap, for the per-roadmap
`consolidated-review.md` and its `carryover[]` proposals. **Off by default**: the mechanism pass
already routes every finding through Step 5's disposal table, and running both produces two disposal
queues over one body of findings. Reach for it when a single roadmap needs its own reviewable
artifact — a handover, or an operator who owns one roadmap and not the run. **Ledger promotion is no
longer a reason to reach for it** — Step 5c does that unconditionally.

## Step 7 — Advance the watermarks

Only after the analysis is written, and only for roadmaps whose records were actually read:

```bash
python3 <path-to-base-template>/scripts/lane_log_watermark.py advance \
        --roadmap <slug> --run-id <this analysis's filename> --root "$BRAIN_ROOT"
```

Skip drifted and skipped roadmaps — advancing past unread lines loses them permanently, and the loss
is invisible. Under `--dry-run`, advance nothing.

## Write boundary

**No `state.json`, in any repo.** One command writing state across a dozen repos is the contention
pattern that has cost real runs (CLAUDE.md standing rule 10). This command writes exactly seven things:
the analysis at `--out`, `disposal.json` beside it, their `index.md` rows, the watermark file, the
`lifecycle: consolidated` stamps of Step 6, the `> PROMOTED` markers Step 6 appends to
`$BRAIN_ROOT/planning/open-work/orchestration-runs/new-work-log.md` rows it routed, and the test catalogue
writes of Step 5c (`docs/sandbox/test-catalogue.json`, `test-catalogue-run-local.json`, and ledger
verdicts appended to `docs/sandbox/results/<env>.json`).

The board marker is an **append to an existing row**, never a deletion or a rewrite — the board's
own append-only rule is what keeps a finding from evaporating when a drain forgets it, and this
command must not be the exception to it.

**Corrected 2026-09-07.** This section used to say the `lifecycle` stamps were `/consolidate-run`'s
writes and that this command "does not write the test catalogue either" — both were false. The stamp
moved here in Step 6's own deliberate reversal and this section was never updated with it, and the
catalogue moved here in Step 5c. Two commands appending to one catalogue is still the contention this
boundary guards against; the resolution is that **this command is the single writer**, not that
neither is.

## Traps

- **A piped command's exit code is the pipe's.** Redirect to a file, then check `$?`.
- **`rg`/`find` are symlink-blind and every `planning/` is a symlink** — pass `-L`, and `-uu` to
  reach gitignored sub-repos. **With `-uu`, also add
  `--glob '!**/target/**' --glob '!**/node_modules/**' --glob '!**/.git/**'`** — `-uu` disables
  `.gitignore`, and this fleet's ~43GB of Rust `target/` dirs will otherwise get walked, pegging
  350–500% CPU or hitting a Bash timeout that reads as a hang, not a slow search.
- **`find -newermt` with a relative time errors under bfs**, and `2>/dev/null` eats it, leaving an
  empty result that reads as "nothing changed". Use `-mmin -N`. Filed fleet-wide as
  `find-newermt-relative-time-errors-on-bfs` (P1).
- **`validate-brain` flags do not compose** — one per invocation. Run `--graph` and `--links` as a
  pair; they check different things, and a dangling `related:` has shipped behind a green `--links`.
- **`git show HEAD:<path>` lags by one uncommitted emit** on every repo with a live lane. Audit the
  working tree, not `HEAD`.
- **Timestamps mix `Z` and `-03:00`.** The box is UTC-3; a bare `stat` mtime against a `Z` string
  reads three hours wrong.
- **The lane-log is not a completion record.** Six lanes finished a run and one wrote a `LANE-CLOSE`
  row. Absence of a close row means nothing.

## Report

**<= 10 lines.** See the `report-to-the-operator` skill.

```
<n> roadmaps, <r> records, <l> lane-log lines -> <m> mechanisms (<k> new, <j> known)
- <the highest-breadth mechanism, one line>
- <anything skipped, and why>
Ledgers: <e> entries -> <f> to the catalogue, <r> run-local, <d> merged; <x> findings (call_site NONE with a real seam)
Analysis: <path>. Disposal: <path> (<u> of <m> rows carry a non-empty ungrounded[]).
Watermarks advanced: <slugs>. Catalogue: <n> tests. No state.json written.
```

**Report the `ungrounded[]` count, not just the file.** It is the one number that says how much of
the disposal a filing agent will have to invent, and it is the cheapest signal in the artifact.
