# log.md — base-template

*The template's own change history. One dated entry per session, newest at the top. This file
records changes to the **factory** — it is never copied into generated projects.*

---

## 2026-06-23

Reviewed the "Plan F3" planning meta-skill article against our SDLC harness and, combined with user-supplied sdlc-block token telemetry, produced an eight-ADR improvement plan (D18–D25) targeting planning quality and a lean sdlc-block redesign. The eight ADRs span planning-quality changes (D18 living-artifact specs, D19 property guard, D20 clarify gate) and telemetry-driven lean sdlc-block work (D21 honest recommendation, D22 relocate execution-plan.json to /generate-tasks, D23 shared setup + isolation only for true parallelism, D24 consolidated verify depth knob, D25 considered-and-rejected); the lean-block redesign is the centerpiece, driven by measured telemetry showing approximately 200k redundant tokens per task on sequential blocks. Formalized the work in a self-contained plan at planning/plans/planf3-harness-improvements.md, indexed it in planning/index.md, pointed status.md Current focus at the plan, and wrote planning/handoff.md carrying the decision rationale and measured telemetry table. No engine or command code has changed; work lives on branch planf3-harness-improvements, ready for a fresh agent to implement starting at sequencing step 1 (D20).

```diff
 planning/index.md  | 4 ++++
 planning/status.md | 6 ++++--
 2 files changed, 8 insertions(+), 2 deletions(-)
```

## 2026-06-21 — Rewrite /update-docs as documentation health sweep; propagate to all four downstream repos

Transformed `/update-docs` from a narrow surgical git-diff patcher into a comprehensive **5-phase documentation audit** that detects stale sections, missing coverage, and confirmed-current docs. The command is read-only by default; `--patch` applies surgical fixes for clear-cut issues. New `--since <ref>` flag scopes the git history window.

**Five-phase audit model:**
1. **Git history snapshot** — `git log --oneline` and `git diff --stat` to spot recent changes
2. **Codebase inventory** — sweep `.claude/commands/`, `.claude/workflows/`, `harness.schema.json`, scaffold profiles, and `planning/decisions/` to establish source of truth
3. **Documentation inventory** — read every `docs/*.md` and `.claude/commands/README.md`; build a coverage matrix (what each doc covers, what each capability is documented in)
4. **Gap analysis** — classify discrepancies into four buckets: **STALE** (doc ≠ source), **MISSING** (capability has no doc), **NO-DOC** (intentionally undocumented), **CURRENT** (verified in sync)
5. **Structured report** — output categorized findings with fix suggestions
6. **Optional patching** — `--patch` applies surgical edits for clear-cut STALE items; skips architecture-level changes and planning-file modifications

Conservative thresholds: MISSING only flags user-facing capabilities (commands, flags, config fields, behaviors) where the confusion is real and not already addressed in existing docs/comments.

Updated `.claude/commands/README.md` to describe the new command as the **ad-hoc maintenance** counterpart to `/document` — use for periodic doc health checks outside the pipeline; use `/document` inside it.

Propagated both changed files (update-docs.md + README.md) to all four downstream repos (`bastion`, `learn-ai`, `python-orchestration-system`, `markdown-engine-validator`) — byte-identical to base HEAD, left **uncommitted per-repo for review**.

All engines `node --check` clean.

```diff
 .claude/commands/README.md      |  11 ++-
 .claude/commands/update-docs.md | 164 +++++++++++++++++++++++++++++-----------
 2 files changed, 125 insertions(+), 50 deletions(-)
```

---

## 2026-06-21 — D17 `--from <stage>` flag + pipeline recommendation to sdlc-run / generate-tasks; propagate to all four downstream repos

Shipped two user-experience improvements reducing friction when restarting mid-spec or choosing which pipeline to use. Both propagated to downstream projects (uncommitted per-repo for review).

1. **D17 — `--from <stage>` flag to `sdlc-run`** ([D17](planning/decisions/D17-sdlc-run-stage-flag.md)). Added optional `--from stage` parameter that skips the `scout` discovery phase and starts directly at a user-specified stage (implement, fix, test, review, document, wrap-up). Reduces round-trips when resuming after an interruption and the developer knows exactly where to restart. On mismatch (flag says test but no test report exists) the run fails cleanly with a diagnostic. Preserves the `--resume` path's discovery behavior for its use cases. `node --check` clean; standalone runs and under-block runs both tested.

2. **Pipeline recommendation guidance in `generate-tasks`** (step 1 of the command). Added a prose note explaining the choice between `/sdlc-run` (single integrated spec), `/sdlc-block` (numbered tasks with waves), and `/sdlc-task` (parallel worktree runner). Targets the common first-time question "which command do I use?" and clarifies task numbering vs. spec granularity.

3. **Propagated** both changes to all four downstream projects (`bastion`, `learn-ai`, `python-orchestration-system`, `markdown-engine-validator`) — byte-identical to base HEAD, left **uncommitted per-repo for review**.

All engines `node --check` clean. D16 (preflight task-structure lint) is complete and sitting in base-template; D17 propagation (plus D16 spec validation across all four projects) is next work.

```diff
 .claude/commands/generate-tasks.md | 35 +++++++++++++++++++++++++++++------
 .claude/workflows/sdlc-run.js      | 37 +++++++++++++++++++++++++++++++------
 2 files changed, 60 insertions(+), 12 deletions(-)
```

---

## 2026-06-21 — D16 preflight task-structure lint + spec-template/generate-tasks contract; learn-ai orphan worktree cleanup

Shipped the determinism-first unit motivated by the learn-ai `learn-paths-enliven` tokenomics incident
(ambiguous spec → Analyze inferred 21 vs. 3 tasks across runs → duplicate work + orphan worktrees):

1. **D16 — Preflight task-structure lint** ([D16](planning/decisions/D16-preflight-task-structure-lint.md)).
   Added STEP 4 to `sdlc-block.js` pre-flight: `grep -c '^### [0-9]' tasks.md` — if the count is 0
   the pre-flight returns `ready=false, action="aborted"` with a fix message before Analyze runs.
   Applies to CASE B (pre-existing uncommitted spec) and CASE C (already clean); CASE A (pre-flight
   generated the spec itself) is exempt. `PREFLIGHT_SCHEMA` unchanged (`action: "aborted"` already
   covers it). `node --check` clean; not yet propagated downstream.

2. **`spec-template.md` format fix.** Corrected the `## Tasks` section from flat `1. **Title**` format
   to `## Step-by-Step Tasks` with `### N. Title` headings + explicit note that sdlc-block requires
   this format. Template was inconsistent with what `/generate-tasks` produces and what Analyze parses.

3. **`generate-tasks.md` contract callout.** Added an explicit note in step 5 that `### N. Title` is
   the required heading format and explains why (sdlc-block enumerate tasks by this pattern, aborts on
   none). The output format was already correct; the instructions now name the requirement.

4. **learn-ai orphan worktree cleanup.** Removed `trees/learn-paths-enliven-task7` and
   `trees/learn-paths-enliven-task8` (scaffold-only, one init commit each, zero implementation).
   Force-deleted both branches (`-D`; branches had never been merged into main, but contained only
   the `chore: init worktree` scaffold commit). `git worktree list` clean.

Not yet propagated to downstream projects (standing convention — leave uncommitted per-repo for review).

---

## 2026-06-21 — Tokenomics round: commit + propagate D14, port to sdlc-run, relabel parallel telemetry (D15)

Reviewed two heavy live `sdlc-block` runs (`bastion/phase1-blockA`, `learn-ai/learn-paths-enliven`)
that read as token-hungry. **Diagnosis: no leak.** The visible symptoms — `scout` on every fresh task,
a separate `task-log` *and* `finalize` per task — were exactly what D14 fixed, but D14 was uncommitted,
`sdlc-task.js`-only, and never propagated, so both projects ran the pre-D14 engine. The `— (parallel)`
telemetry was D12 working as designed. The learn-ai 163.8k implement was genuine content work (7 modules,
~2,200 MDX lines, `filesReadKb: 240 KB`) — the lever there is repeated context reads, not agent count.

Shipped this session:

1. **Committed D14** (`343cc0e`) — the consolidated `wrap-up` + `--resume`-gated `scout` in `sdlc-task.js`.
2. **Ported the D14 wrap-up merge to `sdlc-run.js`.** Merged `logWork` (sonnet) + `finalize` (haiku) into
   one `wrap-up` agent doing status update + log append + workflow report + chore commit. Kept on
   **Sonnet** (not Haiku): unlike `sdlc-task`'s wrap-up — which only *records* deferred status/log for
   `/clean-worktree` to apply at merge — this runs on main with no worktree and edits status.md/log.md
   directly, so the human-facing prose is the judgment-heavy half. Removed `FINALIZE_SCHEMA` +
   `MODEL.logWork`/`MODEL.finalize`. `sdlc-run.js` carries no telemetry table and never runs under
   `--parallel-wave`, so D15 does not touch it.
3. **D15 — parallel telemetry relabel** ([D15](planning/decisions/D15-parallel-telemetry-relabel.md),
   refines D12's presentation). Under a parallel wave the per-stage cell now shows `~N in`
   (= promptTok + filesRead at ~256 tok/KB), an accurate per-agent **input** estimate, instead of a blank
   `— (parallel)`. Column renamed `outTok` → `tok`; solo runs still show the real output delta. The one
   accurate per-agent number replaces a column of dead markers; `filesReadKb` is also the actionable lever.
4. **Propagated** both engines to all four downstream projects (`bastion`, `learn-ai`,
   `python-orchestration-system`, `markdown-engine-validator`) — byte-identical to base HEAD, left
   **uncommitted per-repo for review** per the standing propagation pattern.

All nine engines (`base` + 4×2 downstream) `node --check` clean.

**Deep-dived the learn-ai run (correcting an earlier mis-read).** The "21 vs 3" was NOT runtime
consolidation — `sdlc-block` never regroups tasks. The spec (`learn-paths-enliven/tasks.md`) is
**granularity-ambiguous**: written as 3 Phases + module bullets with NO numbered `### N.` tasks, so the
Analyze agent had to *guess* the grain (`sdlc-block.js:40-41` — agent proposes the task graph, JS computes
waves) and guessed differently across runs: one-task-per-module (21) once, phase-level mega-tasks (3)
another. Both report sets sit in the same folder; merge commits literally say "take task4 over task1
**stub**" (task1's mega-implement stubbed dsa-foundations 04/05/06, redone per-module). Verified current
state: all 21 EN modules are full on main (174–487 lines); dsa-advanced + system-design + dsa-foundations
01/02/04/05/06 are done-and-verified, **03/07/08 are done-but-unverified** (task1 mega-run only; 07/08 were
the queued redos Brandon paused — 2 orphan worktrees `task7`/`task8`, scaffold-only). Key caveat carried
forward: **`breakdown.mode` is orthogonal to task COUNT** — it refines a task's internal sub-steps, never
the number of tasks; turning it on only adds agents.

**Next direction (proposed, not started):** push determinism into the harness via authoring skills — a
numbered-task **authoring contract** (harden `/generate-tasks`) + a **preflight lint in `sdlc-block`'s
Analyze** that stops when a spec has no numbered tasks instead of silently inferring N pipelines. Both
mechanism-only. Recorded to project memory (`sdlc-determinism-skills-direction`). Session handed off via
`planning/handoff.md`; awaiting Brandon's pick between the skills plan and learn-ai cleanup.

## 2026-06-20 — sdlc-task agent consolidation: merge wrap-up, gate scout on resume (D14)

Structural review of `sdlc-task.js` asked whether all its agents earn their keep. The judgment stages
(implement/fix/test/review/document) are each a real SDLC boundary and stay separate; the overkill was
in the mechanical micro-agents around them. Two cuts ([D14](planning/decisions/D14-sdlc-task-agent-consolidation.md)):

1. **Merged `task-log` + `finalize` into one `wrap-up` agent.** Both were cheap, sequential, Haiku, and
   ran back-to-back with no fresh-context boundary. One agent now writes the task log + the workflow
   report and does the single chore commit. `LOG_SCHEMA` + `FINALIZE_SCHEMA` → one `WRAPUP_SCHEMA`;
   `MODEL.taskLog`/`MODEL.finalize` → `MODEL.wrapup`.
2. **Gated `scout` on `--resume`.** A fresh run gets a clean, suffix-incremented worktree where this
   task's reports can't exist yet, so the start stage is deterministic (`generate-tasks` if the spec is
   missing, else `implement`). `worktree-setup` (Haiku, already running bash there) now also reports
   `specFileExists` + `blockStatus` — the two facts the non-resume path needed — so no scout round-trip.
   On `--resume` the scout still runs its full report-file decision tree.

Net: a standalone happy-path run drops from ~10 agent invocations to ~8, with no judgment stage or
correctness boundary touched (review still re-runs gating checks fresh; B1 hand-off + D12 outTok
suppression preserved).

**Deliberately NOT done:** re-tiering the `harness-config` loader. It is on Sonnet because Haiku fails
StructuredOutput on the nested schema (the 2026-06-20 fix below); `baseline-snapshot` already spawns no
agent on the common path. No defensible win, so it was left alone.

`node --check` clean. **Scope:** `sdlc-task.js` only. Not yet propagated to `sdlc-run.js` (same
task-log/finalize pair; no worktree/scout split) or to downstream projects — both tracked in
`planning/status.md`.

---

## 2026-06-20 — Add `/prepare-next-agent` command + `/prime` handoff detection

New command `prepare-next-agent.md`: writes `planning/handoff.md` (in-flight context, completed
work, remaining tasks, open questions, first command for next session), then invokes `/log-work`
and `/commit`. Designed for sessions that grow larger than expected and need a clean hand-off to
a fresh context. Runs inline (no subagent) so the confirmation gates in `/log-work` and `/commit`
work normally.

Updated `prime.md` to check for `planning/handoff.md` on startup; if found, surfaces an
**Active Handoff** section first — title, remaining work, first command — before the standard
orientation. The handoff file is transient and should be deleted after the new session consumes it.

Also updated `scaffold/planning/index.md` (handoff.md row) and `commands/README.md` (phase table +
description). No behavior change to any other command or engine.

---

## 2026-06-20 — Fix: bump harness-config loader from haiku to sonnet (all three engines)

`loadHarnessConfig` in all three engines (`sdlc-block.js`, `sdlc-task.js`, `sdlc-run.js`) was set to
`model: 'haiku'`. Haiku fails to call StructuredOutput after 2 nudges when given the nested
`HARNESS_CONFIG_SCHEMA` (discriminated `checks[].kind` variants). Bumped to `model: 'sonnet'` in all
three. Propagated to `python-orchestration-system` (committed `dba9248`) and `learn-ai` + `bastion`
(left uncommitted for review). `markdown-engine-validator` already fixed directly.

---

## 2026-06-20 — Downstream propagation: D10–D13 + #1 to all four projects (run-review task D)

Run-review task **D** (`planning/plans/sdlc-block-run-review.md`): pulled the rewritten engines into all
four downstream projects. Recon recipe (diff each project's engines against `base-template` HEAD)
confirmed the three current projects (`learn-ai`, `bastion`, `markdown-engine-validator`) shared an
identical engine lag of `sdlc-task.js` 33 / `sdlc-block.js` 76 lines = exactly fdb6be0 (#1 D10
persistence) + def02fe (D12+D13) = pure lag, safe to overwrite. `python-orchestration-system` lagged
much further (task 165 / block 167 / schema 18) — it was the **overdue** project that never received
D10+D11 (skipped mid-`sdlc-block` last session) and now also needed D12/D13/#1.

What was propagated (all target working trees verified clean first):
- **python-orchestration-system** (caught up two batches): `sdlc-task.js` + `sdlc-block.js` +
  `harness.schema.json` + `generate-tasks.md` overwritten (all agnostic). `harness.json` left untouched
  (`breakdown` defaults to `recommend`).
- **bastion** + **markdown-engine-validator**: `sdlc-task.js` + `sdlc-block.js` + agnostic
  `generate-tasks.md` overwritten.
- **learn-ai**: engines overwritten; the D13 heuristic paragraph **surgically inserted** into its still
  pre-agnostic `generate-tasks.md` (command migration remains a separate effort). Residual 27-line diff
  is purely learn-ai's stack/policy customization — no heuristic-wording divergence remains.

Verification: all eight propagated engines `node --check` clean; every overwritten file now byte-identical
to base HEAD (0 diff); learn-ai's command confirmed free of heuristic-wording drift. Changes left
**uncommitted per-repo for review** (prior-session convention). This resolves the overdue D10+D11 pull and
brings the whole fleet current through D13.

Also closed run-review task **C** (a learn-ai config change, not base-template): set learn-ai's
`breakdown.mode` to `"off"` (was defaulting to `recommend` on an empty `{}` harness.json, paying for a
Sonnet assessment it discarded). learn-ai's content tasks are mostly homogeneous, which D13 now correctly
declines to flag, so the pass rarely fires usefully — skipping beats a discarded assessment. Rationale
folded into the file's top-level `_comment` (the `breakdown` object is `additionalProperties:false`, so no
inline comment there); schema-validated. Left uncommitted in the learn-ai repo for review. Run-review
tasks A/B/C/D + #1 are now all done; only the LOW opportunistic backlog (E: B3/B5/B7 + learn-ai command
migration) remains.

## 2026-06-20 — Breakdown heuristic: file count gated on heterogeneity ([D13](planning/decisions/D13-breakdown-heuristic-homogeneity.md))

Run-review finding #3 (`planning/plans/sdlc-block-run-review.md`): D10's file-count signal over-fires on
homogeneous many-file tasks. In the learn-ai content run, a learning path (one metadata file + N
near-identical lesson/module pairs) tripped "> 3 files" by ~5× as a single cohesive task — but
decomposition there yields little. Raw count is a weak proxy for decomposition *value*; the real
predictors are separable concerns / layers / independently-testable units (heterogeneity).

Fix (prompt-only, mechanism): in both engines (`sdlc-block` Analyze STEP 3b, `sdlc-task` Plan STEP 3),
the `generate-tasks` preview, and `docs/harness-json.md`, file count is demoted from a standalone OR
trigger to a signal that fires **only when the > threshold files are heterogeneous**, plus an explicit
**homogeneity discount** (same-shape files serving one concern are not a candidate on count alone). The
three structural signals stay hard ORs; `complexityThreshold` is unchanged and remains the per-project
knob. No schema/scaffold change (no new field). Both engines `node --check` clean. ADR
[D13](planning/decisions/D13-breakdown-heuristic-homogeneity.md) (refines D10). Not yet propagated.

## 2026-06-20 — Mark per-task outTok as non-isolated under parallel waves ([D12](planning/decisions/D12-parallel-outtok-contamination.md))

Run-review finding A (`planning/plans/sdlc-block-run-review.md`): per-stage `outTok` is a
`budget.spent()` delta over a pool **shared across all concurrent agents**, so under `sdlc-block`'s
parallel waves every per-task `outTok` measures the whole batch's concurrent burn, not the stage's own
output. Proof: a trivial `worktree-setup` (`git worktree add`, no model output) reported 15–21k outTok
in parallel waves vs **2,709** solo. The headline metric on the most-used path actively misled — it had
nearly led to mis-evaluating the D11 re-tier. The runtime exposes no per-agent output count (only the
shared pool), so a correct per-agent number isn't available; an honest gap beats a wrong number.

Fix (mechanism-only, both engines):
- `sdlc-block.js` — `runTask` gains a `parallelWave` param and passes `--parallel-wave` to `/sdlc-task`
  **only** when the parallel batch width is `> 1` (size-1 batches and all sequential waves run solo →
  clean delta → reported as a number). Orchestrator roll-up legend now points readers at the per-task
  `— (parallel)` convention (its own sequential stages stay clean).
- `sdlc-task.js` — parses `--parallel-wave`; renders every stage's `outTok` as `— (parallel)` and
  appends a one-line caveat to `## Token Metrics` when set. `promptTok`/`filesReadKb` (per-agent) are
  untouched and remain the trustworthy signals. Solo/standalone runs are unchanged.

New inter-engine arg `--parallel-wave` (parallel to `--under-block`/`--resume`). `node --check` clean
both engines. ADR [D12](planning/decisions/D12-parallel-outtok-contamination.md). Not yet propagated.

## 2026-06-20 — Persist the D10 breakdown assessment to the block report

Found while reviewing the `learn-ai` `interview-prep-learning-paths` block run: D10 ran (engine
byte-identical to HEAD; the run postdated the D10 commit) and the tasks were unambiguously coarse
(task 1 owns 17 files vs a threshold of 3), but in the default `recommend` mode the recommendation was
emitted via `log()` only — it streamed to the live `/workflows` narrator and left **no durable trace**
in `block-workflow.md`. The recommendation was both invisible after the run and inert.

Fix (`sdlc-block.js`, mechanism-only): capture the assessment outcome at the breakdown gate into a
`breakdownAssessment` record (`mode`, `threshold`, `flagged[]`, `action`, `committed`), build a
deterministic `breakdownSection` next to the token-roll-up builder, and have the Report agent append a
`## Breakdown Assessment (D10)` section to `block-workflow.md` via a literal heredoc (same verbatim
idiom as the roll-up). Also surfaced on the workflow's return object (`breakdown`). Now every mode is
observable post-run: `off`/no-flags say so; `recommend` lists the flagged tasks + their coarseness
signal and the suggested action; `auto` records the committed `breakdown.md`. `node --check` clean.
Not yet propagated downstream. Within D10's intent — no ADR (the gap was persistence, not policy).

## 2026-06-20 — Breakdown assessment (D10) + targeted model re-tiering (D11)

Two harness changes at the maintainer's request.

**Breakdown assessment ([D10](planning/decisions/D10-breakdown-assessment.md)).** Both engines now
assess each task against a universal coarseness heuristic (touches > `complexityThreshold` files, or
bundles separable concerns, or spans layers, or has a large criteria set) and act per a new
`planning/harness.json` → `breakdown` policy (`mode`: recommend (default) · auto · off;
`complexityThreshold`: 3).
- **`sdlc-block`** folds the assessment into the existing Analyze agent (new per-task
  `recommendBreakdown`/`breakdownReason` fields — file counts were already computed there, so it is
  near-free), then a breakdown gate before the waves: `recommend` logs the coarse tasks; `auto`
  generates + commits `breakdown.md` **on main before the waves** so every parallel worktree inherits
  the same file (no shared-file merge conflict — the D9 class of bug). Passes `--under-block` to each
  `/sdlc-task` to suppress duplicate assessment.
- **`sdlc-task`** (standalone) gains a Plan-phase assessment before the implement loop: no-ops if a
  `### Step N:` section already exists, `recommend` logs, `auto` writes sub-steps into its single
  worktree (conflict-free). Skipped under `--under-block`. New `breakdownAssess` (sonnet) /
  `breakdownGen` (opus) model entries.
- **`/generate-tasks`** previews the same recommendation at authoring time (the recurring "should I
  break these down?" question after generation).
- Schema + scaffold stub + `docs/harness-json.md` document the `breakdown` object.

**Model re-tiering ([D11](planning/decisions/D11-model-retier.md)).** Three stages moved down a tier
where the assignment exceeded the work: pre-flight (`sdlc-block`) opus→sonnet (dominant path is trivial
scripted git; the rare generate path is a fallback-of-a-fallback), worktree-setup (`sdlc-task`)
sonnet→haiku (exact git recipe, no judgment), task-log (`sdlc-task`) sonnet→haiku (rigid template +
one-paragraph summary). Kept: implement/fix/review/document/triage/merge on sonnet, analyze on opus,
the opus escalation on the final fix/review. Comment blocks updated to match.

Mechanism only — both engines stay project-agnostic; propagates downstream via the manual update loop.
Both engines `node --check` clean; schema + scaffold `harness.json` valid JSON. Not yet propagated to
the four downstream projects.

## 2026-06-20 — Downstream propagation of the telemetry pass + fix stale `DECISIONS.md` engine refs

Pulled the telemetry-pass harness updates (B4 + B1 + WS2-a + B2 + D9 + the WS2-a stub-grep
scoping) into all four downstream projects: `learn-ai`, `python-orchestration-system`,
`bastion`, `markdown-engine-validator`. All four were on `main` with clean trees; changes left
uncommitted in each working tree for per-repo review.

**Factory fix surfaced by propagation.** Diffing exposed 6 stale `DECISIONS.md` references in
this repo's own engines — `sdlc-run.js` (3) and `sdlc-task.js` (3) — left over from before OKF
Phase 2 settled the lowercase `planning/decisions/` concept-folder convention ([D5](planning/decisions/D5-okf-phase-2-adopted.md)).
`learn-ai` had already locally patched its `sdlc-run.js` to `planning/decisions/`; the rest still
carried the old name. Replaced all 6 in `base-template` → `planning/decisions/`. After the fix,
canonical `sdlc-run.js` converged with learn-ai's local copy (its propagation was a no-op),
confirming this was a genuine factory miss, not a learn-ai customization. Mechanism-prose only —
no ADR (it just brings engine text into compliance with D5). Both engines `node --check` clean.

**How each project was handled (engines are agnostic; commands were not uniformly so):**
- **Engines** (`sdlc-task.js`, `sdlc-run.js`, `sdlc-block.js`, `harness.schema.json`) — pure
  version-lag everywhere (no project-specific tokens in any diff), overwritten with canonical in
  all four. `sdlc-block.js` + `harness.schema.json` were already current everywhere (no-ops).
- **Commands** (`generate-tasks.md`, `breakdown.md`) — `python-orchestration-system`, `bastion`,
  `markdown-engine-validator` are on the agnostic command generation (only the D9 disjoint-file-
  ownership text was missing), so overwritten with canonical. **`learn-ai` is on the older
  pre-agnostic command generation** — its `generate-tasks.md`/`breakdown.md` carry deliberate
  project facts (npm scripts, EN+pt-BR parity, `app/[locale]/`, `content/` mdx, `lib/services/`).
  Did **not** overwrite; surgically inserted only the D9 disjoint-file-ownership rule, preserving
  its customizations.

**Follow-up flagged (not done here):** `learn-ai`'s harness commands predate the OKF-Phase-2
agnostic refactor and still bake stack/policy into `.claude/` rather than `harness.json` + CLAUDE.md.
A full migration of learn-ai to the agnostic command set is a separate, larger effort.

## 2026-06-20 — Three telemetry-pass follow-ups: stub-grep scoping (#1), decomposition guard (#2), slim reports (B2)

Closed three open items from the SDLC telemetry pass in one session. All three are mechanism-only and
propagate downstream via the manual update loop; both engines `node --check` clean.

- **#1 — WS2-a stub-grep scoping (resolves D8's known follow-up).** The implement/fix completeness
  self-checks (`sdlc-task.js`) no longer grep `git diff main..HEAD --name-only | xargs grep` over
  *every* changed file — they now scope the sanity-grep to the in-scope (implement) / flagged (fix)
  criteria's **required paths**, with an explicit "a stub in a file no in-scope criterion requires is
  out of scope — leave it" instruction. Removes the nudge toward out-of-scope edits the bastion run
  surfaced (6 harmless comment-only scaffold edits) without weakening the gate. D8 updated with a
  resolution note.

- **#2 — Spec-decomposition guard ([D9](planning/decisions/D9-disjoint-task-file-ownership.md), new
  ADR).** `generate-tasks` (step 5) and `breakdown` (step 6) gain an explicit disjoint-file-ownership
  rule: decompose so each task owns a distinct file set; when two tasks must share a file, either make
  one `dependsOn` the other (serialize) or restrict it to append-only (`additiveFiles`). The
  `sdlc-block` engine *already* serializes exclusive-file clashes into separate waves — but only on
  *declared* overlap, so the real gap was the spec drawing overlapping slices. The bastion
  `phase0-blockA` block escalated on exactly this (7-file merge conflict, tasks 1/2). Fix is at the
  authoring layer per the plan; no engine change.

- **B2 — slim report templates.** Implement/fix "Validation Output" and the test report's "Full
  Results (JSON)" now store **command list + PASS/FAIL + failing `tail -20` only** — passing checks
  store an empty error and no stdout. The Test stage stays the authoritative full-output capture and
  review re-runs the gating checks fresh, so the full passing transcript is never read downstream.
  Shrinks what every downstream stage re-ingests (the dominant waste pattern the pass targets).

```diff
 .claude/workflows/sdlc-task.js   | stub-grep scoping (×2) + slim report templates (×3)
 .claude/commands/generate-tasks.md | disjoint-ownership rule (step 5)
 .claude/commands/breakdown.md      | disjoint-ownership flag (step 6)
 planning/decisions/D9-...md        | new ADR (decomposition guard)
```

## 2026-06-20 — Document the harness.json extensibility model

Added an **"Extending the suite"** section to `docs/harness-json.md`, prompted by a session question
that the existing reference didn't answer: *is `harness.json` extensible, and where do I add more
criteria?* The reference documented the schema *shape* thoroughly but never captured the *mental model*
for extending it. The new section states three things that were previously scattered or absent:
(1) the **three-layer disambiguation** — validation *checks* live in `harness.json`, acceptance
*criteria* live per-task in the spec's `tasks.md`, project-wide *standing rules* live in `CLAUDE.md`
(conflating checks with criteria is the common first mistake); (2) the **config-vs-engine boundary** —
more of an existing kind is pure config (no ADR), a brand-new *kind* of check is a `base-template`
engine change with an ADR that propagates via the update loop; (3) that the **schema is strict**
(`additionalProperties: false`, fixed `kind` enum) so you cannot invent fields/kinds in a project's
config. No new concepts — consolidates what D5/D6/D8 already established into the durable reference so
the next session doesn't re-derive it.

```diff
 docs/harness-json.md | 31 +++++++++++++++++++++++++++++++
 1 file changed, 31 insertions(+)
```

## 2026-06-20 — Add WS2-b stub-scan profiles (config companion to WS2-a)

Added ready-to-paste **stub / not-implemented scan** profiles (Rust / Python / TypeScript) to the
scaffold's `planning/harness.examples.md`, as a `forbidden-pattern-scan` check projects can opt into.
This is the **policy** half of the stub-completeness lever: WS2-a (D8) is the agnostic implement-stage
*self-check* shipped in the engine; this is the optional per-project *gating test* that hard-fails on
left-in `todo!()`/`unimplemented!()` / `raise NotImplementedError` / `throw new Error('not implemented')`.
Honest false-positive caveats baked into each profile: Rust `unreachable!()` excluded (legit defensive
assertion); Python `raise NotImplementedError` allowlists `@abstractmethod`/interface paths since a
line-based grep can't see the decorator above (Python's self-check is the more reliable catch). All
three JSON blocks parse. Cross-referenced from `docs/harness-json.md`. No engine change — this is config
mechanism already supported by D6's `forbidden-pattern-scan` kind.

## 2026-06-20 — Ship WS2-a (implement/fix completeness self-check) — the loop is gone

Implemented and measured **WS2-a**, the retry-loop lever designed earlier this session. Added a
mandatory `5.5. SELF-CHECK` step to the implement **and** fix prompts in `sdlc-task.js`: before writing
the report or committing, re-read the in-scope acceptance criteria and confirm each is fully met — no
stubs (`todo!()`/`unimplemented!()`/`NotImplementedError`/…) on required paths, every named deliverable
file exists, every "unit-tested" criterion has a real hermetic test — fixing any gap before returning
`success`. Project-agnostic (binds to the criteria, no stack defaults). `node --check` clean; propagated
to `bastion`. Rationale + evidence in [D8](planning/decisions/D8-implement-completeness-self-check.md).

**Before/after (bastion `phase0-blockA` task 1, same base `506b27f`, B1-only vs B1+WS2-a):** review
attempts **2 → 1** — the loop eliminated. The B1-only run had looped because the implementer omitted a
`status()` render test; the WS2-a run included both render tests up front and swept the scaffold stubs,
matching the self-check behavior. Total task out-tokens **~57.1K → ~35.8K (~37% lower)**, and since both
runs had near-identical implement output (~14.3K vs ~14.9K), that delta is cleanly the ~21K-token loop
the self-check removed — not implement variance. The self-check's own cost is small and visible:
implement `filesReadKb` 31 → 35 KB, `promptTok` 1301 → 1652. n=1 caveat logged in D8 (directionally
confirmed on a clean comparison, accepted on the low-risk mechanism — same bar as B1).

**Noted follow-up (not blocking):** the stub grep scans all changed files, which nudged the implementer
to replace scaffold stubs in 6 files outside task 1's scope (harmless, comment-only). Refinement queued
in the plan: scope the grep to the criteria's required paths. Also still open: the spec-decomposition
guard (parallel tasks must touch disjoint files — the bastion block escalated on overlapping task 1/2
slices). Both are in the plan checklist + `status.md` for the next session.

## 2026-06-20 — Ship B1 (structured stage hand-off) + design WS2-a from the bastion baseline

Ran the `bastion` baseline (`/sdlc-block phase0-blockA`) and it taught us more than the tokens. Block
verdict **PARTIAL**: task 1 merged single-pass (PASS, 1 review, ~69.5K out); **task 2 escalated on a
merge conflict** across 7 files after 3 review attempts (~114.5K out); tasks 3-5 skipped. The conflict
is a **spec-decomposition** bug — task 1 and task 2 slices implemented the *same* files — not an engine
bug, but it poisons a full-block before/after. So B1 is measured **per-task** instead.

**Shipped B1** (`sdlc-task.js`): the review and fix stages stop `cat`-ing the upstream implement / test
/ review reports and instead inject those stages' structured StructuredOutput fields (hoisted to loop
scope as `lastImplReport` / `lastTestReport` / `lastReviewResult`). Added a null-safe `handoff()`
renderer + a "read the report only if ambiguous" escape hatch so a cold `review`/`fix` resume degrades
gracefully. The review gate is untouched and authoritative — it still reads the spec's full acceptance
criteria, reads **real source**, and **re-runs every gating check fresh**. `node --check` clean;
propagated to `bastion`. Rationale + the load-bearing "do not weaken the review gate" call recorded in
[D7](planning/decisions/D7-token-efficiency-passes.md).

**B1 before/after (bastion task 1, clean isolated signal — review `filesReadKb`):** 17 KB → 12-13 KB
(~28% lower) across both reviews, verdict PASS held, and the review **still caught a real gap** (a
missing render-path test) which the fix agent then resolved off B1's *structured* `unmetCriteria`
(review-2 PASS) — evidence the gate isn't weakened. Honest caveat logged in D7: total per-task tokens
are confounded by implement non-determinism (B1 doesn't touch implement), so B1 is accepted on the
clean per-review signal + low-risk mechanism, not on token totals (n=1).

That same run **re-priced the retry loop** the plan flagged: one missing unit test triggered a full
fix→test→review loop costing ~21.7K out-tokens — far more than B1 saves. So **designed WS2-a** (now in
the plan): a mandatory implement/fix **completeness self-check** before commit — re-read the in-scope
acceptance criteria, confirm no stubs (`todo!()`/`unimplemented!()`/`NotImplementedError`/…) remain on
required paths and every named deliverable file exists, fix any gap before returning `success`. Project-
agnostic (binds to *the criteria*, hardcodes no stack). Implementing it next, then a loop-rate before/
after. Median review attempts is the WS2 metric (baseline: task 1 = 1, task 2 = 3).

## 2026-06-19 — Phase B kickoff: ship B4 + stand up `bastion` as the B1 experiment vehicle

Reviewed the two clean `## Token Metrics` sections from the `markdown-engine-validator` Block C run
(the first real baseline now that A3-fix lands the section deterministically). The data confirmed the
plan's sequencing: injected prompts are tiny (every stage <1.6K promptTok, so B4 is a pure multiplier),
and **review ingestion tracks implement output** — review `filesReadKb` was 17 KB on a thin task vs
36 KB on a heavier one. That correlation is the B1 signal (review re-`cat`s the full implement/test
reports), and it scales with task complexity — so we want a more complex before/after than the small
markdown tasks, plus a loop-rate sample (both baseline tasks were single-attempt PASS, so we have none
yet).

Acted on it: **shipped B4** (`e60ba6a`) — compressed the per-stage `${W}` worktree header in
`sdlc-task.js` from a 14-line box-drawing banner to 3 load-bearing lines (repo root, the
cd-before-every-Bash rule, no-shell-state-persistence, relative-path resolution). Zero behavior change,
committed alone so the upcoming B1 before/after both sit on top of it. `sdlc-block.js` needs no change
(it runs from the main repo root, no `${W}`).

Then **set up `bastion` as the B1 vehicle** (chosen with Brandon: a more complex, not-yet-started Rust
CLI gives bigger review-ingestion numbers + a fresh loop-rate sample). Propagated the A+B4 engines and
the D6 schema into `bastion/.claude/workflows/` (it was still on the pre-A engines) — `bastion@7500477`,
`node --check` clean. Authored and committed a Phase 0 Block A spec — `bastion@649d23c` — for
`bastion status` (config plumbing + DB/API health probes + `.env.example`). Made the spec
**offline-honest**: the gated checks are all `cargo …` and must pass without live infra, so the
unreachable-service path is the unit-tested behavior; the "real health against a running orchestrator"
line is a manual, non-gating acceptance. Stopped at the baseline run — `/sdlc-block phase0-blockA`
should be launched from a session opened in `bastion/` (the skills prime to CWD + create `./trees`
worktrees there), and must NOT be merged afterward so the B1 re-run starts from identical main.

Remaining sequence (durably recorded in `status.md` + the plan checklist): run baseline → capture
metrics + median review attempts → ship B1 (inject structured fields, stop `cat`-ing reports, keep the
review gate authoritative) → re-run bastion for the after → compare the four gates → D7 ADR + `log.md`
before/after numbers.

```diff
 .claude/workflows/sdlc-task.js | 16 +++-------------
 1 file changed, 3 insertions(+), 13 deletions(-)
```
(Plus, in the separate `bastion` repo: engine propagation `7500477` and spec `649d23c`.)

---

## 2026-06-19 — Fix the universal emoji gate (regex silently broken by JS template-literal escaping)

A downstream telemetry run surfaced a long-standing bug: the universal no-emoji gate's regex was
**inert** (worse, false-positiving). The Python `re.compile(r'[\U0001F300-...]')` lives inside a JS
template literal, where `\U` is not a recognized JS escape — so the backslashes were silently
stripped at render time and the Python received `[U0001F300-U0001FAFF...]`, a char class that matches
ASCII digits and `A`–`U` instead of emoji. Every task touching a `.md` file with a digit or capital
letter tripped the gate's test-stage check (overridden downstream by review, so it limped as noise
rather than a hard block, and never actually caught an emoji).

Fix: double the backslashes in the source (`\\U0001F300`) so JS renders `\U0001F300` and Python's raw
string sees the correct unicode ranges. Verified: post-fix the class matches real emoji (🚀, ✨) and
NOT `Task` / `Heading 3`. Applied in `sdlc-task.js` and `sdlc-run.js` (the two engines with the gate;
`sdlc-block` delegates). Swept both engines for sibling `\b \d \w \s \U` single-backslash escapes
inside template-literal strings — none found (the only other matches are legit JS regex literals).
`node --check` clean. Propagated to the downstream repos.

> Note: harness.json patterns are unaffected — they come from parsed JSON (where `\\.` → `\.`
> correctly), not from template-literal source. This class of bug only bites regex escapes written
> directly in engine template-literal strings.

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
