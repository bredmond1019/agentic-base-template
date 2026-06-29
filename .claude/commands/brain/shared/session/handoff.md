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

Run:
- `git log --oneline -10` — recent commits
- `git diff --stat` — uncommitted changes
- `git status` — untracked / staged state

### Step 2 — Write `planning/handoff.md`

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
Pull from git log. Be specific: "updated docs/career.md Upwork section + planning/status.md
focus line" not "updated docs".>

## Remaining work
<Bulleted list of what's left, in priority order. Mark blockers explicitly.>

## Open questions / choices
<Unresolved decisions or things to verify before proceeding. If none: "None — clear to proceed.">

## Context the next agent needs
<Non-obvious constraints, gotchas, or state the next agent would lose time re-deriving.
Omit if everything is covered above.>

## First command after `/prime`
`<exact command to run first>`
```

Fill every section. Do not leave placeholder text.

### Step 3 — Invoke `/log-work`

Invoke the `/log-work` skill. Pass $ARGUMENTS if provided so the log entry gets the same
narrative. The brain's `/log-work` will ask for the narrative if not passed — let that flow.

### Step 4 — Invoke `/commit`

After `/log-work` completes, invoke the `/commit` skill. It will pick up `planning/handoff.md`
plus any other uncommitted changes and ask for confirmation before committing.

### Step 5 — Report

Tell the user:
- `planning/handoff.md` was written (or updated)
- What was logged and committed
- The exact sequence to resume:
  1. Open a fresh Claude Code session in `agentic-portfolio/`
  2. Run `/prime` — it will surface the handoff automatically
  3. Run the first command listed in the handoff

## Context / Files to Read

- `planning/status.md`
- `log.md` (last 3 entries)
- `planning/handoff.md` (if it already exists)
