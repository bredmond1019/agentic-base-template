# Research Company — Deep research brief on a specific prospect before a conversation.

Research a company or lead, synthesize what's relevant to Brandon's services,
and produce a conversation-ready brief. Saves a reference file in docs/business/leads/.

## Variables

$ARGUMENTS — company name, website URL, or description of the business. Required.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask for the company name or description.

2. Read the context files listed below.

3. Research the company using available tools:
   - Search for the company name, website, LinkedIn, and any press/reviews
   - If a URL is provided, fetch the site directly
   - Look for: what they sell, how many employees, how long they've been operating,
     what tools/tech they mention, any job postings (signals about pain points and team size),
     customer reviews, recent news or changes
   - If the company is an already-documented lead in `docs/business/pipeline.md`, check
     `docs/business/correspondence.md` for any existing notes

4. Synthesize a research brief in this format:

   ---
   # [Company Name] — Research Brief
   *Researched: [date]*

   ## Overview
   What they do, estimated size, how long they've operated, location, any notable context.
   2–4 sentences.

   ## Likely Pain Points
   Based on their industry, size, and what you can observe — what workflows are probably
   slow, manual, or knowledge-dependent? Be specific to this company, not generic.
   3–5 bullets.

   ## Service Fit
   Which of Brandon's services maps most naturally to their pain?
   - Lead with: [diagnostic / RAG / workflow automation / AI assistant / full-stack]
   - Secondary: [if applicable]
   One paragraph explaining the fit.

   ## Conversation Guide
   **Objective:** what you want to learn from this conversation (not pitch, learn)
   **Opening:** one sentence to frame the conversation — curious, not salesy
   **Questions to ask:**
   1. [Most important — about their biggest time sink or knowledge bottleneck]
   2. [About tools they currently use]
   3. [About who owns the problem — decision-maker identification]
   4. [About scale — how often does this happen, how many people are affected]
   5. [Permission to follow up — "would it be useful if I sent you a quick summary?"]
   **What to listen for:** signals that this is a real, funded problem vs. a casual complaint
   **What NOT to say:** specific things to avoid given this company's context

   ## Red Flags
   Anything that would make this a bad-fit engagement: wrong size, likely no budget,
   problem that's too complex or too simple, personality mismatch, etc.

   ## Next Action
   Single sentence: what to do after reading this brief.
   ---

5. Save the brief to `docs/business/leads/<slug>.md` where `<slug>` is a lowercase
   kebab-case version of the company name (e.g. `acme-corp.md`, `smb-client.md`).

6. Report back: where the file was saved and the one-sentence service fit summary.

## Notes

- This is a research command, not a pitch command. The output should make you a better
  *listener*, not a better salesperson. The goal of the first conversation is to understand
  their problem, not to close anything.
- If web search returns no useful results for a small local business, say so clearly and
  base the pain points and conversation guide on industry patterns instead.
- Never fabricate specifics (revenue numbers, employee counts, etc.) — mark anything
  estimated as "(estimated)" or "(based on industry norms)".

## Context / Files to Read

- `docs/career.md`
- `docs/profile-and-pitch.md`
- `docs/business/correspondence.md` (if it exists — skip silently if not)
