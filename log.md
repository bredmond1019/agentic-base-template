# log.md — base-template

*The template's own change history. One dated entry per session, newest at the top. This file
records changes to the **factory** — it is never copied into generated projects.*

---

## 2026-06-19 — Telemetry Phase-A robustness fix: deterministic metrics append (downstream-surfaced)

The first downstream `sdlc-block` run (in a test repo) produced task workflow reports **missing** the
`## Token Metrics` section. The instrumentation was fine — all stages route through `tracedAgent`, the
table was built and `log()`'d — but the Haiku finalize agent, handed the table inside its report
"Format" block, silently dropped that one section while writing every other. Lesson: never rely on a
model to re-emit a machine-generated data table.

Fix — **deterministic heredoc append** in both engines:
- `sdlc-task.js`: removed `## Token Metrics` from the finalize "Format"; added `STEP 2b` that appends
  the literal table via `cat >> ${workflowReport} <<'METRICS_EOF' … EOF`.
- `sdlc-block.js`: the orchestrator roll-up is now computed **before** the Report agent and persisted
  to the block report as a `## Token Roll-up` section via the same heredoc-append pattern (previously
  it was console-`log()` only and vanished after the run).

`node --check` clean on all three engines. Plan updated (A3-fix). Propagated to the downstream repos
running these engines.

---

## 2026-06-19 — Richer validation check kinds (D6) — foundation for the downstream telemetry pass

Extended `harness.json`'s `validation.checks[]` with an optional `kind` discriminator so a project's
suite can be richer than a flat list of exit-code commands. `kind` defaults to `"command"` (the
original shape — fully backward-compatible); four new kinds are engine-interpreted: `baseline-diff`
(fail only on net-new items vs a worktree-creation baseline), `count-delta` (fail on a count
regression vs the previous task), `warning-scan` (exit code gates; pattern matches recorded with
severity per `gates`), and `forbidden-pattern-scan` (source greps that must find nothing).

Motivation: the in-flight `python-orchestration-system` runs an 8-check suite (net-new ruff diff,
pytest count-delta, Pydantic warning capture, CLAUDE.md standing-rule scan) whose mechanics a flat
command list cannot express. Migrating that project onto the agnostic engines to import the
token-telemetry work would have silently dropped them. These four patterns are generic enough to be
*mechanism* — carried in the engine, with all stack-specific commands/patterns kept in `harness.json`
(the D5 split holds; engines still ship zero stack defaults). See
[D6](planning/decisions/D6-harness-richer-checks.md).

```diff
M .claude/workflows/harness.schema.json   (check.kind enum + per-kind if/then required fields + rule $def)
M .claude/workflows/sdlc-task.js           (renderCheckList kind dispatch; snapshotBaselines worktree hook; loader schema/prompt; Test-stage gating prose)
M .claude/workflows/sdlc-block.js          (loader schema + prompt: preserve kind-specific fields)
M scaffold/planning/harness.examples.md    (new Python "rich checks" profile + per-kind run notes)
A planning/decisions/D6-harness-richer-checks.md
M planning/decisions/index.md              (D6 entry)
M planning/plans/sdlc-telemetry-updates.md (reserved telemetry ADR renumbered D6 -> D7)
```

Verification: `node --check` passes on all three engines; all four `harness.examples.md` JSON
profiles parse. No behavior change for existing flat configs. Next: Phase 2 — adopt these engines in
`python-orchestration-system` and author its `harness.json` from the new Python profile, then capture
the Phase-A telemetry baseline.

---

## 2026-06-18 — planning/ cleanup: okf-phase-2/ removed; status.md and index.md rewritten

With `docs/` created and D5 capturing all the key decisions, `planning/okf-phase-2/` (15 files:
plan, context, per-phase implement/report pairs) was deleted — it is now fully historical and
redundant. `planning/status.md` was rewritten from the OKF Phase 2 tracking table to a stable
"completed efforts / upcoming work" format. `planning/index.md` was trimmed to remove the
active-work pointer and now leads directly to the decisions index and D5.

```diff
- planning/okf-phase-2/   (15 files removed)
M planning/status.md      (rewritten: stable format, completed efforts, upcoming work)
M planning/index.md       (trimmed: removed active-work block; points to D5)
```

---

## 2026-06-18 — docs/ created; DEVLOG renamed to log.md; README/CLAUDE/context/status updated

OKF Phase 2 is committed and complete. This session cleaned up the post-Phase-2 state:
renamed `DEVLOG.md` → `log.md` (consistent with the scaffold convention and D15); updated all
references in `CLAUDE.md`, `README.md`, `planning/context.md`, and `planning/status.md`;
removed the "Active work: OKF Phase 2" pointer from `CLAUDE.md` and updated `context.md` to
mark the effort historical. Created `docs/` with four files: `index.md` (navigation),
`architecture.md` (two-halves model, OKF conventions, mechanism/policy split),
`using-the-template.md` (generate → configure → run pipeline), and `harness-json.md` (full
schema reference + all three stack profiles). Also fixed an outdated "deferred to OKF Phase 2"
note in `.claude/commands/README.md` and corrected a `reports/` → `sdlc/reports/` path bug
in the Directory Layout section of that same file.

```diff
+ docs/index.md
+ docs/architecture.md
+ docs/using-the-template.md
+ docs/harness-json.md
R DEVLOG.md → log.md
M CLAUDE.md                          (remove OKF Phase 2 active-work section; log.md refs)
M README.md                          (layout tree; log.md refs; docs/ entry)
M planning/context.md                (log.md refs; current-effort → stable; okf-phase-2 → historical)
M planning/status.md                 (current focus → stable; P6 commit confirmed; log.md ref)
M .claude/commands/README.md         (remove outdated deferred note; fix sdlc/reports/ path)
```

---

## 2026-06-18 — OKF Phase 2 P6: regression dry-run — all scenarios PASS; OKF Phase 2 complete

**Verification:** P6 exercised the committed engine helpers (`renderCheckList`,
`renderUiTestPrompt`, `loadHarnessConfig`) against three `harness.json` states — config present
(Rust profile), config absent, and uiTest enabled (Next.js profile) — plus path resolution and
the example-spec fallback. All five scenarios verified PASS. The inline fix
(`sdlc-task.js:503`: `~/agentic-portfolio` example path → `<repoRoot>/trees/${baseBranchName}`)
closed the last identity leak; the narrative grep is now fully clean in `.claude/workflows/`.

**Provenance stamp:** this commit is the reference point for the next generated project using the
fully agnostic harness. Downstream projects (`learn-ai`, `python-orchestration-system`) pull the
rewritten engines manually and author their own `planning/harness.json` per D18.

```diff
+ planning/okf-phase-2/phase6/report.md   (P6 review — PASS)
M .claude/workflows/sdlc-task.js          (line 503: generalize example worktree path)
M planning/okf-phase-2/index.md           (P6 status — complete)
M planning/status.md                      (P6 Done / Reviewed PASS; OKF Phase 2 complete)
M DEVLOG.md                               (this entry)
```

---

## 2026-06-18 — OKF Phase 2 P5: self-applied the agnostic decouple to the template's own meta

With the engines generalized (P1–P4), this pass made `base-template` **dogfood its own conventions**
and recorded the adoption. The factory now eats what it ships: its docs use the lowercase OKF names,
`okf-phase-2/` is a proper concept folder, and it carries its own `planning/harness.json`.

Changes:
- **Adoption ADR** `planning/decisions/D5-okf-phase-2-adopted.md` — records (a) engines generalized
  to zero stack defaults, (b) the `planning/harness.json` mechanism/policy split (MVP schema:
  `validation.checks[]` + `uiTest.enabled` and enabled-only fields; deferred fields listed),
  (c) adoption of D15–D18 (lowercase docs / concept folders / reserved `sdlc/` / `index.md`), and
  (d) the MVP scope calls (emoji + `port + taskNumber` hardcoded as mechanism; narrative
  externalization opportunistic). **Supersedes D3.** Registered in `planning/decisions/index.md`.
- **base-template's own `planning/harness.json`** — non-web profile dogfooding the loader: a single
  gating `engines-parse` check (`node --check` over the three SDLC engines), `uiTest.enabled:false`.
  Proves the agnostic / non-web path on the factory itself. (Template meta — never copied downstream;
  generated projects get the neutral `scaffold/planning/harness.json` stub.)
- **`planning/okf-phase-2/index.md`** (D17) — directory listing for the concept folder (plan,
  context, per-phase reports). Concept folder registered in `planning/index.md` (P-status refreshed
  to P1–P4 done / P5 now).
- **Root `CLAUDE.md`** — rule #1 now cites `planning/harness.json` as the agnostic seam (mechanism
  vs. policy, no stack defaults, universal rules stay hardcoded); rule #3 states the settled OKF
  names + concept-folder + `sdlc/` convention (was the pre-Phase-2 UPPERCASE/`tasks/` names);
  "Before you change anything" repointed at `planning/` + `okf-phase-2/index.md`; the two-halves
  table updated (scaffold `log.md`, harness ships mechanism only).
- **Root `README.md`** — layout block + canonical-names section rewritten to the settled lowercase /
  concept-folder conventions and the `harness.json` config; documents the template's own
  `planning/harness.json` and the scaffold stub + examples.
- **`init-worktree.md` sparse-checkout residual — RESOLVED** (the P4-deferred follow-up). The
  hardcoded learn-ai cone dir list (`app components hooks lib content scripts docs planning .claude
  __tests__ __mocks__ types`) → `git ls-tree HEAD --name-only -d` (cone all tracked top-level dirs).
  Stack-agnostic, no config field needed (chose option (b) over a `harness.json worktree.*` field).

P6 (regression dry-run) is the only open phase.

```diff
+ planning/harness.json                                  (template's own pipeline config)
+ planning/okf-phase-2/index.md                          (D17 concept-folder index)
+ planning/decisions/D5-okf-phase-2-adopted.md           (supersedes D3)
~ CLAUDE.md, README.md, planning/index.md, planning/decisions/index.md
~ .claude/commands/init-worktree.md                      (sparse-checkout → ls-tree, residual resolved)
```

---

## 2026-06-18 — Dropped the `.agents/` twin (single-harness)

Removed the `.agents/` tree (Gemini/Antigravity skill twins + `compute-waves.ts`) from the
template. It was generated from `.claude/commands/`, not authored independently, and existed only
for occasional non-Claude sessions — so maintaining it meant a double-write on every harness edit
plus OKF Phase 2's dedicated P4b "twin mirror pass" to fight drift. For a solo factory that
permanent cost outweighed the occasional benefit; if a skill-form runtime is needed again,
regenerate `.agents/` from `.claude/` rather than hand-maintaining a twin.

Changes: deleted `.agents/`; `/new-project` and both root/scaffold docs no longer reference it;
OKF Phase 2 **P4b is removed** and all twin-alignment gates voided (`.claude/` is the only harness
tree); added `planning/decisions/D4-drop-agents-twin.md` (supersedes the `.agents/`-twin
assumptions in D1/D2; the deferred `.agents` engine-variant note in D3 is moot). The planned
Phase-2 adoption ADR was renumbered `D4-okf-phase-2-adopted` → `D5` to free D4 for this decision.

```diff
- .agents/   (skill twins + scripts/compute-waves.ts)
```

---

## 2026-06-17 — OKF Phase 2 plan seeded (planning, not yet executed)

Wrote a self-contained Phase 2 execution plan into `planning/okf-phase-2/plan.md` so a session
opened in this repo is fully primed without needing the brain. It restates the settled decisions
(brain D15–D18 + the `sdlc/` path resolution) and gives the ordered task list: rewrite the three
SDLC engines to `planning/<concept>/` + `planning/<concept>/sdlc/`, restructure the scaffold to
lowercase names + concept-folders + `index.md`, update the harness skills, generalize the
stack-coupling (closing D3), self-apply to this repo's meta, and regression-check. Added
`planning/index.md` (active-work pointer + D17 self-application) and a "Before you change anything"
pointer in `CLAUDE.md`. **No harness/scaffold files changed yet** — the rewrite (and its provenance
commit + the D4 ADR that supersedes D3) happens when the plan is executed.

---

## 2026-06-17 — Template established (WS3)

Stood up `base-template/` as its own git repo, gitignored from the brain. Seeded the harness
from learn-ai's corrected (post-WS1) `.claude/` + `.agents/` twins and curated it down to the
project-agnostic SDLC core.

**Kept (project-agnostic core):**
- SDLC pipeline: `sdlc-run` / `sdlc-task` / `sdlc-block` (engines), `init-worktree`,
  `clean-worktree`, `start-block`, `generate-tasks`, `process-tasks`, `update-task`,
  `review-task`, `breakdown`, `implement`, `test`, `fix`, `review-workflow`, `document`.
- General: `prime`, `status`, `plan`, `commit`, `log-work`, `update-docs`, `session-recap`,
  `chore`, `feature`.
- `.agents/scripts/compute-waves.ts` (backs `sdlc-block`).

**Dropped (project-specific):**
- `write-learn-module`, `write-blog-post`, `blog-idea` — learn-ai content authoring.
- `playwright` + `.claude/skills/playwright-cli/` — browser-test tooling, learn-ai-specific.
- `dev`, `stop-dev`, `build` — Next.js/npm-specific (port 3003, `npm run dev/build`). A new
  project defines its own run/build commands; a stack-agnostic stub would carry no real value.

**Generalized in place:**
- `update-docs` (both twins): removed hardcoded learn-ai doc names (`DEPLOYMENT.md`,
  `OPERATIONS.md`, `docs/agentic-workflows/`) and Next paths; now recurses `docs/` generically.
- `log-work` (both twins): brain-sync target `../docs/projects/learn-ai.md` → `{{SLUG}}` token.
- All skill/command `description` identity labels: "learn-ai" qualifier generalized.
- SDLC engine header/`description` labels: dropped the `(learn-ai)` identity tags.
- Both `README.md` indexes rewritten to project-agnostic, tokenized form (dropped commands
  removed, npm/bilingual gates described as adapt-to-your-stack).

**Built:** the tokenized `scaffold/` (complete-OKF docs with `{{TOKENS}}`), folding in the
section depth from the deprecated pos `scaffold-project.md` (CONTEXT Governing Principles +
Fast Facts; MASTER_PLAN phase structure). Decisions use the atomic `planning/decisions/`
form, not a single `DECISIONS.md`.

**Notes / retired:** `generate-new-docs.js` was already absent from learn-ai — nothing to
retire. The pos `scaffold-project` command is to be marked superseded by `/new-project` +
`base-template` (deletion deferred to OKF Phase 2).

**Known deferred (OKF Phase 2):** the SDLC engines (`sdlc-run/block/task.js`) and several skill
bodies (`test`, `generate-tasks`, `review-task`) still carry npm/Next/content-validation and
bilingual/public-narrative assumptions. Generalizing them to be fully stack-agnostic is Phase-2
work — see `planning/decisions/D3-engine-stack-deferred.md`. The user also flagged that the
`.agents` `sdlc-block`/`sdlc-task` may want an improved variant; tracked there too.

```diff
(initial harness + scaffold + template meta — no application code)
```
