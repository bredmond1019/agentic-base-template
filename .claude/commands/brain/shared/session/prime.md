# Prime — Orient to this repo at the start of a session.

This command is **`brain.toml`-driven**. Bare invocation reads HQ top-level + the four tier rollups
(compact generated tables) + `_root` repo cache cards — far fewer files than a flat all-projects scan.
Pass a tier flag to drill into live per-repo status files.

## Variables

$ARGUMENTS — optional:
  (empty)     — bare: HQ + 4 tier rollups + _root caches (default, lightest)
  `core`      — also read each core/ repo's live `planning/status.md`
  `portfolio` — also read each portfolio/ repo's live `planning/status.md`
  `side`      — also read each side/ repo's live `planning/status.md`
  `client`    — also read each client/ repo's live `planning/status.md`
  `--all`     — also read every repo's live `planning/status.md`

## Instructions

### Step 0 — Handoff check

Run `ls planning/handoff.md 2>/dev/null`. If the file exists, read it and **lead the summary** with:
```
## Active Handoff — <title from handoff.md>
<What's in flight and why.>
Remaining: <bullet list from "Remaining work">
First command: `<command from "First command after /prime">`
> Delete `planning/handoff.md` once this session has consumed it.
```
If absent, skip silently.

### Step 1 — Core orientation (always)

Read in order:
- `brain.toml` — the manifest (tiers + repos)
- `README.md` — project index and quick status
- `CLAUDE.md` — standing rules and structure
- `planning/status.md` — Operating Board (NOW/NEXT/BLOCKED)

### Step 2 — Tier rollups (always)

For each tier (`core`, `portfolio`, `side`, `client`): read `<tier>/planning/status.md` if it exists.
Each file is a compact generated rollup table plus hand-maintained Momentum — one read gives the
whole tier.

### Step 3 — `_root` repo caches (always)

From `brain.toml`, find every `[[repos]]` entry where `tier == "_root"` and `slug != "brain"`.
Read `<BRAIN_ROOT>/<cache_doc>` for each (lightweight cache cards, not full status files).

### Step 4 — Drill-down (only if $ARGUMENTS is set)

For the selected tier (or all tiers if `--all`): additionally read each matching repo's live
`<status_file>` as listed in `brain.toml`. Use when per-block detail beyond the rollup is needed.

### Step 5 — Summarize (read-only; do not edit any file)

Output in plain prose:

1. **What this brain is** — one paragraph (what it tracks, who it's for, primary program).
2. **Active Handoff** — lead with this if present (from Step 0).
3. **Operating Board** — current focus, NOW/NEXT/BLOCKED from `planning/status.md`.
4. **Tier summaries** — for each tier rollup read: one short paragraph on what's active and blocked.
   For a drill-down tier: per-repo one-liner (current block, status, blocker if any).
5. **`_root` repos** — one sentence each from the cache cards (learn-ai, base-template).
6. **Standing rules** — key items from CLAUDE.md worth flagging for this session.

## Context / Files to Read

Always:
- `brain.toml`
- `README.md`
- `CLAUDE.md`
- `planning/status.md`
- `core/planning/status.md` (if exists)
- `portfolio/planning/status.md` (if exists)
- `side/planning/status.md` (if exists)
- `client/planning/status.md` (if exists)
- Each `cache_doc` from brain.toml where `tier == "_root"` and `slug != "brain"`

Drill-down (per $ARGUMENTS): each matching repo's `status_file` from brain.toml.
