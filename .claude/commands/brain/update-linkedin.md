# Update LinkedIn — Mark linkedin.md sections as live when updated on-platform.

## Variables

$ARGUMENTS — what was updated. Examples:
  - `"headline — now live"`
  - `"about section — now live"`
  - `"posted: The Builder's Arc EN, 2026-06-20"`
  - `"featured section — site link pinned"`

## Execution Model

Spawn a Haiku subagent (Agent tool, `model: "haiku"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Instructions

1. If $ARGUMENTS is not provided, stop and ask: "What did you update on LinkedIn? (headline, about section, featured section, or a post?)"

2. Read `business/docs/linkedin.md` in full.

3. Determine what was updated based on $ARGUMENTS:

   **If it's the headline, about section, featured section, or profile photo:**
   - Find the corresponding row in the Platform Status table (Section 7 of linkedin.md)
   - Change the Status cell from "Not updated" to "Live — <today's date>"
   - If new copy was provided in $ARGUMENTS, update the relevant copy section (Section 1 or 2)

   **If it's a new post going live:**
   - Extract the post title/hook and date from $ARGUMENTS
   - Append a new row to the Posts — Published table (Section 5):
     `| <date> | <title/hook> | <language: EN or PT> | — | <any note from $ARGUMENTS> |`
   - Find the matching entry in Posts — Upcoming (Section 6) and remove it (or mark with ~~strikethrough~~ if it was a multi-part series and only one part published)
   - Update the Platform Status table row for "First post" if this is the first published post
   - Check `docs/content/linkedin/` for a draft file matching this post. If found, note its filename in the Published row so there's a record of where the draft lived.

4. Show the user the updated sections of `business/docs/linkedin.md` to confirm.

## Context / Files to Read

- `business/docs/linkedin.md`
