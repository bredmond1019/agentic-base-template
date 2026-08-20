# Handoff — Hand off an in-flight brain session to a fresh agent.

Use this when the current session has grown large enough that continuing in a new context is
better than pressing on. Writes `planning/handoff.md` so the next agent orients instantly
after running `/prime`, then logs and commits.

## Variables

$ARGUMENTS — optional free-text note to include in the handoff (e.g. "focus on the services
             page next, the PT post is drafted and ready to review"). If omitted, the agent
             derives context from git history and status.md.

## Execution Model

Run inline — do NOT spawn a subagent. `/log-work` and `/commit` are invoked as Skill tool
calls from the main agent context; they have their own confirmation gates.

## Instructions

### Step 1 — Gather current state

Read:
- `planning/status.md` — current focus and active work
- `log.md` — the three most recent entries (for narrative context)
- `planning/handoff.md` — if it exists, read it (you are updating it, not replacing blindly)
- `planning/state.json` — the existing `carryover[]` (you are appending to it, not duplicating)
- `docs/state/state-schema.md` — the `carryover[]` section, for the field shape

Run:
- `git log --oneline -10` — recent commits
- `git diff --stat` — uncommitted changes
- `git status` — untracked / staged state

### Step 2 — Drain durable context into `state.json` `carryover[]`

**This is what keeps `handoff.md` disposable.** Before writing the handoff, route anything that must
outlive *this* handoff (so the next one can't overwrite it away) into the right durable home — do **not**
leave it living only in the prose below:

- **Committed, sequenced work** with real dependencies → a `tracks[].blocks[]` block in the target repo.
- **Free-floating ideas/chores** not on a critical path → HQ `backlog[]` (via `/backlog-ticket`).
- **Work only a human can do** — a decision only the operator can make, a credential only they hold,
  a judgement call, a thing they must look at → an `{"type":"operator", ...}` edge on the block it
  gates, per the operator-work rule below. **Ask this before reaching for `carryover[]`**, because
  the two look alike at write time and behave nothing alike afterwards: a carryover entry gates
  nothing, so operator work parked there is never forced. Measured 2026-08-19 — **30 of the fleet's
  202 `carryover[]` entries are operator work misfiled this way.**
- **Permanently-true facts** — a gotcha still true next month, a deliberate non-fix nobody intends to
  reverse, a load-bearing measured number → `reference[]`, not `carryover[]`. The signal is a finding
  with no `clears_when` because nothing will ever make it stop being true.
  See `docs/state/reference-container-schema.md`.
- **Durable caveats, environmental notes, drifted surfaces, and not-yet-ticketed deferred follow-ons** →
  append a `carryover[]` entry to `planning/state.json`. This is the in-between lane the others miss —
  work-class findings that eventually clear. The kind vocabulary is exactly four (HQ D72):
  - `kind: defect` — a real unticketed bug with a fix, not yet filed as its own block.
  - `kind: deferred` — a real follow-on you haven't ticketed yet; promote it to a block/backlog when ready.
  - `kind: drift` — a doc, comment, block title or generated surface out of step with the code or graph.
  - `kind: env` — a transient environmental caveat (e.g. "installed binary is stale, rebuild first").

  `constraint` and `known_issue` are **retired** — D72 removed them and okf-core now preserves them
  only through its `Unknown(String)` fallback. Do not mint new entries with either.

  Follow the `carryover[]` field shape in `docs/state/state-schema.md` — the authoritative table — for
  the required core (`slug`, `scope`, `kind`, `text`, `created`) plus the optional fields worth naming
  inline here since this is what agents actually read while appending:
  - `priority` (int, `0..=3`) — value if resolved, same rubric as `tracks[].blocks[]`; omit when the
    entry carries no value judgement.
  - `blocks` (array) — edges to the work this entry blocks (`{type:"block",repo,id}` /
    `{type:"external",what}`), feeding the same reverse-topological `min`-propagation that derives
    `effective_priority`. Omit (don't write `[]`) when it blocks nothing.
  - `finding_id` (string) — free-form join key so `mev carryover` can correlate the same finding filed
    in several repos.
  - `related`, `reviewed`, `snoozed_until` — as documented in `docs/state/state-schema.md`.
  - `clears_when` — either the legacy human-readable string (subjective conditions only), or a **typed
    predicate** mev can evaluate: `block_closed` (`repo`, `id`), `file_exists` (`path`), `file_contains`
    (`path`, `pattern`), `command_exits_zero` (`command`) — each takes an optional `note`. Prefer the
    typed form whenever the condition is checkable.

  **Only entries with a typed `clears_when` predicate are machine-evaluable by `mev carryover`** — a
  prose `clears_when` (or none) lands the entry in its not-evaluable lane; `priority` and `finding_id`
  are what make it rankable and cross-repo-correlatable.

  Keep it valid JSON; append, don't duplicate an existing slug. **Delete** any existing `carryover[]`
  entry whose `clears_when` resolved this session.

The handoff prose in Step 3 then *points at* these slugs instead of being their only home.

**File operator work as a graph edge, never as prose.** Anything this session is leaving for the
operator to decide, review, approve, or judge — a call only they can make, a credential only they
hold, a thing they must look at — is filed as a `{"type":"operator", slug, exit, start, what?}`
entry in `depends_on` on the block(s) it gates, **not** written into the handoff prose, a `note`
field, or an `## Open questions` bullet. `slug` is kebab-case, prefixed `operator-`; `exit` names
the artifact whose existence ends the gate (never a description of the work — e.g. `planning/
decision-rate-card.md exists`, not "decide on pricing"); `start` is a paste-ready command the
operator runs to begin. If the decision reduces to a single yes/no on a fixed payload, use
`{"type":"approval", slug, what, digest}` instead. **Why:** an operator (or approval) edge
inherits the effective priority of everything it gates and surfaces in `/next` as the reason work
cannot start; prose in a handoff file surfaces nowhere and is exactly how these get left for days.
Skip entirely if this repo has no `planning/state.json` — say so explicitly in the handoff instead
and name who is expected to file it once one exists.

### Step 3 — Write `planning/handoff.md`

Create or overwrite `planning/handoff.md` using this template. Be specific: the next agent
has zero session memory and relies entirely on this file + `/prime` to orient.

```markdown
---
type: Handoff
created: YYYY-MM-DD
---

# Handoff — <5–10 word title: what's in flight>

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why
<One paragraph. State the goal, why it matters right now, and any non-obvious background.
Reference specific file paths, doc sections, or business context where helpful.>

## Completed this session
<Bulleted list of concrete things done — commits made, docs updated, decisions reached.
Pull from git log. Be specific: "updated business/docs/career.md Upwork section + planning/status.md
focus line" not "updated docs".>

## Remaining work
<Bulleted list of what's left, in priority order. Mark blockers explicitly. For anything durable
you drained in Step 2, *point at the home* rather than re-describing it: "see `state.json` carryover
`cortex-leaf-migration`" or "block `BA.11.C` in `core/bastion`".>

## Open questions / choices
<Name the `operator-`/`approval` slugs already filed in `depends_on` (Step 2) and what each
gates — this section points at the graph, it does not substitute for it. If none: "None — clear
to proceed.">

## Context the next agent needs
<Only ephemeral, this-session framing the next agent needs to read the above. Durable constraints,
known-issues, and env caveats belong in `state.json` `carryover[]` (Step 2) — reference their slugs
here, don't restate them. Omit this section if Step 2 captured everything.>

## First command after `/prime`
`<exact command to run first>`
```

Fill every section. Do not leave placeholder text.

### Step 4 — Invoke `/log-work`

Invoke the `/log-work` skill. Pass $ARGUMENTS if provided so the log entry gets the same
narrative. The brain's `/log-work` will ask for the narrative if not passed — let that flow.

### Step 5 — Invoke `/commit`

After `/log-work` completes, invoke the `/commit` skill. It will pick up `planning/handoff.md`,
the `state.json` `carryover[]` edits, plus any other uncommitted changes and ask for confirmation
before committing.

### Step 6 — Report

Tell the user:
- `planning/handoff.md` was written (or updated)
- Any `operator`/`approval` edges filed this session, and what they gate
- What was logged and committed
- The exact sequence to resume:
  1. Open a fresh Claude Code session:
     - **At HQ root:** open in `agentic-portfolio/`
     - **In a sub-brain tier:** open in this sub-brain directory (e.g. `agentic-portfolio/core/`), not the brain root
  2. Run `/prime` — it will surface the handoff automatically
  3. Run the first command listed in the handoff

## Context / Files to Read

- `planning/status.md`
- `log.md` (last 3 entries)
- `planning/handoff.md` (if it already exists)
- `planning/state.json` (existing `carryover[]`) + `docs/state/state-schema.md` (`carryover[]` field shape)
