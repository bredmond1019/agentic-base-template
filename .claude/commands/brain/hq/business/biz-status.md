# Biz Status — Business dashboard: launch stage, platforms, leads, and content queue.

Read the business-facing docs and output a concise business dashboard.
Use this to quickly orient on the business side without wading through all project status.
Read-only — does not modify any files.

## Instructions

1. Read `docs/progress.md` — extract the current stage callout and what's blocking.
2. Read `docs/linkedin.md` — extract Platform Status table (Section 7) for LinkedIn, and note any post that's queued or live.
3. Read `docs/business/pipeline.md` — extract Active Leads table (name, stage, next action, gate status).
4. Read `docs/content/ideas.md` — identify any Confirmed or Committed pieces ready to publish.
5. Read `docs/career.md` — note competence checkpoint status and whether post-checkpoint tasks are unlocked.

6. Output in this exact format — keep it tight and scannable:

---

## Business Status — <today's date>

### Launch Stage
<One sentence: what stage we're in and what the current gate is.>
<One sentence: what unblocks the next stage.>

### Platform Status
- **LinkedIn:** [✅ live / ⬜ not updated] — <one-line note on headline/about/posts>
- **Upwork:** [✅ live / ⬜ not started]
- **Toptal:** [✅ applied / ⬜ gated — after competence checkpoint]
- **Rust repos public:** [✅ / ⬜ not yet — Brandon's call]

### Active Leads
<List each lead from pipeline.md as: "- [Name] — Stage: X — Next: Y [🔒 if gated]">
<If pipeline is empty: "No active leads. Both warm leads gated on competence checkpoint.">

### Content Queue
<List any Confirmed/ready-to-publish pieces: title + target platform + any blocking note.>
<If nothing confirmed: "Nothing ready to publish. Next post: [name the next piece and what it's tied to].">

### Gate Status
- **Competence checkpoint:** [Pending / Cleared] — unlocks after Project D ships

### Next Business Action
<One sentence: the single most actionable business thing to do right now.>

---

## Context / Files to Read

- `docs/progress.md`
- `docs/linkedin.md`
- `docs/business/pipeline.md`
- `docs/content/ideas.md`
- `docs/career.md`
