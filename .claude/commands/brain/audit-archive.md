# Audit Archive — Scan for planning directories ready to be archived.

This command scans the workspace's `planning/` directories, cross-references each folder's task completion with `state.json` and master plans, and generates a consolidated report recommending candidates for the `/archive` command. **It does not archive anything automatically.**

## Execution Model

Spawn a subagent (Agent tool) to execute all steps below; pass the resolved target directory and this whole Instructions section in its prompt; return its result to the user. This command is an **analytical audit pass** to prevent planning directories from piling up and rot.

## Instructions

### Step 0 — Resolve the Scope and Manifests

1. **Find the brain root.** From the current working directory, walk **up** parent by parent until you locate a `brain.toml`. This directory is `BRAIN_ROOT`.
2. **Determine run scope.** 
   - If running from `BRAIN_ROOT`, perform a **Global Scan** across all repositories listed in `brain.toml`.
   - If running inside a subdirectory (such as `core/bastion`), perform a **Local Scan** targeting only that subdirectory's `planning/` folder.

### Step 1 — Scan Planning Subfolders

3. For each target repository path (e.g. `core/mev/planning/` or root `planning/`):
   - **CRITICAL: Follow symlinks during directory scanning (`find -L` or `os.walk(..., followlinks=True)`).** Leaf repositories' `planning/` directories are symlinks into `_planning/` vaults (`core/_planning/<repo>`, etc.). Skipping symlinks will omit sub-project planning folders.
   - Scan all top-level subdirectories inside every discovered `planning/` folder.
   - Ignore metadata/system directories named `archive`, `artifacts`, `decisions`, `archive-report`, `.playwright-cli`, or worktree paths (`trees/*`). **Do not ignore `sdlc/`** — it is read in this step, not skipped (see below).
   - For each directory, inspect for:
     - `sdlc/sdlc-task-state.json` or `sdlc/sdlc-flow-state.json`: read the top-level `"status"` field. This is the **engine's own authoritative completion record** and is frequently the *only* completion signal a folder has — most closed tickets have no `tasks.json`/`tasks.md` at all. If `"status"` is `"done"`, mark tasks as complete. If `"blocked"` or `"failed"`, mark incomplete regardless of any other signal (a blocked engine run is not done work).
     - `tasks.json`: Check statuses. If `"status"` is `"done"`, `"closed"`, or `"PASS"`, or if all items in `tasks[]` are marked complete, mark tasks as complete.
     - `tasks.md`: Count checked checkboxes (`- [x]`) vs unchecked ones (`- [ ]`). If there are unchecked checkboxes, mark tasks as incomplete unless block is closed in `state.json` or frontmatter.
     - `plan.md` / `notes.md` / `tasks.md`: Parse YAML frontmatter to extract `status` and `title`. If frontmatter `status` is `closed`, `done`, or `completed`, mark block as complete.
   - A folder needs **at least one** positive completion signal (`sdlc-*-state.json` done, `tasks.json`/`tasks.md` complete, or frontmatter closed) to be eligible for Step 2; absence of all three means "no local signal," carried into Step 2 as such — not treated as complete.

### Step 2 — Cross-Reference with state.json and Master Plans (deterministic — script it, do not eyeball it)

Prose substring-matching against `state.json` by hand is what causes this audit to under-report: nested `tracks`/lane structures get mis-walked, matches silently fail, and the folder falls back to looking "open" when it is actually closed. **Treat this step as code, not judgment call.**

4. Load every `state.json` for the repositories/tiers in scope. Write and run a small script (Python is fine) that recursively walks each `state.json` and flattens **every** record carrying an `id`/`slug` and a `status` field — across `tracks`, `focus`, `backlog`, `carryover`, and any other nested list — into one flat lookup table: `(normalized_id, normalized_slug, status, source_file)`. Do this for the whole scope in one pass before matching any folder; do not re-derive it per folder.
5. Normalize both sides identically: lowercase, strip everything but alphanumerics, and drop known track-prefix tokens (`bt`, `en`, `ok`, `hq`, `bw`, `la`, `ticket`, `chore`, etc. — derive the live prefix set from the `id`s actually seen in this scope's `state.json` files, don't hardcode a stale list).
6. For each scanned folder, match its normalized name against the lookup table:
   - **Matched** if the normalized folder name equals, contains, or is contained by a normalized `id` or `slug` (e.g. `EN.3.D-check-selection-parity` ↔ `EN.3.D`; `ticket-vault-aware-state-commits` ↔ `BT.ticket.vault-aware-state-commits`).
   - **No match** — record it explicitly as `state=unmatched`. **Never write `state=unknown` and then classify the folder as "Incomplete/open."** Unmatched is a distinct outcome from "confirmed still open," and the two must never be conflated in the report (this conflation is the specific bug that caused the 2026-08-12 run to silently keep ~59 already-closed folders).
7. If a master plan (such as `master-plan.md` or `plan.md` wave tables) exists in the parent tier, verify all blocks associated with the planning directory are marked as completed there too.
8. Classify each directory into exactly one of four buckets. **`state.json`/master-plan closed status is sufficient evidence on its own — do not require a local Step-1 signal in addition.** Most closed tickets have no `tasks.json`/`tasks.md` at all; requiring one as well as a closed match causes real, already-done work to be silently under-reported (this happened in the first cut of this rule — folders with a `tasks.json` schema carrying no `status` field per item, or no tasks file at all, were wrongly excluded despite an unambiguous closed match). A **local signal only matters when it *contradicts* the state.json match** — that contradiction is itself the finding:
   - **Archive Candidate** — matched `state.json`/master-plan status is closed/complete/done/PASS, **and no local contradiction** (see below) — **OR** no state.json match exists for this tier at all (no block-ID system in use) but a positive local signal (frontmatter/tasks/sdlc-done) confirms completion on its own. If the folder has an active `NOW`/`NEXT` reference in `status.md`, still list it as a candidate but flag it in a **Stale Board References** note (a closed block still pinned to the Operating Board is itself a finding, not a reason to hide the candidate).
   - **Needs Verification — Contradiction** — matched `state.json`/master-plan status is closed/done, **but** a local signal directly contradicts it: `sdlc-task-state.json`/`sdlc-flow-state.json` status is `blocked` or `failed`, or `tasks.md`/`tasks.json` shows unfinished items with no frontmatter override. List these separately with the specific contradiction spelled out (e.g. "state.json: closed; sdlc-task-state.json: blocked — engine run never finished"). **Never silently resolve a contradiction either direction** — not by trusting state.json and archiving it, not by trusting the local file and keeping it quiet.
   - **Keep (confirmed open)** — matched to a `state.json`/master-plan status that is open/in-progress/blocked, or an unfinished `tasks.md`/`tasks.json` with no closing signal anywhere, or an active `NOW`/`NEXT` board reference with no closing signal anywhere.
   - **Unmatched — Needs Manual Verification** — no `state.json`/master-plan match was found (`state=unmatched`) for a tier that does use a block-ID system, AND Step 1 found no positive local completion signal either, so there is no basis to classify it automatically. List these separately; do not fold them into Keep.

### Step 3 — Write the Report

9. Write the audit findings to `planning/archive-report/report.md` in the current planning scope:
   - **OKF Frontmatter**: Type `Note`, title `Archive Candidates Report`, status `active`, layer `[meta]`.
   - **Match-rate summary line**: e.g. "187/202 folders matched a state.json/master-plan record (92%); 15 unmatched." A run with a low match rate is a signal the scan itself is unreliable, not that the fleet is unusually incomplete.
   - **Archive Candidates table**: candidate folder path, block/subject, matched `state.json` status (or "no tier state.json"), which signal fired (sdlc-state / tasks / frontmatter / state.json), and a brief gist of knowledge to harvest.
   - **Stale Board References note**: any Archive Candidate that still has a `NOW`/`NEXT` line in its tier's `status.md` — call out the file and line so it can be cleaned up alongside the archive.
   - **Needs Verification — Contradiction table**: folder path, matched `state.json` status, the contradicting local signal and its exact value, and what a human should check to resolve it. Never in Archive Candidates or Keep.
   - **Keep table**: folders confirmed open, their current status, and the reason (active reference, in-progress, blocked, backlog).
   - **Unmatched table**: folders with no `state.json` match and no local completion signal — path, what was checked, and a one-line suggestion for how a human would resolve it (e.g. "check git log for a merge commit," "no block-ID convention in this tier — check status.md by hand").
   - **Knowledge harvest notes**: Highlight specific architectural details or lessons to extract before archiving (e.g., specific algorithms, error handling, config models).

### Step 4 — Directory Index Integrity (Rule 7)

10. Create or update `planning/archive-report/index.md` in OKF format:
    - Type `Index`, title `Archive Report Directory Index`, layer `[meta]`, listing `report.md`.
11. Update the parent `planning/index.md`:
    - Add a row for `archive-report/` to the active folders list.

### Step 5 — Report Findings

12. Present the final summary table of archive candidates to the user, highlighting the path of the generated `report.md`.
