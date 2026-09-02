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

`/consolidate-run` answers *"what did this roadmap turn up?"* and proposes `carryover[]` entries for
it. This command answers a different question: **"across every run since the last time we looked,
what is wrong with our orchestration system, our engines, and the way we file findings?"**

They are two artifacts, and both already exist on disk, written by hand:
`planning/roadmaps/<slug>/consolidated-review*.md` (per roadmap) and
`planning/open-work/orchestration-runs/retros/pattern-analysis-*.md` (across runs). This command
automates the second. It **calls** `/consolidate-run` for the first rather than reimplementing it.

**Run from a fresh Opus session at the brain root.** It reads across every repo and holds the whole
corpus in view; that is the job. Extraction fans out to Sonnet subagents (Step 3) — the synthesis in
Step 4 does not.

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
| `--also-per-roadmap` | off | **Additionally** invoke `/consolidate-run` per roadmap for its own `consolidated-review.md`. Off by default — this command is the harvest (Step 6). |
| `--since <YYYY-MM-DD>` | — | Select by lane-log activity date rather than by roadmap. A roadmap is not a run: one run spans several roadmaps and one roadmap spans months, so a slug list cannot express "the run of 2026-09-02". Composes with the selectors above; narrows, never widens. |
| `--dry-run` | off | Do everything except write the analysis and advance the watermarks. |
| `--out <path>` | `planning/open-work/orchestration-runs/retros/pattern-analysis-<YYYY-MM-DD>.md` | Where the analysis lands. |

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
     \( -name notes.md -o -name review.md \) | grep -v '/trees/'
```

Filter to records whose frontmatter `roadmap:` matches a selected slug **and** whose `lifecycle:` is
**not** `consolidated` — that stamp is `/consolidate-run`'s own resume mechanism and this command
honours it rather than adding a second one for the same files.

| Input | Where | Why |
|---|---|---|
| Lane-log lines | `lane_log_watermark.py pending --roadmap <slug> --json` | The per-block narrative; the `note` field carries the real signal |
| Run records | the `find` above | Decisions, findings, ledgers |
| Carryover state | `mev carryover --json --allow-exec` | Clusters, suggested duplicates, single-repo `finding_id` warnings, broken-predicate diagnostics, misfiled-operator warnings |
| Commander retros | `planning/open-work/orchestration-runs/retros/*.md` | Instrument failures; the highest-transfer material there is |
| Commander chronology | `planning/open-work/orchestration-runs/run-log-*.md` | Drain-by-drain timeline |
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
5. **No finding in this corpus has a `finding_id`.** Do not invent one. Minting them is Step 4's job,
   after clustering — an id assigned per-record cannot cluster anything.
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

**The gap is cross-repo, not absence — measured 2026-09-02, correcting this file's first draft.**
30 of 268 carryover entries carry a `finding_id` and 29 clusters render, so the ids exist and the
mechanism works. What does not exist is a single **cross-repo** cluster, against **100 cross-repo
similarity suggestions**: every id in the fleet was minted inside one repo, by an author who could
not see the other repo saying the same thing. That is the gap this command's vantage point closes,
and it is a stronger argument than "nothing writes them" — which was false.

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

## Step 5 — Write the analysis

Write to `--out`. OKF frontmatter (`type: Log`, `layer: [meta]`, `project: brain`), a row in the
retros `index.md` (standing rule 7), and these sections:

| Section | Content |
|---|---|
| Scope | Roadmaps, watermark ranges consumed (`<slug> lines N–M`), records read, records skipped and why |
| Mechanisms | `M1..Mn`, each: claim · severity · breadth · owning repo · `finding_id` · the contributing findings with their provenance tags |
| Instrument failures | Their own section. Every command that returned a plausible wrong answer, with the correct form. The single most transferable output a run produces |
| Carryover health | Read from `/triage-carryover`'s evidence, never re-audited here: per-repo rot rate **beside pool age**, machine-checkable share, broken-predicate counts in all three directions, `needs` coverage, retired-kind survivors (`known_issue`/`constraint` on disk mark entries nobody has re-read since August) |
| Self-report audit | Every number a record asserted about itself, recounted, with the delta |
| Already known | Mechanisms matching a prior analysis — reported as another instance, with the instance count |
| Proposed disposal | One row per mechanism → a block, a `carryover[]` entry, or explicitly nothing, each with its `needs` value so the row routes by executor |
| What needs the operator | Only what genuinely cannot be decided by an agent |

Every claim carries a provenance tag. A section that reports nothing says so as a claim
("no instrument failures found in 6 records") so a reader can tell it ran.

**Disposal has machinery now; propose against it rather than inventing a shape.** A block is filed
with `mev create-block --from <payload.json>` (`block.schema.json`'s 15 required fields arrive as a
JSON payload, never per-field flags). A `carryover[]` entry is authored per the
**`write-carryover-entry`** skill — load it before proposing one, and do not restate its rules here.
This command still **proposes only**; see the write boundary.

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

`--also-per-roadmap` additionally invokes `/consolidate-run <slug>` per roadmap, for the per-roadmap
`consolidated-review.md` and its `carryover[]` proposals. **Off by default**: the mechanism pass
already routes every finding through Step 5's disposal table, and running both produces two disposal
queues over one body of findings. Reach for it when a single roadmap needs its own reviewable
artifact — a handover, or an operator who owns one roadmap and not the run.

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
pattern that has cost real runs (CLAUDE.md standing rule 10). This command writes exactly three
things: the analysis at `--out`, its `index.md` row, and the watermark file. The
`lifecycle: consolidated` stamps are `/consolidate-run`'s writes, made by that command.

## Traps

- **A piped command's exit code is the pipe's.** Redirect to a file, then check `$?`.
- **`rg`/`find` are symlink-blind and every `planning/` is a symlink** — pass `-L`, and `-uu` to
  reach gitignored sub-repos.
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
Analysis: <path>. Watermarks advanced: <slugs>. No state.json written.
```
