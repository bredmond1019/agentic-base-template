---
name: review-task
description: >-
  Verify a completed task against its spec and acceptance criteria — read the
  spec and prior reports as context, run a FRESH authoritative test suite, check every
  acceptance criterion against actual source, enforce standing rules, and issue a
  PASS/PARTIAL/FAIL verdict in a review report. Use when the user says "review", "verify
  the task", or "check it against the spec" after implement/test.
---

# Review Task — Verify a completed task against its spec and acceptance criteria.

## Inputs

Path to the task spec, with an optional task number suffix (same format as the **implement**
skill), taken from the user's request. Examples:
- `planning/tasks/phase0-blockC/tasks.md` — review all tasks in the spec
- `planning/tasks/phase0-blockC/tasks.md 1` — review only Task 1
- `planning/tasks/phase0-blockC/tasks.md 3` — review only Task 3

## Instructions

1. If no input is provided, stop and ask the user for the task spec path.
2. Parse the input: split on the last space. If the trailing token is a number, treat it as the **task number** to review; the remainder is the task spec path.
3. Orient first (the `prime` skill's read-list): read `README.md`, `CLAUDE.md`, `planning/CONTEXT.md`, `planning/STATUS.md` to load standing rules and architecture before reading any files.
4. **Derive file paths for prior step outputs** (reports live in the spec's `reports/` sibling directory):

   Implement report (written by the **implement** skill):
   - Plan only: `planning/tasks/phase0-blockC/tasks.md` → `planning/tasks/phase0-blockC/reports/implement.md`
   - Plan + task N: `planning/tasks/phase0-blockC/tasks.md 3` → `planning/tasks/phase0-blockC/reports/task3-implement.md`

   Test report (written by the **test** skill):
   - Plan only: `planning/tasks/phase0-blockC/tasks.md` → `planning/tasks/phase0-blockC/reports/test.md`
   - Plan + task N: `planning/tasks/phase0-blockC/tasks.md 3` → `planning/tasks/phase0-blockC/reports/task3-test.md`

5. Read the task spec in full.
6. Read both prior step outputs as historical context:
   a. Read the implement report if it exists. If absent, note it and continue from source alone.
   b. Read the test report if it exists. Note the historical results, but do NOT treat them as
      authoritative — a fresh test run is required in step 8. If absent, note that the **test** skill was
      not run before this review; the fresh run below covers it.
7. Read every file listed in the implement report's **Files Created or Modified** table (or, if no
   report, read the files most likely touched by the task based on the spec). Verify the actual
   content — do not trust the report alone.
8. **Run a fresh test suite** as the authoritative verification. Do NOT rely on the historical
   test report — run the commands now and capture the results.
   - **Task-scoped:** run the spec's Validation Commands section exactly as written.
   - **Full block:** run the plan's complete Validation Commands block. If none exist, run:
     ```
     npm run lint
     npx tsc --noEmit
     npm run validate:content
     npm test -- --listTests
     npm test
     npm run build
     ```
   `npm test` is authoritative for the verdict, with `npm run build` as a co-gate for any spec
   that changes routing, pages, or components. For specs that edit `content/`, also confirm
   bilingual EN/pt-BR parity for the touched slugs and that `npm run validate:content` passes.
   A fresh test failure always prevents PASS, even if all acceptance criteria appear MET from
   reading the code.
9. **Check every Acceptance Criterion** in the spec against the actual code and fresh test output:
   - For each criterion: state whether it is **MET**, **PARTIAL**, or **NOT MET**, and cite the evidence (file + line, test name, command output).
   - A criterion is MET only when you can point to code or test output that directly satisfies it.
   - Do not mark anything MET based solely on the implementation report — verify in source.
10. Write the review report file and summarize to the user (see Report).

## Context / Files to Read

- The task spec (the input path)
- `planning/tasks/phase0-blockC/reports/implement.md` (or task-scoped variant — the implementation report, if present)
- `planning/tasks/phase0-blockC/reports/test.md` (or task-scoped variant — the test report, if present)
- `CLAUDE.md` (standing rules — check for violations)
- All files created or modified by the implementation

## Report

**Derive the review report file path** (reports live in the spec's `reports/` sibling directory):
- Plan only: `planning/tasks/phase0-blockC/tasks.md` → `planning/tasks/phase0-blockC/reports/review.md`
- Plan + task N: `planning/tasks/phase0-blockC/tasks.md 3` → `planning/tasks/phase0-blockC/reports/task3-review.md`

**Write the review report file** in this exact format:

```markdown
# Review Report — <plan filename> [Task <N> | All Tasks]

**Date:** <YYYY-MM-DD>
**Plan:** <plan file path>
**Scope:** Task <N> | All tasks
**Implement report:** found / not found
**Test report:** found / not found
**Overall verdict:** PASS / FAIL / PARTIAL

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | <criterion text, truncated to ~80 chars> | MET / PARTIAL / NOT MET | file:line or test name or command output |
| 2 | … | … | … |

## Fresh Test Run

**Commands run:**
\`\`\`
<exact commands executed>
\`\`\`

**Output:**
\`\`\`
<stdout/stderr, truncated to relevant lines>
\`\`\`
Result: PASS / FAIL

## CLAUDE.md Rule Violations

Check against the the project's standing rules:
- **Bilingual parity** — a content change in one locale mirrored in the other, or the deferral recorded in the spec's `## Notes / deviations`.
- **Public-narrative rule** — Brandon is the subject; no former employer named or criticized; Helpscout and AI Scribe de-identified; the April-2025 proposal story not used publicly.
- **No fabricated metrics** — every number verifiable; model ids / package names verified, not from memory.
- **Gates pass** — `npm run validate:content` and `npm run build` pass before the task is done.

- <any standing-rule violation found, or "None">

## Issues Found

- <concrete problem with file + line reference, or "None">

**Verdict rules:**
- **PASS** — all acceptance criteria MET AND fresh test run passed.
- **PARTIAL** — criteria MET but one or more fresh tests failed; or fresh tests pass but some criteria only partially met.
- **FAIL** — blocking acceptance criteria NOT MET, or fresh test run produced failures that invalidate the implementation.

## Verdict

<One paragraph: overall assessment, what passed, what failed, what must be fixed before this task is considered done. If PASS, state clearly. If FAIL or PARTIAL, list the blocking items.>
```

Then summarize the verdict and any blocking issues to the user in the chat.

Then output the pipeline next step:
```
If verdict is PASS:     Next: invoke the document skill on planning/tasks/phase0-blockC/tasks.md [N]
If verdict is not PASS: invoke the fix skill on planning/tasks/phase0-blockC/tasks.md [N]
                        then: invoke the test skill on planning/tasks/phase0-blockC/tasks.md [N]
                        then: invoke the review-task skill on planning/tasks/phase0-blockC/tasks.md [N]
```
