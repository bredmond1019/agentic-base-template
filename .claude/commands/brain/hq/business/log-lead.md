# Log Lead — Add a new lead to the pipeline.

Quick capture for when a contact or opportunity surfaces.
For a full research brief, use `/research-company` instead — that does web research and saves a deep brief to `docs/business/leads/`.

## Variables

$ARGUMENTS — lead info. Should include: name/description, source (warm/cold/referral/inbound),
and any initial notes or next action. Examples:
  - `"a local gym — warm (personal contact) — WhatsApp automation opportunity — next: research conversation after checkpoint"`
  - `"SaaS founder via LinkedIn — cold inbound — asked about RAG pipeline — next: follow up with diagnostic offer"`

## Execution Model

Spawn a Haiku subagent (Agent tool, `model: "haiku"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Instructions

1. If $ARGUMENTS is not provided, stop and ask: "Who is the lead and how did they come in? Include any notes on the opportunity and what the next action should be."

2. Read `docs/business/pipeline.md` in full.
3. Read `docs/career.md` — check whether the competence checkpoint has cleared.

4. Parse $ARGUMENTS into:
   - **Name/description** — the lead identifier (use generic descriptors per de-identification rules)
   - **Source** — warm / cold / referral / inbound
   - **Initial notes** — opportunity type, context
   - **Next action** — what to do next
   - **Stage** — infer from notes; default to `identified` if no contact made yet

5. Determine gate status:
   - If competence checkpoint NOT cleared: set Gate column to `(locked) After competence checkpoint`
   - If competence checkpoint IS cleared: set Gate column to `—`

6. Add a row to the Active Leads table in `docs/business/pipeline.md`:
   `| <Name> | <Source> | <stage> | <last contact or —> | <Next Action> | <Gate> |`

7. Add a dated entry to the Lead History section:
   ```
   ### <Name>

   - **<today's date>** — <Summary from $ARGUMENTS. Include source, opportunity type, gate status.>
   ```
   If a history section for this lead already exists, append the entry under it instead of creating a new heading.

8. Show the user the updated pipeline rows to confirm.

## Context / Files to Read

- `docs/business/pipeline.md`
- `docs/career.md`
