# Update Progress — Mark a business task block complete in the state.json graph and regenerate the board.

## Variables

$ARGUMENTS — the BZ.* block ID (e.g. `BZ.1.C`) or a description of what was completed, and optionally assignment updates (e.g., priority or due date).

## Execution Model

Spawn a self subagent (Agent tool, `model: "self"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Priority Rubric (P0–P3)
When assigning priority, use this anchored rubric:
- **P0**: Blocks revenue now or due <~1 week
- **P1**: Enables revenue / this month
- **P2**: Normal, default
- **P3**: Someday

## Instructions

1. If $ARGUMENTS is not provided, stop and ask: "What did you complete?"

2. Read `business/planning/state.json`.

3. Identify the `BZ.*` block in the `tracks` array that matches $ARGUMENTS (either by exact ID or by title/description matching).

4. Update the block in `state.json`:
   - If the task was completed, set its `status` to `"closed"`.
   - If $ARGUMENTS includes a priority change, update the `priority` field using the Priority Rubric.
   - If $ARGUMENTS includes a due date change, update the `due` field (ISO format `YYYY-MM-DD`).

5. Run `mev emit-state --write` to regenerate the HQ board (which now includes the unified priority-ranked view).

6. Show the user:
   - Confirmation of the block(s) updated and closed.
   - The output of the board regeneration.

## Notes

- The status-of-record for business progress is `business/planning/state.json`. Do NOT edit `business/docs/progress.md` for status changes; it is narrative-only.
- Only touch items that match $ARGUMENTS.

## Context / Files to Read

- `business/planning/state.json`
