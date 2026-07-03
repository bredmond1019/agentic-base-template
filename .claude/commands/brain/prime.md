# Prime — Orient to this brain or sub-brain tier at the start of a session.

This command is **`brain.toml`-driven**. It behaves differently based on CWD:
- **At Brain Root (HQ):** Orients to the full company brain (HQ + all tiers). Reads HQ top-level + 4 tier rollups + _root caches.
- **In a Sub-brain Tier (core, portfolio, side, client):** Orients to this tier only (tier README/CLAUDE/index/status + per-repo cache cards).

## Variables

$ARGUMENTS — optional:
  - **At HQ root:**
    (empty)     — bare: HQ + 4 tier rollups + _root caches (default, lightest)
    `core`      — also read each core/ repo's live `planning/status.md`
    `portfolio` — also read each portfolio/ repo's live `planning/status.md`
    `side`      — also read each side/ repo's live `planning/status.md`
    `client`    — also read each client/ repo's live `planning/status.md`
    `--all`     — also read every repo's live `planning/status.md`
  - **In a Sub-brain tier:**
    (empty)       — tier orientation: this sub-brain's README/CLAUDE/index/status + per-repo cache cards (default, lightest)
    `<repo-slug>` — also read that repo's live `<repo-slug>/planning/status.md` (e.g. `bastion`)
    `--all`       — also read every tier repo's live `planning/status.md`

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

### Step 1 — Resolve CWD / Context

Check if `brain.toml` exists in the current directory:
- **If present (HQ Brain root):** Proceed to **Step 2a (HQ Orientation)**.
- **If absent (Sub-brain tier):** The current directory is a sub-brain tier (`core`, `portfolio`, `side`, or `client`). Proceed to **Step 2b (Tier Orientation)**.

---

### Step 2a — HQ Brain Orientation (CWD has brain.toml)

1. Read in order:
   - `brain.toml` — the manifest (tiers + repos)
   - `README.md` — project index and quick status
   - `CLAUDE.md` — standing rules and structure
   - `planning/status.md` — Operating Board (NOW/NEXT/BLOCKED)
   - `planning/state.json` — the `carryover[]` array (durable constraints, known-issues, env caveats,
     and not-yet-ticketed deferred follow-ons that must survive across handoffs). Skip if absent.

2. Read tier rollups: For each tier (`core`, `portfolio`, `side`, `client`), read `<tier>/planning/status.md` if it exists.

3. Read `_root` caches: Find every `[[repos]]` entry where `tier == "_root"` and `slug != "brain"`. Read `<BRAIN_ROOT>/<cache_doc>` for each.

4. Drill-down (only if $ARGUMENTS is set): For the selected tier (or all if `--all`), read each matching repo's live `<status_file>` listed in `brain.toml`.

5. Summarize (read-only):
   - **What this brain is** — one paragraph (what it tracks, who it's for, primary program).
   - **Active Handoff** — lead with this if present.
   - **Operating Board** — current focus, NOW/NEXT/BLOCKED from `planning/status.md`.
   - **Tier summaries** — indented bullet points for each tier (e.g., `core (Bastion Program)`, `portfolio`, `side`, `client`), structured as:
     - **<tier-name>** (e.g. core (Bastion Program)): <overview of the tier rollup as a whole (momentum, blockers)>
       - `<repo-slug>`: <repo status/updates from the rollup table/cache card>
   - **`_root` repos** — one sentence each from the cache cards.
   - **Carryover** — active `carryover[]` entries (slug, kind, one-line gist).
   - **Standing rules** — key items from CLAUDE.md.

---

### Step 2b — Sub-brain Tier Orientation (CWD has NO brain.toml)

1. Resolve the tier name (basename of the current directory: `core`, `portfolio`, `side`, or `client`).
   Optionally confirm the tier's repo set: walk up to the parent directory to find `brain.toml` (`BRAIN_ROOT`). The repos in this tier are the `[[repos]]` entries in `brain.toml` whose `tier` matches this tier's name.

2. Read in order (relative to current directory):
   - `README.md` — what this sub-brain is
   - `CLAUDE.md` — this tier's standing rules (inheriting company-brain rules)
   - `index.md` — sub-brain index
   - `planning/status.md` — the tier rollup (generated per-repo table + Momentum)
   - `planning/state.json` — the `carryover[]` array. Skip if absent.

3. Read per-repo cache cards: Read `docs/projects/index.md`, then each `docs/projects/<slug>.md` cache card for the repos in this tier.

4. Drill-down (only if $ARGUMENTS is set): For the named repo slug (or all if `--all`), read `<repo-slug>/planning/status.md`.

5. Summarize (read-only):
   - **What this sub-brain is** — one paragraph (the tier, its repos, its role/primary program).
   - **Active Handoff** — lead with this if present.
   - **Operating Board** — current focus + Momentum from `planning/status.md`.
   - **Repos in this tier** — one line each from the cache cards.
   - **Carryover** — active `carryover[]` entries (slug, kind, one-line gist).
   - **Standing rules** — key items from CLAUDE.md.

---

## Context / Files to Read

- **At HQ root:**
  - `brain.toml`
  - `README.md`
  - `CLAUDE.md`
  - `planning/status.md`
  - `planning/state.json` (if present)
  - `<tier>/planning/status.md` (for each tier, if exists)
  - Each `cache_doc` from `brain.toml` where `tier == "_root"` and `slug != "brain"`
  - Drill-down: matching repo's `status_file` from `brain.toml`
- **In a Sub-brain Tier:**
  - `README.md`
  - `CLAUDE.md`
  - `index.md`
  - `planning/status.md`
  - `planning/state.json` (if present)
  - `docs/projects/index.md` + each `docs/projects/<slug>.md`
  - Optional: `../brain.toml`
  - Drill-down: `<slug>/planning/status.md`
