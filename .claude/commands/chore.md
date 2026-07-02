# Chore — Plan a maintenance or housekeeping task.

## Variables

$ARGUMENTS — description of the chore to plan.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the chore.
2. Research the codebase: read `CLAUDE.md`, then any files directly relevant to the chore.
3. Create a plan using the Plan Format below.
4. Choose a short descriptive slug for the chore (e.g. `remove-k8s-secret`, `fix-devin-typos`, `update-stale-handles`).
6. Create the directory `planning/chore-{descriptive-name}/` if it does not exist, then save the plan to `planning/chore-{descriptive-name}/tasks.md`.
6. Return only the path to the file created.

## Codebase Structure

- `CLAUDE.md` — standing rules, the SDLC pipeline, build/test/validate commands (start here)
- `planning/context.md` — why the project exists + audit findings; `planning/status.md` — progress
- `planning/harness.json` — the project's validation commands + UI-test config
- `planning/` — task specs and plan files (one concept folder per task)

Read `CLAUDE.md` for the project's actual stack, directory layout, and conventions — do not assume
any framework, language, or directory structure that isn't written there.

## Standing rules to respect

Read `CLAUDE.md` and `planning/context.md` — internalize and enforce **the project's standing rules**.
CLAUDE.md is the authority; do not assume any stack, locale-parity, narrative, or content-layout rule
unless written there. Universal harness rules still apply: no fabricated metrics/quotes, no emoji,
every change ships with tests.

## Plan Format

```md
# Chore: <chore name>

## Metadata
prompt: `{$ARGUMENTS}`

## Chore Description
<describe the chore in detail — what it is, why it matters, any known constraints>

## Relevant Files
<list files relevant to the chore with bullet points explaining why each is needed>

### New Files
<list any new files that will be created, if applicable>

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### <BlockID>.1 <First Task Name>
- <specific action>
- <specific action>

### <BlockID>.2 <Second Task Name>
- <specific action>

### <BlockID>.N Validate
- Run the Validation Commands listed below and confirm all pass.

## Validation Commands
```
<the project's validation commands — see `planning/harness.json` (`validation.checks[]`) or CLAUDE.md; one command per line, in order>
```
<add any chore-specific checks above the standard project checks>

## Notes
<optional context, edge cases, or gotchas>
```


### Step X — Register the block in state.json
After writing the `tasks.md` file, you MUST also register this chore's block in `planning/state.json`
— a chore is a standalone block, not one already sitting in `master-plan.md`.
1. Open `planning/state.json`. Find or create a `tracks[]` entry titled `"Chores"` (reuse it if it
   already exists).
2. Add an entry to that track's `blocks[]` for this chore's `<BlockID>`, if it doesn't already exist:
   - `id`: the chore's Block ID
   - `title`: the chore name
   - `status`: `"open"`
   - `wave`: default to one past this repo's current highest wave (chores queue behind roadmap work
     unless the user says it's urgent — ask before assigning an earlier wave)
   - `depends_on`: `[]` unless the chore explicitly names a prerequisite block, in which case
     `{ "type": "block", "repo": "<this-repo-slug>", "id": "<ID>" }`
3. Add a `tasks` array to that block. For each task generated in the spec, add an object with the following schema (aligning with SDLC_FLOW):
   - `task_id`: Integer (1-indexed)
   - `title`: The task title
   - `description`: The task description
   - `acceptance_criteria`: Array of acceptance criteria strings
   - `status`: "pending"
   - `validation_commands`: []
   - `max_attempts`: 3
4. Save `planning/state.json` and validate it is still valid JSON:
   `python3 -c "import json;json.load(open('planning/state.json'))"`.

### State Refresh

Run `mev emit-state --write` to update the brain's focus derivation and state based on the new planning files.

## Report

Output the path to the plan file created and the next step:
```
planning/chore-{name}/tasks.md

Next (implement + test loop):
  /sdlc-task chore-{name}
```
