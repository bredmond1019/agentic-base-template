# Backlog Ticket — Capture a queued idea into planning/backlog.md

## Variables

$ARGUMENTS — free-form description of the idea, improvement, or research thread.
             Can include a target repo, type hint, or just a raw description.

## Execution Model

Spawn a Haiku subagent (Agent tool, `model: "haiku"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Instructions

1. If $ARGUMENTS is not provided, stop and ask the user to describe the idea.

2. Read `planning/backlog.md` to understand the current format and check for near-duplicates.

3. From $ARGUMENTS infer the following fields:

   **title** — a concise, action-oriented title (5–10 words)

   **repo** — the primary repo/area this belongs to. Pick one:
   `base-template` · `orchestrator` · `learn-ai` · `bastion` · `mev` · `brain` · `business` · `cross-repo`
   If the description clearly targets multiple repos and neither dominates, use `cross-repo`.

   **type** — what kind of work this is:
   - `feature` — new capability or user-facing addition
   - `improvement` — refine, fix, or simplify something existing
   - `research` — investigation or scoping pass before building
   - `content` — writing, course material, or learning content
   - `business` — CV, outreach, rates, career, client ops
   - `planning-session` — needs a design/planning pass before implementation work can begin

   **status** — default to `idea` unless the description implies it's already scoped and ready (`ready`)

   **related** — optional; any decisions (D##), master-plan blocks, or doc paths mentioned or clearly implied
                 by the description. Omit if nothing obvious.

   **gist** — 1–3 sentences: what it is and why it matters. Be specific. Do not pad.

4. Append to the `## Active` section of `planning/backlog.md` (before the `## Promoted` section)
   using this exact format:

   ```
   ### [YYYY-MM-DD] <title>
   `repo:<repo>` `type:<type>` `status:<status>`
   **related:** <related> (omit this line entirely if no related items)

   <gist>

   ---
   ```

   Use today's date for YYYY-MM-DD.

5. Confirm: output the ticket title, repo, type, and the first sentence of the gist.
   Nothing else.

## Notes

- Capture-only. Do not create plans, tasks, or sub-repo files — the backlog is the holding area.
- If the idea is clearly a content piece (blog post, LinkedIn), add it here AND suggest running
  `/add-idea` to also capture it in `docs/content/ideas.md`.
- When an item is ready to promote: update its `status` tag to `promoted`, add a
  `> Promoted: [date] → [where]` line, then go create the plan in the target repo.
- Never edit existing entries unless the user explicitly asks.
