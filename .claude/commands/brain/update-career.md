# Update Career — Make a surgical edit to business/docs/career.md.

## Variables

$ARGUMENTS — description of the update: new lead, lead status change, platform status change,
checklist item completed, checkpoint cleared, rate/positioning change, etc.

## Execution Model

**Run entirely inline. Spawn no subagent.** This is a small, single-file append/edit —
a subagent round trip adds latency without adding value.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user what they want to update.

2. Read `business/docs/career.md` in full.

3. Identify which section the update belongs to:
   - **Warm Leads** — new lead, status change, outcome (converted, dropped, paused)
   - **Contracting Platforms** — status change for Upwork, Toptal, LinkedIn, Wellfound
   - **Business Development Checklist** — mark an item done, add a new item
   - **Competence Checkpoint** — checkpoint cleared or milestone note
   - **Target Rate / Positioning** — rate change or repositioning
   - **Project Sequence** — phase or project status update (prefer syncing from sub-projects via `/sync-status` for routine updates)

4. Make the surgical edit — touch only the relevant section. Do not rewrite or reformat other sections.

5. Update the `**Last updated:**` date at the top to today's date.

6. Report back: which section was changed and a one-line summary of what changed.

## Notes

- For routine project progress updates, use `/sync-status` instead — it pulls from both sub-project STATUS files.
- For business correspondence (emails, meetings), use `/log-correspondence` — that goes to `business/docs/correspondence.md`.
- Never fabricate lead status, rates, or metrics. Record only what the user states.

## Context / Files to Read

- `business/docs/career.md`
