# Briefing — Master orientation across all projects

Read the key brain docs and produce a tight cross-project briefing. Use at the start of any
brain-level session, or any time you need a full picture. **`brain.toml`-driven** — reads the tier
rollups and cache cards rather than individual project status files. Read-only; does not modify files.

## Instructions

1. Read `brain.toml` to discover tiers and repos.

2. Read the **operating state**:
   - `planning/status.md` — Operating Board (NOW/NEXT/BLOCKED, current focus)
   - `core/planning/status.md` — core sub-brain rollup (if exists)
   - `portfolio/planning/status.md` — portfolio sub-brain rollup (if exists)
   - `side/planning/status.md` — side sub-brain rollup (if exists)
   - For every `[[repos]]` entry with `tier == "_root"` and `slug != "brain"`: read its `cache_doc`

3. Read the **business docs**:
   - `docs/career.md` — contracting strategy and checkpoint status
   - `docs/progress.md` — launch stage and immediately actionable items
   - `docs/linkedin.md` — platform status
   - `docs/business/pipeline.md` — active leads
   - `docs/content/ideas.md` — content backlog

4. Output the briefing in this format — keep it under 500 words:

---

## Project Status

### Company Brain
Current focus: <NOW line from planning/status.md Operating Board>
<2 bullets: primary program status, what's blocked>

### core (Bastion sub-brain)
<Summary from core/planning/status.md Momentum + rollup table — active blocks, key blockers>

### portfolio
<One-liner per repo from the rollup table in portfolio/planning/status.md>

### side
<One-liner per repo from the rollup table in side/planning/status.md>

### _root repos
<One sentence each for learn-ai and base-template from their cache cards>

## Business Operations

### Launch Stage
<One sentence from docs/progress.md — current stage and the gate>

### Platform Status
<LinkedIn / Upwork / Toptal — one line each: ✅ live or ⬜ pending>

### Active Leads
<From pipeline.md — leads with stage and open next action>

## Content Queue
<From ideas.md — Confirmed/Committed pieces, or next piece to draft and what milestone it's tied to>

## Suggested Next Action
<One sentence: the highest-value thing to work on right now, per the Operating Board>

---

## Context / Files to Read

- `brain.toml`
- `planning/status.md`
- `core/planning/status.md` (if exists)
- `portfolio/planning/status.md` (if exists)
- `side/planning/status.md` (if exists)
- Each `cache_doc` from brain.toml where `tier == "_root"` and `slug != "brain"`
- `docs/career.md`
- `docs/progress.md`
- `docs/linkedin.md`
- `docs/business/pipeline.md`
- `docs/content/ideas.md`
