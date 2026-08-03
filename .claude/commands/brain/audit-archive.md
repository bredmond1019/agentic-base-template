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
   - Ignore metadata/system directories named `archive`, `artifacts`, `decisions`, `archive-report`, `sdlc`, `.playwright-cli`, or worktree paths (`trees/*`).
   - For each directory, inspect for:
     - `tasks.json`: Check statuses. If `"status"` is `"done"`, `"closed"`, or `"PASS"`, or if all items in `tasks[]` are marked complete, mark tasks as complete.
     - `tasks.md`: Count checked checkboxes (`- [x]`) vs unchecked ones (`- [ ]`). If there are unchecked checkboxes, mark tasks as incomplete unless block is closed in `state.json` or frontmatter.
     - `plan.md` / `notes.md` / `tasks.md`: Parse YAML frontmatter to extract `status` and `title`. If frontmatter `status` is `closed`, `done`, or `completed`, mark block as complete.

### Step 2 — Cross-Reference with state.json and Master Plans

4. Load all `state.json` files for the corresponding repositories/tiers across `BRAIN_ROOT`.
5. Extract the state of all blocks across tracks and focus lists.
6. Match each planning subfolder name to its block ID:
   - Perform **flexible / substring matching**: folder names like `EN.3.D-check-selection-parity` match block ID `EN.3.D`; `ticket-vault-aware-state-commits` matches block ID `BT.ticket.vault-aware-state-commits`.
   - Normalize names by lowercasing and stripping non-alphanumeric characters.
   - If the block status in `state.json` is `"closed"`, `"complete"`, `"done"`, or `"PASS"`, the state is **complete**.
7. If a master plan (such as `master-plan.md` or `plan.md` wave tables) exists in the parent tier:
   - Verify if all blocks associated with the planning directory are marked as completed.
8. Classify directories as **Archive Candidates** if:
   - They correspond to a closed block in `state.json` / master plans.
   - **OR** their frontmatter status is `closed`/`done`/`completed`.
   - **OR** their local tasks (`tasks.json` or `tasks.md` checklists) are 100% complete.
   - **AND** they have no active references as `NOW` or `NEXT` in the `status.md` Operating Board.

### Step 3 — Write the Report

9. Write the audit findings to `planning/archive-report/report.md` in the current planning scope:
   - **OKF Frontmatter**: Type `Note`, title `Archive Candidates Report`, status `active`, layer `[meta]`.
   - **Summary Table**: List candidate folder path, block/subject, `state.json` status, tasks completion, and a brief gist of knowledge to harvest.
   - **Keep Table**: List folders to keep, their current status, and the reason they should be preserved (e.g., active reference, in-progress, backlog).
   - **Knowledge harvest notes**: Highlight specific architectural details or lessons to extract before archiving (e.g., specific algorithms, error handling, config models).

### Step 4 — Directory Index Integrity (Rule 7)

10. Create or update `planning/archive-report/index.md` in OKF format:
    - Type `Index`, title `Archive Report Directory Index`, layer `[meta]`, listing `report.md`.
11. Update the parent `planning/index.md`:
    - Add a row for `archive-report/` to the active folders list.

### Step 5 — Report Findings

12. Present the final summary table of archive candidates to the user, highlighting the path of the generated `report.md`.
