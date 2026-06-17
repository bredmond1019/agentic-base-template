---
name: log-work
description: >-
  Wrap up completed work — sync planning/STATUS.md (flip statuses to Done,
  advance Current focus, bump Last updated, log deviations), append a dated DEVLOG.md
  entry with the git diff --stat, prompt to record any settled choice in planning/decisions/, and sync the
  company-brain docs. Use when the user says "log work", "wrap up", or finishes a block.
  Never edits MASTER_PLAN.md.
---

# Log Work — Sync STATUS.md and append a DEVLOG entry for completed work.

## Inputs

Optional free-text explanation of what was done today, taken from the user's request. May be
brief ("ported the credibility-fixes spec and re-ran validate:content") or detailed (several
sentences). If provided, it is woven into the DEVLOG prose entry as the primary narrative —
do not discard or summarise it down. If omitted, derive the narrative from git history and the
task spec alone.

## Instructions

1. Read `planning/STATUS.md` and the current task spec at `planning/tasks/<name>/tasks.md`.
2. Run `git diff --stat` and `git log --oneline -10` to see what changed.

3. **Determine STATUS.md changes — ask before writing if uncertain.**
   - From git history, the task spec, and the input, identify which blocks are newly complete
     and what the next focus should be.
   - If you are confident (e.g. a block's acceptance criteria are clearly met and git confirms
     it), state the proposed changes and proceed.
   - If you are NOT certain which block(s) to flip to `Done`, or which block becomes the new
     current focus, STOP and ask the user:
     > "Before I update STATUS.md, I want to confirm: should I mark [block X] as done and
     > set the current focus to [block Y]? Or did something differ from the plan?"
     Wait for confirmation before writing any STATUS.md changes.
   - Changes to make once confirmed:
     - Flip newly-completed block statuses to `Done`.
     - Update the **Current focus** line to the next block.
     - Bump the **Last updated** date.
     - Append to the **Decisions & Deviations** log if reality diverged from the plan.

4. Append a new dated entry to `DEVLOG.md` in this exact format:
   ```
   ## YYYY-MM-DD

   <One paragraph of prose: what was built or changed, why, and any notable decisions or
   surprises. If the input was provided, use it as the primary narrative — include the
   user's own words and context, not just what git can infer.>

   ```diff
   <git diff --stat output, pasted verbatim>
   ```
   ```

5. **If a settled architectural choice was made during this work, record it as an atomic
   decision — ask first, never auto-author.**
   - Ask the user: "A settled choice came up — should I record it as a decision in
     `planning/decisions/`?" Wait for confirmation. Never write a decision unprompted.
   - On confirmation: read `planning/decisions/index.md` to find the last decision number;
     the new number is `last + 1` (D{N+1}).
   - Create `planning/decisions/D{N+1}-<kebab-title>.md` with OKF frontmatter:
     ```yaml
     ---
     type: Decision
     title: D{N+1} — Short Title
     description: One-sentence summary.
     ---
     ```
     followed by the body in the established form:
     ```
     ### D{N+1} — Short Title
     **Decided:** <what was decided>
     **Why:** <the reasoning>
     **Rejected:** <alternatives considered and why not> (optional)
     ```
   - Register it in `planning/decisions/index.md` by appending a row to the table (newest at
     the bottom — append-only; never edit or renumber prior entries).
6. Never edit the master plan file (`MASTER_PLAN.md`).

7. **Sync the company brain.** After STATUS.md and DEVLOG.md are confirmed:
   - Read `../docs/projects/{{SLUG}}.md` in the company brain.
   - Update the **Current Status** date and focus line to match the new STATUS.md state.
   - Update the Status column in the 13-spec table for any rows that changed.
   - Open `../README.md` and update the Quick Status section for learn-ai: the Current
     focus line and any changed status rows.
   - Surgical updates only — do not rewrite sections that didn't change.
   - If the brain docs are already in sync with STATUS.md, skip this step silently.

## Context / Files to Read

- `planning/STATUS.md`
- The current `planning/tasks/<name>/tasks.md`
- `DEVLOG.md`
- `../docs/projects/{{SLUG}}.md` (brain sync target)
- `../README.md` (brain sync target)
