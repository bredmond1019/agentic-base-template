# Draft Post — Draft a LinkedIn post or blog post using brand guidelines.

Outputs a full draft ready to edit and publish. Does not publish directly.
Always check output against brand guardrails before posting.

## Variables

$ARGUMENTS — what to draft. Include: title or angle, and optionally the language (EN / PT / both).
Examples:
  - `"The Builder's Arc EN"`
  - `"Rust portfolio release PT"`
  - `"what I learned building agentic systems both"`
  - `"testing agentic pipelines EN — LinkedIn format"`

## Instructions

1. If $ARGUMENTS is not provided, ask: "What post do you want to draft? Give me a title or angle, and whether you want EN, PT, or both."

2. Read `docs/brand.md` — absorb the six public rules, de-identification requirements, voice guidelines, and the five-part arc.
3. Read `docs/linkedin.md` — check Upcoming posts (Section 5) for any spec or notes on this topic. Check Engagement Rules (Section 6) for format guidance.
4. Read `docs/content/ideas.md` — check whether this idea is in the backlog with any notes on angle or hook.
5. Read `docs/profile-and-pitch.md` — use the verbal pitches and positioning language as a voice reference.

6. Draft the post. Format depends on the target platform:

   **LinkedIn post format:**
   - Hook (first line — must work as the preview before "see more" cutoff, ~150 chars)
   - Body (3–6 short paragraphs or punchy lines; LinkedIn rewards white space)
   - CTA (one line — question, invitation, or action)
   - No hashtag spam — 2–3 max if any
   - Tone: direct, personal, no marketing speak, no buzzwords

   **Blog post / site article format:**
   - H1 title
   - Intro paragraph (hook — what this is about and why it matters to the reader)
   - Subheadings with content
   - Closing section with a "what's next" or reflective note
   - Tone: same directness as LinkedIn but longer form; first-person throughout

7. Apply brand guardrails before outputting:
   - Subject of every sentence is you, your work, or your reasons — never a former employer's conduct
   - No fabricated metrics (don't invent numbers; use only documented figures from profile-and-pitch.md or brand.md)
   - De-identification: no employer names, client names, or identifying details unless already public
   - Voice check: does this sound like Brandon or like a LinkedIn influencer? Cut anything that sounds like the latter.

8. Output the draft(s). If both EN and PT requested, output EN first, then PT (written fresh — not translated).

9. Save the draft to `docs/content/linkedin/<slug>.md` — use a kebab-case filename derived from the post title (e.g. `builders-arc-en.md`, `rust-portfolio-release-pt.md`). If the file already exists (a prior draft), overwrite it.

10. After saving, ask: "Want me to mark this as 'drafted' in the ideas backlog?" If yes, update `docs/content/ideas.md` to note the draft status next to the relevant entry.

## Context / Files to Read

- `docs/brand.md`
- `docs/linkedin.md`
- `docs/content/ideas.md`
- `docs/profile-and-pitch.md`
