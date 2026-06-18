# Application Validation Test Suite

Execute comprehensive validation tests for the project, returning results in a standardized JSON format for automated processing.

## Variables

$ARGUMENTS — optional path to the task spec and optional task number. Same format as `/implement`.

Examples:
- (no args) — run full suite; output JSON to chat only; no file written
- `planning/<spec-slug>/tasks.md` — run full suite; write report to `planning/<spec-slug>/sdlc/reports/test.md`
- `planning/<spec-slug>/tasks.md 1` — run full suite; write report to `planning/<spec-slug>/sdlc/reports/task1-test.md`

The task number N does NOT change which tests run — all checks always run regardless. N only
determines the output file name so the snapshot is scoped to the right pipeline stage.

## Purpose

Proactively identify and fix issues before they impact the site or downstream work. By running this suite you can:
- Detect lint and TypeScript type errors before they reach the build
- Identify broken or malformed MDX content (frontmatter, internal refs)
- Catch broken tests or regressions in `lib/` services and components
- Verify that the Next.js production build compiles cleanly with no route or compile errors

## Constants

TEST_COMMAND_TIMEOUT: 5 minutes

## Instructions

- **Step 0 — Parse `$ARGUMENTS`:** If provided, split on the last space. Trailing number = task N; remainder = spec path. Derive the report file path from the spec's parent directory:
  - No args: no file will be written.
  - Spec only: `planning/<spec-slug>/tasks.md` → `planning/<spec-slug>/sdlc/reports/test.md`
  - Spec + task N: `planning/<spec-slug>/tasks.md 1` → `planning/<spec-slug>/sdlc/reports/task1-test.md`
- Run `/prime` to orient to the codebase before executing any tests.
- Execute each test in the sequence provided below
- Capture the result (passed/failed) and any error messages
- IMPORTANT: Return ONLY the JSON array with test results
  - IMPORTANT: Do not include any additional text, explanations, or markdown formatting
  - We'll immediately run JSON.parse() on the output, so make sure it's valid JSON
- If a test passes, omit the error field
- If a test fails, include the error message in the error field
- Execute all tests even if some fail
- Error Handling:
  - If a command returns a non-zero exit code, mark as failed
  - Capture stderr output for the error field
  - Timeout commands after `TEST_COMMAND_TIMEOUT`
- Test execution order is important — lint and type checks must pass before trusting the build
- All commands are run from the repo root unless the command itself changes directory
- Always run `pwd` before each test to confirm you are in the repo root

## Test Execution Sequence

### Code Quality

1. **ESLint**
   - Preparation Command: None
   - Command: `npm run lint`
   - test_name: "eslint"
   - test_purpose: "Lint gate (ESLint flat config, next/core-web-vitals + next/typescript) — catches unused vars, undefined names, React/Next anti-patterns, and import issues. Pre-existing warnings are tolerated; new errors fail."

2. **TypeScript Type Check**
   - Preparation Command: None
   - Command: `npx tsc --noEmit`
   - test_name: "tsc"
   - test_purpose: "Type gate (tsconfig is strict:true, noEmit:true) — deep, type-aware analysis across the whole project that ESLint's AST-only pass cannot detect. Catches attribute/prop mismatches, bad imports, and unsafe types."

### Content Validation

3. **Content Validate**
   - Preparation Command: None
   - Command: `npm run validate:content`
   - test_name: "content_validate"
   - test_purpose: "Content correctness — validates MDX frontmatter, structure, and internal references under content/. A failure means malformed or broken content that would break pages at build or runtime."

### Test Suite

4. **Jest Collection**
   - Preparation Command: None
   - Command: `npm test -- --listTests`
   - test_name: "jest_collect"
   - test_purpose: "Verifies that jest can discover and enumerate all test files without import or load errors — a discovery failure means tests can't run at all, usually caused by a broken import in a test file or setup module."

5. **Full Test Suite**
   - Preparation Command: None
   - Command: `npm test`
   - test_name: "jest_full"
   - test_purpose: "Runs every unit/integration test in the suite — validates lib/ services, components, and content helpers. This is authoritative for the review verdict; a failure here always prevents PASS."

### Build

6. **Next Build**
   - Preparation Command: None
   - Command: `npm run build`
   - test_name: "next_build"
   - test_purpose: "Production build gate (next build) — compiles every route, page, and component and resolves MDX content. Catches compile errors, broken routes, and runtime-at-build failures that the lint and type passes miss."

### Content Gates (include ONLY when the spec edits `content/`)

7. **Bilingual Parity**
   - Preparation Command: None
   - Command: per touched slug, confirm the pt-BR mirror exists — e.g. `test -f content/blog/published/<slug>.mdx && test -f content/blog/published/pt-BR/<slug>.mdx`
   - test_name: "bilingual_parity"
   - test_purpose: "EN/pt-BR mirror check — every content slug the task touched exists in BOTH locales, OR the spec's `## Notes / deviations` records an explicit deferral. NOTE the real tree: EN blog/projects live at the `published/` TOP LEVEL and only the pt-BR copy is nested under `published/pt-BR/`, so it is NOT a symmetric `en/` vs `pt-BR/` diff. (blog: `content/blog/published/<slug>.mdx` ↔ `content/blog/published/pt-BR/<slug>.mdx`; projects: `content/projects/published/<slug>.json` ↔ `content/projects/published/pt-BR/<slug>.json`; learn: `content/learn/paths/` is currently irregular — named path dirs alongside an `en/` subdir — until `2.1-learn-paths-structural-fixes` lands, so compare the specific path dir you touched across locales rather than a flat `ls` diff.)"

8. **Link Check**
   - Preparation Command: None
   - Command: `npm run validate:content` (plus a grep of changed files for `TODO`/placeholder/`localhost`/stale handles)
   - test_name: "link_check"
   - test_purpose: "Dead-link / handle hygiene — no broken internal links, no dead external URLs, no stale social handles introduced. validate:content passes AND a grep of changed files surfaces no placeholder or known-stale handles."

## Report

- IMPORTANT: Return results exclusively as a JSON array based on the `Output Structure` section below.
- Sort the JSON array with failed tests (passed: false) at the top
- Include all tests in the output, both passed and failed
- The execution_command field should contain the exact command that can be run to reproduce the test
- This allows subsequent agents to quickly identify and resolve errors

### Output Structure

```json
[
  {
    "test_name": "string",
    "passed": boolean,
    "execution_command": "string",
    "test_purpose": "string",
    "error": "optional string"
  }
]
```

### Example Output

```json
[
  {
    "test_name": "eslint",
    "passed": false,
    "execution_command": "npm run lint",
    "test_purpose": "Lint gate (ESLint flat config, next/core-web-vitals + next/typescript) — catches unused vars, undefined names, and React/Next anti-patterns",
    "error": "./lib/services/content.ts 12:7  Error: 'parsed' is assigned a value but never used.  @typescript-eslint/no-unused-vars"
  },
  {
    "test_name": "jest_full",
    "passed": true,
    "execution_command": "npm test",
    "test_purpose": "Runs every unit/integration test in the suite — validates lib/ services, components, and content helpers. This is authoritative for the review verdict; a failure here always prevents PASS."
  }
]
```

## File Output

If `$ARGUMENTS` was provided, after returning the JSON array to chat, write a report file to the
derived path. Create `planning/<name>/sdlc/reports/` if it does not exist.

**Write the report file in this exact format:**

```markdown
# Test Report — <spec filename> [Task <N> | All Tasks]

**Date:** <YYYY-MM-DD>
**Plan:** <spec file path, or "ad-hoc">
**Scope:** Task <N> | All tasks
**Overall result:** PASS (<n>/6 passed) | FAIL (<n>/6 passed)

## Summary

| Test | Result | Error |
|---|---|---|
| eslint | PASS / FAIL | <error snippet or blank> |
| tsc | PASS / FAIL | |
| content_validate | PASS / FAIL | |
| jest_collect | PASS / FAIL | |
| jest_full | PASS / FAIL | |
| next_build | PASS / FAIL | |

## Full Results (JSON)

\`\`\`json
<the full JSON array, verbatim>
\`\`\`

## Next Step

`/review-task <spec file path> [N]`
```

If the spec edits `content/`, include the two content gates (`bilingual_parity`, `link_check`) as
two extra rows in the Summary table and the JSON array, and use `<n>/8` in the Overall result line.

After writing the file, output one line to chat:
```
Next: /review-task planning/<spec-slug>/tasks.md [N]
```
