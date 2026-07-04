# Weekly Plan — Produce a prioritized action list for the week.

Read the current state of all projects, content, and contracting, then output a concrete weekly agenda.
**`brain.toml`-driven** — reads tier rollups and cache cards, not individual project status files.
Read-only; does not modify any files.

## Instructions

1. Read `brain.toml` to discover tiers and repos.

2. Read the **operating state**:
   - `planning/status.md` — Operating Board (NOW/NEXT/BLOCKED)
   - `core/planning/status.md` — core sub-brain rollup (if exists)
   - `portfolio/planning/status.md` — portfolio sub-brain rollup (if exists)
   - `side/planning/status.md` — side sub-brain rollup (if exists)
   - For every `[[repos]]` entry with `tier == "_root"` and `slug != "brain"`: read its `cache_doc`

3. Read the **business + content docs**:
   - `business/docs/career.md` — competence checkpoint status, active leads, open checklist
   - `docs/content/ideas.md` — confirmed/committed pieces ready to move
   - `docs/content/blog-tracker.md` — last post date (cadence check: flag if >3 weeks)
   - `business/docs/progress.md` — current stage and immediately actionable items
   - `business/docs/linkedin.md` — what's drafted vs. live
   - `business/docs/pipeline.md` — leads with open next actions

4. Output the plan in this exact format — keep it under 400 words:

---

## Week of <date>

### Building
<2–3 concrete tasks from the Operating Board NOW/NEXT + tier rollups. Name the exact block or repo.
If a project is blocked, say so and name the blocker.>

### Content
<What to write or publish this week. If a Confirmed piece is ready, name it and the publish target.
If nothing is ready, name the next piece to draft and what project milestone it's tied to.
Flag if the cadence has slipped (no post in >3 weeks).>

### Business
<Gate-aware: if the competence checkpoint is not cleared, list only pre-checkpoint open tasks
(site pages, copy, profile, research conversations). If cleared: active lead next actions and
platform tasks. One bullet per item — max 3.>

### Visibility
<LinkedIn, GitHub, or profile/presence tasks. Name the specific action — not "update LinkedIn"
but "go live with the headline copy in business/docs/linkedin.md Section 1". Skip if nothing actionable.>

### Protect
<One line: what is off-limits this week.>

---

Do not read source code files. Do not suggest tasks outside the documented strategy in business/docs/career.md.

## Context / Files to Read

- `brain.toml`
- `planning/status.md`
- `core/planning/status.md` (if exists)
- `portfolio/planning/status.md` (if exists)
- `side/planning/status.md` (if exists)
- Each `cache_doc` from brain.toml where `tier == "_root"` and `slug != "brain"`
- `business/docs/career.md`
- `docs/content/ideas.md`
- `docs/content/blog-tracker.md`
- `business/docs/progress.md`
- `business/docs/linkedin.md`
- `business/docs/pipeline.md`
