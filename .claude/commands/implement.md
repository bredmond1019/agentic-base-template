# Implement — Execute a plan file against the codebase.

## Variables

$ARGUMENTS — path to the plan file to implement, with an optional task number suffix.

Examples:
- `planning/tasks/1.1-site-credibility-fixes/tasks.md` — run all tasks in the plan
- `planning/tasks/1.1-site-credibility-fixes/tasks.md 1` — run only Task 1
- `planning/tasks/1.1-site-credibility-fixes/tasks.md 3` — run only Task 3

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user for the plan file path.
2. Parse `$ARGUMENTS`: split on the last space. If the trailing token is a number, treat it as the **task number** to run in isolation; the remainder is the plan file path. If no number is present, run all tasks.
3. Run `/prime` to orient to the codebase before touching any code.
4. Read the plan file in full.
5. THINK HARD about the plan: understand the goal, relevant files, and the target task(s) before writing anything.
6. **If a task number was given:** execute only that numbered task from the Step-by-Step Tasks section. Skip all others. After completing it, run only the validation commands directly relevant to that task (e.g. `npx tsc --noEmit` for the file(s) changed, `npm run validate:content` for content edits, or the specific `npm test` path for tests written). Do NOT run the full validation suite — that is reserved for when all tasks are complete.
7. **If no task number was given:** execute every Step-by-Step task in order, top to bottom.
   - Follow existing code patterns and conventions (see CLAUDE.md).
   - Bilingual parity: most content ships EN + pt-BR. A content change in one locale must be mirrored in the other, or the deferral recorded explicitly in the spec's `## Notes / deviations`.
   - Honor the PUBLIC-NARRATIVE RULE: Brandon / his work / his reasons is the SUBJECT of every sentence; never name or criticize a former employer; de-identify Helpscout and AI Scribe; the April-2025 proposal story stays private.
   - NO fabricated metrics. Every number must be verifiable. Verify model ids / package names via the claude-api skill, not from memory.
8. After all tasks are complete (full run only), run the plan's Validation Commands exactly as written. If no plan-specific commands exist, run the standard checks:
   ```
   npm run lint
   npx tsc --noEmit
   npm run validate:content
   npm test
   npm run build
   ```
9. If validation fails, fix the failure before reporting.
10. Report the completed work (see Report).

## Context / Files to Read

- `$ARGUMENTS` (the plan file)
- `CLAUDE.md` (standing rules)
- Files listed in the plan's Relevant Files section

## Report

After completing work, write a report file AND summarize to the user.

**Derive the report file path** from the plan path and optional task number:
- Plan only: `planning/tasks/1.1-site-credibility-fixes/tasks.md` → `planning/tasks/1.1-site-credibility-fixes/reports/implement.md`
- Plan + task: `planning/tasks/1.1-site-credibility-fixes/tasks.md 3` → `planning/tasks/1.1-site-credibility-fixes/reports/task3-implement.md`

Create `planning/tasks/1.1-site-credibility-fixes/reports/` if it does not exist.

**Write the report file** in this exact format:

```markdown
# Implementation Report — <plan filename> [Task <N> | All Tasks]

**Date:** <YYYY-MM-DD>
**Plan:** <plan file path>
**Scope:** Task <N> | All tasks

## What Was Built or Changed

- <bullet per logical change>

## Files Created or Modified

| File | Action |
|---|---|
| path/to/file.tsx | created / modified |

## Validation Output

**Commands run:**
\`\`\`
<exact commands executed>
\`\`\`

**Results:**
\`\`\`
<stdout/stderr output, truncated to relevant lines>
\`\`\`
Status: PASSED / FAILED

## Decisions and Trade-offs

- <any non-obvious choice made during implementation, or "None">

## Follow-up Work

- <items deferred or out of scope, or "None">

## git diff --stat

\`\`\`
<output>
\`\`\`
```

Then summarize the same information to the user in the chat.

Then output the pipeline next step:
```
Next: /test planning/tasks/1.1-site-credibility-fixes/tasks.md [N]
```
