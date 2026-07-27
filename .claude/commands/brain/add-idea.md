# Add Idea — Append a content idea to docs/content/ideas.md

## Variables

$ARGUMENTS — description of the blog post, LinkedIn post, or other content idea.
             Can be a title hint, angle, or free-form notes.

## Execution Model

**Run entirely inline. Spawn no subagent.** This is a small, single-file append/edit —
a subagent round trip adds latency without adding value.

## Instructions

1. If $ARGUMENTS is not provided, stop and ask the user to describe the idea.
2. Read `docs/content/ideas.md` to understand current structure and check for duplicates.
3. From $ARGUMENTS determine:
   - A short, punchy working title
   - A one-line hook (the angle or why this is worth reading)
   - Output target: `[LI]` for LinkedIn-length · `[Blog]` for long-form · `[Both]`
   - Section: **Confirmed** (drafted, ready to publish) · **Committed** (tied to an upcoming spec) · **Ideas Backlog** (needs development first)
   - Default section: Ideas Backlog unless the description implies the piece is ready or tied to specific work

4. **Apply the public narrative guardrails** before shaping the title and hook:
   - Frame Brandon and his work as the subject
   - Never name or criticize a former employer
   - De-identify any client/employer reference (see `business/docs/brand.md`)
   - No fabricated metrics — if the hook leans on a number, it must be verifiable

5. Append to the appropriate section using this format:
   ```
   - **<Working Title>** `[LI|Blog|Both]`
     <One-line hook.>
     *(Revisit when: ...)* — only if the idea needs a future artifact or shipped project first
   ```

6. Confirm the title and the section it was added to.

## Notes

- Capture-only — drafting the actual post is a separate task (use /plan or /feature in the sub-project).
- This writes to the TOP-LEVEL brain only. If you're in a sub-project session, run /blog-idea there too
  (it writes to planning/blog/BLOG_IDEAS.md in that repo). The two are complementary, not redundant.
- Never edit existing entries unless the user explicitly asks.
