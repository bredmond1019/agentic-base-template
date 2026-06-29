# Find Leads — Generate a prioritized list of prospect types to target.

Map Brandon's services against business sectors to surface the best-fit targets —
where the pain is real, the budget exists, and the work matches his positioning.
Output is a prioritized lead-generation guide, not a cold-contact list.

## Variables

$ARGUMENTS — optional focus: industry sector, city/region, problem type, or company size.
Examples: "São Paulo brick-and-mortar", "remote US SaaS", "document-heavy businesses",
"small professional services". Default: best-fit sectors across all markets he can serve.

## Instructions

1. Read the context files below.

2. Based on Brandon's positioning (production RAG, workflow automation, AI pipelines,
   full-stack — NOT generalist dev), identify 10–15 business types that are strong fits.
   
   For each business type, assess:
   - **Pain-workflow match**: do they have repetitive, document-heavy, or knowledge-retrieval
     workflows that map to RAG, automation pipelines, or AI assistants?
   - **Budget fit**: small enough to not need enterprise vendors, large enough to pay
     $1,000–15,000 for a bounded engagement
   - **Access**: São Paulo local advantage (personal relationship, bilingual), or accessible
     remotely (US/EU async-friendly, English)
   - **Speed to value**: can a diagnostic + quick win be delivered in 1–2 weeks?

3. If `$ARGUMENTS` specifies a sector or region, focus the list there. Otherwise, spread
   across: (a) São Paulo local, (b) Brazil remote, (c) US/EU remote.

4. Output the list in priority order — best fits first. For each entry:

   ```
   ## [Business Type] — [Location/Market]
   **Why they're a fit:** one sentence on the workflow match
   **Typical pain points:** 2–3 bullets — specific, not generic
   **Your angle:** which service to lead with (diagnostic / RAG / automation / full-stack)
   **Where to find them:** how to identify and reach specific companies of this type
   **Watch out for:** one red flag (budget risk, wrong size, vendor lock-in, etc.)
   ```

5. At the end, add a **Quick Wins** section: the 2–3 business types most likely to
   convert to a first paid engagement within 30–60 days, and why.

6. Do not suggest sectors where Brandon has no documented experience or proof.
   Do not suggest enterprise targets that require procurement cycles or RFPs.
   Do not suggest platforms or job boards — this is about direct outreach targets.

## Context / Files to Read

- `docs/career.md`
- `docs/profile-and-pitch.md`
- `docs/progress.md`
