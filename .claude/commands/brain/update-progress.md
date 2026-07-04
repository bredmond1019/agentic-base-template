# Update Progress — Check off completed items in business/docs/progress.md and update the current position callout.

## Variables

$ARGUMENTS — what was completed. Be specific enough to identify the item(s) in the checklist.
Examples:
  - `"manual site review done — site approved"`
  - `"Upwork profile live"`
  - `"Builder's Arc PT post published 2026-06-22"`
  - `"first research conversation with a lead"`
  - `"competence checkpoint cleared"`

## Execution Model

Spawn a Haiku subagent (Agent tool, `model: "haiku"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Instructions

1. If $ARGUMENTS is not provided, stop and ask: "What did you complete? Describe it and I'll check it off in progress.md."

2. Read `business/docs/progress.md` in full.

3. Identify the checklist item(s) that match $ARGUMENTS:
   - In the **Where You Are Now** section: change `[ ]` to `[x]` for the matching item(s)
   - In the relevant **Stage** section: change `[ ]` to `[x]` for the matching task(s)
   - If a whole stage is now complete, mark its **Done when:** line with `[x]`

4. Rewrite the **CURRENT POSITION** callout at the top to reflect the new state:
   - If the completed item was the gate blocking a stage, advance to the next stage
   - Format: `> **CURRENT POSITION: <stage description>. <What's next / what's now unblocked.>**`
   - Keep it to 1–2 sentences — it's a quick-glance callout, not a summary

5. Update the `*Last updated:*` date at the top of the file to today's date.

6. Show the user:
   - The updated CURRENT POSITION callout
   - Each line that was changed (before → after)

## Notes

- Only touch items that match $ARGUMENTS — do not check off anything else
- Do not rewrite prose sections — only change `[ ]` to `[x]` and update the CURRENT POSITION callout
- If the item described in $ARGUMENTS doesn't clearly map to a checklist item, show the user the closest matches and ask which to check off

## Context / Files to Read

- `business/docs/progress.md`
