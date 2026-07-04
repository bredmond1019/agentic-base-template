# Log Correspondence — Record a business email, meeting, or client conversation

## Variables

$ARGUMENTS — summary of the correspondence. Include: who (use a role/description, not
             a full name for external contacts), what was discussed, date, and next actions.
             Example: "Email to a local gym, proposed initial diagnostic call,
             2026-06-15. Next: schedule call this week."

## Execution Model

Spawn a Haiku subagent (Agent tool, `model: "haiku"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Instructions

1. If $ARGUMENTS is not provided, ask the user to describe the correspondence.
2. Check if `business/docs/correspondence.md` exists. If not, create it with:
   ```
   # Business Correspondence Log

   Running log of emails, meetings, and client conversations. Most recent first.

   ---
   ```
3. From $ARGUMENTS determine:
   - Date (use today's date if not provided)
   - Contact type: `warm-lead` · `client` · `platform` (Upwork/Toptal/etc) · `networking` · `other`
   - Summary of what was communicated
   - Next action (if any) and its date

4. **Prepend** a new entry to the log (most recent first):
   ```
   ## YYYY-MM-DD — <Contact type: one-line description>

   <2–4 sentences: what was communicated, any key commitments or decisions made.>

   **Next action:** <what happens next, or "None">
   ```

5. If there's a next action with a specific date, ask: "Want me to note this in business/docs/career.md
   under the contracting pipeline section?"

## Notes

- Use generic descriptions for potential clients (e.g. "a local gym" is fine;
  full names of individuals are not necessary for this log).
- This is a private repo — this log is for your reference only, never published.
- Keep entries terse. This is a running log, not a CRM. One paragraph per entry is enough.
- For actual CRM tracking as the practice grows, consider a dedicated tool — this is the
  lightweight version for early-stage.
