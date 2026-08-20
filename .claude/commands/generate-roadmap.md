---
type: Command
title: generate-roadmap — Author a multi-repo roadmap and its /orchestrate lane files
description: Turn a body of findings, open blocks and operator decisions into a roadmap document plus per-repo lane chain files that /begin-orchestration can drive concurrently, with the concurrency budget, cross-lane edges, operator gates and registration gate made explicit.
---
# Generate Roadmap — author a multi-repo run and the lanes that execute it

Produces the two things `/begin-orchestration` consumes: a **roadmap document** and one
**`lane-<name>.txt` chain file per lane**. It does not run anything.

A roadmap is not a list of what would be nice to do. It is a **concurrency plan** — an assignment of
work to parallel `/orchestrate` sessions that cannot step on each other, behind a definition of done
that can be checked by observation rather than asserted.

**Related:** `/generate-master-plan` authors *one repo's* canonical block definitions. This command
sits above it and spans repos. `/begin-orchestration` drives one lane of the result.

**Upstream:** for work on an existing system, the pre-plan pipeline runs first —
`/assess` → `/seams` → `/sequence`. Its `sequence.md` is an authored cut, not a body of findings,
and Step 1b says how to carry it through rather than re-derive it. Method:
`docs/how-to-plan-with-agents.md` in the brain repo.

**Single-copy command.** This command runs at `BRAIN_ROOT` and is deliberately **not** synced
downstream by `scripts/sync_downstream_harness.py` (it has no meaning inside a leaf repo) — a
change here needs no `/sync-downstream-harness` pass.

## Variables

`$ARGUMENTS` — a concept name or slug, plus optional flags.

| Flag | Required | Default | What it does |
|---|---|---|---|
| `<slug>` | **yes** | — | Roadmap slug. Becomes `planning/roadmaps/<slug>/`. Kebab-case, names the *outcome* not the date. |
| `--from <path ...>` | no | — | Source documents: a review, an audit, an action register, a previous roadmap. Repeatable. A `consolidated-review.md` emitted by `/consolidate-run` is a valid source, and so is a **`sequence.md` from the pre-plan pipeline** — see "Pre-plan input" below, it is handled differently from the rest. |
| `--supersedes <path>` | no | — | The roadmap this replaces. Adds the banner to both documents. |
| `--lanes <n>` | no | `4` | Target concurrent lanes. The real ceiling is operator capacity, not repo count. |
| `--dry-run` | no | off | Print the lane assignment and cut list; write nothing. |

Empty `$ARGUMENTS` → print usage and stop.

```
Usage: /generate-roadmap <slug> [--from <path> ...] [--supersedes <path>]
                         [--lanes <n>] [--dry-run]
```

---

## Step 1 — Resolve and scope

**A. `BRAIN_ROOT`** — walk up from cwd for `brain.toml`. This command runs at HQ. A roadmap spanning
repos cannot be authored from inside one of them.

**B. `roadmap_dir`** = `<BRAIN_ROOT>/planning/roadmaps/<slug>/`. If it exists and holds a
`roadmap.md`, stop and ask whether to supersede or amend — never overwrite one.

**C. Read every `--from` source in full.** Not summaries of them.

**D. Read the superseded roadmap's outcome**, if any. Two questions, both mandatory:
what did it *achieve*, and what did it *not* — the second is the reason this one exists and belongs
in the opening paragraph.

---

## Step 1b — Pre-plan input: when a `sequence.md` is among the sources

Most `--from` sources are **bodies of findings** — this command inventories them and makes the cut.
A `sequence.md` from `/assess` → `/seams` → `/sequence` is different in kind: **the cut has already
been made, against evidence, with the operator's forks already answered.** Treat it as an authored
input to carry through, not raw material to re-derive. Re-deriving it silently discards a pass that
resolved decisions this command has no standing to reopen.

When `--from` names a `sequence.md`, also read its siblings — `seams.md`, `assessment.md` and
`verification.md` in the same folder. **Where `assessment.md` and `verification.md` disagree,
verification wins**; no claim it marked REFUTED may reach a lane file or a block record.

### What maps to what

| From the pre-plan folder | Lands in the roadmap as |
|---|---|
| `sequence.md` wave headings (*what becomes true*) | The **outcomes** (Step 3) — already stated as observable statements |
| Wave exit lines (a command + expected output) | The **Definition of done**, verbatim. They were authored as observations for exactly this |
| Blocks marked `registered` | Lane table rows, ready to run |
| Blocks marked `candidate`, and the Wave 0 table | **Wave 0** registration items, i.e. this command's `[*]` items (Step 6) |
| `depends_on` edges crossing repos + the cross-repo contract table | **Cross-lane edges** (Step 5), with the contract author naming which side goes first |
| Operator errands | The **operator lane** and its gates |
| The cut list | The **cut list** — extend it, never replace it |
| Repos-and-gate-weight table | Lane assignment and the heavy budget (Step 4) — verify the weights still hold, do not re-derive them |
| The 6b consistency sweep — cross-tree writers, single-writer calls, split-row edges | **Lane-assignment input, not commentary** (Step 4). A block whose files leave its own repo's tree cannot be scheduled from its `Repo` cell alone, and that is the one collision the lane model cannot see |
| Fork answers with dates | Wave 0 **operator ratifications** |
| `seams.md` blast radius, half-built classification, what-to-delete-first | The lane table's **notes column** and the lane file's `#` comments. A blast radius is precisely the "trap that has cost a real run" class those comments exist for — it is read at execution time, not planning time |
| Canonical block IDs (`<PFX>.<phase>.<block>`) | **The identity carried into every lane file, table and `state.json` row.** Take them as allocated; do not re-mint or renumber |
| `SQ-nn` refs | The **coverage crosswalk** ref scheme only (Step 7), and `#` comments for traceability. Grep them exactly as the check greps `AR-nn` |

### The rules for carrying it through

- **Do not re-cut.** If you depart from `sequence.md`'s block boundaries, ordering, or repo
  ownership, say so explicitly in the roadmap with the reason. A silent departure means the seam
  analysis was done and then ignored.
- **Do not re-open the forks.** They were answered by the operator with a date. If one now looks
  wrong, stop and say so — do not quietly decide it the other way.
- **Do not drop the ships-alone property.** Every block arrived carrying a "what the operator can do
  the day this lands" line. Lane assignment must not merge two blocks into one lane row in a way
  that loses it, and no wave may be re-cut into "plumbing first, value later."
- **Never write `SQ-nn` where a block ID belongs.** A lane file's executable lines, a lane table's
  block column, a `depends_on` edge and a `state.json` row all take the canonical
  `<PFX>.<phase>.<block>` ID. `SQ-nn` is a row label local to `sequence.md`; it belongs in a `#`
  comment at most. **Both crosswalks pass on a lane file full of `SQ-nn` lines** — they check that
  refs appear, not that they resolve — so this defect ships silently and surfaces as a lane that
  stops on its first block or improvises a spec. It has already shipped once.
- **If `sequence.md` did not allocate canonical IDs**, stop and send it back rather than minting
  them here. Allocation requires reading each owning repo's `state.json` for its highest phase, and
  a roadmap that invents IDs against a graph it did not read produces collisions that only surface
  at registration.
- **You still own lane assignment, the heavy budget, isolation, Wave 0 mechanics and the crosswalk.**
  `/sequence` decides *what* and *in what order*; this command decides *who runs it concurrently
  without colliding*. That division is the whole reason both exist.

### Freshness, not re-derivation

`sequence.md` carries a date and its evidence carries commit SHAs. Step 2's re-verification still
applies but changes shape: **re-check whether the pre-plan work has gone stale, rather than redoing
it.** Concretely — has any repo moved since the SHAs in `assessment.md`; are the `registered` blocks
still open in `state.json`; do the gate weights still hold; did a sibling roadmap adopt or close one
of these blocks in the meantime. Record every drift as a Wave 0 correction so nothing downstream
cites the stale version.

If the pre-plan folder is more than a few weeks old, or its repos have moved substantially, say so
and recommend a `/seams` refresh rather than building four concurrent lanes on it.

### When there is no `sequence.md` — the floor

This command stays fully usable without the pre-plan chain; most roadmaps are built from a review,
an audit or a previous roadmap, and Steps 2–7 handle that unchanged. But a roadmap fans one cut out
to four concurrent lanes, which multiplies a wrong assumption by four. Three questions are cheap and
must be answered somewhere in the document, in proportion to the roadmap's size:

1. **Built, half-built, or absent** — for every capability a lane *calls* rather than builds. A
   capability that exists in source with no production call site is a rewrite wearing a wiring
   block's clothes, and lane balancing built on that estimate is wrong by a lane.
2. **The single writer per shared artifact.** Any file, table or state two lanes both touch. This
   is the one the lane model cannot absorb — two lanes writing one artifact is the contention
   failure lanes exist to prevent, and it does not surface until the merge.
3. **What is being deleted first.** Dead surface inherited into four lanes is inherited four times.

**Escalation trigger.** If question 1 cannot be answered for a capability on a lane's critical
path, or question 2 comes back "unclear" for any shared artifact, **stop and recommend
`/assess` + `/seams` on that area** rather than authoring lanes over the gap. Name the capability.
A roadmap is the most expensive artifact to be wrong in — it is the one that dispatches concurrent
sessions against the mistake.

---

## Step 2 — Inventory, and re-verify before you plan on it

**If a `sequence.md` is among the sources, Step 1b governs and this step narrows to freshness.**
The inventory below is for roadmaps built from findings rather than from an authored cut.

Collect candidate work from, in this order of trustworthiness:

1. **`state.json` across the fleet** — every `open`/`blocked` block. This is the graph and it is fact.
2. **Carryovers past their staleness threshold** — `mev carryover`, or `validate-brain --state`.
3. **Findings in the `--from` documents** that have no block. These become `[*]` items (Step 6).
4. **Operator decisions** named anywhere as gating something.

> **Re-verify the load-bearing claims before building on them.** In this fleet a formal review was
> wrong in six cited places within five days, and the follow-up built on it was wrong in three more.
> Nothing had been sloppy — the system moved. A roadmap inherits every stale claim in its sources
> and then multiplies it by four concurrent lanes.
>
> Cheap and mandatory: for each claim that determines a lane's shape, run the one command that
> checks it. "The CI is red" — look at the run list. "The name is available" — query the registry.
> "The gate is not wired" — read the `harness.json`. Record what changed; a killed claim is a
> finding, and the correction belongs in the roadmap's Wave 0 so nothing downstream cites it.

---

## Step 3 — Choose the outcomes, then cut everything else

**If Step 1b applied, the outcomes are `sequence.md`'s wave headings** — they were authored as
"what becomes true" statements for this purpose. Restate them here; do not invent a parallel set.

**Three to five outcomes, each stated as something that becomes true**, not as an area of work.
"The demo is live and browser-verified" is an outcome. "Demo hardening" is a theme, and themes do
not terminate.

Then write the **cut list, and make it long.** Every substantial candidate that is not in an outcome
gets a row and a reason. This is the highest-value section of the document and the one most often
skipped: an unstated cut reads as an oversight, gets re-proposed next roadmap, and re-litigated.
A stated cut is a decision with a date on it.

Cut aggressively on this rule: **if no outcome depends on it, it is out, no matter how good it is.**

---

## Step 4 — Assign lanes

### The lane unit is the repo, never the wave

`/orchestrate` drives **one repo per session, engines serial inside it**. Two blocks in the same
repo can never run in parallel however a wave grid groups them. So:

- A repo holding 10 blocks **is the critical path**, regardless of what is scheduled beside it.
- "N concurrent agents" means N sessions in N *different* repos.
- Balance lanes by the *longest repo chain*, not by block count.

### Lane collisions are decided by files touched, not by the repo field

The lane unit is the repo, but **the thing two lanes actually collide on is a path**. A
`base-template` block that edits files under `core/mev/` runs concurrently with a live `mev` lane
and nothing detects it: the registry was told two different repos are in flight, which is true and
irrelevant. `fleet_concurrency_check.py` reasons about repos and cannot see this either.

So before assigning lanes, read every block's `files[]` (or `sequence.md`'s `Files` column) and
build the path → block map for the whole roadmap:

- **A block whose files leave its own repo's tree** is a cross-tree writer. Name it in its lane
  table's notes column and in its lane file, with the lane it may not run beside. Then sequence
  those two lanes so they are not live together, and say so in the lane file of *both*.
- **Two blocks in different repos naming the same path** is two writers on one artifact — the
  contention failure the lane model exists to prevent. One of them is wrong; resolve it here,
  before four sessions are dispatched against it.

If `sequence.md` ran its 6b sweep, this is already computed — verify it still holds rather than
re-deriving it. If it did not, this step is where it happens.

### The heavy budget is the real constraint

**At most two heavy-gate repos concurrently.** Heavy = its `planning/harness.json` gates include a
browser or a full production build (Playwright, `next build`) — or a very large native build.
Determine this by **reading each repo's `harness.json`**, not from memory.

If the work has three heavy repos, the third lane **opens on a light repo and reaches the heavy one
later**, and the roadmap says so in the lane table. Do not simply hope the operator sequences it.

> Nothing enforces this ceiling. It is prose in the roadmap and nowhere else — say so in the
> document rather than implying a machine checks it.

### Isolation is policy, not preference

| Repo | Isolation | Why |
|---|---|---|
| `base-template` | **`--worktree` always** | It owns `.claude/workflows/sdlc-*.js`; a chain there edits the engines while they execute it. |
| the brain root (HQ) | **`--no-worktree` always** | `validate-brain` in a worktree resolves the gitignored sub-repos against the worktree's own `brain.toml` — measured 64 structure / 601 state errors versus 0/0 in the main tree. |
| everything else | `--no-worktree` | Cheaper. Use `--worktree` when a change deserves quarantine. |

**If `base-template` is in the roadmap, decide its propagation timing explicitly.** Its work must
land early (every other lane runs on those engines) but `/sync-downstream-harness` must not run
while any lane is live — a mid-flight sync has already swapped a running lane's engine underneath
it. The resolution is always the same: **land in the worktree early, defer propagation to an
operator gate at the end.** Write both halves into the lane file.

---

## Step 5 — Find the cross-lane edges, and only those

A cross-lane edge is a place a lane must **wait on a different repo**. Everything else is sequential
inside one repo and needs no coordination.

For each edge, name: source block → target block, and **what breaks without it**. An edge whose
consequence you cannot state is usually not an edge.

Draw them as ASCII in the roadmap. Six to eight edges is normal for four lanes; twenty means the
lane split is wrong and should be redrawn.

**The operator lane is a real lane, and it should be the shortest one.** Its gates are what let a
roadmap sequence correctly around a human instead of pretending one is not needed — each is filed
as a `{"type": "operator", slug, exit, start}` edge on the block it gates and driven by
`/begin-session <slug>`. But a roadmap's value is the hours it runs without you: every gate is a
point where four concurrent lanes can end up waiting on one desk. Keep only the gates where *only*
a human can act (a credential, an outward-facing or irreversible action, a machine visit, a
decision that is theirs to own), give each a named exit artifact, and place it on the last block
that needs it rather than the first — so the lane ahead of it runs unattended. State the count and
where each falls in the run; a roadmap with a gate early in every lane is a roadmap that runs at
operator speed.

**Operator gates are edges too.** A block waiting on a DNS record or a human read-through is
blocked exactly as hard as one waiting on a sibling repo — and unlike a code dependency, nothing in
the graph models it. Name every one in the lane file *and* in the operator table, with the block it
gates. The two gates that will actually bite are worth calling out by name; in practice they are
the ones that must happen mid-run and get deferred to deploy time instead.

---

## Step 6 — Wave 0, the registration gate

**`/orchestrate` resolves block IDs from `state.json`.** A lane file naming an ID that is not in the
graph does not degrade gracefully — the lane stops, or worse, improvises a spec.

So every `[*]` item from Step 2.3 must be **filed as a ticket and registered in its repo's
`state.json` before any lane launches.** Make that Wave 0 and say it is a hard gate.

**From a pre-plan folder, `[*]` is already computed for you:** every row `sequence.md` marks
`candidate`, listed in its own Wave 0 table. Re-check each against the live `state.json` rather than
trusting the column — a sibling lane may have registered or closed one since. A row marked
`registered` whose ID is no longer in the graph is a Wave 0 item too, and a more urgent one, because
nothing in the document will look wrong.

**Registration does not close until the initiative-wide consistency pass has run** —
Step 7 of `.claude/workflows/block-registration.md`, once over every block in this roadmap, across
every repo, never per block. A roadmap is exactly the case it exists for: N authoring agents, one
row each, none of them able to see a second repo, a concurrent lane, an inherited edge, a prior
sizing flag, or an ungrounded operator artifact. Its five checks (C1–C5) are the last point at
which any of those is cheap to fix; after Wave 0 closes, four concurrent lanes are running on them.
Record its findings in Wave 0 — including "none".

Wave 0 also carries:
- Any **claim correction** from Step 2's re-verification, before a downstream lane cites it.
- The **operator ratifications** that gate a lane's first block.
- `mev emit-state --write`, then commit every touched `state.json` with an explicit pathspec.

A roadmap whose sequence table is empty before Wave 0 is correct and should say so. A *populated*
table is the signal the lanes may launch.

> **Registration is not optional bookkeeping.** Tickets filed on disk but absent from `state.json`
> are invisible to the board, to the generated sequence table, and to `/attention`. This has already
> happened once here: six tickets about drift, filed where the drift detector could not see them.
>
> The rule generalizes past tickets: **everything this roadmap says must happen has a row in
> `state.json`** — a block, an operator or approval edge, a `carryover[]` entry, a `reference[]`
> fact, a `backlog[]` row, the `epics[]` entry for the roadmap itself. The document carries the
> narrative and the reasoning; the graph carries the work. An item that lives only in a lane table's
> notes column, an operator paragraph, or a "still to decide" line is not scheduled, not sorted, and
> not on any board — it is lost, not deferred. Where the two disagree, the graph wins.

---

## Step 7 — Write the files

### `planning/roadmaps/<slug>/roadmap.md`

OKF frontmatter (`type: Plan`, `status: active`, `related:` pointing at the sources and the
superseded roadmap). Then, in order:

| Section | Content |
|---|---|
| Supersedes banner | What the previous roadmap achieved, what it did not, and **whether its folder may be archived** — if any of its documents are still referenced, say so explicitly so nobody archives them |
| The trade | Why this work, now. Lead with the finding that motivated it, with evidence |
| The outcomes | Three to five, each an observable statement |
| How to use this document | The generated table is authoritative; lane tables are execution order; `[*]` means filed in Wave 0 |
| Wave 0 | The gate. A table of registration, corrections and operator ratifications |
| Dependency graph | ASCII lane chains, then the cross-lane edges |
| The lanes | One table per lane: block, engine, and a **notes column that carries the evidence** — file:line, `AR-nn`/`SQ-nn`, the trap, the blast radius from `seams.md`, the thing the last run got wrong |
| Isolation and CPU budget | The policy table plus the two-heavy rule |
| Operator lane | Every gate, what it gates, and enough detail to act without re-reading a source doc |
| Coverage crosswalk | **Required whenever `--from` includes a runbook or action register.** One row per source item → where it lands. See below |
| What is cut, and why | Long. One row per cut candidate |
| Definition of done | See below — this is the section that decides whether the roadmap worked |
| Sequence | The generated region, between the markers |
| Live board · Lane log | Pointers |

**The coverage crosswalk is not documentation — it is the check.** A roadmap built from an action
register absorbs 30–60 discrete items and re-homes them into lanes. Items do not get dropped by
decision; they get dropped by *reorganisation*, and a prose roadmap gives you no way to notice.
Write one row per source item → its destination, then **verify it mechanically** before handing over:

```bash
C=$(cat roadmap.md lane-*.txt)
for ref in $(grep -o 'AR-[0-9A-Z]*' <source>.md | sort -u); do
  echo "$C" | grep -q "$ref" || echo "MISSING $ref"
done
```

A citation-style ref (`AR-nn`, `OPEN-n`, `SQ-nn`) in the source makes this a one-liner, which is a
good reason to insist sources carry them — `/sequence` assigns `SQ-nn` for exactly this check, so a
pre-plan-sourced roadmap always runs it as the one-liner. For items without a ref, grep a distinctive string from each.

**A row with no destination is a bug in the roadmap, not a decision.** If something should be
dropped, it goes in the cut list with a reason — that is a different row, and a deliberate one.
Real result of running this check on its first roadmap: four items had silently fallen out, two of
them operator infrastructure jobs that had been collapsed into a single link.

**The reverse crosswalk — check it too, it is a different failure.** The check above catches
sources dropped on the way in. It says nothing about the opposite direction: a lane file naming a
block that *this roadmap's own document never mentions*. That happened for real —
`carryover-improvements` filed two blocks and told a sibling roadmap's lane to run them first;
`close-the-loop`'s `roadmap.md` never names either, so its own crosswalk read clean while the
attribution was already broken in both directions (the filing roadmap's consolidation finds no
record of them either, since they landed in someone else's lane log). Verify it mechanically,
alongside the forward check:

```bash
for id in $(grep -vE '^\s*#|^\s*$' lane-*.txt); do
  grep -q -- "$id" roadmap.md || echo "UNDOCUMENTED $id (in $(grep -l -- "$id" lane-*.txt))"
done
```

A block a lane file names but this roadmap's document never mentions is a bug **unless** it is a
deliberately **adopted** block — see the next section, which is the one legitimate reason this
check can flag something and not be a defect.

**Cross-roadmap block adoption is a supported pattern, not a mistake.** Placing a block from
roadmap A into roadmap B's lane file is how a program with only one or two blocks in a repo avoids
standing up a whole lane of its own for that repo — the lane already exists on a sibling roadmap
that is running now. When a lane file adopts a block this way:

- The lane file **must** carry an `# ORIGIN: <path to the owning roadmap>` comment immediately
  above the adopted block ID, naming the roadmap whose outcomes and Wave 0 actually cover it.
- This roadmap's own document should say so too — in the lane table's notes column, or the cut
  list, whichever is true — so a reader of *this* roadmap is not left thinking the block is unowned.
- The reverse-crosswalk check above should treat any block ID with an `# ORIGIN:` comment as
  resolved, not undocumented, and its consolidation belongs to the roadmap the comment names, not
  to this one.

**When Step 1b applied, the Definition of done is `sequence.md`'s wave exit lines, verbatim.**
They were authored as commands with expected outputs precisely so they could land here unchanged.
Add to them if a lane's completion needs an observation the sequence did not name; never replace
them with block IDs.

**Definition of done must be written as observations.** Not "block X closed" — a block closes when
its spec is satisfied, which is not the same as the capability working. Prefer a command and its
expected output:

```
✅  curl https://<site>/<path> returns the body AND `utm_source` in the HTML
✅  `npx playwright test` runs to completion
✅  `cargo add <crate>@<version>` compiles in a scratch project outside this fleet
❌  BW.10.F closed
❌  the funnel is instrumented
```

This is the single most valuable rule in this command. A previous roadmap closed 30 of 53 blocks and
still shipped a demo nobody had loaded in a browser, a funnel no lead had traversed, and six
capabilities wired into nothing — because every one of its DoD items was a block, not an observation.

**The generated region, verbatim, and never hand-edited afterwards:**

```markdown
<!-- BEGIN generated:epic-sequence -->
<!-- END generated:epic-sequence -->
```

`mev emit-state --write` fills it from `state.json`. Do **not** author a wave table beside it. The
last roadmap that did accumulated a second "Revised Wave Table" while the first was still marked
authoritative, so the document carried two contradictory plans plus a generated table that outranked
both. **A wave grid is a communication device, not a schedule.**

### `planning/roadmaps/<slug>/lane-<name>.txt`

One per lane. `<name>` must match what an operator would type after `--lane`.

Required header — `/begin-orchestration` **cross-checks the `# ROADMAP:` line against its own
`--roadmap` flag and stops if they disagree**, which is the cheapest available check that the lane
was pointed at the right run:

```
# Lane <X> · <repo-or-theme> — <one line on what this lane is for>
# ROADMAP: <absolute path to roadmap.md>
# LOG:     <absolute path to lane-log.jsonl>
#
# RUN FROM <dir> :
#   /begin-orchestration --roadmap <rel path> --lane <name>
#
# ISOLATION: <flag> — <why>
```

Then the structured directives (below) when the lane has a corresponding constraint, then the
traps, holds and spec sources as comments, then **bare block IDs, one per line, in execution
order**. Blank lines and `#` comments are stripped by the reader.

### Structured directives — mev's parser reads these, the prose above is for the operator

The header and the trap comments below it are prose: read by whoever drives the lane, at the
moment they drive it. Nothing reads them mechanically. Alongside that prose — **never instead of
it** — emit the machine-readable directive mev's parser (`parse_lane_directives` in
`core/mev/src/brain/lane_segments.rs`) actually checks, whenever the corresponding constraint is
real. Both ship in the same lane file because they serve two different readers: the directive is
for the parser, the prose is for the operator holding the file open at 2am.

Each directive is a **comment-only line** — nothing before the `#` but whitespace — whose body
starts, immediately after `#` and any leading whitespace, with one of these three prefixes,
spelled and cased exactly as shown. A directive-looking phrase buried inside an ordinary sentence
does not parse; the prefix must be the first thing after `#`.

- **`# HELD-UNTIL: <token>`** — emit only when this lane genuinely waits on a block ID or an
  operator-gate slug before it can run. `<token>` is the first whitespace-delimited word after the
  prefix — it is carried opaque, never resolved by the parser, so use the exact block ID or slug.
- **`# BUDGET: HEAVY`** or **`# BUDGET: LIGHT`**, with an optional `NOT-WITH <repo>[,<repo>...]`
  clause — e.g. `# BUDGET: HEAVY NOT-WITH mev,orchestrator`. Unlike the other two, **every lane
  emits this one** — Step 4's "heavy budget is the real constraint" rule means every lane already
  has a real heavy-or-light classification, so there is no "constraint absent" case for `BUDGET`.
  The level is matched case-insensitively but write it upper-case to match the fleet's convention.
  Add `NOT-WITH` only when this lane's heavy budget collides with another repo's; a bare
  `# BUDGET: HEAVY` with no `NOT-WITH` is a complete, valid directive on its own. Keep the
  directive line itself free of trailing prose when `NOT-WITH` is present — text after the repo
  list gets folded into the last repo name by `parse_repo_list` rather than rejected, so it
  produces a wrong exclusion instead of a diagnostic. Put the "why" on its own comment line
  instead, as the worked example below does.
- **`# EXCLUSIVE-REPOS: <repo>[,<repo>...]`** — emit only when this lane claims exclusive write
  access to one or more repos beyond its own (the cross-tree-writer case below).

**A `HELD-UNTIL` or `EXCLUSIVE-REPOS` constraint that does not exist emits no line for it at all —
never an empty directive, a placeholder, or a value of `none`.** (`BUDGET` is the one exception —
see above — because it is never absent.) A malformed value (a `HELD-UNTIL:` with no token after
it, a `BUDGET:` with no `HEAVY`/`LIGHT` in it, an `EXCLUSIVE-REPOS:` with no repo after it)
produces a mev diagnostic against a real lane file; an absent directive produces nothing, because
the constraint is simply not there. When in doubt, omit the line — do not guess at a value to fill
it.

**Worked example** — a lane that is held on a sibling block, runs a heavy build that must not
overlap `mev`'s lane, and owns one file outside its own repo's tree, with both the directives and
the prose that explains them to the operator:

```
# Lane B · base-template — land the generator change, defer propagation
# ROADMAP: /Users/brandon/Dev/agentic-portfolio/planning/roadmaps/lane-directives/roadmap.md
# LOG:     /Users/brandon/Dev/agentic-portfolio/planning/roadmaps/lane-directives/lane-log.jsonl
#
# RUN FROM /Users/brandon/Dev/agentic-portfolio/base-template :
#   /begin-orchestration --roadmap ../planning/roadmaps/lane-directives/roadmap.md --lane B
#
# ISOLATION: --worktree — base-template owns the engines this run executes under
# HELD-UNTIL: MV.ticket.lane-file-structured-directives
# BUDGET: HEAVY NOT-WITH mev
# EXCLUSIVE-REPOS: mev
#
# HELD: waits on mev landing the directive grammar this generator emits against —
#   emitting against an unlanded contract risks a format mev never actually reads.
# BUDGET WHY: heavy — full harness + prompt-template checks; must not run beside mev's lane,
#   which is what NOT-WITH above encodes.
# TRAP: /sync-downstream-harness is roadmap gate G4 — do not run it while this lane
#   or any other lane is live; a mid-flight sync swaps a running lane's engine underneath it.
# WRITES OUTSIDE ITS OWN TREE: planning/harness.json only — no other repo's files.
#
BT.ticket.generate-roadmap-lane-directives
```

**Those lines are canonical `<PFX>.<phase>.<block>` IDs — `EN.12.A`, `MV.4.B` — and nothing else.**
Not a `SQ-nn` row ref, not a slug, not a title. `/orchestrate` resolves each line against
`state.json`; a line it cannot find stops the lane or makes it improvise a spec for work nobody
specced. Verify mechanically before handing over, because neither crosswalk catches this:

```bash
for id in $(grep -vhE '^\s*#|^\s*$' lane-*.txt); do
  echo "$id" | grep -qE '^[A-Z]{2,3}\.[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)?$' \
    || echo "NOT A BLOCK ID: $id"
done
```

The pattern is deliberately permissive about the segments after the prefix, because a block ID has
three legitimate shapes — `EN.12.A` (roadmap block), `BT.ticket.<slug>`, `HQ.chore.<slug>` — plus
legacy forms still live in the corpus (`OR.B`, `EN.1-plan.A`, `MV.3B.Q`, `BU.0.A-ccf`). Verified
against all 792 registered IDs: zero false positives. What it is actually asserting is *a repo
prefix followed by dot-separated segments*, which is what separates a real ID from `SQ-01`,
`AR-12` or a bare slug. **Do not tighten it to `[0-9]+\.[0-9A-Za-z]+` — that rejects every ticket
and chore block**, which is most of what a roadmap of small work contains.

Three things belong in these comments and nowhere else, because they are read at the moment of
execution rather than at planning time:

- **Every HELD block**, with the exact sibling block it waits on and why. Pair the prose with a
  `# HELD-UNTIL: <token>` structured directive (see "Structured directives" above) — the prose
  carries the *why*, the directive is what a machine can check.
- **Every spec source that is not master-plan slug mode** — `/generate-tasks --from <path>`. A lane
  that cannot resolve a spec improvises one.
- **The traps that have cost a real run in that repo.** Not general advice; specific, cited, and
  ideally with the failure it caused.
- **The blast radius of any seam this lane touches**, when the roadmap came from a pre-plan folder.
  `seams.md` states, per attachment point, what else breaks if it is wrong and who owns the write on
  either side. That is read at the moment a block is implemented, not at planning time, which is
  what these comments are for. A block touching a seam with a **single named writer** must say so —
  two lanes writing one artifact is the contention failure the whole lane model exists to prevent.
- **Any block that writes outside its own repo's tree**, with the exact paths and the lane it may
  not run beside. The lane agent is the single writer for its repo, and this is the one write it
  cannot know about from the repo it is standing in. If the exclusivity is against another whole
  repo (not just a sibling lane's budget), pair the prose with a `# EXCLUSIVE-REPOS: <repo>[,...]`
  structured directive; if it is specifically about not overlapping another repo's *heavy* run,
  that is the `NOT-WITH` clause on `# BUDGET:` instead.
- **`# ORIGIN: <roadmap path>` above any adopted block** — a block ID that belongs to a *different*
  roadmap's outcomes and Wave 0, placed in this lane only because the lane already exists here. See
  "Cross-roadmap block adoption" above. Every block ID a lane file names either appears in this
  roadmap's own document or carries this comment; there is no third option.

A lane file covering several repos uses section markers and says **"take only your repo's section"**
at the top — the reader stops and asks if it cannot tell which section is its own.

### `planning/roadmaps/<slug>/lane-log.jsonl`

Create it empty. Append-only, one line per integrated block. Four sessions editing one markdown
file is the contention pattern this structure exists to avoid.

### Register the roadmap in `epics[]`

**A roadmap's home is a folder; its findability is a registry row — the folder alone only tidies
the directory listing.** Epics already solved this: `state.json`'s `epics[]` array gives each entry
an explicit `plan` field naming the doc that makes it real, and `mev`'s `epics_index` conformance
check already validates that a registered `plan:` target resolves — one of its own fixtures already
uses `planning/<slug>/roadmap.md` as an epic's `plan:` value. Reuse that registry rather than
inventing a parallel `roadmaps[]` array: a roadmap is a multi-repo initiative's plan, which is
exactly what an epic's `plan` field is for.

In `<BRAIN_ROOT>/planning/state.json`'s `epics[]`:

- **If this roadmap continues an existing epic** (it was authored `--from` that epic's prior
  roadmap, or its outcomes are that epic's outcomes), update that epic's `plan` field to
  `planning/roadmaps/<slug>/roadmap.md`. Do not add a second entry for the same initiative.
- **If no existing epic covers this roadmap's outcomes**, add a new `epics[]` entry:
  `{"slug": "<slug>", "title": "...", "description": "...", "status": "active", "weight": <n>,
  "plan": "planning/roadmaps/<slug>/roadmap.md", "repos": [...]}` — `repos` is the union of every
  lane's repo.

Round-trip `state.json` with `json.dump(..., indent=2, ensure_ascii=False)` plus a trailing newline
(CLAUDE.md trap), and commit it with an explicit pathspec — never a bare `git commit` against the
brain's index (standing rule 10).

### `planning/index.md`

Add the folder (standing rule 7) at `planning/roadmaps/<slug>/`. If superseding, mark the old
folder's row — and if its documents are still referenced, write **"NOT archived"** on that row with
the reason.

---

## Step 8 — Verify before handing over

```bash
bastion validate-brain --okf-structure   # one invocation per flag; they do not compose
bastion validate-brain --links
bastion validate-brain --state
```

Then check by hand:

- [ ] **Every executable line in every lane file matches `<PFX>.<phase>.<block>`** — run the shape
      check above. A `SQ-nn` ref, a slug or a title on one of those lines makes the lane unrunnable,
      and both crosswalks pass anyway.
- [ ] Every block ID in every lane file exists in a `state.json`, **or** is marked `[*]` and appears in Wave 0.
- [ ] No lane has more than one heavy repo live at a time, given the stated ordering.
- [ ] Every cross-lane edge in the ASCII appears in the lane file of the *waiting* lane.
- [ ] Every operator gate names the block it gates, in both the operator table and the lane file.
- [ ] **The crosswalk check above runs clean** — every ref in every `--from` source appears in the
      roadmap or a lane file, or has a cut-list row.
- [ ] **The reverse crosswalk check also runs clean** — every block ID named in a lane file appears
      in this roadmap's own document, or carries an `# ORIGIN:` comment naming the roadmap that
      does mention it (cross-roadmap adoption).
- [ ] **No multi-step operator sequence is collapsed into a single link.** A runbook referenced as
      one row loses its steps. Break it out; two of its items probably touch live traffic.
- [ ] **The initiative-wide consistency pass ran over every block in this roadmap** (Step 7 of
      `block-registration.md`) and its findings are recorded in Wave 0. In particular: no
      `depends_on` edge is `{"type": "external"}` for work that lives in a fleet repo (that is an
      unfiled block, not an external dependency); every block spanning two repos has a block record
      in both; no two blocks split from one sequence row carry identical inherited `depends_on`;
      every block flagged oversized carries a split-now-or-defer decision; and every operator
      `exit` names an artifact that exists on disk or that a named block or command creates.
- [ ] **Every actionable item in this roadmap has a `state.json` row** — a block, an operator or
      approval edge, a carryover, a reference, a backlog row, or the roadmap's own `epics[]` entry —
      or a cut-list line with a reason. Sweep the document for open questions, "still to decide"
      lines and agreed findings with no home before handing over.
- [ ] **No two concurrent lanes write the same path**, and every cross-tree writer (a block whose
      files leave its own repo's tree) names the lane it may not run beside, in both lane files.
- [ ] Every Definition-of-done item is an observation with a command, not a block ID.
- [ ] The `# ROADMAP:` line in each lane file resolves to this roadmap.
- [ ] The roadmap is registered in `epics[]` with a `plan` field pointing at `roadmap.md`'s new path.
- [ ] The cut list is longer than you are comfortable with.
- [ ] **The floor is answered** — carried from `seams.md`/`sequence.md`, or answered inline per
      Step 1b: no capability on a lane's critical path is unclassified, and every artifact two lanes
      touch has one named writer.
- [ ] **If a `sequence.md` was a source:** every `SQ-nn` ref appears in the roadmap or a lane file
      or has a cut-list row; every `candidate` row is in Wave 0; every wave exit line survived into
      the Definition of done as a command; every departure from the authored cut is stated with a
      reason; and no fork was silently re-decided.

Report the lane assignment, the Wave 0 item count, and the cut list. **Do not run `/orchestrate`** —
this command authors; `/begin-orchestration` executes.

## Session boundary — end here, one fresh session per lane

**This command ends its session, and it does not run anything.** Authoring the concurrency plan and
driving a lane are different jobs, and the second is not one session but N.

Each lane is **one fresh Opus session, held open for that lane's whole chain.** Fresh because the
lane agent must read the lane file and the roadmap as written — it is the first reader, and if it
needs context only this session has, the lane file is underspecified and every other lane has the
same hole. Held open because the lane agent is the **single writer** for its repo: it owns the run
record, resolves conflicts, decides the ordinary scope calls, and carries what block 1 taught it
into block 7. That continuity is the job. The engines spawn their own agent stacks inside it.

Never drive two lanes from one session. The lane model's entire premise is one repo per session.

Close by telling the operator:

```
Roadmap authored: planning/roadmaps/<slug>/
  roadmap.md · lane-<a>.txt · lane-<b>.txt · ... · lane-log.jsonl
Registered in state.json epics[] as <slug>.

Wave 0 is a HARD GATE — <n> items must be filed and registered before any lane
launches. /orchestrate resolves block IDs from state.json; a lane naming an
unregistered ID stops or improvises a spec.
  <the Wave 0 items, or "none — lanes may launch">

Then open ONE FRESH SESSION PER LANE — Opus — each in its own repo directory:
  cd <repo-a> && /begin-orchestration --roadmap planning/roadmaps/<slug>/roadmap.md --lane <a>
  cd <repo-b> && /begin-orchestration --roadmap planning/roadmaps/<slug>/roadmap.md --lane <b>

Concurrency: at most 2 browser-automation lanes and 4 native-build lanes at once.
Start with: <the lanes that may run together, and which repo waits and why>.

Operator gates on this run: <each, with the block it gates>.

I have not run anything. This command authors; /begin-orchestration executes.
```

---

## Traps

- A piped command's exit code is the **pipe's**, not the command's. Redirect, then check `$?`.
- `rg`/`find` are symlink-blind and every `planning/` is a symlink into a `_planning/` vault — pass
  `-L`, and `-uu` to reach gitignored sub-repos. An inventory sweep without them is not trustworthy.
- `planning/state.json` round-trips with `json.dump(..., indent=2, ensure_ascii=False)` plus a
  trailing newline. The default escapes every em dash and turns a small edit into ~130 lines of churn.
- **HQ commits need an explicit pathspec** — `git commit -o <paths>`. Every repo's `planning/` is a
  symlink into the one HQ git index, so a bare commit sweeps other sessions' staged work in.
- `timeout` does not exist on this macOS shell.
- Block IDs must be allocated by reading the canonical `state.json`, not `status.md` or
  `master-plan.md` — narrative files lag and produce ID collisions. One repo already carries two
  unrelated "Phase 4"s from exactly this.
