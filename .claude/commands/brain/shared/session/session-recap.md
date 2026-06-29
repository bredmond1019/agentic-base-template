# Session Recap — Summarize recent brain work and current standing before starting a session.

Reads the handoff file (if present), recent log entries, and status.md to produce a tight
briefing: what was completed recently, where work left off, and the exact next action.
Use this at the start of a brain session instead of the heavier `/prime`.

## Instructions

0. Check for an active handoff: `ls planning/handoff.md 2>/dev/null`.
   - If the file exists, read it and **lead the briefing** with an Active Handoff section:
     ```
     ## Active Handoff — <title from handoff.md>
     <What's in flight and why.>
     Remaining: <bullet list from "Remaining work">
     First command: `<command from "First command after /prime">`
     > Delete `planning/handoff.md` once this session has consumed it.
     ```
   - If absent, skip silently and proceed to step 1.

1. Read `log.md`. Focus on the three most recent dated sections (`## [YYYY-MM-DD]`) and
   their `### <title>` sub-entries. Extract: what was done, why, and any explicit next-step
   notes.

2. Read `planning/status.md`. Extract:
   - Current Focus
   - Any active plans or tasks with pending items
   - Last updated timestamp

3. Output the briefing in this exact format — keep it under 250 words:

---

## Recent Work
<2–4 bullet points from the latest log entries. Use the What/Why language from the log.>

## Where We Left Off
<One paragraph: current focus, what was last completed, anything noted as in-flight or next.>

## Next Action
<Single line: the exact command or action to take next.>
Example: `/draft-post "Builder's Arc PT-BR"` or `/log-work <desc>` or `/sdlc-run planning/…`
If nothing is queued: `Run /prime for full cross-project orientation.`

---

Do not read any source code files. Do not run any commands. This is read-only.

## Context / Files to Read

- `planning/handoff.md` (if present — check with ls first)
- `log.md` (last 3 dated sections)
- `planning/status.md`
