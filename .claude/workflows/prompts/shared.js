// ============================================================================
// SHARED ENGINE LIBRARY — the master copy of every block that is identical in
// BOTH .claude/workflows/sdlc-task.js and .claude/workflows/sdlc-flow.js.
//
// THIS FILE IS NEVER EXECUTED. The Workflow harness snapshots and runs ONE .js
// file per engine (base-template standing rule 10), so the engines must stay
// self-contained -- they cannot `import` this. Instead `scripts/build_engines.py`
// INLINES each block below into the matching `// <<shared:NAME>> ... <</shared:NAME>>`
// region of both engines, in place, and the gated `engines-inlined` check
// re-runs that build and fails if either engine differs by a single byte.
//
// SO: edit a shared block HERE, then run
//     python3 scripts/build_engines.py --write
// and commit the library and both engines together. Editing the inlined copy
// inside an engine directly is pointless -- the next build overwrites it, and
// the gate fails until it does.
//
// A block belongs here ONLY while it is byte-identical in both engines. Where
// the engines genuinely must differ (run-root variable, worklog vs no worklog,
// review vs reconcile), the block stays engine-local and is recorded as an
// INTENDED difference in docs/workflows/prompt-parity.md section 2 -- never
// forced into this file with a flag.
// ============================================================================


// <<shared:GIT>>
const GIT = 'env -u GIT_DIR -u GIT_COMMON_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES -u GIT_NAMESPACE -u GIT_PREFIX -u GIT_CEILING_DIRECTORIES git'
// <</shared:GIT>>

// <<shared:hasFlag>>
function hasFlag(name) { return tokens.includes(name) }
// <</shared:hasFlag>>

// <<shared:flagStr>>
function flagStr(name) {
  const i = tokens.indexOf(name)
  return (i === -1 || i + 1 >= tokens.length) ? null : tokens[i + 1]
}
// <</shared:flagStr>>

// <<shared:withModel>>
function withModel(base, model) {
  return model ? { ...base, model } : base
}
// <</shared:withModel>>

// <<shared:ESCALATION_MODEL>>
const ESCALATION_MODEL = 'opus'
// <</shared:ESCALATION_MODEL>>

// <<shared:tracedAgent>>
async function tracedAgent(prompt, opts = {}) {
  const before = (typeof budget !== 'undefined' && budget.spent) ? budget.spent() : 0
  const r = await agent(prompt, opts)
  const after = (typeof budget !== 'undefined' && budget.spent) ? budget.spent() : 0
  metrics.push({
    label: opts.label || 'agent',
    model: opts.model || 'session',
    promptTokEst: Math.round(prompt.length / 4),
    outTok: after - before > 0 ? after - before : null,
  })
  return r
}
// <</shared:tracedAgent>>

// <<shared:recordFilesRead>>
function recordFilesRead(result) {
  if (result && result.filesReadKb != null && metrics.length) {
    metrics[metrics.length - 1].filesReadKb = result.filesReadKb
  }
}
// <</shared:recordFilesRead>>

// <<shared:buildTokensBlock>>
function buildTokensBlock() {
  const stages = metrics.map(m => {
    const filesReadKb = m.filesReadKb != null ? m.filesReadKb : null
    const inTokEst = m.promptTokEst + (filesReadKb != null ? Math.round(filesReadKb * 256) : 0)
    return { label: m.label, model: m.model, promptTokEst: m.promptTokEst, filesReadKb, inTokEst, outTok: m.outTok }
  })
  const total = stages.reduce((acc, s) => {
    acc.promptTokEst += s.promptTokEst
    acc.filesReadKb  += s.filesReadKb || 0
    acc.inTokEst     += s.inTokEst
    acc.outTok       += s.outTok || 0
    return acc
  }, { promptTokEst: 0, filesReadKb: 0, inTokEst: 0, outTok: 0 })
  return { stages, total }
}
// <</shared:buildTokensBlock>>

// <<shared:VAULT_DETECT_SCHEMA>>
const VAULT_DETECT_SCHEMA = {
  type: 'object',
  required: ['vaulted', 'planningPath'],
  properties: {
    vaulted:      { type: 'boolean', description: 'true iff planning/ is a symlink' },
    planningPath: { type: 'string', description: 'the resolved absolute real path of planning/' }
  }
}
// <</shared:VAULT_DETECT_SCHEMA>>

// <<shared:RESOLVE_REPO_ROOT_SCHEMA>>
const RESOLVE_REPO_ROOT_SCHEMA = {
  type: 'object',
  required: ['repoRoot', 'gitCommonDir', 'tierPrefix', 'brainTomlAtRoot'],
  properties: {
    repoRoot:        { type: 'string', description: 'Absolute repo root from the REPO_ROOT: line' },
    gitCommonDir:    { type: 'string', description: 'Absolute --git-common-dir from the GIT_COMMON_DIR: line' },
    tierPrefix:      { type: 'string', description: 'The invoking directory\'s path relative to repoRoot, with a trailing slash (e.g. "business/"), or "" at the repo root, from the TIER_PREFIX: line' },
    brainTomlAtRoot: { type: 'boolean', description: 'true iff the BRAIN_TOML: line reads "yes" — a brain.toml exists at repoRoot' }
  }
}
// <</shared:RESOLVE_REPO_ROOT_SCHEMA>>

// <<shared:SETUP_GUARD_SCHEMA>>
const SETUP_GUARD_SCHEMA = {
  type: 'object',
  required: ['gitCommonDir', 'brainTomlAtRun'],
  properties: {
    gitCommonDir:   { type: 'string', description: 'Absolute --git-common-dir from the GIT_COMMON_DIR: line' },
    brainTomlAtRun: { type: 'boolean', description: 'true iff the BRAIN_TOML_AT_RUN: line reads "yes"' },
    missingCount:   { type: 'integer', description: 'Worktree mode only: the MISSING_COUNT: integer (0 when the script was not asked to check population)' },
    missingSample:  { type: 'array', items: { type: 'string' }, description: 'Worktree mode only: up to 5 example missing paths, split from the MISSING_SAMPLE: line on "|" with empty entries dropped' },
    notes:          { type: 'string' }
  }
}
// <</shared:SETUP_GUARD_SCHEMA>>

// <<shared:VAULT_VERIFY_SCHEMA>>
const VAULT_VERIFY_SCHEMA = {
  type: 'object',
  required: ['allCommitted'],
  properties: {
    allCommitted:     { type: 'boolean', description: 'true iff every given path is tracked+committed either in THIS repo\'s vault, or (BRAIN_ROOT case) in the brain root repo directly' },
    uncommittedPaths: { type: 'array', items: { type: 'string' }, description: 'the subset (vault-relative) not committed anywhere — a real failure' },
    brainRootExempt:  { type: 'array', items: { type: 'string' }, description: 'the subset that does not exist under this repo\'s own vault at all, but IS committed directly in the brain root repo — a legitimate cross-repo write (e.g. /generate-roadmap authoring at HQ), not a vault-commit failure' },
    notes:            { type: 'string' }
  }
}
// <</shared:VAULT_VERIFY_SCHEMA>>

// <<shared:DERIVE_SCHEMA>>
const DERIVE_SCHEMA = {
  type: 'object',
  required: ['derivable', 'written'],
  properties: {
    derivable:  { type: 'boolean', description: 'true iff tasks.md exists and carries a numbered step decomposition to derive from' },
    written:    { type: 'boolean', description: 'true iff a D45-shaped tasks.json (bare array, integer task_id, single-string description, no status/attempt_count) was written and committed' },
    commitHash: { type: 'string' },
    taskCount:  { type: 'integer' },
    notes:      { type: 'string' }
  }
}
// <</shared:DERIVE_SCHEMA>>

// <<shared:BAIL_REASONS>>
const BAIL_REASONS = [
  'Missing/undefined upstream dependency or symbol the spec assumes exists.',
  'Spec ambiguity/contradiction — intended behavior is genuinely undeterminable.',
  'Environment/credential/auth/network failure (not a code defect).',
  'Change would require a destructive or out-of-scope action.',
  'Same failure twice with no progress (stuck), or a structural design flaw needing a re-plan.',
  ...extraBailReasons,
].map((r, i) => `  ${i + 1}. ${r}`).join('\n')
// <</shared:BAIL_REASONS>>

// <<shared:detectPlanningVault>>
async function detectPlanningVault(repoRoot) {
  const result = await agent(`
Determine whether planning/ in this repo is a symlink (a brain-vaulted repo) or a plain directory.
Run exactly this ONE Bash call (from the repo root, ${repoRoot}):
  cd ${repoRoot} && { [ -L planning ] && echo "SYMLINK" || echo "PLAIN"; } && python3 -c "import os; print(os.path.realpath('planning'))"
The first line is SYMLINK or PLAIN. The second line is the resolved absolute real path (this works
for both cases — realpath of a plain directory is itself).
Return via StructuredOutput: vaulted (true iff the first line is SYMLINK), planningPath (the
resolved absolute path from the second line).
`, { label: 'detect-vault', schema: VAULT_DETECT_SCHEMA, model: 'haiku' })
  if (!result) return { vaulted: false, planningPath: `${repoRoot}/planning` }
  return result
}
// <</shared:detectPlanningVault>>

// <<shared:resolveRepoRoot>>
async function resolveRepoRoot() {
  const result = await agent(`
Resolve this repo's root and related mechanical facts ONCE, before anything else runs.
Run exactly this ONE Bash call, from the invoking directory — do not cd anywhere first, do not
substitute or re-derive any value, and do not run any other command:
  REPO_ROOT=$(${GIT} rev-parse --show-toplevel) && echo "REPO_ROOT:$REPO_ROOT" && echo "GIT_COMMON_DIR:$(${GIT} rev-parse --path-format=absolute --git-common-dir)" && echo "TIER_PREFIX:$(python3 -c "import os; r=os.path.relpath(os.getcwd(), '$REPO_ROOT'); print('' if r=='.' else r+'/')")" && { [ -f "$REPO_ROOT/brain.toml" ] && echo "BRAIN_TOML:yes" || echo "BRAIN_TOML:no"; }
Four labelled lines come back — REPO_ROOT:, GIT_COMMON_DIR:, TIER_PREFIX:, BRAIN_TOML: (yes/no).
Return via StructuredOutput: repoRoot (the REPO_ROOT: value), gitCommonDir (the GIT_COMMON_DIR:
value), tierPrefix (the TIER_PREFIX: value, "" when invoking at the repo root), brainTomlAtRoot
(true iff BRAIN_TOML: is yes).
`, { label: 'resolve-repo-root', schema: RESOLVE_REPO_ROOT_SCHEMA, model: 'haiku' })
  return result || null
}
// <</shared:resolveRepoRoot>>

// <<shared:verifyVaultCommit>>
async function verifyVaultCommit(runDir, vault, vaultRelPaths) {
  if (!vault.vaulted || !vaultRelPaths.length) return { allCommitted: true, uncommittedPaths: [], brainRootExempt: [] }
  // The classification logic runs entirely IN THE SCRIPT, not in the model's own reasoning — a cheap
  // model following multi-branch conditional prose reliably skips the "else" branch (observed live:
  // Haiku checked only the vault path for 4/6 paths and never attempted the brain-root fallback for
  // any of them, silently treating a path that simply doesn't exist in the vault as UNCOMMITTED
  // instead of trying the brain root). The agent's only job now is to run ONE script and transcribe
  // its already-classified output lines — no per-path decision-making left to delegate.
  const script = `set -e
BRAIN_ROOT=$(cd "${vault.planningPath}" && while [ ! -f brain.toml ] && [ "$PWD" != "/" ]; do cd ..; done; pwd)
for p in ${vaultRelPaths.map(p => JSON.stringify(p)).join(' ')}; do
  if [ -e "${vault.planningPath}/$p" ]; then
    if [ -z "$(${GIT} -C ${vault.planningPath} status --porcelain -- "$p")" ] && ${GIT} -C ${vault.planningPath} ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
      echo "VAULT_OK:$p"
    else
      echo "UNCOMMITTED:$p"
    fi
  elif [ -e "$BRAIN_ROOT/planning/$p" ]; then
    if [ -z "$(${GIT} -C "$BRAIN_ROOT/planning" status --porcelain -- "$p")" ] && ${GIT} -C "$BRAIN_ROOT/planning" ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
      echo "BRAIN_ROOT_OK:$p"
    else
      echo "UNCOMMITTED:$p"
    fi
  else
    echo "UNCOMMITTED:$p"
  fi
done`
  const result = await agent(`
Run this exact script from ${runDir} with Bash, verbatim, and transcribe its output — do not
reason about vault vs. brain-root yourself, the script already decided it:
\`\`\`
${script}
\`\`\`
Each output line is "<BUCKET>:<path>". Return via StructuredOutput: allCommitted (true only if
every line's bucket is VAULT_OK or BRAIN_ROOT_OK — false if any line is UNCOMMITTED, or if the
script produced fewer lines than paths given, or errored), uncommittedPaths (the paths from every
UNCOMMITTED line), brainRootExempt (the paths from every BRAIN_ROOT_OK line — not a failure, just a
different repo), notes (paste the raw script output).
`, { label: 'verify-vault-commit', schema: VAULT_VERIFY_SCHEMA, model: 'haiku' })
  if (!result) return { allCommitted: false, uncommittedPaths: vaultRelPaths, brainRootExempt: [], notes: 'verification agent returned null' }
  if (!Array.isArray(result.brainRootExempt)) result.brainRootExempt = []
  return result
}
// <</shared:verifyVaultCommit>>

// <<shared:renderCommitSafetyGuard>>
function renderCommitSafetyGuard(gitCmd = 'git') {
  return `if ${gitCmd} rev-parse --verify -q HEAD >/dev/null; then TRACKED=$(${gitCmd} ls-tree -r HEAD --name-only | wc -l | tr -d ' '); STAGED=$(${gitCmd} ls-files -s | wc -l | tr -d ' '); if [ "$TRACKED" -gt 0 ] && [ "$STAGED" -eq 0 ]; then echo "COMMIT_GUARD_ABORT: index holds 0 entries but HEAD tracks $TRACKED files - refusing to commit a tree that deletes everything (BT.ticket.worktree-run-can-commit-an-empty-tree)"; exit 1; fi; fi`
}
// <</shared:renderCommitSafetyGuard>>

// <<shared:renderWorkAssertion>>
function renderWorkAssertion(gitCmd = 'git', taskNum, tasksJsonPath) {
  return `NAME_STATUS=$(${gitCmd} diff --name-status HEAD~1 HEAD); if [ -z "$NAME_STATUS" ]; then echo "WORK_ASSERTION_ABORT: task ${taskNum} commit diff is EMPTY (condition 1) - no work was committed"; exit 1; fi; WA_DECLARED=$(python3 -c "
import json
d = json.load(open('${tasksJsonPath}'))
t = [x for x in d if x.get('task_id') == ${taskNum}]
print(chr(10).join(t[0].get('files', []) if t else []))
"); WA_MATCH=0; WA_BADDEL=""; while IFS=$'\t' read -r WA_ST WA_P1 WA_P2; do WA_CHK="$WA_P1"; case "$WA_ST" in R*) WA_CHK="$WA_P2" ;; esac; if printf '%s\n' "$WA_DECLARED" | grep -qFx "$WA_CHK"; then WA_MATCH=1; else case "$WA_ST" in D*) WA_BADDEL="$WA_CHK" ;; esac; fi; done <<< "$NAME_STATUS"; if [ "$WA_MATCH" -eq 0 ]; then echo "WORK_ASSERTION_ABORT: task ${taskNum} commit's changed paths do not intersect declared files[] (condition 2) - declared: [$WA_DECLARED] - changed: [$NAME_STATUS]"; exit 1; fi; if [ -n "$WA_BADDEL" ]; then echo "WORK_ASSERTION_ABORT: task ${taskNum} commit deletes undeclared file '$WA_BADDEL' not present in files[] (condition 3) - declared: [$WA_DECLARED]"; exit 1; fi`
}
// <</shared:renderWorkAssertion>>

// <<shared:renderEngineParseChecks>>
function renderEngineParseChecks(files, cd, startIndex) {
  files = (files || []).filter(f => f.endsWith('.js'))
  if (!files || !files.length) return ''
  return files.map((f, i) => {
    const n = startIndex + i
    return `CHECK ${n} — engine-parse-safety (hardcoded parse-time gate on modified SDLC engine file — mechanism, unconditional on harness.json) [GATING — a failure here blocks the verdict]:
  ${cd}if [ -f ${f} ]; then node --check ${f}; else echo "engine-parse-safety: ${f} does not exist (deleted by this task) — nothing to parse"; fi
  echo "CHECK${n}_EXIT:$?"
  Run that line EXACTLY as written and judge it ONLY by CHECK${n}_EXIT. Do NOT substitute a bare
  node --check on ${f}: this task may legitimately DELETE ${f}, and a deleted engine has no syntax
  to be wrong. The [ -f ] guard IS the check. "Cannot find module" from an unguarded node --check
  is YOUR command failing, not this gate failing, and reporting it as a gate failure bails the run
  on work that is actually correct (observed twice on 2026-08-19).`
  }).join('\n\n')
}
// <</shared:renderEngineParseChecks>>

// <<shared:skipCountRegressionResult>>
function skipCountRegressionResult(baselineCount, currentCount, dominantReason) {
  const regressed = currentCount > baselineCount
  const delta = currentCount - baselineCount
  const message = regressed
    ? `SKIP COUNT REGRESSED: baseline=${baselineCount} current=${currentCount} (rose by ${delta})${dominantReason ? ` — dominant reason: ${dominantReason}` : ''}`
    : `skip count did not rise (baseline=${baselineCount}, current=${currentCount})`
  return { regressed, message }
}
// <</shared:skipCountRegressionResult>>

// <<shared:snapshotBaselines>>
async function snapshotBaselines(cfg, cwd) {
  const checks = (cfg?.validation?.checks || [])
    .filter(c => (c.kind === 'baseline-diff' || c.kind === 'skip-count-regression') && c.baselineCommand)
  if (!checks.length) return
  const steps = checks.map(c => {
    const slug = (c.name || 'check').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    const path = c.kind === 'skip-count-regression'
      ? `${reportsDir}/${slug}-skip-baseline.txt`
      : `${reportsDir}/${slug}-baseline.json`
    return `Baseline "${c.name}" -> ${path}:
  cd ${cwd} && mkdir -p ${reportsDir}
  cd ${cwd} && { [ -f ${path} ] && echo "BASELINE EXISTS (kept): ${path}" || { ${c.baselineCommand} > ${path} 2>/dev/null; echo "BASELINE WRITTEN: ${path}"; } ; }`
  }).join('\n\n')
  await agent(`
You are the baseline-snapshot agent for the SDLC pipeline. Capture the pre-run baseline for each
baseline-diff / skip-count-regression validation check BEFORE any implementation runs. Run each block
exactly as written. Do NOT modify source. Existing baselines are kept (resume-safe).

${steps}

Return using StructuredOutput: done=true, and note which baselines were written vs already present.
`, { label: 'baseline-snapshot', schema: { type: 'object', required: ['done'], properties: { done: { type: 'boolean' }, notes: { type: 'string' } } }, model: 'haiku' })
}
// <</shared:snapshotBaselines>>

// <<shared:expectRedFor>>
function expectRedFor(taskNum) { return taskExpectRedMap.get(taskNum) || new Set() }
if (taskExpectRedMap.size) {
  log(`Per-task expect_red overrides (inverted-verdict, D68): ${[...taskExpectRedMap.keys()].sort((a, b) => a - b).join(', ')} — each named command PASSES on a NON-ZERO exit and FAILS on exit 0; every other check on that task's list is judged normally.`)
}
// <</shared:expectRedFor>>
