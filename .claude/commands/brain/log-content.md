# Log Content — Record published content in docs/content/blog-tracker.md

## Variables

$ARGUMENTS — description of what was published. Include: title, platform (blog/dev.to/linkedin),
             and date. Example: "The Builder's Arc, published on blog and LinkedIn, 2026-06-15"

## Execution Model

Spawn a Haiku subagent (Agent tool, `model: "haiku"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Instructions

1. If $ARGUMENTS is not provided, stop and ask the user to describe what was published.
2. Read `docs/content/blog-tracker.md` to understand the current structure.
3. From $ARGUMENTS determine:
   - Title
   - Platform(s): learn-agentic-ai.com blog · Dev.to · LinkedIn · combination
   - Date (use today's date if not provided)
   - Category: `return-post` · `build-log` · `technical-depth` · `evergreen` · `linkedin-only`
   - Notes (e.g. "EN only, PT pending", "Dev.to cross-post pending")

4. Add a row to the relevant Published table in `docs/content/blog-tracker.md`.

5. If this piece appeared in `docs/content/ideas.md` as a **Confirmed** or **Committed**
   entry, remove or strike it there (or ask the user if they want it removed).

6. Confirm what was logged and what (if anything) was removed from ideas.md.

## Notes

- This is a logging command — content was already published before you call this.
- The blog-tracker is the authoritative record of what's live. Keep it accurate and current.
- If the content was published in both EN and PT-BR, note both in the entry.
