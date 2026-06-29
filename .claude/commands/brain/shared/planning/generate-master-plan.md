# Generate Master Plan — Author a cross-repo program master-plan in a brain planning folder.

> **Brain-adapted** from `base-template/.claude/commands/generate-master-plan.md` (provenance:
> base-template@b8ebbf7, D34/D35). The base command authors a *single-repo* roadmap that
> `/generate-tasks` consumes in place. This brain version authors a **cross-repo program plan** that
> lives in `planning/<concept>/` and coordinates work across the sub-repos. It is **not** consumed by
> `/generate-tasks` here (the brain has no SDLC harness) — each block is *executed* by opening Claude
> Code in the sub-repo it names and running that repo's own harness. The brain keeps track of all the
> moving parts and the order they go in. This is a brain-maintained fork; it does not auto-sync with
> base-template.

## Variables

$ARGUMENTS — the **concept folder** under `planning/` to author the master-plan into
             (e.g. `bastion-product`), optionally followed by free-text framing notes and `--clarify`.
             Required. If the concept folder is omitted, stop and say:
             "Usage: /generate-master-plan <concept-folder>  (e.g. bastion-product)"

## Purpose

Turn a planning folder's raw material (its `plan.md`, `architecture.md`, etc.) into a canonical
`planning/<concept>/master-plan.md`: a dependency-sequenced set of **block definitions**, each one
naming **which sub-repo it executes in** and the **cross-repo interfaces** it consumes or produces.
The brain master-plan is the program-level coordination artifact — it answers *what lands where, in
what order, and how the pieces connect* — while the actual building happens in each sub-repo via that
repo's own `/generate-master-plan` / `/generate-tasks` / `/sdlc-flow`.

## Instructions

1. Run `/prime` to orient to the brain (cross-project state, standing rules, the public-narrative
   rule, all sub-projects).
2. Read the target concept folder and surrounding context — **do not write from a blank slate**:
   - `planning/<concept>/` — every file in it (`plan.md`, `architecture.md`, `index.md`, …). This
     existing material **is** the planning-session input; the master-plan structures it, it does not
     replace it.
   - `CLAUDE.md` (brain standing rules, the sub-project + data-contract map), `docs/projects/index.md`
     and the `docs/projects/<slug>.md` for each sub-repo the plan touches (to ground each block's repo
     assignment and sequencing in each repo's real current state).
   - Any existing `planning/<concept>/master-plan.md` — you may be **revising/extending** it; preserve
     completed phases.
3. **Clarify gate + plan-quality floor.**
   - **Clarify** when `$ARGUMENTS` is thin, when it contains `--clarify`, or when the destination /
     phase boundaries / which-repo-does-what is genuinely ambiguous: pause and ask **2–4 targeted
     questions** before writing. Strip a `--clarify` token before using `$ARGUMENTS` as prose.
   - **Plan-quality floor — clarify, don't fabricate (always).** The program plan is the
     highest-leverage artifact; a wrong assumption here multiplies across every repo. If filling a
     load-bearing element (a block's target **repo**, its cross-repo **interface/contract**, its
     **sequencing/dependency**, scope, or acceptance criteria) would require *inventing* a fact you
     cannot ground in `planning/<concept>/`, `CLAUDE.md`, the sub-project docs, or `$ARGUMENTS` —
     **stop and ask** rather than write a plausible-looking guess. An honest "I need X to place block
     N / assign its repo" beats a confident invention.
4. **THINK HARD about cross-repo decomposition before writing:**
   - **Sequence by dependency across repos, not calendar.** Foundational/enabling work (the shared
     contracts, the repo that others consume) comes first; the most-differentiating integration is
     last. The brain's whole job here is the *order*.
   - A **block** is a coherent segment of the program — typically one that executes in **one sub-repo**
     and produces something a later block (often in another repo) consumes.
   - **Name each block's target repo** (where you'd open Claude Code and run that repo's harness). A
     block with no repo is too abstract to execute.
   - **Name each block's cross-repo interfaces/contracts** — the data contracts, APIs, or shared
     formats it consumes from or produces for other repos. This is the load-bearing seam (the
     cross-repo analog of single-repo file-ownership): it is what makes the ordering real. (See the
     orchestrator↔bastion data-contract rule in `CLAUDE.md` for the established pattern.)
   - **Declare each block's Out of scope** — what belongs to a later block or a different repo.
   - **Distant blocks may be forward-looking** — full skeleton now, but say so; expect to refine the
     interface/repo lines when the prerequisite repos are further along.
   - Keep blocks about *what / why / which repo / which contracts / bounds* — not low-level
     stack detail (that surfaces when the sub-repo runs its own `/generate-master-plan`).
   - **North-star enrichment (encouraged for capability-building blocks).** Per the
     [north star](file://~/agentic-portfolio)
     and [D30](file://~/agentic-portfolio),
     a block isn't "done" when it runs once — it is done when it **graduates one rung of the
     capability-acquisition ladder and leaves a reusable ratchet behind.** For any block that builds a
     durable capability (not a one-off mechanical edit), also state its **Ratchet** (the reusable asset
     left behind), its **Eval slice** (how "better/done" is measured — the eval domain it feeds), and
     its **Ladder rung** (where it sits on solve→repeatable→skill→workflow→harness→eval→automation→
     monitor→trust→package, and which rung it advances). These keep the program pointed at compounding
     leverage rather than one-off motion.
5. Write (or revise) `planning/<concept>/master-plan.md` using the Output Format below. Maintain OKF
   frontmatter.
6. **Property self-check (before reporting).** Re-read and **revise in place** until every property
   holds, then re-check:
   - **Every block is a `### Block X — <name>` heading under a `## Phase N — <name>` heading.** No flat
     lists.
   - **Every block names a target Repo** and **at least one cross-repo interface/contract** (or states
     it is self-contained in one repo with no cross-repo seam).
   - **Every block declares Out of scope** — at least one explicit boundary.
   - **Every block has a non-empty What, Why, and observable Acceptance criteria** — each judgable
     true/false (a block whose work lands in a sub-repo should reference that repo's gates as part of
     "done").
   - **Every capability-building block carries the north-star enrichment trio** — a **Ratchet**, an
     **Eval slice** (or an explicit "n/a — deterministic acceptance only"), and a **Ladder rung**. A
     purely mechanical block (a rename, a doc move) may omit them; a block that builds a durable
     capability and omits them is incomplete — add them or justify the omission.
   - **The Quick Reference Sequence Table lists one row per block** (with its Repo) and matches the
     block headings.
   - **No fabricated facts** (repos, contracts, metrics) and **no leftover `<...>` stubs**. Honor the
     public-narrative rule from `CLAUDE.md`.
7. **Update `planning/<concept>/index.md`** to list the new `master-plan.md` (brain OKF rule: adding a
   file to a directory requires updating its `index.md`).
8. **Register the program in the Brain RAG corpus when `planning/<concept>/` is new.** The brain
   indexer's CORPUS list (`python-orchestration-system/scripts/index_brain.py`) is a hand-maintained
   set of paths — a new top-level `planning/<concept>/` is **not** picked up automatically and will be
   silently absent from the Brain vector store until added. If this command creates a *new* program
   folder that should be queryable (a standing cross-repo program like `bastion-product` /
   `bastion-ui`, not a transient single-initiative folder), flag it in the Report: the next
   orchestrator session must add `("planning/<concept>", "plan")` to `index_brain.py`'s CORPUS before
   the next `--rebuild`. (Cross-repo edit — the brain command does not touch the orchestrator repo;
   surface it so it isn't forgotten. See `planning/brain-rag-improvements/plan.md` Block E1.)
9. Report the path written and the first block to execute (see Report). Do **not** commit — leave that
   to `/commit`.

## Context / Files to Read

- `planning/<concept>/` (all files — the raw planning material)
- `CLAUDE.md` (brain standing rules + sub-project / data-contract map)
- `docs/projects/index.md` + the `docs/projects/<slug>.md` for each repo the plan touches
- any existing `planning/<concept>/master-plan.md`

## Standing rules to respect

Enforce the **brain standing rules** in `CLAUDE.md` — especially the public-narrative rule, "decisions
belong where they are scoped" (cross-repo → `docs/decisions/`; per-repo → that repo's
`planning/decisions/`), and the data-contract protocol. No fabricated metrics/quotes, no emoji.
Maintain OKF frontmatter. This command never edits a sub-repo — it only writes under
`planning/<concept>/`.

## Output Format

```md
---
type: Plan
title: <Concept Name> Master Plan
description: Cross-repo program roadmap for <Concept Name> — what lands in which repo, in what order.
---

# <Concept Name> — Master Plan

*Living document. Cross-repo program plan. Created <DATE>.*

## The Goal, Stated Plainly
<2–3 paragraphs: what the combined product is, why it matters, and what "ready" means — the
checkpoint that signals the program is delivered.>

## The Destination
<The named product/outcome that combines the sub-repos. The through-line tying them together.>

## Cross-Repo Architecture
<How the sub-repos combine into one product: which repo owns what, the data contracts / APIs / shared
formats that connect them, an ASCII diagram if useful, and the load-bearing decisions (point to
`architecture.md` and any `docs/decisions/` file). This is the map the block sequencing is built on.>

## Repos In Play
<Bullet list: each sub-repo this program touches, one line on its role in the combined product, and a
pointer to its `docs/projects/<slug>.md`.>

---

## The Block Contract

Each block below is **executed in the sub-repo it names** (open Claude Code there and run that repo's
`/generate-master-plan` → `/generate-tasks` → `/sdlc-flow`). The brain master-plan coordinates the
*order* and the *seams between repos*. Every block uses the same skeleton:

- **What** — the segment's scope.
- **Why** — why this segment, why now in the cross-repo sequence.
- **Repo** — the sub-repo where this block is built (the execution home).
- **Interfaces / contracts** — the cross-repo seams it consumes from / produces for other repos (data
  contracts, APIs, shared formats). The load-bearing part — what makes the ordering real.
- **Depends on** — the earlier block(s)/repo output(s) this block needs first.
- **Out of scope** — what belongs to a later block or another repo.
- **Ratchet** — *(north-star, capability blocks)* the reusable asset this block leaves behind: a skill,
  workflow, harness, eval, template, dashboard, monitor, policy, or memory artifact. If it leaves none,
  some of the value is being lost (north-star §"Momentum Ratchets").
- **Eval slice** — *(north-star, capability blocks)* how "better/done" is measured — the eval domain
  this block adds to the program's eval engine — or "n/a — deterministic acceptance only".
- **Ladder rung** — *(north-star, capability blocks)* where the block sits on the capability-acquisition
  ladder (solve→repeatable→skill→workflow→harness→eval→automation→monitor→trust→package) and which rung
  it advances to.
- **Acceptance criteria** — observable, true/false; include the target repo's gates as part of "done".

---

## Phase 0 — <name>

### Block A — <name>
- **What:** <segment scope>
- **Why:** <why now in the cross-repo order>
- **Repo:** <which sub-repo this is built in>
- **Interfaces / contracts:** <cross-repo seams consumed/produced; or "self-contained, no cross-repo seam">
- **Depends on:** <earlier block(s) / repo output(s), or "nothing — foundational">
- **Out of scope:** <boundaries; later-block / other-repo work>
- **Ratchet:** <reusable asset left behind — skill/workflow/harness/eval/template/dashboard/monitor/policy/memory; omit only for purely mechanical blocks>
- **Eval slice:** <how "better/done" is measured / the eval domain it feeds; or "n/a — deterministic acceptance only">
- **Ladder rung:** <position on solve→…→package and which rung it advances; omit only for purely mechanical blocks>
- **Acceptance criteria:** <observable conditions; include the target repo's gating checks>

### Block B — <name>
<!-- same skeleton -->

---

<!-- ...continue per phase; the last phase is the hardest cross-repo integration.
     Distant blocks carry the full skeleton but may be flagged forward-looking. -->

---

## Quick Reference Sequence Table

| Phase | Block | Repo | What | Depends on | Role in destination |
|---|---|---|---|---|---|
| 0 | A | <repo> | <short> | <short> | <short> |

---

*Sequenced by cross-repo dependency, not calendar. Each block is built in its named repo; the brain
tracks the order. Pick up where you left off.*
```

## Report

Output the path written and the next step:
```
planning/<concept>/master-plan.md  (<N> phases, <M> blocks across <K> repos)

Blocks, in order:
  - 0.A [<repo>] — <name>
  - 0.B [<repo>] — <name>
  ...

Next (execute the first block in its repo):
  cd <repo-path> && /generate-master-plan <slug>   (or /generate-tasks / /sdlc-flow there)

Then /commit here to save the program plan.
```

If a **new** `planning/<concept>/` folder was created and should be queryable, also emit:
```
Brain RAG: planning/<concept>/ is a new corpus path — add ("planning/<concept>", "plan") to
index_brain.py CORPUS (orchestrator) before the next --rebuild, or it won't be indexed.
```
