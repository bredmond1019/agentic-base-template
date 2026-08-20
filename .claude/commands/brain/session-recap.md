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

3. Read `planning/state.json` if present. Extract any active `carryover[]` entries (those whose
   `clears_when` is unresolved) — durable constraints, known-issues, env caveats, and deferred
   follow-ons. Skip silently if the file or array is absent.

4. **Warm memory — by budget, never by reflex** (brain decision **D67**). Run
   `wc -w planning/knowledge.md planning/memory.md` and branch on the **combined** count:
   **≤ 2,500 words** → read both in full; **over** → read only the topic list
   (`grep '^### ' planning/knowledge.md planning/memory.md`). These are D35-distilled entries —
   the only retrieval path back to archived plans once `planning/archive/` leaves the corpus.
   Never call `syn recall` here: at session start there is no question yet. Skip if absent.

5. Output the briefing in this exact format — keep it under 250 words:

---

## Recent Work
<2–4 bullet points from the latest log entries. Use the What/Why language from the log.>

## Where We Left Off
<One paragraph: current focus, what was last completed, anything noted as in-flight or next.>

## Carryover
<One line per active `carryover[]` entry: `slug` (`kind`) — gist. Omit this section entirely if there
are none. Flag any `kind: env` caveat that gates the next action (e.g. "rebuild binary first").>

## Warm Memory
<One line. Under budget: the distilled facts bearing on the current focus. Over budget:
`N words across M topics — headings only` plus the topics nearest the focus. Omit if absent.>

## Next Action
<Single line: the exact command or action to take next.>
Example: `/draft-post "Builder's Arc PT-BR"` or `/log-work <desc>` or `/sdlc-flow planning/…`
If nothing is queued: `Run /prime for full cross-project orientation.`

---

Do not read any source code files. This is read-only: the only commands permitted are the
read-only warm-memory probes (`wc -w`, `grep '^### '`) and the `ls` in step 0.

## Context / Files to Read

- `planning/handoff.md` (if present — check with ls first)
- `log.md` (last 3 dated sections)
- `planning/status.md`
- `planning/state.json` (the `carryover[]` array, if present)
- `planning/knowledge.md` + `planning/memory.md` — **under the warm-memory budget** (D67),
  never both in full when the combined `wc -w` exceeds 2,500 words
