// =============================================================================
// sdlc-task — Parallel-Safe SDLC Pipeline with Auto-Managed Worktree
// =============================================================================
//
// A parallel-safe variant of sdlc-run that:
//   1. Auto-creates a git worktree for this specific task
//   2. Runs the full SDLC pipeline inside that worktree
//   3. Defers STATUS.md / DEVLOG.md updates to a task log file
//      (applied at merge time via /clean-worktree)
//
// This lets multiple tasks run simultaneously with zero shared file writes,
// eliminating merge conflicts. sdlc-run.js is unchanged and still available
// for sequential use.
//
// USAGE
//   /sdlc-task 1.1-site-credibility-fixes 2   runs task 2 in an isolated worktree
//
//   Task number is REQUIRED. For full-spec runs use /sdlc-run instead.
//
// PIPELINE STAGES (in order)
//   Worktree   → auto-create (or suffix-increment) isolated git worktree
//   Scout      → detect current stage from report files
//   Plan       → generate task spec (skipped if spec already exists)
//   Implement  → execute the task from spec
//   Fix        → targeted fixes for FAIL/PARTIAL review (up to 3 attempts)
//   Test       → 7-check suite: lint, tsc, content-validate, jest collect + full, build, emoji
//   Review     → fresh npm test + acceptance criteria; verdict gates next stage
//   Document   → surgical patches to docs/ (gates on PASS verdict)
//   Wrap-up    → write task log file (defers STATUS/DEVLOG to merge time)
//
// WHAT RUNS IN THE WORKTREE vs. MAIN
//   Worktree branch: all code, content, doc, and report changes
//   Main (at merge): STATUS.md + DEVLOG.md updates (applied by /clean-worktree)
//
// MERGE FLOW
//   After pipeline completes:
//     /clean-worktree <branchName>
//   This: merges the branch → applies the task log → updates STATUS/DEVLOG →
//         commits → removes worktree → deletes branch.
//
// WORKTREE PATH CONVENTION
//   trees/<specSlug-lowercased>-task<N>   e.g. trees/1.1-site-credibility-fixes-task2
//   If that name is taken, auto-increments: trees/...-task2-2, -3, etc.
//   The actual branch name is always reported in the pipeline output and task log.
//
// RESUMPTION
//   Same as sdlc-run: the scout checks which report files exist.
//   If the worktree already exists at setup time, a new suffixed worktree is
//   created rather than resuming the old one. This ensures clean state for retries.
//
// COMMIT STRATEGY (same as sdlc-run)
//   feat: implement <stem>         implement agent
//   fix: fix pass N for <stem>     fix agent (one per pass)
//   docs: update docs for <stem>   document agent
//   chore: wrap up <stem>          finalize agent (reports + task log)
//
// MODEL TIERING (token lever — see the MODEL map below)
//   Three tiers: Opus earns its cost on PLANNING (generate-tasks fallback); Haiku handles the
//   purely-mechanical stages (scout, test, finalize — fixed procedures, no judgment); Sonnet
//   handles everything in between (implement/fix/review/document/task-log). Tune one place: the
//   MODEL map. Real planning happens upstream in the /generate-tasks and /breakdown skills — run
//   those on Opus. This matters most under /sdlc-block, which fans this pipeline out across many tasks.
//
// STAGED MODEL ESCALATION (ESCALATION_MODEL)
//   The FINAL fix pass and FINAL review attempt before the loop gives up run on Opus.
//   The cheap Sonnet path covers the common case; a genuinely hard failure that has
//   already failed twice gets one strong shot before the task escalates. Set null to off.
//
// =============================================================================

export const meta = {
  name: 'sdlc-task',
  description: 'Run the SDLC pipeline for a single task in an isolated worktree — parallel-safe variant of sdlc-run',
  whenToUse: 'When running a specific numbered task in parallel with other tasks. Task number is required. Usage: /sdlc-task 1.1-site-credibility-fixes 2',
  phases: [
    { title: 'Worktree',   detail: 'Auto-create (or suffix-increment) git worktree for isolated execution' },
    { title: 'Scout',      detail: 'Determine current pipeline stage from report files' },
    { title: 'Plan',       detail: 'Generate task spec (only if spec file does not yet exist)' },
    { title: 'Implement',  detail: 'Execute the task' },
    { title: 'Fix',        detail: 'Targeted fixes for FAIL/PARTIAL review' },
    { title: 'Test',       detail: 'Run 7-check validation suite in the worktree' },
    { title: 'Review',     detail: 'Verify acceptance criteria; issue verdict' },
    { title: 'UI Test',    detail: 'Browser smoke check via playwright-cli (frontend-touching specs only)' },
    { title: 'Document',   detail: 'Patch docs/ (gates on PASS verdict)' },
    { title: 'Wrap-up',    detail: 'Write task log file (STATUS/DEVLOG deferred to merge time)' },
  ]
}

// ----------------------------------------------------------------
// Parse args: REQUIRE "1.1-site-credibility-fixes 2" — task number is mandatory
// ----------------------------------------------------------------
const rawArgs = typeof args === 'string' ? args.trim() : ''
if (!rawArgs) {
  log('ERROR: No arguments provided.')
  log('Usage: /sdlc-task 1.1-site-credibility-fixes 2')
  log('Task number is required. For full-spec runs, use /sdlc-run instead.')
  return { error: 'Missing required arguments: spec name and task number' }
}

const parts = rawArgs.split(/\s+/)
const blockId = parts[0]
const taskNumber = parts.length > 1 ? parseInt(parts[1], 10) : null
// --resume: reuse an EXISTING worktree for this task (set by /sdlc-block when a prior run was
// interrupted after implement completed) instead of suffix-incrementing into a fresh duplicate.
const resumeMode = parts.includes('--resume')

if (taskNumber === null || isNaN(taskNumber)) {
  log(`ERROR: Task number is required but not provided (got: "${rawArgs}").`)
  log('Usage: /sdlc-task 1.1-site-credibility-fixes 2')
  log('For full-spec runs use /sdlc-run instead.')
  return { error: 'Task number required', rawArgs }
}

const specFile    = `planning/tasks/${blockId}/tasks.md`
const stem        = `${blockId}-task${taskNumber}`
const reportsDir  = `planning/tasks/${blockId}/reports`
const taskPrefix  = `task${taskNumber}-`
const implementReport = `${reportsDir}/${taskPrefix}implement.md`
const testReport      = `${reportsDir}/${taskPrefix}test.md`
const reviewReport    = `${reportsDir}/${taskPrefix}review.md`
const documentReport  = `${reportsDir}/${taskPrefix}document.md`
const uitestReport    = `${reportsDir}/${taskPrefix}ui-test.md`
const workflowReport  = `${reportsDir}/${taskPrefix}workflow.md`
const logFile         = `${reportsDir}/${taskPrefix}log.md`
const breakdownFile   = `planning/tasks/${blockId}/breakdown.md`

// Base branch name (suffix may be appended by setup agent).
// Dots are kept so a phase-dotted spec slug (e.g. 1.1-site-credibility-fixes) round-trips
// to its planning/tasks/<slug>/ directory; git allows '.' in a branch name (just not '..').
const baseBranchName = `${blockId}-task${taskNumber}`.toLowerCase().replace(/[^a-z0-9.-]/g, '-')

log(`Target: ${blockId} task ${taskNumber}`)
log(`Spec: ${specFile} | Stem: ${stem}`)

// ----------------------------------------------------------------
// Schemas
// ----------------------------------------------------------------
const SETUP_SCHEMA = {
  type: 'object',
  required: ['branchName', 'worktreePath', 'wasCreated'],
  properties: {
    branchName:    { type: 'string', description: 'Actual branch name used (may have -2, -3 suffix if base was taken)' },
    worktreePath:  { type: 'string', description: 'Absolute path to the worktree directory' },
    wasCreated:    { type: 'boolean', description: 'true if a new worktree was created, false if it already existed' },
    notes:         { type: 'string' }
  }
}

const SCOUT_SCHEMA = {
  type: 'object',
  required: ['startStage', 'specFileExists', 'blockStatus', 'existingReports', 'statusSummary'],
  properties: {
    startStage: {
      type: 'string',
      enum: ['generate-tasks', 'implement', 'fix', 'test', 'review', 'ui-test', 'document', 'wrap-up'],
    },
    specFileExists:    { type: 'boolean' },
    blockStatus: {
      type: 'string',
      enum: ['Not started', 'In progress', 'Done', 'Blocked', 'Skipped', 'Unknown'],
    },
    existingReports:   { type: 'array', items: { type: 'string' } },
    reviewVerdict:     { type: 'string', description: 'PASS, FAIL, PARTIAL, or empty string' },
    currentFocus:      { type: 'string' },
    lastDevlogEntry:   { type: 'string' },
    statusSummary:     { type: 'string' },
    discrepancies:     { type: 'string' }
  }
}

const STAGE_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'success'],
  properties: {
    reportFile:     { type: 'string' },
    success:        { type: 'boolean' },
    filesModified:  { type: 'array', items: { type: 'string' } },
    commitHash:     { type: 'string' },
    notes:          { type: 'string' }
  }
}

const TEST_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'allPassed', 'passCount', 'failCount'],
  properties: {
    reportFile:   { type: 'string' },
    allPassed:    { type: 'boolean' },
    passCount:    { type: 'integer' },
    failCount:    { type: 'integer' },
    failedTests:  { type: 'array', items: { type: 'string' } },
    notes:        { type: 'string' }
  }
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'verdict'],
  properties: {
    reportFile:      { type: 'string' },
    verdict:         { type: 'string', enum: ['PASS', 'FAIL', 'PARTIAL'] },
    failureReasons:  { type: 'array', items: { type: 'string' } },
    unmetCriteria:   { type: 'array', items: { type: 'string' } },
    notes:           { type: 'string' }
  }
}

const LOG_SCHEMA = {
  type: 'object',
  required: ['logFile', 'applied'],
  properties: {
    logFile:    { type: 'string' },
    applied:    { type: 'boolean' },
    nextFocus:  { type: 'string', description: 'The Current focus string written to the log file' },
    notes:      { type: 'string', description: 'Any decisions that should be added to DECISIONS.md' }
  }
}

const FINALIZE_SCHEMA = {
  type: 'object',
  required: ['workflowReportFile', 'commitMessage'],
  properties: {
    workflowReportFile: { type: 'string' },
    commitMessage:      { type: 'string' },
    commitHash:         { type: 'string' },
    notes:              { type: 'string' }
  }
}

const UI_TEST_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'verdict'],
  properties: {
    reportFile:      { type: 'string' },
    verdict:         { type: 'string', enum: ['PASS', 'WARN', 'FAIL', 'SKIPPED'] },
    failureReasons:  { type: 'array', items: { type: 'string' } },
    notes:           { type: 'string' }
  }
}

// ----------------------------------------------------------------
// MODEL TIERING — the primary token lever for this pipeline.
//
// Principle: match the model to the work. Opus earns its cost on PLANNING; Haiku handles the
// purely-mechanical stages; Sonnet handles the judgment work in between.
//   • Opus   — generate-tasks (authors the spec; fallback path only)
//   • Haiku  — scout / test / finalize. Each is a fixed procedure with no real judgment:
//              scout is a deterministic file-existence decision tree, test runs 6 commands and
//              reads exit codes (review re-runs npm test authoritatively anyway), and finalize
//              just fills a JS-precomputed table and runs scripted git adds.
//   • Sonnet — implement / fix / review / document / task-log. A sharp spec + breakdown makes
//              these well-scoped enough that Sonnet does them reliably. (Review is gated by an
//              authoritative fresh-test run, and fix failures escalate rather than silently ship.)
//   • Sonnet — worktree-setup stays here too: scripted, but it runs once and a failure aborts the
//              whole pipeline, so the tiny Haiku saving isn't worth the blast radius.
//
// Note: the REAL planning usually happens upstream in the /generate-tasks and /breakdown
// SKILLS (run those on an Opus session). The generate-tasks stage below is only a fallback
// that fires when the spec file is missing — pinned to Opus so that path is strong too.
//
// To re-tier, change one value here — nothing else moves.
// Valid values: 'haiku' | 'sonnet' | 'opus' | undefined (inherit session model).
// ----------------------------------------------------------------
const MODEL = {
  worktreeSetup: 'sonnet',   // scripted git, but runs once per task and a failure aborts the whole
                             //   pipeline (high blast radius) — not worth Haiku's risk for the tiny saving
  scout:         'haiku',    // deterministic decision tree: ls a few files, apply a fixed 7-rule order
  generateTasks: 'opus',     // PLANNING — authors the spec that drives everything (fallback path)
  implement:     'sonnet',   // writes content/code + tests against a scoped spec/breakdown
  fix:           'sonnet',   // targeted fixes; failures escalate, never silently ship
  test:          'haiku',    // run 6 fixed commands, read exit codes; review re-runs npm test authoritatively
  review:        'sonnet',   // verify criteria; gated by an authoritative fresh-test run
  uiTest:        'sonnet',   // live browser smoke checks via playwright-cli; needs judgment to interpret results
  document:      'sonnet',   // surgical doc patches, gated on PASS
  taskLog:       'sonnet',   // authors the human-facing DEVLOG prose + STATUS lines — keep the quality
  finalize:      'haiku',    // assembles a JS-precomputed table + scripted git add; can't break the pipeline
}

// Merge an optional model override into an agent's opts (omits the key when undefined,
// so the agent inherits the session model rather than receiving model: undefined).
function withModel(base, model) {
  return model ? { ...base, model } : base
}

// ----------------------------------------------------------------
// Stage results accumulator
// ----------------------------------------------------------------
const stageResults = []

// ================================================================
// PHASE 0: WORKTREE SETUP — auto-create isolated worktree
// ================================================================
phase('Worktree')
log(`Setting up worktree for ${stem}${resumeMode ? ' (resume mode — reuse existing worktree if present)' : ''}...`)

const setupResult = await agent(`
You are the worktree setup agent. Your job is to create (or locate) an isolated git worktree
for this pipeline run. All bash commands run from the MAIN REPO ROOT (your current CWD).

Target:
  Spec:           ${blockId}
  Task:           ${taskNumber}
  Base name:      ${baseBranchName}

STEP 1 — Get the absolute path to the repo root:
  Run: git rev-parse --show-toplevel
  Store the output as repoRoot (trim whitespace).
${resumeMode ? `
RESUME MODE IS ON — reuse the existing worktree for this task instead of creating a fresh one.
  a. Check whether the base worktree directory exists:
       git worktree list | grep "trees/${baseBranchName}" && echo "WT_EXISTS" || echo "WT_MISSING"
  b. Check whether the base branch exists:
       git branch --list "${baseBranchName}"
  Then:
  - WT_EXISTS → REUSE it verbatim. Set branchName="${baseBranchName}", do NOT create anything,
    do NOT recreate the empty init commit. Skip STEP 2 and STEP 3 entirely; go to STEP 4.
    Set wasCreated=false.
  - WT_MISSING but the branch "${baseBranchName}" exists (orphan branch, dir was removed) →
    re-attach a worktree to the existing branch (note: NO -b flag, so it checks out the existing branch):
       mkdir -p trees
       git worktree add --no-checkout trees/${baseBranchName} ${baseBranchName}
       git -C trees/${baseBranchName} sparse-checkout init --cone
       git -C trees/${baseBranchName} sparse-checkout set app components hooks lib content scripts docs planning .claude __tests__ __mocks__ types
       git -C trees/${baseBranchName} checkout
       if [ -f .env ]; then cp .env trees/${baseBranchName}/.env; fi
       if [ -f .env.local ]; then cp .env.local trees/${baseBranchName}/.env.local; fi
    Set branchName="${baseBranchName}", wasCreated=false. Skip STEP 2 and STEP 3; go to STEP 4.
  - Neither exists → resume was requested but nothing is there; fall through to STEP 2/3 and create
    a fresh worktree named "${baseBranchName}" as normal.
` : ''}
STEP 2 — Find a free worktree name using this exact algorithm:

  Start with candidate = "${baseBranchName}" and work through each suffix in turn:

  Iteration 1 — candidate = "${baseBranchName}":
    Run: git worktree list | grep "trees/${baseBranchName}"
    Run: git branch --list "${baseBranchName}"
    If BOTH return nothing → "${baseBranchName}" is free. Use it. Skip to STEP 3.

  Iteration 2 — candidate = "${baseBranchName}-2":
    Run: git worktree list | grep "trees/${baseBranchName}-2"
    Run: git branch --list "${baseBranchName}-2"
    If BOTH return nothing → "${baseBranchName}-2" is free. Use it. Skip to STEP 3.

  Iteration 3 — candidate = "${baseBranchName}-3":
    ... same pattern ...

  Continue through "-10" as the cap. Use the first free candidate found.
  Store the chosen name as branchName.

STEP 3 — Create the worktree:
  Run these commands in order (replace [branchName] and [repoRoot] with actual values):

  a. mkdir -p trees
  b. git worktree add --no-checkout trees/[branchName] -b [branchName]
  c. git -C trees/[branchName] sparse-checkout init --cone
  d. git -C trees/[branchName] sparse-checkout set app components hooks lib content scripts docs planning .claude __tests__ __mocks__ types
  e. git -C trees/[branchName] checkout
  f. if [ -f .env ]; then cp .env trees/[branchName]/.env; fi
  g. if [ -f .env.local ]; then cp .env.local trees/[branchName]/.env.local; fi
  h. git -C trees/[branchName] commit --allow-empty -m "chore: init worktree [branchName]"

STEP 4 — Verify:
  Run: git worktree list
  Run: ls trees/[branchName]/
  Confirm the worktree exists and contains app/, components/, content/, planning/, .claude/ directories.

STEP 5 — Compute the absolute worktree path:
  worktreePath = repoRoot + "/trees/" + branchName

Return your result using the StructuredOutput tool:
  branchName:   the final chosen branch name (e.g. "${baseBranchName}" or "${baseBranchName}-2")
  worktreePath: the ABSOLUTE path to the worktree (e.g. ~/agentic-portfolio)
  wasCreated:   true if a NEW worktree was created; false if an existing one was reused (resume mode)
  notes:        any issues encountered
`, withModel({ label: 'worktree-setup', schema: SETUP_SCHEMA, phase: 'Worktree' }, MODEL.worktreeSetup))

if (!setupResult) {
  log('Worktree setup agent returned null — aborting pipeline')
  return { error: 'Worktree setup failed', blockId, taskNumber, stem }
}

const { branchName, worktreePath } = setupResult
log(`Worktree ready: ${worktreePath} (branch: ${branchName})`)
stageResults.push({ stage: 'worktree-setup', ...setupResult, success: true })

// ----------------------------------------------------------------
// Build the worktree path injection header — prepended to EVERY agent prompt
// ----------------------------------------------------------------
const W = `
╔══════════════════════════════════════════════════════════════════╗
║  WORKING DIRECTORY: ${worktreePath}
║
║  You are in a git worktree — NOT the main repo.
║  Shell state does NOT persist between Bash tool calls.
║  START EVERY Bash tool call with:
║    cd ${worktreePath} &&
║
║  "repo root" = ${worktreePath}
║  Run npm commands (npm test, npm run build, etc.) from the repo root.
║  Relative paths (planning/tasks/...) resolve from: ${worktreePath}
╚══════════════════════════════════════════════════════════════════╝
`

// ================================================================
// PHASE 1: SCOUT — determine current pipeline stage
// ================================================================
phase('Scout')

const scout = await agent(`${W}
You are the pipeline scout for the SDLC workflow system.

Target:
  Spec ID:     ${blockId}
  Task number: ${taskNumber}
  Spec file:   ${specFile}
  Report stem: ${stem}
  Reports dir: ${reportsDir}

Your job is to determine which SDLC stage to start from, based on which report files exist.
Run these checks using the Bash tool (all commands start with: cd ${worktreePath} &&):

STEP 1 — Check spec file:
  cd ${worktreePath} && ls -la ${specFile} 2>/dev/null && echo "SPEC_EXISTS" || echo "SPEC_MISSING"

STEP 2 — Check report files:
  cd ${worktreePath} && ls ${implementReport} 2>/dev/null && echo "HAS_IMPLEMENT" || echo "NO_IMPLEMENT"
  cd ${worktreePath} && ls ${testReport} 2>/dev/null && echo "HAS_TEST" || echo "NO_TEST"
  cd ${worktreePath} && ls ${reviewReport} 2>/dev/null && echo "HAS_REVIEW" || echo "NO_REVIEW"
  cd ${worktreePath} && ls ${uitestReport} 2>/dev/null && echo "HAS_UITEST" || echo "NO_UITEST"
  cd ${worktreePath} && ls ${documentReport} 2>/dev/null && echo "HAS_DOCUMENT" || echo "NO_DOCUMENT"
  cd ${worktreePath} && ls ${reportsDir}/*.md 2>/dev/null | head -20 || echo "NO_BLOCK_REPORTS"

STEP 3 — Read STATUS.md:
  cd ${worktreePath} && head -60 planning/STATUS.md

STEP 4 — Read recent DEVLOG (at the worktree root):
  cd ${worktreePath} && head -60 DEVLOG.md

STEP 5 — If review report exists, extract the verdict:
  cd ${worktreePath} && grep -iE "\\*\\*Verdict|## Verdict|^Verdict:" ${reviewReport} 2>/dev/null | head -5 || echo "NO_REVIEW_REPORT"

STEP 6 — Determine startStage using this EXACT priority order:
  1. Spec file MISSING → "generate-tasks"
  2. Spec exists, no implement report → "implement"
  3. Implement report exists, no test report → "test"
  4. Test report exists, no review report → "review"
  5. Review report with FAIL or PARTIAL verdict → "fix"
  6. Review report with PASS verdict, no ui-test report → "ui-test"
  7. Review report with PASS verdict, ui-test report exists, no document report → "document"
  8. Document report exists → "wrap-up"

STEP 7 — Find this spec's status in STATUS.md progress table. Look for a row containing
  "${blockId}" and extract its Status column value (title-case: Not started / In progress / Done / Blocked / Skipped).

STEP 8 — Note any discrepancy between DEVLOG and report files.

Return your findings using the StructuredOutput tool.
`, withModel({ label: 'scout', schema: SCOUT_SCHEMA, phase: 'Scout' }, MODEL.scout))

if (!scout) {
  log('Scout agent failed — cannot determine pipeline state, aborting')
  return { error: 'Scout failed', blockId, taskNumber, stem }
}

log(`Scout: start from "${scout.startStage}" | block status: "${scout.blockStatus}"`)
if (scout.discrepancies) log(`Discrepancies: ${scout.discrepancies}`)
if (scout.statusSummary) log(scout.statusSummary)

// Block "Not started" warning — do NOT edit STATUS.md in the worktree.
// STATUS.md changes are always deferred to the task log (applied at merge time).
// If the block needs to be flipped before parallel tasks start, run /start-block first.
if (scout.blockStatus === 'Not started') {
  log(`Note: Spec "${blockId}" is "Not started" in STATUS.md.`)
  log(`The task log will record the status flip — applied when this branch merges to main.`)
  log(`To update STATUS.md immediately (e.g. before other parallel tasks start), run /start-block ${blockId} from the main session.`)
}

let currentStage = scout.startStage
let reviewAttempts = 0
const MAX_REVIEW_ATTEMPTS = 3
let lastReviewResult = null

// STAGED MODEL ESCALATION — the FINAL fix pass and FINAL review attempt before the loop
// gives up run on a stronger model. The common path stays on Sonnet (MODEL.fix/review);
// only the genuinely-hard case that has already failed twice gets one Opus shot before
// the task escalates to /sdlc-block triage (or a FAIL wrap-up). Set to null to disable.
const ESCALATION_MODEL = 'opus'

// ================================================================
// PHASE 2: PLAN — generate-tasks (only if spec file missing)
// ================================================================
if (currentStage === 'generate-tasks') {
  phase('Plan')
  log('Spec file not found — running generate-tasks...')

  const genResult = await agent(`${W}
You need to generate the task spec for "${blockId}".

Spec file to create: ${specFile}
Worktree root: ${worktreePath}

Instructions:

1. Read planning/MASTER_PLAN.md (at the worktree root) — find the section covering "${blockId}".
   Run: cd ${worktreePath} && cat planning/MASTER_PLAN.md

2. Read CLAUDE.md — note all standing rules (bilingual parity, public-narrative rule,
   no fabricated metrics, validate:content + build must pass).
   Run: cd ${worktreePath} && cat CLAUDE.md

3. Read an existing spec as format reference:
   cd ${worktreePath} && cat planning/tasks/1.1-site-credibility-fixes/tasks.md

   Also create the spec directory structure now if it does not exist:
   cd ${worktreePath} && mkdir -p planning/tasks/${blockId}/reports

4. Write ${specFile} (absolute path: ${worktreePath}/${specFile}) following the standard format.

   Rules:
   - Every task ships with the validation that proves it (npm run validate:content + npm run build pass)
   - Content tasks must respect bilingual parity (EN + pt-BR) or record the deferral in ## Notes
   - The final task must always be "Validate"
   - Tasks should be numbered ### 1., ### 2., etc.
   - Include exact file paths (.ts / .tsx / .mdx) and component/function names
   - Include a ## Validation Commands block using: npm run lint, npx tsc --noEmit,
     npm run validate:content, npm test, npm run build

Return using StructuredOutput:
  reportFile: "${specFile}"
  success: true if written successfully
  filesModified: ["${specFile}"]
  notes: brief note about what was generated
`, { label: 'generate-tasks', schema: STAGE_SCHEMA, phase: 'Plan' })

  if (!genResult || !genResult.success) {
    log('generate-tasks failed — aborting pipeline')
    stageResults.push({ stage: 'generate-tasks', success: false })
    return { error: 'generate-tasks failed', blockId, taskNumber, stem, stageResults }
  }
  stageResults.push({ stage: 'generate-tasks', ...genResult })
  log(`Task spec written: ${genResult.reportFile}`)
  currentStage = 'implement'
}

// ================================================================
// PHASES 3–5: IMPLEMENT → (FIX →) TEST → REVIEW (with retry loop)
// ================================================================
while (['implement', 'fix', 'test', 'review', 'ui-test'].includes(currentStage) && reviewAttempts < MAX_REVIEW_ATTEMPTS) {

  // ----------------------------------------------------------
  // IMPLEMENT
  // ----------------------------------------------------------
  if (currentStage === 'implement') {
    phase('Implement')
    log('Running implement...')

    const implResult = await agent(`${W}
You are the implementation agent for the SDLC pipeline.

Target:
  Spec:            ${blockId}
  Task:            Task ${taskNumber} only
  Spec file:       ${specFile}
  Report to write: ${implementReport}
  Worktree root:   ${worktreePath}

Instructions:

1. Read CLAUDE.md — internalize all standing rules.
   Run: cd ${worktreePath} && cat CLAUDE.md

2. Read the spec file, focusing on the "### ${taskNumber}." section:
   Run: cd ${worktreePath} && cat ${specFile}
   Implement ONLY the "### ${taskNumber}." section. Do not implement other tasks.

2.5. Check for an optional breakdown file (more granular sub-steps written by /breakdown):
   Run: cd ${worktreePath} && ls ${breakdownFile} 2>/dev/null && echo "BREAKDOWN_EXISTS" || echo "NO_BREAKDOWN"

   If BREAKDOWN_EXISTS:
     Read ${worktreePath}/${breakdownFile}
     Find the "### Step ${taskNumber}:" section — use its atomic sub-steps as the primary
     execution guide for HOW to implement this task.
     Inline "Verify:" commands are live checkpoints — run each before moving to the next sub-step.
     tasks.md is authoritative for scope/acceptance criteria; breakdown.md is authoritative for HOW.

   If NO_BREAKDOWN: proceed using tasks.md only.

3. Execute each step methodically using Read, Edit, Write, and Bash tools.
   ALL file paths must be absolute (under ${worktreePath}) OR use:
     cd ${worktreePath} && <command>

4. As you implement, follow every CLAUDE.md standing rule:
   - Bilingual parity: a content change in one locale (content/.../en/) must be mirrored in
     pt-BR (content/.../pt-BR/) or the deferral recorded in the spec's ## Notes / deviations
   - Public-narrative rule: Brandon is the subject; never name/criticize a former employer;
     de-identify Helpscout & AI Scribe; the April-2025 proposal story stays private
   - No fabricated metrics — every number must be verifiable
   - Pages are defined ONCE under app/[locale]/; content is MDX under content/
   - Add or update tests for any new lib/ or component logic

5. Run the Validation Commands from the spec to confirm correctness:
   cd ${worktreePath} && npm test 2>&1 | tail -20
   cd ${worktreePath} && npm run lint 2>&1 | tail -20
   cd ${worktreePath} && npm run validate:content 2>&1 | tail -20   # for content-touching tasks

6. Write the implementation report:
   Absolute path: ${worktreePath}/${implementReport}

   Format:
   # Implementation Report — ${stem}

   **Date:** [run: cd ${worktreePath} && date +%Y-%m-%d]
   **Plan:** ${specFile}
   **Scope:** Task ${taskNumber}

   ## What Was Built or Changed
   - [bullet list with file paths]

   ## Files Created or Modified
   | File | Action |
   |---|---|
   | path/to/file.tsx | created / modified |

   ## Validation Output
   **Commands run:**
   \`\`\`
   [commands]
   \`\`\`
   **Results:**
   \`\`\`
   [actual output]
   \`\`\`
   Status: PASSED / FAILED

   ## Decisions and Trade-offs
   [non-obvious choices]

   ## Follow-up Work
   [anything deferred]

   ## git diff --stat
   \`\`\`
   [run: cd ${worktreePath} && git diff --stat]
   \`\`\`

7. Commit your changes. Run from the worktree:
   cd ${worktreePath} && git status
   Stage files explicitly by name (never git add -A or git add .):
     cd ${worktreePath} && git add components/Foo.tsx __tests__/foo.test.ts ${implementReport}
   Commit using HEREDOC:
     cd ${worktreePath} && git commit -m "$(cat <<'EOF'
     feat: implement ${stem}

     EOF
     )"
   Run: cd ${worktreePath} && git log --oneline -1

Return using StructuredOutput:
  reportFile: "${implementReport}"
  success: true if implementation completed without critical errors
  filesModified: array of source files created or modified
  commitHash: 7-character short hash from git log --oneline -1
  notes: one-line summary
`, { label: 'implement', schema: STAGE_SCHEMA, phase: 'Implement' })

    if (!implResult) {
      log('Implement agent returned null — aborting pipeline')
      stageResults.push({ stage: 'implement', success: false, notes: 'Agent returned null' })
      break
    }
    stageResults.push({ stage: 'implement', ...implResult })
    if (!implResult.success) {
      log('Implement reported failure — aborting pipeline')
      break
    }
    currentStage = 'test'
  }

  // ----------------------------------------------------------
  // FIX (review retry path)
  // ----------------------------------------------------------
  if (currentStage === 'fix') {
    phase('Fix')
    const fixPass = reviewAttempts + 1
    log(`Running fix (pass ${fixPass}) — targeting review failures...`)

    // Last fix pass before the loop can give up → escalate the model.
    const fixModel = (ESCALATION_MODEL && fixPass === MAX_REVIEW_ATTEMPTS) ? ESCALATION_MODEL : MODEL.fix
    if (fixModel !== MODEL.fix) log(`Final fix pass — escalating model to ${fixModel}.`)

    const fixResult = await agent(`${W}
You are the fix agent for the SDLC pipeline. Make targeted fixes for the failures identified
in the last review — NOT a full re-implementation.

Target:
  Spec:                 ${blockId}
  Task:                 Task ${taskNumber}
  Review report:        ${reviewReport}
  Prior implement report: ${implementReport}
  Report to write:      ${implementReport}  ← overwrites this slot (Fix Pass ${fixPass})
  Worktree root:        ${worktreePath}

GATE CHECKS (do these first):
1. cd ${worktreePath} && ls ${reviewReport} 2>/dev/null && echo EXISTS || echo MISSING
   If MISSING → stop, return success: false, notes: "No review report found."
2. cd ${worktreePath} && grep -i "verdict" ${reviewReport} | head -3
   If verdict is PASS → stop, return success: false, notes: "Review verdict is already PASS."

Instructions:

1. Read the review report:
   cd ${worktreePath} && cat ${reviewReport}
   Extract: failing criteria, Issues Found section, Fresh Test Results.

2. Read the prior implement report:
   cd ${worktreePath} && cat ${implementReport}

3. If a breakdown file exists, check the relevant sub-steps for original intent:
   Run: cd ${worktreePath} && ls ${breakdownFile} 2>/dev/null && echo EXISTS || echo MISSING
   If EXISTS: read ${worktreePath}/${breakdownFile} and find the "### Step ${taskNumber}:" section.
   Use it to understand what the original implementation was supposed to do for the failing criterion.
   Do NOT re-implement from scratch — use it only as context for the targeted fix.

4. Make MINIMUM targeted changes to address the failing criteria.
   Fix ONLY what the review identified as failing.

5. Run the Validation Commands from the spec:
   cd ${worktreePath} && cat ${specFile} | grep -A 20 "## Validation Commands"
   Then run those commands.

6. Overwrite the implement report at: ${worktreePath}/${implementReport}

   Format:
   # Fix Pass ${fixPass} — ${stem}

   **Date:** [run: cd ${worktreePath} && date +%Y-%m-%d]
   **Plan:** ${specFile}
   **Fix pass:** ${fixPass}

   ## Failures Addressed
   [each failing criterion and how it was fixed]

   ## Changes Made
   - [targeted changes with file paths]

   ## Files Created or Modified
   | File | Action |
   |---|---|
   [IMPORTANT: include ALL files from prior implement report PLUS newly touched files]

   ## Validation Output
   [commands and actual output]
   Status: PASSED / FAILED

   ## git diff --stat
   \`\`\`
   [run: cd ${worktreePath} && git diff --stat]
   \`\`\`

7. Commit your changes:
   cd ${worktreePath} && git status
   cd ${worktreePath} && git add <changed files> ${implementReport}
   cd ${worktreePath} && git commit -m "$(cat <<'EOF'
   fix: fix pass ${fixPass} for ${stem}
   EOF
   )"
   cd ${worktreePath} && git log --oneline -1

Return using StructuredOutput:
  reportFile: "${implementReport}"
  success: true if fixes applied and validation passed
  filesModified: files changed this pass only
  commitHash: 7-character short hash
  notes: one-line summary of what was fixed
`, withModel({ label: `fix-${fixPass}`, schema: STAGE_SCHEMA, phase: 'Fix' }, fixModel))

    if (!fixResult) {
      log('Fix agent returned null — aborting pipeline')
      stageResults.push({ stage: 'fix', attempt: fixPass, success: false, notes: 'Agent returned null' })
      break
    }
    stageResults.push({ stage: 'fix', attempt: fixPass, ...fixResult })
    if (!fixResult.success) {
      log(`Fix pass ${fixPass} reported failure — aborting pipeline`)
      break
    }
    currentStage = 'test'
  }

  // ----------------------------------------------------------
  // TEST
  // ----------------------------------------------------------
  if (currentStage === 'test') {
    phase('Test')
    log('Running 7-check test suite...')

    const testResult = await agent(`${W}
You are the test agent for the SDLC pipeline. Run the 7-check validation suite in the worktree.

Target:
  Spec:            ${specFile}
  Report to write: ${testReport}
  Worktree root:   ${worktreePath}

PRE-FLIGHT — Verify all top-level tracked directories exist in this sparse-checkout worktree:
  cd ${worktreePath} && for DIR in $(git ls-tree HEAD --name-only 2>/dev/null); do [ -d "$DIR" ] || echo "MISSING_DIR: $DIR"; done
  If any "MISSING_DIR:" lines appear above, materialize all tracked directories now:
    cd ${worktreePath} && git sparse-checkout reapply && ls -d */ | head -20
  This catches any directory added to main after this worktree was initialized (not just hooks/),
  preventing silent module-resolution failures on checks 2, 5, and 6.

Run ALL 7 checks IN ORDER. Capture full output (stdout + stderr) for each.
All commands start with: cd ${worktreePath} &&

CHECK 1 — ESLint (lint gate):
  cd ${worktreePath} && npm run lint > /tmp/check1-lint.txt 2>&1; echo "CHECK1_EXIT:$?"
  tail -20 /tmp/check1-lint.txt
  grep -E "[0-9]+ (problem|error|warning)" /tmp/check1-lint.txt | tail -3 || echo "(no ESLint problem-count line found)"

CHECK 2 — TypeScript (type gate, replaces pylint):
  cd ${worktreePath} && npx tsc --noEmit 2>&1 | tail -80
  echo "CHECK2_EXIT:\${PIPESTATUS[0]}"

CHECK 3 — Content validation (frontmatter / MDX / internal refs):
  cd ${worktreePath} && npm run validate:content 2>&1 | tail -80
  echo "CHECK3_EXIT:\${PIPESTATUS[0]}"

CHECK 4 — Jest collect (syntax check — does NOT resolve module imports):
  cd ${worktreePath} && npm test -- --listTests > /tmp/check4-list.txt 2>&1; echo "CHECK4_EXIT:$?"
  tail -20 /tmp/check4-list.txt
  CHECK4_COUNT=$(grep -c '\.test\.' /tmp/check4-list.txt 2>/dev/null || echo 0)
  echo "CHECK 4: $CHECK4_COUNT test files discovered"
  [ "$CHECK4_COUNT" -lt 45 ] && echo "WARNING: only $CHECK4_COUNT test files discovered (expected >= 45) — sparse-checkout may be incomplete"
  NOTE: A passing CHECK 4 does NOT guarantee imports work — missing modules cause CHECK 5 to
  fail while CHECK 4 still passes. CHECK 5 is the authoritative module-resolution gate.

CHECK 5 — Jest full (authoritative unit/integration run):
  cd ${worktreePath} && npm test 2>&1 | tail -80
  echo "CHECK5_EXIT:\${PIPESTATUS[0]}"

CHECK 6 — Next build (production build gate):
  cd ${worktreePath} && npm run build 2>&1 | tail -80
  echo "CHECK6_EXIT:\${PIPESTATUS[0]}"

CHECK 7 — Emoji prohibition (CLAUDE.md standing rule):
  Two passes: task-introduced files cause hard FAIL; pre-existing files emit WARN only.

  Pass A — files modified by THIS TASK vs main (hard FAIL if emoji found):
  cd ${worktreePath} && python3 - <<'PYEOF'
import subprocess, re, sys, os
EMOJI = re.compile(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF]')
changed = subprocess.run(['git','diff','main..HEAD','--name-only'], capture_output=True, text=True).stdout.splitlines()
md_files = [f for f in changed if f.endswith(('.md','.mdx')) and os.path.isfile(f)]
hits = []
for path in md_files:
    for n, line in enumerate(open(path, errors='ignore'), 1):
        if EMOJI.search(line):
            hits.append(f'{path}:{n}: {line.rstrip()[:100]}')
if hits:
    print('CHECK 7 FAIL: emoji in task-modified files (violates CLAUDE.md no-emoji rule):')
    for h in hits[:25]: print(h)
    sys.exit(1)
print('CHECK 7 Pass A: OK — no emoji in task-modified files')
sys.exit(0)
PYEOF
  echo "CHECK7_EXIT:$?"

  Pass B — full content/ scan for pre-existing emoji (WARN only — does NOT affect allPassed):
  cd ${worktreePath} && python3 - <<'PYEOF'
import os, re
EMOJI = re.compile(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF]')
hits = []
for root, _, files in os.walk('content'):
    for f in files:
        if not f.endswith(('.md', '.mdx')): continue
        path = os.path.join(root, f)
        for n, line in enumerate(open(path, errors='ignore'), 1):
            if EMOJI.search(line):
                hits.append(f'{path}:{n}: {line.rstrip()[:100]}')
if hits:
    print('CHECK 7 WARN (pre-existing, NOT introduced by this task — fix separately):')
    for h in hits[:25]: print(h)
else:
    print('CHECK 7 Pass B: OK — no pre-existing emoji in content/')
PYEOF
  (Pass B exit code is intentionally ignored — only Pass A determines CHECK7_EXIT)

For content-touching tasks, ALSO note in the report whether bilingual parity (EN/pt-BR mirror)
and link/handle hygiene hold — npm run validate:content partially covers this.

Write the test report to: ${worktreePath}/${testReport}

Format:
# Test Report — ${stem}

**Date:** [run: date +%Y-%m-%d]
**Spec:** ${specFile}
**Scope:** Task ${taskNumber}

## Summary

| Test | Result | Error |
|---|---|---|
[FAILED rows first, then PASSED rows]

## Full Results (JSON)
\`\`\`json
[array of {test_name, passed, execution_command, test_purpose, error}]
\`\`\`

Return using StructuredOutput:
  reportFile: "${testReport}"
  allPassed: true only if ALL 7 checks passed (exit code 0)
  passCount: integer (out of 7)
  failCount: integer (out of 7)
  failedTests: array of test_name strings for failed checks
  notes: one-line summary
`, withModel({ label: 'test', schema: TEST_SCHEMA, phase: 'Test' }, MODEL.test))

    if (!testResult) {
      log('Test agent returned null — recording failure, continuing to review')
      stageResults.push({ stage: 'test', attempt: reviewAttempts + 1, allPassed: false, success: false, notes: 'Agent returned null' })
    } else {
      stageResults.push({ stage: 'test', attempt: reviewAttempts + 1, ...testResult, success: testResult.allPassed })
      if (!testResult.allPassed) {
        log(`Test failures (${testResult.failCount}): ${(testResult.failedTests || []).join(', ')}`)
      } else {
        log(`All ${testResult.passCount} checks passed`)
      }
    }
    currentStage = 'review'
  }

  // ----------------------------------------------------------
  // REVIEW
  // ----------------------------------------------------------
  if (currentStage === 'review') {
    phase('Review')
    reviewAttempts++
    log(`Running review (attempt ${reviewAttempts}/${MAX_REVIEW_ATTEMPTS})...`)

    // Final review attempt before the loop can give up → escalate the model.
    const reviewModel = (ESCALATION_MODEL && reviewAttempts === MAX_REVIEW_ATTEMPTS) ? ESCALATION_MODEL : MODEL.review
    if (reviewModel !== MODEL.review) log(`Final review attempt — escalating model to ${reviewModel}.`)

    const reviewResult = await agent(`${W}
You are the review agent for the SDLC pipeline. Verify the implementation against the spec.

Target:
  Spec:             ${blockId}
  Task:             Task ${taskNumber}
  Spec file:        ${specFile}
  Implement report: ${implementReport}
  Test report:      ${testReport}
  Report to write:  ${reviewReport}
  Worktree root:    ${worktreePath}

Instructions:

1. Read the spec file:
   cd ${worktreePath} && cat ${specFile}
   Extract the COMPLETE "## Acceptance Criteria" section.

2. Read the implement report:
   cd ${worktreePath} && cat ${implementReport}

3. Read the test report:
   cd ${worktreePath} && cat ${testReport}

4. Run FRESH authoritative tests (this result determines the verdict):
   cd ${worktreePath} && npm test 2>&1
   For specs that change routing/pages/components, also run the co-gate:
   cd ${worktreePath} && npm run build 2>&1

5. Scope your review to Task ${taskNumber} only.
   The spec may list acceptance criteria spanning multiple tasks. For each criterion:
   - If tagged for a different task (e.g. "[T5]", "(Task 5)") OR clearly belongs to a later
     task's scope (the work it describes is not in Task ${taskNumber}'s step list) →
     mark SKIP with a note. SKIP criteria do NOT affect the verdict.
   - All others: evaluate normally.

   For each in-scope criterion, read relevant source files and determine:
   MET — fully satisfied by this task's changes
   PARTIAL — partially satisfied
   NOT_MET — not satisfied (counts as a verdict failure)
   Also check CLAUDE.md standing-rules compliance (bilingual parity, public-narrative rule,
   no fabricated metrics, validate:content + build pass) — a violation is a failing criterion.
   URL INTEGRITY: When reading rewritten content, flag any GitHub URLs (github.com/*,
   raw.githubusercontent.com/*) that do NOT use the handle bredmond1019. Mark as NOT_MET
   under "No fabricated metrics" — only bredmond1019 is a verified Brandon handle.

5.5. HARD RULE — do NOT fix environment or infrastructure issues yourself:
   If the fresh npm test or npm run build fails due to environment/infrastructure causes
   (missing module files, sparse-checkout gaps, missing hooks, missing directories), do NOT
   fix them yourself. Return verdict: FAIL with failureReasons: ["Environment issue —
   missing files or sparse-checkout gap; the fix agent must resolve them and re-run the
   pipeline."]. A review agent that resolves infrastructure issues itself bypasses the
   test gate that validates the fix.

6. Determine verdict:
   PASS — ALL criteria MET AND fresh npm test passes (exit 0)
   PARTIAL — some criteria PARTIAL, OR tests pass but some criteria not fully met
   FAIL — any criterion NOT_MET, OR fresh npm test fails
   (A fresh test failure ALWAYS prevents PASS)

7. Write the review report: ${worktreePath}/${reviewReport}

   Format:
   # Review Report — ${stem}

   **Date:** [run: date +%Y-%m-%d]
   **Spec:** ${specFile}
   **Scope:** Task ${taskNumber}
   **Verdict:** PASS / PARTIAL / FAIL

   ## Acceptance Criteria Check
   | Criterion | Status | Evidence |
   |---|---|---|
   | [criterion] | MET / PARTIAL / NOT_MET | [file:line or test name] |

   ## Fresh Test Results
   [npm test summary — pass/fail counts, failure output; build result if run]

   ## Verdict: PASS / PARTIAL / FAIL
   [one paragraph explaining the verdict]

   ## Issues Found
   [specific problems — empty if PASS]

   ## Next Steps
   [what to do based on verdict]

Return using StructuredOutput:
  reportFile: "${reviewReport}"
  verdict: "PASS", "FAIL", or "PARTIAL"
  failureReasons: array of strings (empty if PASS)
  unmetCriteria: array of criterion texts that were NOT_MET or PARTIAL (empty if PASS)
  notes: one-line summary
`, withModel({ label: `review-${reviewAttempts}`, schema: REVIEW_SCHEMA, phase: 'Review' }, reviewModel))

    if (!reviewResult) {
      log(`Review agent returned null (attempt ${reviewAttempts}) — treating as FAIL`)
      lastReviewResult = { verdict: 'FAIL', failureReasons: ['Review agent returned null'], unmetCriteria: [], reportFile: reviewReport }
      stageResults.push({ stage: 'review', attempt: reviewAttempts, verdict: 'FAIL', success: false, notes: 'Agent returned null' })
    } else {
      lastReviewResult = reviewResult
      stageResults.push({ stage: 'review', attempt: reviewAttempts, ...reviewResult, success: reviewResult.verdict === 'PASS' })
      log(`Review verdict: ${reviewResult.verdict} (attempt ${reviewAttempts}/${MAX_REVIEW_ATTEMPTS})`)
    }

    if (lastReviewResult.verdict === 'PASS') {
      currentStage = 'ui-test'
    } else if (reviewAttempts < MAX_REVIEW_ATTEMPTS) {
      log(`Review ${lastReviewResult.verdict} — running fix pass ${reviewAttempts + 1}/${MAX_REVIEW_ATTEMPTS}...`)
      currentStage = 'fix'
    } else {
      log(`Review FAILED after ${MAX_REVIEW_ATTEMPTS} attempts — skipping to wrap-up with FAIL status`)
      currentStage = 'wrap-up'
    }
  }

  // ----------------------------------------------------------
  // UI TEST (after Review PASS — browser smoke check)
  // ----------------------------------------------------------
  if (currentStage === 'ui-test') {
    phase('UI Test')
    log('Running UI test stage...')

    const devPort = 3003 + taskNumber

    const uitestResult = await agent(`${W}
You are the UI test agent for the SDLC pipeline. Your job is to run a quick live browser smoke
check using playwright-cli to catch visual/runtime regressions that Jest cannot catch.

Target:
  Spec:              ${blockId}
  Task:              Task ${taskNumber}
  Implement report:  ${implementReport}
  Report to write:   ${uitestReport}
  Dev server URL:    http://localhost:${devPort}
  Worktree root:     ${worktreePath}

STEP 1 — Triage: does this task touch the frontend?

  Read the implement report:
    cd ${worktreePath} && cat ${implementReport}
  Scan the "Files Modified" list for any paths under app/, components/, or lib/.
  - If ALL changes are under content/ (MDX, JSON) only → set verdict = SKIPPED, write the report, and stop.
    SKIPPED means "no frontend code was modified — browser check is not applicable."
  - If ANY file under app/, components/, or lib/ was modified → continue to STEP 2.

STEP 2 — Start the dev server on port ${devPort} (unique per task to avoid conflicts).

  Check if port ${devPort} is already in use:
    lsof -ti :${devPort} 2>/dev/null && echo "PORT_IN_USE" || echo "PORT_FREE"

  If PORT_IN_USE: the server is already running — skip to STEP 3.
  If PORT_FREE: start the server in the background from the worktree:
    cd ${worktreePath} && PORT=${devPort} npm run dev > /tmp/uitest-${stem}.log 2>&1 &
    echo "SERVER_PID=\$!"

  Wait up to 60 seconds for the ready signal:
    for i in \$(seq 1 30); do grep -q "Ready in" /tmp/uitest-${stem}.log 2>/dev/null && echo "READY" && break; sleep 2; done
    tail -20 /tmp/uitest-${stem}.log

  If "READY" not seen within 60 s, write the report with verdict = FAIL (dev server did not start),
  kill the background process, and stop.

STEP 3 — Run smoke checks using playwright-cli.

  Open a browser session:
    playwright-cli open http://localhost:${devPort}/en/

  Run all 5 checks. For each, record PASS, WARN, or FAIL with evidence:

  CHECK 1 — Homepage renders:
    playwright-cli goto http://localhost:${devPort}/en/
    playwright-cli snapshot
    Verify: page title is not blank and does not contain "404", "500", "Error", "Not Found".
    Verify: at least one nav element is present in the snapshot.

  CHECK 2 — No JS console errors on homepage:
    playwright-cli console
    Verify: no "error"-level entries. "warning"-level entries → WARN (not FAIL).

  CHECK 3 — Nav element present:
    From the snapshot in CHECK 1 — confirm a navigation/header element exists (nav, header, or
    an element with "nav" in its accessible role or text).

  CHECK 4 — Internal link works (pick any link from the homepage snapshot and click it):
    playwright-cli click <ref of any internal link>
    playwright-cli snapshot
    Verify: the target page loads without an error page. URL changed to an expected path.

  CHECK 5 — No 500 errors (sanity check on the /en/about route):
    playwright-cli goto http://localhost:${devPort}/en/about
    playwright-cli snapshot
    Verify: page does not show a 500/error page. Title does not contain "Error" or "500".

  Close the browser session:
    playwright-cli close

STEP 4 — Kill the dev server (only if YOU started it in STEP 2).
  If SERVER_PID was captured: kill \$SERVER_PID 2>/dev/null || true

STEP 5 — Determine verdict and write report.

  Verdict rules:
  - PASS:    All 5 checks passed with no errors.
  - WARN:    All checks passed but console warnings were found.
  - FAIL:    One or more checks failed — list each with quoted evidence.
  - SKIPPED: No frontend files modified (from STEP 1 triage).

  Write the report to ${uitestReport} (absolute: ${worktreePath}/${uitestReport}):
  \`\`\`markdown
  # UI Test Report: ${stem}

  **Verdict:** <PASS|WARN|FAIL|SKIPPED>
  **Date:** <today>

  ## Smoke Check Results

  | Check | Result | Notes |
  |---|---|---|
  | Homepage renders | PASS/FAIL/WARN | |
  | No JS console errors | PASS/WARN | |
  | Nav present | PASS/FAIL | |
  | Internal link works | PASS/FAIL | |
  | /en/about no 500 | PASS/FAIL | |

  ## Summary
  <one paragraph — what was tested and what was found>
  \`\`\`

  Commit the report:
    cd ${worktreePath} && git add ${uitestReport} && git commit -m "test(ui): ui smoke check for ${stem}"

Return the result using StructuredOutput.
`, withModel({ label: 'ui-test', schema: UI_TEST_SCHEMA, phase: 'UI Test' }, MODEL.uiTest))

    if (!uitestResult) {
      log('UI test agent returned null — treating as WARN, continuing to document')
      stageResults.push({ stage: 'ui-test', verdict: 'WARN', success: true, notes: 'Agent returned null' })
      currentStage = 'document'
    } else {
      stageResults.push({ stage: 'ui-test', ...uitestResult, success: uitestResult.verdict !== 'FAIL' })
      log(`UI test verdict: ${uitestResult.verdict}`)

      if (uitestResult.verdict === 'FAIL') {
        if (reviewAttempts < MAX_REVIEW_ATTEMPTS) {
          log(`UI test FAIL — running fix pass ${reviewAttempts + 1}/${MAX_REVIEW_ATTEMPTS}...`)
          currentStage = 'fix'
        } else {
          log(`UI test FAILED after ${MAX_REVIEW_ATTEMPTS} attempts — skipping to wrap-up`)
          currentStage = 'wrap-up'
        }
      } else {
        currentStage = 'document'
      }
    }
  }
} // end implement→fix→test→review→ui-test retry loop

// ================================================================
// PHASE 6: DOCUMENT (gates on PASS verdict)
// ================================================================
if (currentStage === 'document') {
  phase('Document')
  log('Running document stage...')

  const docResult = await agent(`${W}
You are the documentation agent for the SDLC pipeline. Surgically patch docs/ in the worktree.

Target:
  Spec:             ${blockId}
  Task:             Task ${taskNumber}
  Review report:    ${reviewReport}
  Implement report: ${implementReport}
  Report to write:  ${documentReport}
  Worktree root:    ${worktreePath}

Instructions:

1. Read the review report:
   cd ${worktreePath} && cat ${reviewReport}
   GATE CHECK: If the verdict is FAIL or PARTIAL, stop immediately.
   Return: success: false, notes: "Blocked — review verdict was not PASS".

2. Read the implement report:
   cd ${worktreePath} && cat ${implementReport}
   Find the "## Files Created or Modified" table.

3. For each source file in that table, find which docs/*.md files reference it:
   cd ${worktreePath} && grep -rl "ComponentName\\|functionName\\|filename" docs/ 2>/dev/null

4. Read each relevant doc file and surgically patch ONLY affected sections:
   - Update component signatures, prop lists, descriptions that changed
   - Add documentation for new public APIs / lib utilities
   - Never delete documented items that still exist
   - Use the Edit tool with absolute paths: ${worktreePath}/docs/filename.md

5. If a change touched core wiring (lib/, middleware.ts, next.config.mjs, or app/[locale]/ routing)
   and an architecture/patterns doc would need updating, add that doc to NEEDS_REVIEW in the
   document report but do NOT edit it directly.

6. Write the document report: ${worktreePath}/${documentReport}

   Format:
   # Documentation Report — ${stem}

   **Date:** [run: date +%Y-%m-%d]
   **Spec:** ${specFile}
   **Verdict gate:** PASS (confirmed)

   ## Docs Patched
   | Doc File | Section Updated | Change Summary |
   |---|---|---|

   ## Docs Flagged NEEDS_REVIEW
   [list any docs needing human review]

   ## Docs Clean (no changes needed)
   [docs checked but unchanged]

7. Commit your changes:
   cd ${worktreePath} && git status
   If no doc files were patched, commit just the report:
     cd ${worktreePath} && git add ${documentReport}
   If docs were patched:
     cd ${worktreePath} && git add docs/file1.md docs/file2.md ${documentReport}
   cd ${worktreePath} && git commit -m "$(cat <<'EOF'
   docs: update docs for ${stem}
   EOF
   )"
   cd ${worktreePath} && git log --oneline -1

Return using StructuredOutput:
  reportFile: "${documentReport}"
  success: true if docs checked and report written (even if no changes needed)
  filesModified: doc files actually patched (empty if none)
  commitHash: 7-character short hash
  notes: one-line summary
`, withModel({ label: 'document', schema: STAGE_SCHEMA, phase: 'Document' }, MODEL.document))

  if (!docResult) {
    stageResults.push({ stage: 'document', success: false, notes: 'Document agent returned null' })
    log('Document agent returned null')
  } else {
    stageResults.push({ stage: 'document', ...docResult })
    if (!docResult.success) {
      log(`Document stage blocked: ${docResult.notes}`)
    } else {
      log(`Docs updated: ${(docResult.filesModified || []).join(', ') || 'none needed changes'}`)
    }
  }
  currentStage = 'wrap-up'
}

// ================================================================
// PHASE 7: WRAP-UP — write task log (deferred STATUS/DEVLOG) + finalize
// ================================================================
phase('Wrap-up')

const finalVerdict = lastReviewResult?.verdict || 'NOT_REACHED'
const stageResultsSummary = stageResults
  .map(r => `${r.stage}${r.attempt ? `(#${r.attempt})` : ''}: ${r.success ? (r.verdict || 'OK') : 'FAILED'}`)
  .join(' → ')

log(`Wrap-up. Final verdict: ${finalVerdict}. Pipeline: ${stageResultsSummary}`)

// ----------------------------------------------------------------
// TASK LOG: write deferred STATUS/DEVLOG content — do NOT touch those files
// ----------------------------------------------------------------
log('Writing task log (STATUS/DEVLOG deferred to merge time)...')

const logResult = await agent(`${W}
You are the task-log agent for the SDLC pipeline.

Your job is to write a structured task log file that records what STATUS.md and DEVLOG.md
should be updated to. Do NOT modify planning/STATUS.md or DEVLOG.md directly — those files
are updated when the worktree branch is merged into main via /clean-worktree.

Target:
  Spec:             ${blockId}
  Task:             ${taskNumber}
  Final verdict:    ${finalVerdict}
  Review attempts:  ${reviewAttempts}
  Pipeline summary: ${stageResultsSummary}
  Branch:           ${branchName}
  Log file:         ${logFile}
  Worktree root:    ${worktreePath}

Instructions:

1. Read the spec file to identify the NEXT task after ${taskNumber}:
   cd ${worktreePath} && cat ${specFile}
   Look for the section "### ${taskNumber + 1}." to get the next task's title.
   If no task ${taskNumber + 1} exists, note "spec complete".

2. Read current STATUS.md to understand the progress-table notes format (title-case status):
   cd ${worktreePath} && head -30 planning/STATUS.md

3. Get the git log for this pipeline run:
   cd ${worktreePath} && git log --oneline main..HEAD 2>/dev/null || git log --oneline -8

4. Run to get today's date:
   date +%Y-%m-%d

5. Write the task log file: ${worktreePath}/${logFile}

   Use EXACTLY this format (fill in all bracketed values):

   # Task Log — ${blockId} task ${taskNumber}

   **Spec:** ${blockId}
   **Task:** ${taskNumber}
   **Verdict:** ${finalVerdict}
   **Date:** [today's date from step 4]
   **Branch:** ${branchName}
   **Applied:** false

   ---

   ## STATUS.md — Spec Status
   [Only include this section if the spec was "Not started" when this task ran (blockStatus: ${scout.blockStatus}).
    Write: "In progress" to flip it. Omit this section entirely if it was already In progress or Done.]

   ## STATUS.md — Current Focus Line
   [The COMPLETE replacement string for the "Current focus:" line.
    If task ${taskNumber + 1} exists: "${blockId} — Task ${taskNumber + 1}: [task title]"
    If spec complete: the next spec's focus line]

   ## STATUS.md — Last Updated Line
   [The COMPLETE replacement string for the "Last updated:" line.
    Format: "YYYY-MM-DD — ${blockId} in progress (Tasks 1–${taskNumber} complete; Tasks ${taskNumber + 1}–N next — [brief description])"]

   ## STATUS.md — Notes Column
   [The updated Notes column text for this spec's row in the progress table.
    Summarizes which tasks are done and which remain.]

   ---

   ## DEVLOG Entry

   ## [today's date] (task ${taskNumber} — [brief description matching the task])

   [One paragraph: what was implemented or tested, how review went (${finalVerdict} verdict${reviewAttempts > 1 ? ` after ${reviewAttempts} attempts` : ''}), notable findings. End with: "Next: Task ${taskNumber + 1} — [next task description]."]

   \`\`\`
   [paste the git log --oneline output from step 3]
   \`\`\`

6. Do NOT commit the log file — the finalize agent will commit it with all other reports.

Return using StructuredOutput:
  logFile: "${logFile}"
  applied: false
  nextFocus: the exact Current Focus Line string you wrote to the log
  notes: any settled decisions that should be added to DECISIONS.md
`, withModel({ label: 'task-log', schema: LOG_SCHEMA, phase: 'Wrap-up' }, MODEL.taskLog))

if (logResult) {
  stageResults.push({ stage: 'task-log', ...logResult, success: true })
  log(`Task log written: ${logFile}`)
  if (logResult.notes) log(`Decisions to log manually: ${logResult.notes}`)
} else {
  stageResults.push({ stage: 'task-log', success: false, notes: 'Agent returned null' })
  log('Task-log agent returned null — log file may need manual creation')
}

// ----------------------------------------------------------------
// FINALIZE: workflow report + commit all reports + print merge instructions
// ----------------------------------------------------------------
log('Running finalize: workflow report + commit...')

const stageTable = stageResults.map(r => {
  const label  = r.stage + (r.attempt ? ` (attempt ${r.attempt})` : '')
  const status = r.verdict ? r.verdict : (r.success ? 'completed' : 'FAILED')
  const file   = r.reportFile || r.workflowReportFile || r.logFile || '—'
  const commit = r.commitHash ? r.commitHash.substring(0, 7) : '—'
  const notes  = (r.notes || '').substring(0, 60)
  return `| ${label} | ${status} | ${file} | ${commit} | ${notes} |`
}).join('\n')

const finalizeResult = await agent(`${W}
You are the finalize agent for the SDLC pipeline.

IMPORTANT: Do NOT modify planning/STATUS.md or DEVLOG.md. Those are applied at merge time.
Your chore commit includes ONLY: test report, review report, document report, task log,
and the workflow report you write here.

Target:
  Spec:            ${blockId}
  Task:            Task ${taskNumber}
  Final verdict:   ${finalVerdict}
  Worktree root:   ${worktreePath}
  Branch:          ${branchName}
  Workflow report: ${workflowReport}

Stage results so far:
${stageResultsSummary}

STEP 1 — Get the commit history from this pipeline run:
  cd ${worktreePath} && git log --oneline -15

STEP 2 — Write the workflow report: ${worktreePath}/${workflowReport}

  Format:
  # SDLC Workflow Report — ${blockId} Task ${taskNumber}

  **Date:** [run: date +%Y-%m-%d]
  **Spec:** ${blockId}
  **Task scope:** Task ${taskNumber}
  **Pipeline started from:** ${scout.startStage}
  **Review attempts:** ${reviewAttempts} of ${MAX_REVIEW_ATTEMPTS} max
  **Worktree:** ${worktreePath}
  **Branch:** ${branchName}

  ## Final Verdict
  ${finalVerdict} — [one sentence explanation]

  ## Stage Results

  | Stage | Status | Report | Commit | Notes |
  |---|---|---|---|---|
  ${stageTable}

  ## Key Findings
  [what was implemented, notable decisions, content/bilingual-parity notes]

  ## Files Modified
  [source files created or modified — from the implement report]

  ## Docs Updated
  [doc files patched — from the document report; NEEDS_REVIEW flags]

  ## Commits (this pipeline run)
  [relevant lines from git log --oneline]

  ## Next Step
  To merge this task into main and apply STATUS/DEVLOG updates:
    /clean-worktree ${branchName}

STEP 3 — Commit the report files. Never use git add -A or git add .

  Run: cd ${worktreePath} && git status
  Stage ONLY report files (NOT STATUS.md or DEVLOG.md — never touch those in the worktree):
    cd ${worktreePath} && git add ${testReport} 2>/dev/null || true
    cd ${worktreePath} && git add ${reviewReport} 2>/dev/null || true
    cd ${worktreePath} && git add ${uitestReport} 2>/dev/null || true
    cd ${worktreePath} && git add ${documentReport} 2>/dev/null || true
    cd ${worktreePath} && git add ${logFile} 2>/dev/null || true
    cd ${worktreePath} && git add ${workflowReport}

  Commit using HEREDOC:
    cd ${worktreePath} && git commit -m "$(cat <<'EOF'
    chore: wrap up ${stem}
    EOF
    )"
  cd ${worktreePath} && git log --oneline -1

STEP 4 — Print the merge instructions EXACTLY as shown:

  ╔══════════════════════════════════════════════════════════════════╗
  ║  Pipeline complete: ${stem}
  ║  Verdict: ${finalVerdict}
  ║
  ║  Worktree: ${worktreePath}
  ║  Branch:   ${branchName}
  ║
  ║  To merge and apply STATUS/DEVLOG updates, run from main session:
  ║    /clean-worktree ${branchName}
  ╚══════════════════════════════════════════════════════════════════╝

Return using StructuredOutput:
  workflowReportFile: "${workflowReport}"
  commitMessage: "chore: wrap up ${stem}"
  commitHash: 7-character short hash from git log --oneline -1
  notes: any follow-up items (DECISIONS.md entries, NEEDS_REVIEW doc flags)
`, withModel({ label: 'finalize', schema: FINALIZE_SCHEMA, phase: 'Wrap-up' }, MODEL.finalize))

if (finalizeResult) {
  stageResults.push({ stage: 'finalize', ...finalizeResult, success: true })
  log(`Committed: ${finalizeResult.commitMessage}`)
  log(`Workflow report: ${finalizeResult.workflowReportFile}`)
} else {
  stageResults.push({ stage: 'finalize', success: false, notes: 'Finalize agent returned null' })
  log('Finalize agent returned null — manual commit may be needed')
}

log(`Pipeline complete. Verdict: ${finalVerdict} | Worktree: ${worktreePath} | Branch: ${branchName}`)
log(`To merge: /clean-worktree ${branchName}`)
log(`IMPORTANT: If running multiple tasks in parallel, merge them in task-number order.`)
log(`Merging out of order will cause STATUS.md "Current focus" to point to the wrong next task.`)

return {
  blockId,
  taskNumber,
  stem,
  branchName,
  worktreePath,
  finalVerdict,
  reviewAttempts,
  startStage: scout.startStage,
  workflowReport: finalizeResult?.workflowReportFile || workflowReport,
  logFile,
  mergeCommand: `/clean-worktree ${branchName}`,
  stageResults
}
