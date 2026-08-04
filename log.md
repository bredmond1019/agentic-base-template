# log.md — base-template

*The template's own change history. One dated entry per session, newest at the top. This file
records changes to the **factory** — it is never copied into generated projects.*

**Last updated:** 2026-08-04T16:53:14Z

---

## [2026-08-04]

### Closed the clippy blind gate (D55) and found the lane it does not reach

- **What:** `BT.ticket.all-targets-clippy-gate` shipped, all 7 tasks. **[D55](planning/decisions/D55-all-targets-clippy-placement.md)**
  puts `cargo clippy --all-targets -- -D warnings` in the shipped Rust profile's authoritative
  `command` and demotes the narrow lib+bins form to `fastCommand`, on a measured `engine-rs` delta
  of **+6.72s warm (~3.3x, ~26% of D57's 26s tripwire)**. Applied to `harness.examples.md`,
  `docs/harness-json.md`, `.claude/commands/test.md`, `.agents/skills/test/SKILL.md` and the D57
  playbook. Verifying D55 then surfaced a larger defect, now specced as
  `BT.ticket.sdlc-task-has-no-authoritative-gate` (wave 34): **`/sdlc-task` never runs any check's
  authoritative `command` and never runs any `perTask: false` check at all** — `testDepth` defaults
  to `fast` (`sdlc-task.js:1005`), applies to every task including the last (L1322), substitutes
  `fastCommand` (L622), filters out `perTask: false` (L525), and bookkeep runs no tests. Seven live
  repos each have at least one gating check the lane cannot run: `build` in all seven, plus the
  integration half of the test suite in `bastion`/`bella`/`engine-rs`/`mev`.
- **Why:** `mev` and `okf-core` both shipped almost-all-test-code blocks green on 2026-08-03 — the
  lint gate was structurally incapable of seeing the diff. The naive fix collided with D57, which
  had just tuned that same tripwire and left clippy in it at ~75% of its cost, so the ticket was
  written to force a measurement rather than a flag swap. The follow-up matters more than the
  original: `/ticket` and `/chore` route to `/sdlc-task` by default, so the blind lane is exactly
  where the bug was found — two blind spots (lint can't see tests, tests don't run integration)
  stacked in one engine.
- **Refs:** `planning/ticket-all-targets-clippy-gate/` (+ `measurement.md`), `planning/decisions/D55-all-targets-clippy-placement.md`,
  `planning/ticket-sdlc-task-has-no-authoritative-gate/`, brain `docs/decisions/D57-rust-sdlc-iteration-speed.md`

### The brain root became an engines-only sync target (D54)

- **What:** HQ (`agentic-portfolio`) was given `.claude/workflows/` so the SDLC engines and
  `/orchestrate` can drive its own chore blocks — it had none, which is the real reason the HQ track
  sat at 0/10 through the `bullet-proof-software` week. Creating that directory silently made HQ an
  eligible target for `scripts/sync_downstream_harness.py`, which also copies `commands/*.md`.
- **The trap:** twelve command filenames exist in both trees and **all twelve differ** — `archive`,
  `backlog-ticket`, `capture`, `commit`, `generate-master-plan`, `handoff`, `log-work`, `prime`,
  `README`, `session-recap`, `update-state`, `wrap-up`. HQ's `/prime` is 164 lines to
  base-template's 55; HQ's `/log-work` carries the cross-repo brain sync. The script only ever
  adds/updates, so the clobber would never have been reported as a deletion.
- **Fix:** `RepoTarget.engines_only`, set for the target whose `repo_path` resolves to the brain
  root; `harness_files()` drops `commands/*.md` when it is set. Threaded through all three
  iteration sites (diff, stale-key computation, manifest rebuild) so detection, application, and
  manifest bookkeeping agree.
- **Verified:** `--repo brain` dry-run reports "up to date" (0 files), while a full dry-run still
  reports 40 files across 17 repos — the guard is selective, not a no-op.
- **Refs:** `planning/decisions/D54-brain-root-is-an-engines-only-sync-target.md`.

## [2026-08-04]

### `/orchestrate` chain — all 9 open BT.ticket state-reliability blocks closed

- **What:** Ran `/orchestrate` end-to-end (`--worktree`, self-paced, no user prompts) across all 9 open
  `BT.ticket.*` blocks: `sdlc-state-write-reliability`, `auto-emit-state-after-sdlc`,
  `trim-state-writer-roundtrips`, `fold-state-write-into-test-agent`, `sdlc-engine-parse-gate`,
  `harness-content-hash-manifest`, `state-write-updated-at-freeze`, `sdlc-block-resume-stale-state`,
  `per-task-fast-checks`. All 9 closed; every engine `node --check` clean; `mev validate-brain
  --state` reports 0 errors after the full chain. Four of the nine had no spec yet
  (`sdlc-state-write-reliability`, `auto-emit-state-after-sdlc`, `sdlc-engine-parse-gate`,
  `harness-content-hash-manifest`) — authored all four as `/ticket`-shaped specs from the rich `note`
  fields already captured in `planning/state.json` at backlog-promotion time (this repo's actual
  convention for `BT.ticket.*` blocks; `/generate-tasks` targets `master-plan.md` phase/block
  sections, which doesn't apply to standalone tickets).
  Key fixes shipped: (1) replaced the free-form, model-authored Edit-tool JSON surgery for flipping a
  `state.json` block's `status` to `"closed"` with one deterministic scripted `python3` mutation, in
  all three terminal-stage engines (`sdlc-task.js`, `sdlc-flow.js`, `sdlc-run.js`) — block-id
  *resolution* stays agent prose, only the JSON *mutation* is now scripted; (2) decoupled each
  engine's `mev emit-state --write` trigger from full block completion, so a partial/task-subset run
  — which already edits `status.md`/`tasks.md` — resyncs derived surfaces too, instead of only a
  full block close doing so; (3) added a hardcoded, project-agnostic `node --check` gate over any
  `.claude/workflows/*.js` file a task's diff touches, in `renderCheckList()` across all three
  engines that render checks directly (plus a confirmed, documented delegation finding for
  `sdlc-block.js`) — closes the exact gap that let two real parse-time breaks land undetected in a
  downstream repo (wild-trail-photo commits `0d82648`, `59d217a`), since that project's own
  `harness.json` had no reason to check the harness's own JS; (4) ported a `qm`-style content-hash
  manifest into `scripts/sync_downstream_harness.py` (`stale-safe` unmodified-since-last-sync →
  delete, `stale-conflict` locally-modified → never delete, report instead), closing the "removed
  harness files never get cleaned up downstream" gap. Two blocks
  (`trim-state-writer-roundtrips`, `per-task-fast-checks`) turned out to already be implemented
  inline before this run (confirmed by grep before launching each engine) — their pipeline runs were
  clean no-ops (zero implement commits) that formally closed them with a real validation pass on
  record, resolving a "task 5/task N outstanding" note each had been carrying.
- **Why:** These 9 blocks were the queued next work on the state-reliability/fleet-integrity thread —
  the state graph is the authoritative plan surface every board, `/attention`, and staleness clock
  reads from, so a writer that silently fails to update it (or derived surfaces that go stale between
  writes) corrupts what the whole fleet trusts. Run via `/orchestrate <9 ids> --worktree`, "finish
  until completed, answer your own questions with your strongest recommendation, keep a running tab
  of issues/decisions" — a fully self-paced session goal.
- **Issues found + repaired during the run:** a bookkeep stage (Haiku, cheap model) copy-pasted BLOCK
  1's description verbatim into `status.md`'s "Current focus" under BLOCK 2's heading (code and
  `state.json` were correct; only the prose was wrong) — repaired by hand. One pre-existing spec
  (`ticket-fold-state-write-into-test-agent/tasks.json`) has a task-id gap (no `4`; jumps `3→5→6`)
  predating this session, with no Amendment Log entry explaining it — cosmetic, not a correctness
  issue, left as-is (all declared tasks passed, `dependsOn` ids all resolve).
- **Explicitly declined:** building `mev`-binary-freshness detection into the harness for
  `auto-emit-state-after-sdlc` — would require a hardcoded path to `core/mev`'s source repo, which
  violates this repo's own project-agnosticism standing rule (`.claude/` ships mechanism, never
  project facts). Logged as a needed follow-up ticket to file against the `mev` repo instead (`mev
  --version` currently carries no build provenance to assert freshness against).
- **Refs:** `planning/ticket-sdlc-state-write-reliability/`, `planning/ticket-auto-emit-state-after-sdlc/`,
  `planning/ticket-trim-state-writer-roundtrips/`, `planning/ticket-fold-state-write-into-test-agent/`,
  `planning/ticket-sdlc-engine-parse-gate/`, `planning/ticket-harness-content-hash-manifest/`,
  `planning/ticket-state-write-updated-at-freeze/`, `planning/ticket-sdlc-block-resume-stale-state/`,
  `planning/ticket-per-task-fast-checks/`.

## [2026-08-03]

### `BT.ticket.triage-verify-pre-existing-claims` shipped — triage can no longer assert an unverified pre-existing/baseline claim

- **What:** Ran `/sdlc-flow ticket-triage-verify-pre-existing-claims` end to end (3 tasks, review PASS,
  docs patched). Task 1 added two new fields to `TRIAGE_SCHEMA` in both `sdlc-task.js` and
  `sdlc-flow.js` — `evidence` (string, observed output only) and `baseStateChecked` (boolean) —
  inserted verbatim-identical (same key order, same descriptions) alongside the unchanged
  `class`/`reason`/`bailReason`/`sameFailureAsBefore` fields. Task 2 inserted a new rule into both
  engines' `triage()` prompt bodies, placed immediately after the `BAIL_REASONS` list and before the
  RETRYABLE/MAJOR classification block: before triage may claim a failure predates the current task
  (a "pre-existing"/"at baseline" assertion), it must first re-run **only the failing check** against
  base state, or else phrase the claim as an explicit hypothesis rather than observed fact; a
  harness-created workspace (worktree, sparse checkout, copied env files, repaired symlinks) is named
  as a candidate cause, not a fixed backdrop, since an identical failure before and after a change is
  not evidence of pre-existence when the environment is shared between the two states. The
  `StructuredOutput` line in both files was extended to enumerate `evidence` and `baseStateChecked` so
  the prompt actually instructs the agent to populate the new schema fields. Task 3 verified no drift
  between the two engines' `TRIAGE_SCHEMA`/`BAIL_REASONS`/prompt bodies after tasks 1–2 and confirmed
  `node --check` on both engines plus the `harness.schema.json` parse. Review verdict PASS with no
  findings.
- **Why:** Bailing on an environment fault is correct and stays unchanged (`BAIL_REASONS` #3), but the
  *diagnosis* triage writes into `bailReason` was previously unconstrained — the agent could describe a
  self-inflicted environment fault as "pre-existing … at baseline, unrelated to this task" without ever
  checking, because a broken shared environment fails identically before and after the task's edits.
  The observed incident (`core/orchestrator` session 12, issue I36) sent the operator hunting for a
  missing fixture and inherited test debt, neither of which existed, while the real cause — a reverting
  `planning/` symlink introduced by the harness itself — sat one `ls -l` away.
- **Decisions:** Constrained the assertion, not the bail — no new retry attempts for environment faults,
  `BAIL_REASONS` #3 and "when unsure, BAIL" untouched. Preferred a cheap re-run-the-failing-check
  verification over a bare disclaimer, per the ticket's design decision 2. Separated observation from
  inference in the schema via the new `evidence` field rather than overloading `bailReason`. The new
  prompt block was inserted verbatim identically in both engines despite their pre-existing
  engine-specific differences (`extraBailReasons` spread, "worktree root" vs "run root" wording), to
  keep the duplicated `triage()` stages behaviorally equivalent per the ticket's drift-prevention
  requirement.

### `BT.ticket.gate-skip-count-regression` shipped — the gate now fails when tests stop running, not only when they fail

- **What:** Ran `/sdlc-flow ticket-gate-skip-count-regression` end to end (3 tasks, review PASS, docs
  patched). Task 1 added a new opt-in `skip-count-regression` check kind to `harness.schema.json`,
  modeled closely on the existing `baseline-diff` kind: it captures a baseline skip count at run start
  (`baselineCommand`) and fails the gate only when the current count (`command`) *rises* above it,
  plus an optional `reasonCommand` (fired only when the check is about to fail) to surface the
  dominant skip reason instead of a bare number. Task 2 ported identical rendering + gate-time
  evaluation into both `sdlc-task.js` and `sdlc-flow.js`, including a shared pure
  `skipCountRegressionResult(baselineCount, currentCount, dominantReason)` delta function (mirrored
  verbatim in both engines, per the ticket's "testable without running a suite" requirement) and a
  new baseline-artifact convention (`<reportsDir>/<slug>-skip-baseline.txt`, bare integer — distinct
  from `baseline-diff`'s JSON-array `-baseline.json` file since the payload shape differs). Task 3
  added a configured Python/pytest example (`pytest -q -rs | grep -c '^SKIPPED'`) to the rich-checks
  profile in `scaffold/planning/harness.examples.md` plus documented cargo/nextest and vitest count
  commands for stacks that don't get a full worked example. Schema stays valid Draft-7; every existing
  example profile and this repo's own `harness.json` still validate unchanged (opt-in, zero behavior
  change for anyone not adopting the new kind). Review verdict PASS with no findings.
- **Why:** A pass→skip conversion is invisible to every prior check — "no failures" holds and the
  collect-count guard holds too (skipped tests are still *collected*) — so a suite can silently lose
  its entire integration surface (the triggering incident: 46 pgvector tests in `core/orchestrator`
  stopped running when a container daemon was down, and nothing caught it). This closes that blind
  spot as an opt-in, stack-agnostic check.
- **Decisions:** Reused `baseline-diff`'s capture-at-start/compare-at-gate plumbing rather than
  inventing a second mechanism; fails on a *rise* in skips (not any nonzero count) to avoid noise on
  legitimately conditional suites; the count command is fully config-supplied, no runner hardcoded.
  `skipCountRegressionResult()` was verified manually (`node -e`) rather than wired into an automated
  JS test runner, since neither engine script has one and no sibling check kind does either — recorded
  as a spec amendment rather than silently deferred.
- **Refs:** `planning/ticket-gate-skip-count-regression/` (tasks.md Amendment Log has the two task-2
  deviations); `.claude/workflows/harness.schema.json`, `.claude/workflows/sdlc-task.js`,
  `.claude/workflows/sdlc-flow.js`, `scaffold/planning/harness.examples.md`, `docs/harness-json.md`.
  Downstream propagation via `/sync-downstream-harness` is explicitly out of scope per the spec (D5).

### Logged three wave-28 tickets forwarded from `core/orchestrator`, plus a field-evidence amendment

- **What:** `core/orchestrator` filed three new tickets directly into this repo's ticket vault —
  `BT.ticket.triage-verify-pre-existing-claims` (I36's diagnostic half: triage must not assert a
  failure is pre-existing without verifying it), `BT.ticket.gate-skip-count-regression` (I37: a new
  `harness.schema.json` check kind so the gate fails when tests stop running, not only when they
  fail), and `BT.ticket.worktree-env-file-copy` (I35, patch-tier: worktree setup must copy every
  gitignored env file, not just the root pair) — all registered wave 28, `open`, with full specs
  (`tasks.md` + `tasks.json`, 3 tasks each) and listed in `planning/index.md`. Rather than filing a
  fourth ticket, `core/orchestrator` also amended the existing
  `BT.ticket.init-worktree-symlink-repair` (wave 23) with field evidence from a live session
  (2026-08-02, `core/orchestrator` session 12, issue I36): a **tracked** symlink defeats the repair
  entirely, and any repair should verify the link resolves instead of assuming the write stuck. All
  four items were already fully filed when reviewed this session; this entry only records that the
  hand-off happened, since it was never logged.
- **Why:** The tickets and amendment landed directly in `state.json` / the planning vault without a
  corresponding `log.md` entry, so the hand-off was invisible to session-recap and would have looked
  like unexplained pre-existing backlog to a future session.
- **Refs:** `planning/ticket-triage-verify-pre-existing-claims/`,
  `planning/ticket-gate-skip-count-regression/`, `planning/ticket-worktree-env-file-copy/`,
  `planning/ticket-init-worktree-symlink-repair/` (Amendment Log).

## [2026-07-31]

### Distributed the harness pull (D53 + validation_commands) to every scaffolded repo

- **What:** Ran `/sync-all` (regenerated `.agents/skills/` from `.claude/commands/` for base-template,
  the workspace root, and all five sub-brain tiers; reconciled global `~/.claude/commands/` and
  `~/.gemini/config/skills/`) and committed the result in both the brain root and base-template.
  Then ran `scripts/sync_downstream_harness.py --apply` to pull `commands/generate-tasks.md`,
  `commands/README.md`, `commands/close-out.md`, `workflows/sdlc-flow.js`, and `workflows/sdlc-task.js`
  (the D53 code-review drop plus the new per-task `validation_commands` override in `sdlc-flow.js`'s
  `ENUMERATE_SCHEMA`/`runTests`) into all 16 eligible downstream repos, then committed the change in
  each of the 15 that track `.claude/` in git (`rag-engine-rs` gitignores it by design and was
  skipped). Also added a `carryover[]` entry to `orchestrator`'s `planning/state.json` flagging that
  its independent Python `SDLC_FLOW` workflow declares `validation_commands` on `SDLCTask` but never
  reads it, unlike the JS engine's new override path.
- **Why:** A harness fix landing only in `base-template` isn't fixed anywhere real work happens —
  `/sync-all` and `/sync-downstream-harness` are the two distribution steps (skills/commands vs. the
  `.claude/workflows/*.js` engines) that make a change here actually reach every consumer.
- **Refs:** [D53](planning/decisions/D53-drop-close-out-code-review.md),
  [D48](planning/decisions/D48-downstream-harness-sync-script.md)

## [2026-07-30]

### D53 — dropped the `/close-out` code-review step

- **What:** Removed `Step 2.5` and the `--no-review` / `--review-level <level>` flags from
  `.claude/commands/close-out.md`, regenerated the `.agents/skills/close-out/SKILL.md` mirror from
  it, and updated both `.claude/commands/README.md` surfaces (the summary-table row and the catalog
  entry). Edits touched Variables, Examples, the Execution Model command list, the Step 0
  argument-stripping list, the Step 2.5 block itself, and the Step 4 handoff-note strip list. The
  README catalog entry now states outright that code review is not part of the pipeline. Authored
  [D53](planning/decisions/D53-drop-close-out-code-review.md) superseding the code-review half of
  D49 and added its index row. Grep-clean of `no-review` / `review-level` / `Step 2.5` outside this
  log's own historical entries.
- **Why:** `/code-review` is user-triggered and separately billed — an agent cannot launch it from
  inside another slash command. Step 2.5 therefore either silently no-oped or invited the model to
  improvise a stand-in review carrying none of `/code-review`'s guarantees. A gate that cannot fire
  is worse than no gate: it reports confidence it never earned. D49's `--clean-worktree` half is
  untouched.
- **Refs:** `planning/decisions/D53-drop-close-out-code-review.md`. Propagation via
  `/sync-downstream-harness` + `/sync-global-commands` still outstanding.

### BT.ticket.trim-state-writer-roundtrips task 5 — invariants verified by audit; an `updated_at` freeze found and ticketed

- **What:** Closed out task 5's verification half without starting a throwaway run. Audited the 39
  state files already in `core/_planning/*/*/sdlc/` — 28 from runs that started after `3beac11`, i.e.
  already on the trimmed engines, across `engine-rs`, `bastion`, `bastion-web`, `mev` (all four
  confirmed to carry `cachedStartedAt`). **Verified:** all 39 parse and the post-change set adds no
  engine key the pre-change set lacks; `started_at` preservation holds (27/28 runs show it well
  behind `updated_at`, median span 48.9 min, max ~2.7 days across multiple `--resume` processes);
  D46 disk-only holds in practice (zero state-file commits since 07-27 in engine-rs/bastion-web/
  bastion); `node --check` clean on all four engines and the D46 prohibition text intact. Then
  sampled two **live** runs (`bastiel/6.A-market-abstraction-config`, `engine-rs/EN.6.B-email-adapter`)
  read-only through to `done`, capturing 16 distinct state writes: `updated_at` advanced strictly
  monotonically in both — no freeze reproduced, but at a ~7% per-run rate two clean runs prove
  nothing (P(zero) ≈ 0.86), and it is recorded that way. **Found:** `updated_at` intermittently
  freezes at `started_at` on later writes — `bastion/11.S-last-touched-board-dto` (7 tasks, 0.0 min
  span) and `bastion/ticket-enrich-block-authored-status` (4 tasks, 0.4 min) against 9–3986 min for
  every other run. Wrote `planning/ticket-state-write-updated-at-freeze/` (tasks.md + tasks.json, 5
  tasks) and registered `BT.ticket.state-write-updated-at-freeze` in `state.json` (Tickets, wave 27,
  origin the trim ticket). **Still open:** the before/after timing number.
- **Why:** Task 5 was the last thing standing between `BT.ticket.trim-state-writer-roundtrips` and
  done, and its measurement is the explicit go/no-go gate on
  `BT.ticket.fold-state-write-into-test-agent`. An artifact audit beat a fresh run on sample size
  (28 runs vs 1) for every invariant except the timing, which turned out not to be recoverable from
  disk at all: `worklog.md` carries no timestamps and `state:*` uses plain `agent()` rather than
  `tracedAgent()`, so no duration was ever recorded. A file-mtime proxy was tried twice and
  **abandoned twice** — on historical artifacts (the vault is tracked inside the brain repo, whose
  merge commits rewrite mtimes) and again on live runs (files were rewritten in bursts every ≤8 s
  while `updated_at` held constant, so the "lag" tracked an unidentified rewriter, not the writer).
  Recorded as the `state-file-mtime-is-not-a-clock` carryover so it is not attempted a third time.
- **Refs:** `planning/ticket-trim-state-writer-roundtrips/tasks.md` (Notes + Amendment Log),
  `planning/ticket-state-write-updated-at-freeze/`, `planning/state.json` `carryover[]`.

## [2026-07-29]

### BT.ticket.per-task-fast-checks — perTask/fastCommand fields land, manually verified

- **What:** Implemented `planning/ticket-per-task-fast-checks/` directly (no `/sdlc-task`),
  working tasks.json 1–4 in strict sequence. Added optional `perTask` (boolean, default true) and
  `fastCommand` (string) fields to `harness.schema.json`'s `$defs.check.properties`. Mirrored the
  wiring into both `sdlc-flow.js` and `sdlc-task.js`: `HARNESS_CONFIG_SCHEMA` gains the two
  properties; `loadHarnessConfig`'s STEP 2 field-copy instruction now names them so the loader
  agent doesn't silently strip them; `renderCheckList`'s `gatingOnly` filter becomes
  `c.gates && c.perTask !== false`; the plain-command/count-delta render branch substitutes
  `c.fastCommand` for `c.command` only when `gatingOnly && c.fastCommand`. `sdlc-run.js` and
  `sdlc-block.js` deliberately untouched (no `gatingOnly` concept / no `renderCheckList` copy).
  `scaffold/planning/harness.examples.md`: Rust and Next.js `build` checks default to
  `"perTask": false`; Python profile unchanged (no build check); new "Per-task fast tripwire"
  subsection documents both fields plus a Rust `fastCommand` callout
  (`cargo test --lib --workspace`) for when the test command itself becomes the per-task
  bottleneck.
  Task 5 (Validate) was done **manually and honestly**, per explicit instruction not to report
  PASS on `node --check` alone (this repo's harness.json gates only that one check, which doesn't
  exercise any Testing Strategy assertion). `node --check` passed on all four engines; all five
  Testing Strategy assertions were then run against the ACTUAL extracted `renderCheckList` source
  (exact line-range extraction from the real files, not a re-typed copy) via a scratch Node script
  against fixture `harness.json` configs: (1) default-preserving — a check with neither field set
  renders byte-identical between `gatingOnly:true`/`false`; (2) `perTask:false` excludes a check
  from the fast-tripwire render only, still present unchanged in the full/review render; (3)
  `fastCommand` substitution verified in **both directions** on **both** engines — the fast
  tripwire emits `fastCommand` and never leaks `command`, the full/review render emits `command`
  unchanged and never leaks `fastCommand` (this is the dangerous failure mode: a leak here would
  silently weaken the review gate for every downstream repo, and it's invisible to every automated
  check this repo has); (4) loader round-trip — grep-confirmed both `HARNESS_CONFIG_SCHEMA`s and
  both `loadHarnessConfig` field lists name `perTask`/`fastCommand`; (5) profile spot-check —
  grep-confirmed Rust/Next.js `build` checks carry `"perTask": false`, Python unchanged. All five
  PASS on both engines; results recorded in `tasks.md`'s Amendment Log. `git status --porcelain`
  confirmed only the four intended files changed.
- **Why:** `testDepth:"fast"` (the default per-task tripwire in `/sdlc-flow` and `/sdlc-task`)
  currently means "every `gates:true` check," not "a cheap subset" — discovered in engine-rs,
  where all four `gates:true` checks (fmt/clippy/test/build --release) replayed a full ~1168-test
  `cargo test` plus a release build up to 3x per task, turning a multi-task flow that should take
  minutes into roughly an hour. The mechanism fix (optional, default-preserving opt-in fields) lets
  a project keep every check `gates:true` for review while giving the per-task tripwire a cheaper
  path, without weakening what review gates on.
- **Refs:** `planning/ticket-per-task-fast-checks/tasks.md`, `planning/ticket-per-task-fast-checks/tasks.json`.
  Downstream note: engine-rs (and any other repo) does not get this automatically —
  `/sync-downstream-harness` plus that repo's own `harness.json` edit (its own carryover,
  `harness-per-task-relinks-all-test-binaries`) is still required to realize the speedup; out of
  scope for this ticket.

## [2026-07-27]

### Scoped BT.ticket.fold-state-write-into-test-agent — /handoff for Opus review before implementation

- **What:** Wrote `planning/ticket-fold-state-write-into-test-agent/` (tasks.md + tasks.json, 6
  tasks) — folds the per-task `writeFlowState`/`writeTaskState` call in `sdlc-flow.js` and
  `sdlc-task.js` into the test agent's turn (on pass) or the triage agent's turn (on a terminal
  bail), removing a dedicated Haiku state-writer spawn per task. Task 5 additionally scopes a
  research pass (implement only if favorable) into folding `state:docs` and `state:wrap-up` the
  same way, per a follow-up user ask. Registered as `BT.ticket.fold-state-write-into-test-agent`
  in `planning/state.json` (Tickets track, wave 24, status open). Wrote `planning/handoff.md`
  (replacing a stale 2026-07-16 handoff) — the ticket is deliberately NOT implemented yet.
- **Why:** User measured `state:task` at 1.5–2 min/task and `test` at 0.5–3 min/task in real
  `/sdlc-flow` runs and asked what could cut that; investigation traced both to fixed agent-spawn
  overhead rather than model reasoning cost. Given this touches core engines every project's SDLC
  pipeline depends on, the user asked for an Opus-model review of the ticket's scope before any
  implementation, hence `/handoff` instead of proceeding straight to `/sdlc-task`.
- **Refs:** `planning/ticket-fold-state-write-into-test-agent/tasks.md`, `planning/handoff.md`,
  `planning/decisions/D52-inline-cheap-commands.md` (the related, already-committed command-level
  fix from earlier this session).

### Inline the cheap harness commands — drop subagent spawns from log-work, commit, and 8 others

- **What:** Removed the "spawn a subagent" Execution Model from 17 command files (8 in
  `.claude/commands/`, 9 mirrors in `.claude/commands/brain/`) in favour of running entirely
  inline: `log-work`, `commit`, `backlog-ticket`, `capture`, `update-task`, `start-block`, plus
  the brain-tier `add-idea`, `log-content`, `log-correspondence`, `log-decision`, `log-lead`,
  `update-career`, `update-linkedin`. Each is a small state edit (one file append, one git commit,
  one status flip) where a subagent round trip added latency without adding value — and for
  `log-work`/`capture` specifically, a cold-started subagent has no memory of the current session
  and can only reconstruct the narrative from `git log`, which actively hurt accuracy. Kept
  subagent-spawning for `archive`, `audit-archive`, and `initial-research` (real multi-step
  analytical work where the subagent boundary protects the main context window from long tool
  output) and left `brain/update-progress.md`'s `model: "self"` subagent untouched (out of scope).
- **Why:** User flagged that `log-work`/`commit` subagent round trips were taking too much time for
  what they do; reviewing surfaced the same pattern repeated across 15 more commands.
- **Refs:** none — mechanical command-doc edit, no spec.

### BT.ticket.vault-aware-state-commits — SDLC engines made vault-aware when staging planning/ writes

- **What:** Ran `/sdlc-task ticket-vault-aware-state-commits`; all 6 tasks passed in a single run,
  each fast-tested and committed individually on `main` (`04bb0e9`, `d3174c8`, `7025f59`, `9d1ac4a`,
  `a6ead54` — task 6 was validation-only, no code change). Added a `detectPlanningVault()` helper to
  both `.claude/workflows/sdlc-flow.js` and `.claude/workflows/sdlc-task.js` (`fs.lstatSync` +
  `fs.realpathSync`, in-process rather than shelling out) that reports whether `planning/` is a
  symlink and, if so, its resolved realpath. `writeFlowState` / `writeTaskState` are now write-only —
  they write `sdlc-flow-state.json` / the task-state file and append `worklog.md`, but issue no git
  command at all (deleted the failing `addList`/STEP 5 commit path entirely). The wrap-up commit in
  both engines now stages vault-owned files (`planning/status.md`, `planning/state.json`) via
  `git -C <vault-realpath> add <absolute-path>` when vaulted, never falling back to a `git checkout`/
  `git switch`/`git branch` outside the invoking repo's own root — both engines' state-writing prompts
  now carry an explicit prohibition on that. `docs/workflows/sdlc-flow.md` updated: documents that
  run-state is written but deliberately not committed (read back off disk only by `--resume`), plus a
  new "Vaulted planning directories (D46)" subsection stating the `git -C <vault>` staging rule.
  Validated: all four engines `node --check` clean; vault detection correct on vaulted vs. non-vaulted
  repos; no brain branch/commit contamination from this run; `--resume` still recovers passed tasks
  with run-state left uncommitted.
- **Why:** Under [D46](planning/decisions/D46-planning-vault-symlink.md) every sub-repo's `planning/`
  is a symlink into the brain's `_planning/` vault, so `git add planning/...` from the repo root fails
  with `fatal: pathspec is beyond a symbolic link`. The state-writer agent was "recovering" from that
  failure by checking out the run's branch inside the brain repo and committing there instead —
  contaminating HQ with spec-named branches and a stream of per-task `chore: flow state` commits (live
  evidence: 8 stray branches + commits touching `core/_planning/<repo>/`). This ticket fixes the two
  engines that do the staging so the failure mode can't occur.
- **Refs:** `planning/ticket-vault-aware-state-commits/tasks.md`,
  `planning/ticket-vault-aware-state-commits/tasks.json`. Follow-up (not done this session): per
  base-template's own `CLAUDE.md` update-loop rule, `/sync-downstream-harness` still needs to run to
  propagate this engine change to already-scaffolded downstream repos.

## [2026-07-16]

### D51 + resume-safety fixes committed; doc patch landed

- **What:** Committed D51 (`/sdlc-flow` defaults to a plain branch checked out in the main working
  tree, `--worktree` opt-in; `/close-out --merge-branch`; worktree `planning/` symlink repair in both
  `sdlc-flow.js` and `sdlc-task.js`; mode-aware auto-merge running `mev emit-state --write` on the
  base) as commit `b8a000b`. Also investigated and fixed a resume-safety bug in `sdlc-flow.js`
  discovered while debugging reports of "`/sdlc-flow --resume` restarts from task 1": `state.tasks`
  was only populated for tasks executed in the current invocation, so the first `writeFlowState()`
  after a resume silently dropped already-passed tasks from the committed `sdlc-flow-state.json`,
  causing the next resume to re-run them — fixed by merging the prior file's full `tasks` object into
  `state.tasks` before the per-task loop runs. Also hardened Setup's branch/worktree name-picker to
  abort with an explicit `setupError` (telling the caller to add `--resume`) instead of silently
  forking a `-2` name when the exact `<spec>-flow` candidate is already taken and `--resume` wasn't
  passed — this addresses a separate cause where an agent restarts a failed run via a cached Workflow
  `resumeFromRunId` without also adding `--resume` to args (`resumeFromRunId` only replays the
  Workflow tool's own cache; it has no effect on `sdlc-flow.js`'s own `resumeMode` flag). Ran
  `/code-review` low over the full diff — no findings. Confirmed no blocking coverage gaps (this
  repo's only build gate for the three engines is `node --check`; no unit-test convention exists for
  these prompt-orchestration scripts). Patched `docs/workflows/sdlc-flow.md`'s Resumption section to
  document both causes and the new setup guard. Committed the doc patch + log entry as `4c6d476`.
  Wrote `planning/handoff.md` and added a new carryover entry
  `sdlc-flow-resume-state-tasks-truncation` to `planning/state.json` (already done manually this
  session — not duplicated here). Both D51 and the resume-safety fixes are committed but NOT YET
  real-run verified (`node --check` clean, logic traced by hand only) — real-run verification on a
  vaulted downstream repo (not base-template) is the next step, tracked via the
  `worktree-relative-symlink-breakage` and `sdlc-flow-resume-state-tasks-truncation` carryovers in
  `planning/state.json`.
- **Why:** Two silent correctness gaps (a resumed run erasing its own passed-task history on the next
  state write, and a stale-name collision silently orphaning prior progress instead of telling the
  operator to `--resume`) needed fixing and landing before D51 could be trusted for real-run
  verification on a downstream repo.
- **Refs:** commits `b8a000b`, `4c6d476`. `.claude/workflows/sdlc-flow.js`, `.claude/workflows/sdlc-task.js`, `docs/workflows/sdlc-flow.md`.

### sdlc-flow resume-safety fixes (follow-up to D51)
- **What:** Investigated a recurring report that `/sdlc-flow --resume` (worktree and branch mode
  alike) restarted from task 1 instead of skipping already-passed tasks. Found two distinct causes
  and fixed the engine-side one:
  1. **Operator error (separate incident, no engine fix):** restarting via `Workflow({scriptPath,
     resumeFromRunId})` without also adding `--resume` to `args`. `resumeFromRunId` only replays the
     Workflow tool's own cached `agent()` calls — it has no relationship to `sdlc-flow.js`'s own
     `resumeMode = hasFlag('--resume')`. Without the flag, the engine has no signal a prior run
     exists and walks every task fresh.
  2. **Real engine bug, fixed:** `state.tasks` (the in-memory object `writeFlowState()` serializes
     wholesale on every commit) was only ever populated for tasks executed in the CURRENT invocation.
     Tasks skipped via `--resume` (already `passed`) never re-entered it, so the first state write
     after a resume silently dropped them from the committed `sdlc-flow-state.json` — the *next*
     resume would then see them as never-passed and re-run them. Fix: the resume-state-load agent now
     also returns the prior file's full `tasks` object (`tasksJson`), merged into `state.tasks` before
     the per-task loop runs, so committed history survives multiple resume cycles.
  3. **Backstop for cause #1:** Setup's name-picker (`worktreeRecipe` + `branchRecipe`, STEP 2) now
     checks the exact `<spec>-flow` candidate first. If it's already taken and `--resume` wasn't
     passed, setup **aborts** with a `setupError` explaining that `--resume` is required (spelling out
     that this holds even under a cached `resumeFromRunId` restart) instead of silently bumping to a
     `-2` name and orphaning the prior run's progress. Only a genuine unrelated-name collision still
     falls through to `-2`/`-3`/etc.
  - Docs: `docs/workflows/sdlc-flow.md` "Resumption" section rewritten to cover both causes and the
    new setup guard.
- **Why:** The silent-`-2`-fallback + `state.tasks`-truncation combo meant a resumed run could look
  like it acknowledged prior progress (`Resume: N task(s) already passed... skipping them.`) while
  simultaneously erasing that same progress from the committed record for the *next* resume — a
  correctness gap independent of whether the operator remembered `--resume`.
- **Refs:** `.claude/workflows/sdlc-flow.js`, `docs/workflows/sdlc-flow.md`. Folded into the same
  commit as D51 (`b8a000b`) since both touch `sdlc-flow.js`'s resume path. `node --check` clean.
  Same real-run verification requirement as D51 applies (untested on a live resumed run).

## [2026-07-15]

### D51 — /sdlc-flow defaults to a plain branch; --worktree opt-in; /close-out --merge-branch
- **What:** Flipped `/sdlc-flow`'s default from an isolated worktree to a **plain branch checked out
  in the main working tree**, keeping `--worktree` as an opt-in flag. Motivation: in brain-vaulted
  repos `planning/` is a gitignored **relative symlink** (`planning -> ../_planning/<repo>`) that
  breaks when evaluated from inside `trees/<slug>/`, so worktree runs hit the broken link and agents
  clobber it (carryover `worktree-relative-symlink-breakage`). Changes:
  - **`sdlc-flow.js`** — new `const useWorktree = hasFlag('--worktree')`. The setup agent now branches:
    default recipe does `git checkout -b <slug>-flow` in the main tree (aborts on a dirty tree via a
    new `setupError` schema field; no sparse-checkout/env-copy/init-commit; `worktreePath = repoRoot`);
    `--worktree` keeps the exact old sparse-checkout recipe. The `${W}` run-context header, the log
    lines, `state.mode`, and the return object are all mode-aware. Wrap-up's emit-state deferral note
    reworded (branch mode: "on a feature branch, not the base"). **Auto-merge** is now mode-aware
    (drops `git worktree remove/prune` in branch mode) **and runs `mev emit-state --write` on the base**
    after landing the PR in both modes (new `emitStateRan` field) — also closing the prior gap where
    `--auto-merge` merged without regenerating derived surfaces.
  - **`sdlc-block.js`** — `runBlockFlow` now passes `--worktree` to every child `/sdlc-flow`
    (`${slug} --no-pr --worktree`). Mandatory: the orchestrator fans out blocks concurrently and its
    gap-check/PR-open read each child's worktree path — branch-mode children would collide in one tree.
  - **`close-out.md`** — new `--merge-branch` flag (Step 5b): merges the current plain branch into the
    base (`git merge --ff-only`, mirroring `/clean-worktree`'s failure handling), runs
    `mev emit-state --write` on the base (graceful degrade), deletes the branch. Mutually exclusive
    with `--clean-worktree`.
  - **Worktree symlink repair (both `sdlc-flow.js` + `sdlc-task.js`):** `--worktree` setup now, when
    the main repo's `planning` is a symlink, recreates it inside the worktree as an **absolute** symlink
    to the resolved vault target (`python3 realpath` -> `ln -s`), for all paths (create / re-attach /
    reuse). Reads+writes hit the real vault; gitignored so never committed/merged — the broken-link ->
    real-dir -> force-add -> clobber chain can't start. Chosen over copying (which diverges committed
    state and re-introduces the clobber vector). Addresses the `worktree-relative-symlink-breakage`
    carryover in BOTH modes, not just the branch default.
  - Docs: `docs/workflows/sdlc-flow.md` (new "Isolation mode" section + usage/args/stage-table/commit
    updates), `docs/workflows/index.md`, `.claude/commands/README.md` (close-out signature + sdlc-flow
    row). ADR `planning/decisions/D51-sdlc-flow-branch-default.md` + index row. `.agents/skills` mirrors
    regenerated.
- **Why:** Solo, sequential feature work — the common case — no longer needs worktree isolation, and
  paying for it costs the vaulted-`planning/` symlink breakage. Branch mode sidesteps it entirely;
  `--worktree` remains for true parallelism (which `/sdlc-block` now requests explicitly).
- **Refs:** `.claude/workflows/{sdlc-flow,sdlc-block,sdlc-task}.js`, `.claude/commands/close-out.md`,
  `docs/workflows/{sdlc-flow,index}.md`, `.claude/commands/README.md`,
  `planning/decisions/D51-*.md`. All four engines `node --check` clean. **Uncommitted — pending review +
  real-run verification on a vaulted repo before clearing the `worktree-relative-symlink-breakage`
  carryover.** The worktree symlink repair (above) means the carryover is addressed in both the branch
  default and `--worktree`; verify both on a real vaulted-repo run before clearing it.

### Handoff for D50 review + sdlc-block auto-merge carryover
- **What:** Wrote planning/handoff.md pointing the next agent at the uncommitted D50 changes for code review; appended a `carryover[]` entry `sdlc-block-auto-merge-no-emit-state` (kind: deferred) to planning/state.json capturing that D50 left /sdlc-block --auto-merge's merge path without a `mev emit-state --write` call (it lands blocks during its own run, bypassing /clean-worktree + /merge-train). Re-ran `mev emit-state --write` clean (0 errors).
- **Why:** Preserve the one D50 follow-up before handing the review session to a fresh agent, so it isn't lost.
- **Refs:** planning/handoff.md, planning/state.json (carryover `sdlc-block-auto-merge-no-emit-state`), planning/decisions/D50-sdlc-engines-flip-block-status-on-close.md

### D50 — SDLC engines flip state.json block-status on close (+ merge-command emit-state)
- **What:** Closed the two `known_issue` carryovers where the SDLC engines finished blocks but left
  `planning/state.json` `tracks[].blocks[].status` stale (silently rotting every
  `mev emit-state`-derived surface — `focus`, rollups, cache watermarks, wave tables). Fixes,
  mirroring `/start-block` Step 8's block-resolution-from-the-status.md-row pattern:
  - **`sdlc-run.js`** (runs on main) — wrap-up now resolves the canonical block ID from the
    status.md Progress row it edits, flips `tracks[].blocks[].status` → `"closed"`, validates JSON,
    and runs `mev emit-state --write` (graceful degrade if `mev`/`brain.toml` absent); stages
    `planning/state.json` into the wrap-up commit. New `blockStatusFlipped` schema field.
  - **`sdlc-flow.js`** (runs in a worktree) — same authored flip, committed on the branch; does NOT
    run `emit-state` (worktree-unsafe post the mev `is_linked_worktree()` fix). Guarded off on bail /
    partial selection. New `blockStatusFlipped` schema field.
  - **`sdlc-task.js`** — gained a **lean `haiku` bookkeep close-out** (not a full wrap-up): on a
    passing run it marks `tasks.md` done, flips the status.md row + `state.json` block (full passing
    run only) to `closed`, and (in place, on main) runs `emit-state`; under `--worktree` it commits
    the flip and defers emit to merge. Writes no `log.md` narrative / D18 amendment log — prints a
    `/log-work` recommendation. New `bookkeep` MODEL tier + `BOOKKEEP_SCHEMA`; header + SKILL.md
    mirror reworded (and the stale "Antigravity Execution Guide" that told agents to run `sdlc-run`
    and skip status updates was corrected).
  - **`clean-worktree.md` + `merge-train.md`** — run `mev emit-state --write` on main post-merge
    (graceful degrade) so the worktree-deferred derived-surface regen lands once the authored flip
    merges.
  - ADR `planning/decisions/D50-sdlc-engines-flip-block-status-on-close.md` + index row.
- **Why:** `state.json` is the authoritative block graph and `emit-state` derives one-way from its
  authored status — a stale block status poisons every downstream surface until a human reconciles
  by hand (the engine-rs `state-json-block-status-stale` incident). The engines were the last
  writers that never authored the flip. Not the `tasks.json` contract — only wrap-up stages —
  so `core/orchestrator`'s `SDLC_FLOW` schema consumer is unaffected (no action needed there).
- **Refs:** `.claude/workflows/{sdlc-run,sdlc-flow,sdlc-task}.js`,
  `.claude/commands/{clean-worktree,merge-train}.md`, `.agents/skills/sdlc-task/SKILL.md`,
  `planning/decisions/D50-*.md`. Residual follow-up: wire `emit-state` into `sdlc-block.js`'s
  `--auto-merge` path (out of scope this pass). Verify on a real downstream spec run (NOT this repo)
  before clearing the two carryovers in `planning/state.json`.

## [2026-07-04]

### Update capture command and sync all skills
- **What:** Updated `.claude/commands/capture.md` to add the `--backlog` flag, improved its body prompts, and updated the Output Format instructions. Synced the changes to global commands and skills.
- **Why:** To prevent generating unneeded backlog tickets during rapid research sessions and to ensure notes are thoroughly detailed without hallucinated content.
- **Refs:** None

### Root-caused silent state.json reverts; opened sdlc-block --resume ticket
- **What:** Investigated a reported bug where uncommitted edits to `planning/state.json` (and
  similar files) were being silently reverted across repos with no `git checkout`/`reset`/`clean`
  involved. Live-audited `core/mev`'s Rust source (not just the workflow prompts) and root-caused
  it to `mev emit-state --write`: it resolves every repo's derived-file paths via `brain.toml`'s
  registered `repo_path` (`root.join(repo_path)`) regardless of CWD, so running it from inside a
  linked git worktree (e.g. `<repo>/trees/<slug>/`, used by `/sdlc-flow`/`/sdlc-block`) still
  silently writes to the **main checkout's** files, not the worktree's own copy. With several
  `sdlc-flow`s running concurrently in separate worktrees, each one's `mev emit-state --write`
  (invoked from `/log-work` and `sdlc-block.js`) was racing on the same shared main-repo files,
  clobbering any uncommitted manual edits sitting there. Wrote and registered a ticket for this in
  `core/mev` (`planning/update-write-state-in-trees/`, block `MV.ticket.update-write-state-in-trees`)
  with the full root-cause writeup and a fix design (guard `--write` against linked worktrees via
  `is_linked_worktree()`); that ticket has since been implemented and closed by another agent
  (mev commit `46e1e2e`, state.json status `closed`).

  A second, related bug surfaced: `sdlc-block.js`'s `--resume` path re-launched an already-merged
  block because it trusts a single `tracedAgent` read of the `block-orchestration-state.json`
  breadcrumb as the sole completion signal, with no fallback to git-derived truth — despite the
  file's own comment on `writeBlockState` claiming the child commits/PRs are the authoritative
  resume signal. Wrote and registered a ticket for this **in this repo**:
  `planning/ticket-sdlc-block-resume-stale-state/` (`tasks.md` + `tasks.json`), block
  `BT.ticket.sdlc-block-resume-stale-state`, added to `planning/state.json` under a new "Tickets"
  track at wave 21, status `open`. Fix design: cross-check each block's merge status via
  `git merge-base --is-ancestor ${slug}-flow ${trainBranch}` (branch-naming convention confirmed
  from `sdlc-flow.js:128`) OR'd with the breadcrumb — never trust the breadcrumb alone. Per explicit
  instruction, this ticket is left `open`/not-started — do not implement or start it yet.
- **Why:** A user report of files reverting with no visible git operation involved; needed a live
  source audit rather than trusting prompt-level assumptions to find the actual race condition.
- **Refs:** `core/mev/planning/update-write-state-in-trees/` (closed, mev commit `46e1e2e`);
  `planning/ticket-sdlc-block-resume-stale-state/` (open, deferred).

### /close-out after BT.1.B — doc patch + state repair
- **What:** Ran `/close-out` after the `bt-1-b-log-work-sync-rewire` `/sdlc-run`. Gating check
  (`engines-parse`) + emoji gate both passed clean; coverage scan correctly skipped (both changed
  files are markdown command definitions, docs/config-only). `/update-docs --patch` fixed two stale
  sections in `.claude/commands/README.md` — the `/prime` entry (missing the new freshness-gate/
  handoff/carryover mentions) and the `/log-work` entry + "Company Brain Integration" section (both
  still described the pre-rewrite hand-edited-cache behavior instead of the `mev emit-state --write`
  mechanism). Discovered and fixed a `planning/state.json` drift: `BT.1.B` was still `status: "open"`
  in `tracks[].blocks[]` despite being DONE — the prior wrap-up never flipped it. Flipped it to
  `closed`, ran `mev emit-state --write` to re-derive `focus` (correctly went empty, since BT.1.C
  isn't a registered `tracks[]` block yet). Verified mev PR #18 is `MERGED` and cleared the
  now-resolved `bt-1-b-mev-pr-unmerged` carryover. Recorded two new carryover entries for follow-ups
  found this session: the sdlc-run's review stage returned PASS but never wrote `review.md` to disk
  (blocked the document stage that run); and `.agents/skills/log-work/SKILL.md` +
  `.agents/skills/prime/SKILL.md` are now stale mirrors of the two commands BT.1.B changed — this
  session's own `/log-work` invocation loaded the stale mirror and had to be redirected to follow
  the current `.claude/commands/log-work.md` body instead, live confirmation of the gap.
- **Why:** `/close-out` closes the quality loop before handoff — verifying gating, filling doc gaps,
  and reconciling derived state so the next session doesn't inherit silent drift.
- **Refs:** `.claude/commands/README.md`, `planning/state.json`, `planning/handoff.md`.

### BT.1.B — rewire /log-work + session-start --sync gate (state-sync-loop Phase 1)
- **What:** Rewired `.claude/commands/log-work.md` so the agent no longer hand-edits the brain
  cache doc's focus line/`synced_from` watermark or hand-regenerates the tier rollup table — those
  two former manual steps (old Steps 3–4) collapsed into one new Step 3 ("Regenerate derived
  surfaces") that shells out to `mev emit-state --write`, whose description now accurately lists
  every surface the engine regenerates per `core/mev/docs/cli.md` (leaf/brain `state.json` focus +
  rollup, per-project cache `synced_from`, tier-rollup tables, HQ Operating Board, master-plan wave
  tables). The header/Execution-Model over-claim ("`/log-work` writes the freshness spine") is gone
  — reframed as authored state in, `emit-state` derives out. The one surviving manual edit (`_root`
  repos' `README.md` Quick Status — no `generated:` sentinel exists for it) is kept as Step 3b with
  the reason stated. Added a new Step 3.5 to `.claude/commands/prime.md`: a read-only
  `mev validate-brain --sync` gate that surfaces stale projects and *offers* (never auto-runs) the
  reconciling `mev emit-state --write`, degrading gracefully with no `mev`/`brain.toml`; the
  `/prime` summary gained a Freshness line. Reviewed PASS on attempt 1 (all acceptance criteria
  met); all four SDLC engines `node --check` clean. Documentation stage failed (blocked on the
  review report path) — no doc patches applied this run.
- **Why:** Closes Part 3 of the state-sync-loop initiative in base-template — `/log-work` was
  over-claiming ownership of surfaces `mev emit-state` now derives, and there was no session-start
  signal for brain/cache drift. mev's `MV.4.E` (merged PR #18) made this rewire safe to land against
  real generated-surface behavior rather than a design still in flight.
- **Refs:** `.claude/commands/log-work.md`, `.claude/commands/prime.md`,
  `planning/bt-1-b-log-work-sync-rewire/` (spec + reports). Next: BT.1.C (propagate downstream).

```
716a0b9 feat: implement bt-1-b-log-work-sync-rewire
8e82443 chore: add spec for bt-1-b-log-work-sync-rewire
208008f docs: handoff — BT.1.B unblocked (mev MV.4.E closed)
74abab7 feat(BT.1.A): authoring completeness for state-sync-loop
7ec6826 chore(state): register BT.1.A/B (authoring completeness + log-work/session-start rewire)
```

### BT.1.A — authoring completeness (state-sync-loop Phase 1)
- **What:** `/ticket` now registers its own block in `planning/state.json` (mirroring `/chore`'s
  `<Prefix>.ticket.<slug>` convention). `/start-block` flips the matching `state.json` block status
  `open` → `in_progress` alongside `status.md`. `/generate-master-plan`, `/plan`, and `/chore` each
  gained an explicit cross-repo-edge prompt — asking whether a block depends on another repo before
  defaulting `depends_on` to same-repo/empty. `/update-state`'s Purpose section now lists `/plan`,
  `/chore`, `/ticket`, `/start-block` among the callers. Edited
  `.claude/commands/{ticket,start-block,chore,plan,generate-master-plan,update-state}.md` and synced
  all six `.agents/skills/*/SKILL.md` mirrors byte-for-byte. Flipped BT.1.A to `closed` in
  `planning/state.json` (hand-adjusted `focus.next` since `mev emit-state --write`'s derivation isn't
  implemented yet).
- **Why:** Closes the authoring-completeness gap in the state-sync-loop initiative — planning
  commands were creating state.json entries inconsistently (or not flipping status on start), which
  let block state drift from status.md. BT.1.B (rewiring canonical `/log-work`) remains blocked on
  mev's MV.4.E, unaffected by this block.
- **Refs:** `planning/state.json` (BT.1.A closed, BT.1.B still open/blocked on MV.4.E)

### Handoff written — BT.1.B discovered unblocked (mev MV.4.E closed), status.md/state.json corrected
- **What:** Wrote `planning/handoff.md` for the next session, pointing at BT.1.B (rewire canonical
  `/log-work` + session-start `--sync` gate) as the next block. While drafting it, discovered mev's
  `MV.4.E` — the block BT.1.B was recorded as blocked on — closed earlier today in a concurrent mev
  session (`4.E-emit-state-wiring`), so BT.1.B's authored dependency is now met. Corrected
  `planning/status.md`'s `next`/`blocked` frontmatter fields and body prose accordingly (BT.1.B no
  longer listed as blocked). Added a carryover entry `bt-1-b-mev-pr-unmerged` to `planning/state.json`
  flagging that mev's PR #18 (the actual `4.E` shipment) was still open/unmerged at the time of this
  session — clears once confirmed merged. Separately reviewed and committed a legitimate brain-wide
  `mev emit-state --write` refresh (`core/planning/state.json`, `core/planning/status.md`,
  `core/docs/projects/mev.md`) in the brain repo, reflecting mev's real, already-committed closure of
  `MV.4.E`; deliberately left unrelated pre-existing uncommitted brain-root work (a company-name-search
  thread, an in-progress learn-ai visual-redesign cache update) untouched.
- **Why:** A stale "blocked" status would have sent the next session down a wait-and-check-again path
  instead of straight into BT.1.B; catching the mev-side closure now (rather than after another
  needless blocked-check) keeps the state-sync-loop initiative moving. The mev PR-unmerged caveat
  prevents BT.1.B's spec from being written against a shipment that isn't actually on mev's `main` yet.
- **Refs:** `planning/handoff.md`, `planning/status.md` (`next`/`blocked` corrected), `planning/state.json`
  (carryover `bt-1-b-mev-pr-unmerged` added)

## [2026-07-03]

### D49 — /close-out code review and worktree cleanup options
- **What:** Modified `.claude/commands/close-out.md` and `.agents/skills/close-out/SKILL.md` to support customizable code review (`Step 2.5`) and opt-in worktree cleanup (`Step 5`). Added `--no-review` and `--review-level <level>` (default: `low`) to customize or bypass the `/code-review` invocation, and added `--clean-worktree` to fast-forward merge the current worktree/branch and remove it at the end of the close-out session. Updated `.claude/commands/README.md` to document the new parameters.
- **Why:** Code reviews and worktree cleanup are fundamental quality and hygiene steps at the end of implementation. Integrating them directly into `/close-out` makes the workflow more seamless while maintaining safety (the cleanup remains opt-in to protect the "never auto-merge" rule).
- **Refs:** `planning/decisions/D49-close-out-review-and-clean-worktree-options.md`

## [2026-07-02]

### D48 — scripts/sync_downstream_harness.py — automate the manual "update loop"
- **What:** `bastion` generated a spec with the exact D44 bug *after* D44 was already committed
  (11:21:37 vs D44's 10:31:49) — confirming nothing propagates a base-template harness fix into
  downstream repos automatically, and `.claude/workflows/*.js` (the SDLC engines) has no
  global-install path the way `.claude/commands/*.md` does via `/sync-global-commands`. Built
  `scripts/sync_downstream_harness.py`: discovers every repo via `brain.toml`, copies changed
  `.claude/commands/*.md` (flat, never `brain/`) + `.claude/workflows/` files into each one that
  already has its own `.claude/workflows/` directory, never deletes a repo's own customizations,
  and stamps `planning/.template-version`. Dry-run by default. Ran it: 9 repos updated + committed
  (bastion, orchestrator, mev, bastion-ui, bella, amistad, price-scout, learn-ai,
  client-repo); 3 portfolio-tier Rust repos gitignore `.claude/`/`planning/` entirely by
  design (D8) — updated locally, nothing to commit there. Converted bastion's affected
  `13.1-persistent-agent-panel` spec (still `Not started`) to the corrected `tasks.json` contract
  in a follow-up commit; swept every other repo's specs for the same broken pattern — nothing else
  found.
- **Why:** The "update loop" in `docs/using-the-template.md` was fully manual and, in practice,
  never run — every repo's `.template-version` was six days stale. A fix that only lives in
  base-template isn't actually fixed anywhere real work happens.
- **Refs:** `planning/decisions/D48-downstream-harness-sync-script.md`

---

### D47 — .agents/skills/ cleanup — mirror gaps, dead scripts, a copy-paste sync bug
- **What:** Audited everything still sitting untracked after D44–D46. Regenerated `backlog-ticket`'s
  stale `SKILL.md` mirror (it was missing a whole step its `.claude/commands/` counterpart already
  had). Added missing `.claude/commands/sync-brain-skills.md` + `sync-global-skills.md` sources —
  both skills existed only under `.agents/skills/` with no Claude Code-visible counterpart, same
  gap class as `write-lesson`. Fixed `sync-brain-skills`'s rsync include-list: three entries
  (`log-decision`, `sync-status`, `update-progress`) were copied from the brain repo's analogous
  `sync-brain-commands.md` list but don't exist anywhere in base-template — silently matched
  nothing. Deleted `add_state_tasks.py` and `update_planners.py`: these were the actual scripts
  that generated the `### <BlockID>.N` headings and full-array `state.json` sections D44–D46 just
  fixed, and both guard on marker text that no longer exists post-fix — re-running either today
  would re-introduce the bug. Refreshed `.agents/skills/README.md` for `tasks.json`.
- **Why:** Same instinct as D44–D46 — don't leave a known-stale or known-dangerous artifact lying
  around just because it wasn't the file directly asked about.
- **Refs:** `planning/decisions/D47-agent-skills-cleanup.md`

---

### D46 — tasks.json propagated to chore/plan/ticket; state.json tasks field corrected to a pointer
- **What:** Verified D44/D45's `tasks.json` shape against `core/orchestrator/docs/sdlc-flow-
  workflow.md` (matched, once D45 landed) then audited the rest of the commit family the user
  flagged. Found the same `### <BlockID>.N` heading break already **committed** — not uncommitted
  WIP — in `chore.md` and `ticket.md` (commit `610a4d9`), plus a block-level twin in `plan.md`
  (`### Block <Prefix>.<Phase>.<Letter>` breaks `sdlc-block.js`'s single-letter block parser,
  confirmed still unchanged there). Propagated the D44/D45 `tasks.json` contract to `chore.md` and
  `ticket.md`; reverted `plan.md`'s block heading to a bare letter, moving the canonical
  `<Prefix>.<Phase>.<Letter>` id into a `**Block ID:**` body bullet instead, and fixed a duplicate-
  numbered step plus the Report's block-selector example. Redesigned `state.json`'s
  `tracks[].blocks[].tasks` (`core/planning/state-schema.md`, brain repo) from a full duplicate task
  array into a derived `{file, generated, counts}` pointer + status summary; updated every planning
  command's state-registration section (`chore`, `plan`, `ticket`, `generate-tasks`,
  `generate-master-plan`, `handoff`) to stop hand-authoring it.
- **Why:** Same root cause as D44 — a contract changed without checking every consumer.
  `state.json` duplicating the full task list would have created two sources of truth for the same
  content; a pointer + summary keeps `tasks.json` the only place a task's real content lives.
- **Refs:** `planning/decisions/D46-tasks-json-propagation-and-state-pointer.md`

---

### D45 — tasks.json shape aligned to orchestrator's shipped SDLCTask schema
- **What:** D44 designed `tasks.json` from base-template's side only. Checked it against
  `core/orchestrator/app/schemas/sdlc_schema.py` (`SDLC_FLOW`'s already-shipped, tested task
  schema) and found real, structural mismatches — D44 wrapped the array in `{"tasks": [...]}`,
  `SDLCTask` expects a bare array; D44 used `id`, `SDLCTask` uses `task_id`; D44 used an `actions`
  array, `SDLCTask` requires a single `description` string. Corrected `tasks.json` to match
  `SDLCTask` field-for-field, keeping `files`/`dependsOn` as two harmless additive fields (Pydantic
  v2's default `extra='ignore'`, confirmed by reading the model — no `model_config` override).
  Marked D44 `superseded` (shape only; the move off heading-regex parsing stands). Updated all four
  `sdlc-*.js` engines + `generate-tasks.md` + `spec-template.md` to match.
- **Why:** A second, independently-shipped implementation of the same pipeline already existed and
  the two were supposed to be interoperable ("both consume the same kind of task list," per
  orchestrator's own docs) — inventing a shape without checking is the same mistake D44 fixed, one
  level up.
- **Refs:** `planning/decisions/D45-tasks-json-orchestrator-schema-alignment.md`

---

### D44 — tasks.json replaces markdown heading regex as the task-list contract
- **What:** Found an uncommitted, undocumented drift in `generate-tasks.md` (task headings changed
  from `### N.` to `### <BlockID>.<N>`) that had already leaked into global `~/.claude/commands/`
  via `/sync-global-commands` and silently broken the D16 preflight lint in mev/bastion (one spec
  hand-patched back in a standalone fix commit, four others never run through the strict engines at
  all). Root-caused and fixed properly: the per-spec task list now lives in a structured
  `planning/<spec>/tasks.json` (`{id, title, actions, files, dependsOn}`) that all four SDLC engines
  (`sdlc-flow.js`, `sdlc-run.js`, `sdlc-task.js`, `sdlc-block.js`) read directly — no heading regex
  anywhere in the pipeline. `tasks.md` keeps only prose (Goal, Context Pointers, Acceptance
  Criteria, Validation Commands, Notes, Amendment Log). Updated `generate-tasks.md` (+ its
  `.agents/skills` mirror) and `spec-template.md` to author both files. `sdlc-flow.js` also drops
  its now-redundant "mark task in-progress via tasks.md checkbox" stage (that signal already lives
  in the committed `sdlc-flow-state.json`).
- **Why:** A markdown heading convention is not a real contract — nothing enforced that spec
  authoring and the four independent engines agreed on the exact regex shape, so they silently drifted apart. JSON parsing either succeeds or the D16 abort fires with an unambiguous reason.
- **Refs:** `planning/decisions/D44-tasks-json-task-list.md`

---

## [2026-06-30]

### Sub-brain specific .agents/ skills sync
- **What:** Modified `sync_skills.py` to automatically discover sub-brain tiers from `brain.toml` and sync their `.claude/commands` to `<tier>/.agents/skills/` (the plural format expected by the Gemini Agent workspace customizations). Removed all singular `.agent/` custom skill directories from the project and removed singular `.agent` folder sync operations from `sync_skills.py`. Unified `prime.md` and `handoff.md` to dynamically support both HQ and sub-brain scopes based on local files and CWD.
- **Why:** Ensures that each sub-brain tier has its own local, tier-specific `.agents/skills` customization directory (e.g. tier-specific `/prime` skill logic) so they run in their own local contexts without falling back to HQ's global commands or crashing.

---

## [2026-06-29]

### plan-create-global-commands complete
- **What:** Reverted `scaffold/CLAUDE.md` commands table from `<dir>:<name>` subdirectory format back to plain `/<name>` flat format. Block D (downstream CLAUDE.md sweep) declared obsolete — the subdirectory naming convention was abandoned before the sweep ran, so only the scaffold needed fixing. Marked the effort complete in `planning/status.md` and `planning/plan-create-global-commands/plan.md`.
- **Why:** Commands were flattened back to root-level global install; the `<dir>:<name>` format was never propagated downstream, making Block D a no-op.
- **Refs:** `planning/plan-create-global-commands/plan.md`

---

### Block C — Brain command reorganization
- **What:** Reorganized brain `.claude/commands/` flat list into `shared/` + `hq/` subdirectories; created `sync-brain-commands.md`; bootstrapped all 4 sub-brains (core, side, client, portfolio) with `session/`, `planning/`, `projects/` command sets; updated `/new-project` with `--include-commands` flag; updated `/generate-sub-brain` with shared command bootstrap step; updated brain `CLAUDE.md` with namespaced command names + Available Globally section.
- **Why:** Block C is part of the gc-global-commands initiative to restructure brain commands into `shared/` + `hq/` subdirs and distribute shared commands to all sub-brain tiers, completing the brain-side reorganization before Block D's downstream sweep.
- **Refs:** `planning/plan-create-global-commands/plan.md`; `planning/gc-blockC-new-project/tasks.md`

---

### Block B complete (trim scaffold + update docs)
- **What:** Block B of plan-create-global-commands executed (5/5 tasks): deleted 3 redundant scaffold command stubs, added "Available Commands" listing to `scaffold/CLAUDE.md`, updated `docs/using-the-template.md` and `README.md` to reflect the global-commands model. Block C (brain repo reorganization) handed off to a separate brain session.
- **Why:** Block B completes the base-template side of the migration — scaffold no longer ships per-repo command copies for commands that live globally.
- **Refs:** `scaffold/CLAUDE.md`, `docs/using-the-template.md`, `README.md`, `planning/gc-blockB-trim-scaffold/`

---

### Block A complete (global commands install) + capture fix in brain + prime title updates
- **What:** Block A of plan-create-global-commands executed: git mv'd all 34 flat `.claude/commands/` files into `session/`, `planning/`, `sdlc/`, `git/` subdirs; populated `brain/` reference dir (28 brain commands, capture excluded from `shared/session/`); created `sync-global-commands.md`; ran initial global install to `~/.claude/commands/`; updated `commands/README.md` and plan file. Fixed `/capture` command in brain repo (`agentic-portfolio/.claude/commands/capture.md`) — old version wrote backlog to CWD-relative path with no brain.toml walk-up; updated to match harness version so it always routes to HQ backlog. Fixed Block A spec: removed `capture.md` from `brain/shared/session/` copy list, updated AC count 29→28. Updated `/prime` titles: `session/prime.md` → "Deep orient to the current project"; `brain/prime.md` + `brain/shared/session/prime.md` → "Orient to the full company brain (HQ + all tiers)". Reverted `session-recap.md` rename (would conflict with Claude Code built-in `/recap`).
- **Why:** Block A is the first execution block of the global-commands migration — establishes the subdirectory structure and performs the initial install to `~/.claude/commands/`. Capture fix ensures the brain HQ command routes correctly regardless of CWD.
- **Refs:** `.claude/commands/` (reorganized), `planning/plan-create-global-commands/plan.md`, `planning/gc-blockA-sync-command/tasks.md`

---

### Global-commands migration replanned — all 4 block specs (A/B/C revised + Block D) rewritten and ready to execute
- **What:** Settled the global-commands migration design: subdirectory structure for `~/.claude/commands/`, brain/sub-brain command model, `/capture` behavior, naming convention, and `(global)` tag protocol. Rewrote all four block specs — Blocks A/B/C revised and a new Block D added for downstream sweep. All specs committed and ready to execute.
- **Why:** Earlier specs had ambiguities around naming, the sub-brain command model, and capture behavior that needed resolution before execution to avoid rework.
- **Refs:** `planning/plan-create-global-commands/plan.md`, `planning/gc-blockA-sync-command/tasks.md`, `planning/gc-blockB-trim-scaffold/tasks.md`, `planning/gc-blockC-new-project/tasks.md`

---

## [2026-06-28]

### Per-block specs (A/B/C) generated for global-commands migration + 8 HQ commands copied into core/ + side/ sub-brains
- **What:** Generated per-block task specs (A/B/C) for the global-commands migration and copied 8 tier-scoped HQ commands into the core/ and side/ sub-brains. Wrote handoff for Block A execution. Concretely: (1) Generated 3 per-block task specs for `plan-create-global-commands`, each in its own slug-dir (independent runs would collide on a shared `tasks.md`): `planning/gc-blockA-sync-command/tasks.md`, `planning/gc-blockB-trim-scaffold/tasks.md`, `planning/gc-blockC-new-project/tasks.md`; registered all three in `planning/index.md`. Model recommendation: Sonnet for all three; each runs as a lean `/sdlc-task`; none flagged for `/breakdown`. (Committed 70e9cd4.) (2) Copied 8 HQ commands into `core/.claude/commands/` + `side/.claude/commands/` (byte-identical) in the BRAIN repo (`agentic-portfolio/`, committed separately there), with a README index. Adaptations: `prime` rewritten tier-scoped; `log-work` given tier-root mode (tier roots aren't registered `[[repos]]` in `brain.toml`); `generate-master-plan` tier-prefixed RAG path; `handoff` resume-dir fix; `session-recap` cosmetic; `archive`/`commit`/`wrap-up` verbatim. Each carries a TEMP banner (pending the global-commands migration). (3) Wrote `planning/handoff.md` pointing at Block A execution (`/sdlc-task gc-blockA-sync-command`).
- **Why:** User wanted runnable per-block specs for the global-commands work, plus the 8 sub-brain commands copied into core/ and side/ now ("easier to copy them in while I wait for this work to finish").
- **Refs:** `planning/plan-create-global-commands/plan.md`, `planning/handoff.md`

---

## [2026-06-27]

### Plan: global ~/.claude/commands/ migration authored (plan-create-global-commands)
- **What:** Authored the `plan-create-global-commands` mini-roadmap (2 phases, 3 blocks) for migrating all 34 universal SDLC commands to `~/.claude/commands/` globally. Block A = `/sync-global-commands` command + initial install; Block B = trim `scaffold/.claude/commands/`; Block C (brain repo) = `/new-project` engines-only default + delete 9 brain duplicate commands. Also clarified sub-brain command model (currently empty, inherit global) and confirmed `~/.claude/workflows/` not recommended as global location.
- **Why:** Reduce per-project command duplication — all 34 universal SDLC commands repeat in every downstream repo; a single global install eliminates the copy and keeps them in sync.
- **Refs:** planning/plan-create-global-commands/plan.md

---

## 2026-06-26 — Wave 5 downstream propagation complete

Completed Wave 5 downstream propagation of the SDLC engines + planner surface redesign to all five downstream projects (bastion, bella, markdown-engine-validator, price-scout, amistad). Each repo now carries the full harness through Phase 3 C: committed state + token telemetry (D37), lean `/sdlc-task` + `/patch` ladder (D38), block-level `/sdlc-block` orchestrator (D39), branch-train + PR model (D40), restructured planner (D41–D42), and `/close-out` integration (D43). Cross-repo coordination tracked in `planning/handoff.md`. All four engines `node --check` clean across all repos. Brain-level `/new-project` rewrite to call `/generate-master-plan` (D34 follow-up) also complete.

```diff
 planning/handoff.md | 63 ++++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 63 insertions(+), 60 deletions(-)
```

---

## 2026-06-26 — Phase 3 B: Workflow + command docs rewrite — redesign master-plan complete

Phase 3 Block B of the SDLC engines + planner surface redesign master-plan. Final block.

**Full rewrites:**
- `docs/workflows/sdlc-block.md` — block-level roadmap orchestrator (was task-wave machine)
- `docs/workflows/sdlc-task.md` — lean implement→test→fix→commit engine (was full pipeline)

**Targeted updates:**
- `docs/workflows/sdlc-run.md` — committed `sdlc-run-state.json`; removed stale back-half refs
- `docs/workflows/sdlc-flow.md` — `tokens` block added to state description; engine ladder updated
- `docs/workflows/index.md` — new engine ladder, updated mermaid, committed-state model table
- `docs/workflows/commands.md` — `/feature` replaced with `/ticket`; updated ad-hoc routes
- `docs/index.md` — sdlc-block/sdlc-task descriptions updated; ADR range D1–D43
- `docs/harness-json.md` — `block` object rewritten (`maxParallelBlocks`/`autoMerge`); `count-delta`
  caveat note added; stale `/feature` + `--under-block` refs removed
- `.claude/commands/README.md` — `/close-out` description updated (4 steps, `--gap-check-only`)

**Dead-link sweep clean:** `execution-plan.json`, `--from test` (back-half), `--verify-depth`,
`block.verify`, `/feature`, `sdlc-block-state.json`, `sdlc-state.json` — all removed.

**`.agents/` mirrors frozen** — D4 addendum documents that `.agents/skills/` is frozen at
current state; not updated, not shipped, not maintained in lockstep. Separate from `.claude/`.

All four engines `node --check` clean. The SDLC engines + planner surface redesign master-plan
is now complete in `base-template`. Downstream propagation (Wave 5) is next.

---

## 2026-06-26 — Phase 3 C: Schema + scaffold + harness config finalized

Phase 3 Block C of the SDLC engines + planner surface redesign master-plan.

- **`harness.schema.json` `block.*` rewrite:** dropped `verify` (lean-block era, superseded by D39);
  added `autoMerge` (boolean, default false — whether to skip PRs and merge into train automatically)
  and `maxParallelBlocks` (integer, default 3 — concurrent block cap per wave). Description updated to
  describe the block-level orchestrator model (D39/D40).
- **`scaffold/planning/harness.json`:** added `"block": { "maxParallelBlocks": 3 }` stanza; `_comment`
  already referenced this key from Phase 2 code-review fixes — now the JSON matches the comment.
- **`scaffold/planning/harness.examples.md`:** added "Optional: `/sdlc-block` policy (`block` block)"
  section with the `maxParallelBlocks`/`autoMerge` key-by-key table, placed before the existing `flow`
  section.
- **`.gitignore`:** removed the D28 `planning/*/sdlc/sdlc-block-state.json` gitignore line (D28
  superseded by D39); replaced the stale D28 + D27 NOTE with a clean note that all four SDLC state
  files are now intentionally committed authoritative state (D37).
- **`planning/harness.json`:** added `sdlc-flow.js` to the `engines-parse` gating command —
  all four engines now validated, not three. All four engines `node --check` clean.

---

## 2026-06-26 — Phase 3 A: ADRs D37–D43 authored

Phase 3 Block A of the SDLC engines + planner surface redesign master-plan
(`planning/sdlc-block-and-task-updates/plan.md`). Authored 7 atomic ADRs recording every
keep/drop/behavioral decision from Phases 0–2:

- **D37** — Unified committed state + token telemetry across all four engines (supersedes D27;
  extends D12/D15). "Substantive-stages-only" token contract documented.
- **D38** — Lean `/sdlc-task` rewrite (2 126 → ~740 lines; deleted heavy stages + coupling flags)
  + `/patch` 3-rung scope-gate ladder.
- **D39** — `/sdlc-block` rewritten as a block-level roadmap orchestrator (supersedes D22/D23/D24/D28;
  realizes D30). `enumerate-blocks`, `computeWaves` at block granularity, per-block `/sdlc-flow`,
  branch-train merge. `execution-plan.schema.json` deleted.
- **D40** — Branch-train + PR model; `/review-PR` (spec-aware `gh pr review`) and `/merge-train`
  (dependency-ordered bottom-up merge with CONFLICTING-halt).
- **D41** — Planner restructure (extends D34): `/plan` → master-plan format, `/feature` removed,
  `/ticket` added (behavior-change + AC + Testing Strategy → lean `/sdlc-task`), `/chore` routed
  to lean `/sdlc-task`.
- **D42** — Four-engine recommendation ladder + plan-file block addressing in `/generate-tasks`
  (supersedes D21; extends D34). Step 11 rewritten as five-rung ladder; step 12 deleted;
  `--from <plan-file> phaseN-blockX` added. `/generate-master-plan` gains `Depends on` + ordering note.
- **D43** — `/close-out` integration: `--gap-check-only` flag, per-block gap-check in `sdlc-block`,
  final close-out on train branch, `/close-out` recommendation in `sdlc-flow` + `sdlc-run` end reports.

`planning/decisions/index.md` updated with D37–D43 entries. `planning/status.md` updated.
Next: Phase 3 B (docs rewrite) and Phase 3 C (schema + scaffold finalization).

---

## 2026-06-26 — Phase 2 code-review fixes: 6 findings patched

Medium-effort `/code-review` over the Phase 2 diff (prompt-only planner changes spanning `.claude/commands/` + `.agents/skills/` mirrors) surfaced 4 CONFIRMED + 2 PLAUSIBLE findings; all six fixed. (1) **scaffold/planning/harness.json** — removed the dead `block.verify` stanza (legacy `"block": {"verify": "consolidated"}` from D24, removed in Phase 1 rewrite; was dangling in scaffold). Removed matching `_comment` + updated to reference `block.maxParallelBlocks` instead. (2) **ticket.md + ticket SKILL.md Report** — unified `{name}` variable to `{slug}` (steps 5–6 emit the same placeholder twice for consistency; `{name}` was wrong). (3) **chore SKILL.md frontmatter** — wrapped to standard 6 lines so `tail -n +8` mirror-sync extraction works correctly (was breaking the body on output; the command's 6-line header must be byte-identical). (4) **commands/README.md** — `/ticket` added to the "Ad-hoc planners" section heading (was missing despite the full `/ticket` command being shipped in Phase 2 B). (5) **generate-tasks.md + generate-tasks SKILL.md step 11** — clarified that in slug mode (calling `/generate-tasks --from <plan-file>` with a selected block), the `<plan-file>` default is `planning/master-plan.md` (was ambiguous). (6) **generate-master-plan.md + generate-master-plan SKILL.md Depends-on skeleton** — reworded the placeholder line to "omit this line entirely" instruction format (prevents LLM from emitting the placeholder `- **Depends on:** Block <id>` literally when no dependency exists). All four engines `node --check` clean. Phase 3 (ADRs D37+, docs rewrite, schema/scaffold finalization) is next.

```diff
 .agents/skills/chore/SKILL.md                |   3 +-
 .agents/skills/generate-master-plan/SKILL.md |   3 +-
 .agents/skills/generate-tasks/SKILL.md       |   3 +-
 .agents/skills/ticket/SKILL.md               |   4 +-
 .claude/commands/README.md                   |   2 +-
 .claude/commands/generate-master-plan.md     |   3 +-
 .claude/commands/generate-tasks.md           |   3 +-
 .claude/commands/ticket.md                   |   4 +-
 planning/handoff.md                          | 159 +++++++++++++--------------
 scaffold/planning/harness.json               |   5 +-
 10 files changed, 89 insertions(+), 100 deletions(-)
```

---

## 2026-06-25 — Phase 2 C complete: /generate-tasks four-engine ladder + plan-file block addressing, /generate-master-plan `Depends on` + default-order note

Phase 2 C — the last Phase-2 block (planner + routing surface) — is done, prompt-only (no engine JS). Three changes plus mirror sync:

- **`/generate-tasks` step 11 rewrite to the four-engine ladder.** The stale step 11 described `/sdlc-block` as a *lean per-task* runner (the Plan-F3 repurposing that Phase 1 A replaced) and referenced the deleted `--verify-depth`/`block.verify` flags. Rewrote it as an escalating-ceremony ladder — `/patch` → lean `/sdlc-task <slug> [range]` → `/sdlc-run` / `/sdlc-flow` → `/sdlc-block <plan-file>` — with `/sdlc-block` correctly framed as the rung *above* a single spec (a multi-block roadmap orchestrator that fans out one `/sdlc-flow` per block as a branch train of PRs, reviewed with `/review-PR` + `/merge-train`). Removed the `--verify-depth consolidated+review` subsection entirely. Updated the Report's Pipeline-recommendation example to match.
- **Plan-file block addressing in `--from` mode.** `/plan` (Phase 2 A) now emits master-plan format (multiple `### Block X`), but `--from` treated the whole file as one standalone block. Extended `--from <path> [phaseN-blockX]`: a single standalone block file (legacy D34) is decomposed whole; a master-plan-format file reads ONLY the selected block's section; multi-block with no selector STOPs and asks (plan-quality floor), pointing at `/sdlc-block <path>` for the whole roadmap. Output stays in the plan file's parent dir so `/sdlc-flow <slug>` resolves it — matching `/plan`'s Report.
- **`/generate-master-plan` `Depends on` + default ordering.** Added the optional `- **Depends on:** Block <id>` line to the block skeleton (Block Contract + concrete example) and a "phases sequential, blocks within a phase parallel" default-order paragraph, matching what `sdlc-block.js`'s `enumerate-blocks` actually reads (bare `Block A` = same phase; `phaseN-blockA` accepted).
- **Mirror sync.** Re-synced the badly-stale `.agents/skills/generate-tasks/SKILL.md` (it predated both D34's `--from` mode and all of Phase 2) to a faithful copy of the command. Created `.agents/skills/generate-master-plan/SKILL.md`, which never existed (a D34 oversight) — built for parity with the active mirror set. Both mirror bodies are byte-identical to their commands. (The broader `.agents/` keep-or-freeze question is deferred to Phase 3 B.)

Step 12 (the orphaned `execution-plan.json` authoring) was already removed in `f6e800f` during the Phase 1 code-review remediation — confirmed grep-clean, nothing to re-remove. Validation: all four engines `node --check` clean (unchanged — prompt-only); `execution-plan` and `verify-depth` grep-clean in `generate-tasks.md` + mirror. **Phase 2 complete (A/B/C). Next: Phase 3 A (ADRs start at D37) / B (docs) / C (schema + scaffold).**

```diff
 .agents/skills/generate-master-plan/SKILL.md |  +new (mirror)
 .agents/skills/generate-tasks/SKILL.md       |  re-synced to command
 .claude/commands/generate-master-plan.md     |  +Depends on line + default-order note
 .claude/commands/generate-tasks.md           |  step 11 ladder rewrite + --from block addressing
 planning/handoff.md                          |  -consumed
```

---

## 2026-06-25 — Phase 2 A/B complete: /plan rewritten to mini-roadmap format, /feature removed, /ticket added, /chore wired to lean /sdlc-task

Phase 2 A delivered a complete rewrite of the `/plan` command to produce master-plan format (phases/blocks/Quick Reference table) into `planning/plan-<slug>/plan.md`. The new `/plan` routes multi-block efforts via `/sdlc-block <path>` or single standalone blocks via `/generate-tasks --from <path>` + `/sdlc-flow`, while retaining D20 clarify gate, D35 plan-quality floor, and D19 property self-check. Removed `/feature` command entirely; cleaned all cross-references. Phase 2 B added a new `/ticket` command for single-block behavior-change planning with observable Acceptance Criteria + Testing Strategy, routed to lean `/sdlc-task ticket-{name}`. Updated `/chore` command + mirror to recommend `/sdlc-task chore-{name}` in the Report instead of `/patch`, solidifying the distinction: `/chore` for work that doesn't *change observable behavior* (refactoring, docs, cleanup), `/ticket` for work that does. Updated `README.md` with `/ticket` row in the ad-hoc planning table and clarified the `/chore` vs `/ticket` distinction. All four engines `node --check` clean.

```diff
 .agents/skills/chore/SKILL.md              |    9 +-
 .agents/skills/feature/SKILL.md            |  149 -
 .agents/skills/generate-tasks/SKILL.md     |    2 +-
 .agents/skills/plan/SKILL.md               |  230 +++++++++++++---------
 .agents/skills/ticket/SKILL.md             |  127 ++++++++++++
 .claude/commands/README.md                 |   39 ++-
 .claude/commands/chore.md                  |    9 +-
 .claude/commands/conditional_docs.md       |    2 +-
 .claude/commands/feature.md                |  143 -
 .claude/commands/plan.md                   |  243 ++++++++++++----------
 .claude/commands/ticket.md                 |  120 +++++++++++
 .claude/workflows/harness.schema.json      |    2 +-
 planning/handoff.md                        |   64 -
 scaffold/.claude/commands/conditional_docs.md |    2 +-
 scaffold/planning/harness.json             |    2 +-
 16 files changed, 526 insertions(+), 617 deletions(-)
```

---

## 2026-06-25 — Phase 1 A/B/C /code-review: workflow-backed high-effort audit (43 agents) surfaced 8 CONFIRMED + 2 PLAUSIBLE findings; all 10 fixed across sdlc-block.js, /review-PR, /generate-tasks, command + skill docs

Ran a workflow-backed `/code-review` at high effort over the full Phase 1 diff (commit range 80638e9..HEAD), spanning Phase 1 A (block-orchestrator rewrite of sdlc-block.js), Phase 1 B (/review-PR + /merge-train commands), and Phase 1 C (/close-out integration + per-block gap-check). The review (43 agents, run wf_d56efc19-0a0) surfaced 8 verified CONFIRMED findings plus 2 PLAUSIBLE findings. Fixed all 10 findings across the codebase: #1 `gapCheckBlock()` now diffs the whole block (`<train>...HEAD`) for the emoji gate + coverage scan, not `HEAD^` which saw only the last commit and was neutering Phase 1 C's gap-check gate; #2 budget guards now use `typeof budget !== 'undefined' && budget.total` to avoid ReferenceError on startup; #3 state key renamed `base` → `base_branch` to match what `/merge-train` + `/review-PR` read (was a producer/consumer mismatch); #4 removed the dangling `execution-plan.json` / deleted-schema authoring step from `generate-tasks.md` step 12 + skill mirror, and cleaned every now-false reference (README ×2, plan.md, generate-tasks.md cross-ref, sdlc-run.js comment, docs/architecture.md, docs/using-the-template.md, scaffold/planning/index.md); #5 rewrote `.agents/skills/sdlc-block/SKILL.md` to match the branch-train orchestrator model (was the legacy task-wave model); corrected the matching stale `/sdlc-block` section in `commands/README.md`; #6 report child-token table + count now derived from committed `state.blocks[].tokensTotal` so resumed blocks are counted (was undercounting on `--resume`); #7 `/review-PR` now falls back to the spec's `## Validation Commands` when `harness.json` absent, and downgrades to COMMENT (never APPROVE) if no gating suite found; #8 `loadBlockConfig()` reads only `maxParallelBlocks`; dropped the dead `block.autoMerge` extraction; #9 `dependsOn` slugs lowercased before `slugToIndex` lookup (case-sensitivity bug); #10 per-block gap-check now runs for every passed block in ALL modes (was PR-mode-only); PR-open stays PR-mode-only. Bonus: added `/review-PR` + `/merge-train` to the `commands/README.md` catalog per CLAUDE.md rule 7. All four engines `node --check` clean. Deliberately deferred: harness.schema.json block.* finalization → Phase 3 C; docs/workflows/sdlc-block.md page rewrite → Phase 3 B.

```diff
 .agents/skills/generate-tasks/SKILL.md |  23 +-----
 .agents/skills/review-PR/SKILL.md      |  10 ++-
 .agents/skills/sdlc-block/SKILL.md     | 130 +++++++++++++++++----------------
 .claude/commands/README.md             |  61 ++++++++++------
 .claude/commands/generate-tasks.md     |  25 +------
 .claude/commands/plan.md               |   2 +-
 .claude/commands/review-PR.md          |  12 ++-
 .claude/workflows/sdlc-block.js        | 100 +++++++++++++++----------
 .claude/workflows/sdlc-run.js          |   2 +-
 docs/architecture.md                   |   2 +-
 docs/using-the-template.md             |   2 +-
 scaffold/planning/index.md             |   2 +-
 12 files changed, 196 insertions(+), 175 deletions(-)
```

---

## 2026-06-25 — Phase 1 C complete: `/close-out` integration into sdlc-block + recommendations in sdlc-flow/sdlc-run

Phase 1 C delivered the per-block gap-check integration before PR-open and final close-out on the train branch. Refactored `.claude/commands/close-out.md` and `.agents/skills/close-out/SKILL.md` to expose a `--gap-check-only` flag (Steps 1–3 only; skips Step 4 handoff). Existing behavior unchanged when flag is absent. Modified `.claude/workflows/sdlc-block.js`: changed `runBlockFlow` to always pass `--no-pr` to child sdlc-flow (so orchestrator can run per-block gap-check before opening PR); added `gapCheckBlock()` function running close-out gap-check in each block's worktree after PASS; added `openBlockPr()` function opening the GitHub PR from sdlc-block.js after gap-check (PR mode only); updated wave loop batch processing to run gap-check + PR-open in parallel for all passed blocks after each batch (PR mode only); added final close-out phase after REPORT invoking `/close-out --gap-check-only` on the train branch; added `GAP_CHECK_SCHEMA` and `BLOCK_PR_SCHEMA` schemas. Modified `.claude/workflows/sdlc-flow.js` and `.claude/workflows/sdlc-run.js`: added `/close-out` recommendation line after final log. Deleted `planning/handoff.md` (consumed). All four engines `node --check` clean.

```diff
 .agents/skills/merge-train/SKILL.md          |  223 +++
 .agents/skills/review-PR/SKILL.md            |  221 +++
 .claude/commands/merge-train.md              |  217 +++
 .claude/commands/patch.md                    |   35 +-
 .claude/commands/review-PR.md                |  215 +++
 .claude/workflows/execution-plan.schema.json |   54 -
 .claude/workflows/sdlc-block.js              | 2160 +++++++---------------
 .claude/workflows/sdlc-flow.js               |   34 +
 .claude/workflows/sdlc-run.js                |  149 +-
 .claude/workflows/sdlc-task.js               | 2501 +++++++-------------------
 .gitignore                                   |    8 +-
 log.md                                       |   69 +
 planning/handoff.md                          |  136 +-
 planning/sdlc-block-and-task-updates/plan.md |    4 +
 15 files changed, 2568 insertions(+), 3465 deletions(-)
```

---

## 2026-06-25 — Phase 1 Block B complete: `/review-PR` and `/merge-train` commands authored

Phase 1 B delivered two new prompt-only commands plus their `.agents/skills/` mirrors — no engine JS was changed. `/review-PR <PR#> [plan-slug]`: locates `block-orchestration-state.json` via `find planning`, resolves the block spec from the PR's head branch name, checks out the PR with `gh pr checkout`, runs the full `harness.json` gating suite plus an emoji gate (merge-base scoped so only the PR's own markdown changes are scanned), reviews `git diff baseRefName...HEAD` against the block's acceptance criteria, then posts a `gh pr review` verdict (APPROVE/REQUEST_CHANGES/COMMENT with a structured body: AC table + gating table + verdict paragraph) and restores the original branch. `/merge-train [plan-slug]`: reads `merge_order` and `mode` from state (exits early for `auto-merge`/`no-pr` modes), pre-flight cleans the tree and syncs base, classifies each block as ready/already-merged/needs-approval/has-conflicts/escalated, stops before any merge if any block has `CONFLICTING` mergeability, warns non-blocking on missing approval, confirms with the user, merges each PR via `gh pr merge --merge --delete-branch` in dependency order, pulls base after each success, and halts on failure with a resume-safe report (already-merged blocks are auto-detected on re-run). All four engines remain `node --check` clean. Next: Phase 1 C — `/close-out` integration.

```diff
 .agents/skills/merge-train/SKILL.md | 223 ++++++++++++++++++++++++++++++++++++
 .agents/skills/review-PR/SKILL.md   | 221 +++++++++++++++++++++++++++++++++++
 .claude/commands/merge-train.md     | 217 +++++++++++++++++++++++++++++++++++
 .claude/commands/review-PR.md       | 215 ++++++++++++++++++++++++++++++++++
 planning/handoff.md                 | 109 ------------------------------------------------
 planning/status.md                  |   3 +-
 6 files changed, 878 insertions(+), 110 deletions(-)
```

---

## 2026-06-25 — SDLC redesign Phase 1 Block A: block-level `/sdlc-block` orchestrator

Rewrote `sdlc-block.js` (1782 -> ~620 lines) from the legacy task-level wave machine into a block-level roadmap orchestrator. `enumerate-blocks` parses a master-plan-format file (default `planning/master-plan.md`, or a path/slug arg) into `phaseN-blockX` blocks + a dependency graph; blocks are keyed by an integer index in (phase, block-letter) order so `computeWaves` is reused byte-identical; phase-sequential ordering is synthesized (each block implicitly depends on all blocks of the previous distinct phase) and refined by explicit `- **Depends on:**` lines. Per wave the orchestrator ensures each `planning/<slug>/tasks.md` via an inline Opus agent mirroring `/generate-tasks` (the runtime cannot invoke a slash command through `workflow()`, which also yields plan-file addressing for free), then fans out one `workflow('sdlc-flow', '<slug> [--no-pr]')` per block (<= `--max-parallel-blocks`, default 3) over a branch train. Branch-train model: the orchestrator keeps a train branch checked out at the main root so child worktrees fork off it, and merges successful block branches in dependency order after each wave; `--auto-merge` lands blocks on `<base>` (no PRs), default opens one PR per block via the child flow and records `merge_order` for `/merge-train`, `--no-pr` produces branches only. Two-level committed `block-orchestration-state.json` rolls each child flow's `tokens.total` up alongside the orchestrator's own substantive stages. Deleted all legacy machinery (`runTaskInPlace`/`runTaskWorktree`/additive-union merge/`--from test` back-half/`--verify-depth`/`block.verify`/`snapshotBlockBaselines`/the D28 task-state/the execution-plan load) plus `execution-plan.schema.json`; grep-clean of every removed symbol. Resolved the three Phase-0 `/code-review` carry-ins: #1 token roll-up contract decided substantive-stages-only (user-confirmed) and documented identically above `buildTokensBlock()` in all four engines with the function body untouched (still byte-identical, md5 `77d955b3...`); #3 `sdlc-task.js` reuses `state.tokens` instead of rebuilding; #2 (count-delta doc note) left for Phase 3 B. All four engines `node --check` clean. Known transients left for later phases by plan design: `generate-tasks.md` step 12 still authors `execution-plan.json` (Phase 2 C), and `docs/workflows/*` + the `.gitignore` D28 line are still stale (Phase 3 B/C). ADR + `## Completed efforts` row deferred to Phase 3 A.

```diff
 .claude/workflows/sdlc-block.js | 2160 ++++++++++++---------------------------
 .claude/workflows/sdlc-flow.js  |    6 +
 .claude/workflows/sdlc-run.js   |    6 +
 .claude/workflows/sdlc-task.js  |    8 +-
 planning/status.md              |    3 +-
 5 files changed, 703 insertions(+), 1480 deletions(-)
```

---

## 2026-06-25 — Phase 0 `/code-review` complete (verdict: sound); 3 findings folded into Phase 1 A

Reviewed all of Phase 0 using `/code-review` (range `fb04309..HEAD`, high effort). Verdict: **sound** — no correctness bugs. Verified `buildTokensBlock()` is byte-identical across all three Phase-0 engines (`sdlc-run.js`/`sdlc-task.js`/`sdlc-flow.js`, same md5); the shared token contract that Phase 1 A builds on is intact. All four engines pass `node --check` clean; `sdlc-task.js` grep-clean of the four removed flags. Confirmed several intentional patterns are not bugs: the deleted stages/flags, the `count-delta` check degradation to plain-exit-code gates (schema enforces `command` so no runtime crash), untraced helper agents (consistent between engines), and the `recordPhaseState('wrap-up')`-before-wrap-up cadence (documented at `sdlc-run.js:1659–1662`). Three code-review findings survived: folded into Phase 1 A block definition as a new "Review carry-ins (Phase 0 `/code-review`, 2026-06-25)" subsection (token roll-up undercount that compounds in the two-level child roll-up under Phase 1 A; count-delta gating reduction doc note deferred to Phase 3 B; redundant `buildTokensBlock()` cleanup at sdlc-task.js:947+949). All three findings are not Phase-0 bugs — they are design decisions for the orchestrator to handle or doc to clarify, so they are scoped to Phase 1 A / Phase 3 B per the master-plan's phase structure. No ADRs authored this session (deferred to Phase 3 A). Wrote handoff for Phase 1 A implementation (Opus).

```diff
 planning/sdlc-block-and-task-updates/plan.md |   4 +
 planning/handoff.md                          | 160 ++++++++++++---------------
 2 files changed, 72 insertions(+), 92 deletions(-)
```

---

## 2026-06-25 — SDLC redesign Phase 0 Block B: lean `/sdlc-task` + `/patch` ladder

Implemented Block B — repositioned `/sdlc-task` as the cheap "small-work" rung of the pipeline ladder. Rewrote `.claude/workflows/sdlc-task.js` from 2126 lines down to ~740 (diff −1837/+699): the new lean pipeline is `setup → enumerate (D16 lint) → [resume load] → per-task loop → final state commit`, where the per-task loop is `implement → fast gating-test → triage → fix (≤3 attempts, Opus on the last) → commit` and nothing else. The loop plus `runTests({gatingOnly})`, `triage`, `BAIL_REASONS`, `renderCheckList`, and `snapshotBaselines` were lifted from `sdlc-flow.js` (engines are self-contained — lift, don't import). Deleted the whole heavy stage machine — scout, separate review, document, ui-test, wrap-up agent, breakdown assessment — and the coupling flags `--implement-only`/`--under-block`/`--parallel-wave`/`--review` (grep-clean). Isolation is now in-place on the current branch by default, with `--worktree` an opt-in for an isolated worktree/branch; kept `--resume`, optional task selection/range (defaults to all tasks, like `/sdlc-flow`), the D8 completeness self-check, the D19 thin-spec guard, and the D16 heading lint. Adopted the Block-A contract: a committed `sdlc-task-state.json` carrying the canonical `tokens` block via an identical lifted `buildTokensBlock()`. Commit cadence mirrors the family — `--worktree` commits each state write (throwaway worktree); in-place writes uncommitted per task (cat-visible) and sweeps into one final `chore: sdlc-task state` commit. The emoji gate diffs against a `baseSha` captured at setup so it works on `main`, not just `prBase..HEAD`. Turned `.claude/commands/patch.md`'s Step-1 scope-gate into a 3-rung ladder (trivial → `/patch`; small-but-needs-a-test → lean `/sdlc-task`; whole spec → `/sdlc-run`/`/sdlc-flow`), and added `sdlc-task-state.json` to the committed-state note in `.gitignore`. All four engines `node --check` clean; `sdlc-task.js` grep-clean of the removed flags and of `sdlc-state.json`. Deliberate transient inconsistency left in place: `sdlc-block.js` still invokes the removed `/sdlc-task` flags and `docs/workflows/*` still reference them — both are explicitly out of scope for Block B and disappear in Phase 1 A (`sdlc-block.js` rewrite) and Phase 3 B (docs). Block B's ADR and the formal `## Completed efforts` row are deferred to Phase 3 A per the plan's phase structure. Phase 0 is now complete (A committed, B uncommitted at handoff). Next: review all of Phase 0, then Phase 1 A (rewrite `sdlc-block.js` as the block orchestrator).

```diff
 .claude/commands/patch.md      |   35 +-
 .claude/workflows/sdlc-task.js | 2495 +++++++++++-----------------------------
 .gitignore                     |    6 +-
 3 files changed, 699 insertions(+), 1837 deletions(-)
```

---

## 2026-06-25 — SDLC redesign Phase 0 Block A: unified committed state + token telemetry

Implemented the first block of the redesign master-plan — the shared committed-state + token-telemetry spine every later block adopts. Established the canonical `tokens` block contract: `{ stages: [{label, model, promptTokEst, filesReadKb, inTokEst, outTok}], total: {…} }` where `inTokEst = promptTokEst + filesReadKb→tokens` (D15, ~256 tok/KB), null-safe on `filesReadKb`/`outTok` — realized as an identical `buildTokensBlock()` lifted (not imported) into each engine, since engines are self-contained by design. In `sdlc-run.js`: lifted `tracedAgent`/`metrics`/`recordFilesRead` from `sdlc-task.js`, routed the 9 substantive stages through `tracedAgent`, and replaced D27's gitignored `sdlc-state.json` breadcrumb with a committed `sdlc-run-state.json` carrying the phase trail + tokens block — so token usage, previously render-only and lost when a run ended, is now persisted and reviewable. In `sdlc-flow.js`: added the same `buildTokensBlock()` and made `writeFlowState` refresh `state.tokens` on every write, persisting per-task/cumulative tokens into the already-committed `sdlc-flow-state.json`. Dropped the D27 line from `.gitignore`. Notable decision (user call): because `sdlc-run` runs in-place on `main` (no worktree), its state is written uncommitted each phase (still `cat`-visible for crash inspection) and swept into the single wrap-up `chore:` commit — avoiding ~8 per-phase state-churn commits on main; `sdlc-flow` keeps its per-write commit since it runs in a throwaway worktree. All four engines `node --check` clean; `buildTokensBlock` math unit-tested (null paths). Block A's ADR (D37, supersedes D27 / extends D12+D15) and the formal `## Completed efforts` row are deferred to Phase 3 A per the plan's phase structure. Two stale `sdlc-state.json` mentions in `docs/workflows/` left for the Phase 3 B doc rewrite. Validation downstream only — never against base-template. Next: Phase 0 Block B (lean `/sdlc-task` + `/patch` ladder).

```diff
 .claude/workflows/sdlc-flow.js |  28 ++++++++
 .claude/workflows/sdlc-run.js  | 143 ++++++++++++++++++++++++++++++++---------
 .gitignore                     |   8 +--
 3 files changed, 143 insertions(+), 36 deletions(-)
```

---

## 2026-06-25 — Authored SDLC engines & planner-surface redesign master-plan (4 phases, 12 blocks)

Authored the comprehensive redesign master-plan (`planning/sdlc-block-and-task-updates/plan.md`, output of `/generate-master-plan` command) capturing all four SDLC engines and planner surface restructuring. Four phases, twelve blocks, model-tiered: Opus drives P0-A (unified committed state + token telemetry across all four engines), P0-B (lean `/sdlc-task`), and P1-A (`/sdlc-block` rewrite); Sonnet handles the rest. Key work streams: reposition `/sdlc-block` as a block-level orchestrator driving `/sdlc-flow` per block over a branch train of PRs (task-level waves dropped); lean out `/sdlc-task` per-core mechanics; committed authoritative state + persisted/rolled-up token telemetry architecture across all four engines; planner surface restructure (consolidate `/plan` into mini-roadmap, remove `/feature`, add `/ticket`); new `/review-PR` and `/merge-train` commands; `/close-out` gated per-block-before-PR. Added plan row to `planning/index.md`. Notable: D36 already taken by bella Wave 4 validation fix (sdlc-flow.js recordFilesRead removal), so effort ADRs start at D37. bella `/sdlc-flow` Wave-4 validation confirmed DONE (c64d272: 7/7 tasks PASS, review PASS, PR opened). Implementation deferred to fresh agent via handoff; validation happens downstream only, never against base-template.

```diff
planning/sdlc-block-and-task-updates/plan.md  (new, untracked)
planning/index.md  (updated with plan row)
planning/handoff.md  (updated with implementation handoff)
```

---

## 2026-06-25 — D36: fix stale recordFilesRead() crash in sdlc-flow.js + propagate

First real `/sdlc-flow` validation run (bella block 0.C — keyboard navigation) surfaced a
`ReferenceError: recordFilesRead is not defined` crash on task 1. The call at line 944 of
`sdlc-flow.js` was copy-paste residue from `sdlc-task.js`, which has a full per-stage
telemetry infrastructure (`metrics` array + `recordFilesRead()` helper + `filesReadKb`
schema field). `sdlc-flow.js` has none of that — its `tracedAgent()` tracks only
`label`/`model`/`promptTokEst`/`outTok`, and `STAGE_SCHEMA` has no `filesReadKb`.

Fix: remove the orphaned one-liner. `node --check` clean. Propagated to all six downstream
repos (bella, amistad, bastion, markdown-engine-validator, price-scout,
python-orchestration-system). ADR D36 written.

Run result: 7/7 tasks passed on first attempt (no fix loops), review PASS zero findings,
PR opened. ~47 min / 38 agents / ~939k sub-tokens. `/sdlc-flow` validated end-to-end.

```diff
.claude/workflows/sdlc-flow.js  — remove recordFilesRead(stageResult) call (line 944)
planning/decisions/D36-sdlc-flow-recordfilesread-fix.md  — new ADR
planning/decisions/index.md  — D36 entry
```

---

## 2026-06-24 — Fleet-wide propagation complete (remaining 7 repos)

Propagated the full current harness (D14–D35 + `/sdlc-flow`) to the remaining downstream repos, so all
ten harness-carrying repos are now current. **Committed:** `bastion`, `markdown-engine-validator`,
`price-scout` (full pull), and `learn-ai` (engines overwritten byte-identical + new `sdlc-flow.js` +
**additive** commands only — its customized `generate-tasks`/`plan`/`breakdown` preserved, so D34
`--from` + D35 floor still need surgical insertion there). **In place but untracked:** `claude-sdk-rs`,
`rag-engine-rs`, `workflow-engine-rs` — their `.claude/` is gitignored, so the harness landed but there
is nothing to commit (and they carry no `harness.json` yet). Each tracked repo got a `log.md` entry +
`.template-version` stamp (base `b8ebbf7`). All engines `node --check` clean; shared files
byte-identical to base. **Process note:** an initial `for d in $CLEAN` loop hit a zsh non-word-splitting
gotcha (created a garbage concatenated-name dir, propagated nothing); caught via per-repo verification,
removed the garbage dir, redid with a literal loop. Lesson: verify propagation per-repo, never trust a
loop's success message.

```diff
 (downstream repos — see each repo's own log.md + commit)
 bastion e1ff756 | markdown-engine-validator eef44cc | price-scout 17e317f | learn-ai 7a44776
 claude-sdk-rs / rag-engine-rs / workflow-engine-rs — .claude gitignored, harness in place untracked
```

---

## 2026-06-24 — Downstream propagation: full harness (D14–D35 + /sdlc-flow) to bella/amistad/python-orchestration-system + handoff

Propagated the complete harness to three downstream projects via rsync (no --delete, preserving project-specific files: health-check.js in python-orchestration, app work in amistad, harness.json + settings.json per-repo). D34 (ad-hoc planning seam) and D35 (plan-quality floor) shipped moments prior (b8ebbf7); all six planning commands and full /sdlc-flow engine (D30–D33) + Wave 3 satellites now in all three destinations. All engines `node --check` clean; shared files bit-identical to base. Per-repo commits reflect the propagation: bella received D34+D35 planning seam work (5069200) plus its `planning/master-plan.md` roadmap (10feb3b); amistad committed harness-only (57ad697, app implementation work left for separate session); python-orchestration-system preserved the health-check.js during the copy and committed (697c15b). `.template-version` stamped to b8ebbf7 in all three repos. Wrote `planning/handoff.md` for the next session's Wave 4 validation work: `/sdlc-flow` tested end-to-end in **bella** — the Rust terminal markdown viewer, now the designated testing ground with its own hand-built master-plan (phases 0–3, blocks A–J) — then Wave 5 propagation to the remaining downstream repos (learn-ai, bastion, markdown-engine-validator).

```diff
Substantive changes already committed in b8ebbf7. This session's work was rsync + per-repo commit + handoff write.
Changed files in base-template this session: planning/handoff.md (rewritten for Wave 4 validation).
New in b8ebbf7 harness: .claude/commands/generate-master-plan.md, generate-tasks.md (--from mode), plan.md (role note), README.md (phase table); planning/decisions/D34, D35, index.md; docs/using-the-template.md.
```

---

## 2026-06-24 — Ad-hoc planning seam: /generate-master-plan + /plan-as-block + /generate-tasks --from (D34)

Closed two gaps in the Phase-1 planning surface, both rooted in the same insight: the real contract
between planning and `/generate-tasks` is a **block definition** (What / Why / Build notes /
Acceptance criteria + a parseable slug), and `/generate-tasks` is just "block definition → decomposed
`tasks.md`".

- **`/generate-master-plan` (new command).** Authors/revises `planning/master-plan.md` as canonical
  `## Phase N` → `### Block X` definitions whose headers `/generate-tasks <phaseN-blockX>` parses
  directly — so a free-form planning session produces the structure the pipeline expects instead of
  something `/generate-tasks` has to guess at. Reuses the D20 clarify gate; ships mechanism-only.
  **Block skeleton hardened against a hand-built reference** (`bella/planning/master-plan.md`, authored
  backwards from `/generate-tasks`): each block now carries **Files (New vs Modified, by path)**,
  **Out of scope**, an optional **Interfaces / shared surface**, plus a self-documenting **"The Block
  Contract"** section — pushing disjoint-ownership thinking up to authoring time. `/generate-tasks`
  now **carries the block's named Files + Out-of-scope through** (treats Out-of-scope as a hard bound)
  instead of re-deriving when present. See D34 → "The canonical block skeleton".
- **`/generate-tasks --from <path>` (additive input mode).** Decomposes a single standalone block file
  (e.g. a `/plan` output) instead of a master-plan block: derives the slug from the file's parent
  directory, writes `tasks.md` beside the source, runs the identical self-check / decomposition
  assessment / pipeline recommendation / `execution-plan.json` authoring. Default slug mode unchanged.
- **`/plan` (clarified role).** Now framed as a single standalone block definition for an
  ad-hoc/experimental feature — kept **out** of `master-plan.md` until it proves out on a branch.
  Gains a "rigorous route" next-step (`/generate-tasks --from … → /sdlc-flow`). Direct `/implement`
  path retained.

Rationale for the standalone-file route over appending to `master-plan.md`: experimental work runs on
a feature branch via `/sdlc-flow` *because* it might not pan out — forcing it into the roadmap first
records speculation as roadmap. See **D34**. `/feature` and `/chore` (fast one-shot `tasks.md`) are
unchanged.

**Brain-repo follow-up (not done here):** wire `/new-project` (in `agentic-portfolio/`, outside the
harness) to call `/generate-master-plan` as its post-scaffold roadmap step. Captured as an Upcoming
work row in `status.md`.

```diff
 .claude/commands/generate-master-plan.md          | new
 planning/decisions/D34-adhoc-planning-seam.md     | new
 .claude/commands/generate-tasks.md                | --from mode (additive)
 .claude/commands/plan.md                          | role note + rigorous next-step
 .claude/commands/README.md                        | phase table + Phase-1 prose
 planning/decisions/index.md                       | D34 row
 docs/using-the-template.md                        | master-plan + experimental flow
```

**Plan-quality floor (D35).** Same session, prompted by "is Build Notes important?" → no (a soft
catch-all invites imprecision; fold approach hints into a concrete `What`), and "maintain Plan F3's
clarify-don't-assume as we evolve." Added a **plan-quality floor** to all three planning commands that
holds **even when the D20 clarify gate is off**: if filling a load-bearing element (concrete files,
observable acceptance criterion, scope boundary, dependency) would require *inventing* a fact
ungroundable in the prompt / CLAUDE.md / context / repo / master-plan, the command **asks** (interactive)
or **aborts naming exactly what's missing** (unattended preflight, e.g. inside `/sdlc-block`/`/sdlc-flow`)
rather than emit a confident guess. Chosen over flipping D20's default-on (would reverse a settled
decision + hang unattended preflight). Extends D19 (post-hoc → proactive) and complements D20. See
**D35**. Files: `generate-master-plan.md`, `plan.md`, `generate-tasks.md` (one floor paragraph each),
`planning/decisions/D35-plan-quality-floor.md`, `planning/decisions/index.md`.

Mechanism-only, prompt/command-layer (no engine JS touched). Not yet propagated downstream.

---

## 2026-06-24 — Implemented the /sdlc-flow engine (D30–D33)

Built the fourth SDLC engine: `/sdlc-flow` — shared-worktree, single-review, PR-terminating. Key
design calls (D30): one dedicated worktree for the whole spec eliminates the inter-task merge
conflicts that make `/sdlc-block` unreliable; tasks run sequentially as commits on that one branch;
a per-task `fast` test→fix loop (≤3 attempts, Opus escalation on the final pass); one consolidated
end review over the integrated tree; docs patch gated on PASS; `gh pr create` as the terminal step.
Registered via `export const meta` — the Workflow runtime surfaces `.claude/workflows/*.js` directly;
no `.claude/commands/` entry needed.

Four ADRs: **D30** (engine design + assembly rationale — ~80% proven harness parts); **D31** (committed
authoritative state — `sdlc-flow-state.json` + `worklog.md` at `planning/<spec>/sdlc/` are committed,
inverting the usual "state is gitignored" harness rule; replaces 5×N per-stage report files with a
structured index for resume/review/wrap-up); **D32** (triage-gated immediate-bail set — MAJOR findings
break straight to a draft-PR wrap-up without burning all three attempts, distinguishing structural blockers
from retryable glitches); **D33** (PR-based wrap-up — `gh pr create` with auto-generated title/body from
state.json; `--auto-merge` for clean PASS; `--no-pr` to stop after wrap-up).

Wave 3 satellites: engine file `.claude/workflows/sdlc-flow.js`; ADR files D30–D33; canonical workflow
doc `docs/workflows/sdlc-flow.md` + `docs/workflows/index.md` row/mermaid (other agent); `harness.schema.json`
`flow` block + `scaffold/planning/harness.json` stub + `docs/harness-json.md` updates (other agent);
`generate-tasks.md` routing extended — `/sdlc-flow` added as the new default for non-trivial feature work
(extends D21, which covered only `/sdlc-run` vs `/sdlc-block`); `.gitignore` comment confirming
`sdlc-flow-state.json`/`worklog.md` are intentionally tracked (D31). All engines `node --check` clean.

Not yet validated on a downstream spec (Wave 4: python-orchestration-system expose-api-and-telegram-bot,
fresh branch). Not yet propagated (Wave 5).

```diff
 .claude/workflows/sdlc-flow.js                    | new
 planning/decisions/D30-sdlc-flow-engine.md        | new
 planning/decisions/D31-committed-authoritative-state.md | new
 planning/decisions/D32-triage-gated-bail.md       | new
 planning/decisions/D33-pr-based-wrap-up.md        | new
 .claude/commands/generate-tasks.md                | step 11 + Report extended
 .gitignore                                        | D31 comment added
 planning/status.md                                | current focus + completed effort row
 log.md                                            | + (this entry)
 docs/index.md                                     | sdlc-flow.md reference added
```

---

## 2026-06-24 — Planned the /sdlc-flow engine

Designed the `/sdlc-flow` single-spec orchestration engine as the inner complement to `sdlc-block`'s multi-task waves — motivated by the D22–D28 refactor's merge-conflict surface area (shared state.json + worklog.md in every task's worktree branch, leading to collisions when reordering or re-running tasks). The design resolved four forks with the user: name the command `/sdlc-flow` (not `/sdlc-run-v2`); build the inner single-spec engine first and reposition `/sdlc-block` as a documented follow-on orchestrator; commit authoritative `state.json` + one `worklog.md` (replacing per-stage report files) to avoid shared-file merge collisions; add `create-PR-and-stop` with `--auto-merge` opt-in for external integration. Authored `planning/sdlc-flow/plan.md` (design surface, dependencies, load-bearing decisions), `planning/sdlc-flow/orchestration.md` (four-phase build order with actor assignments), and `planning/sdlc-flow/index.md` (directory layout). No engine code written; this is a clean planning handoff for a fresh Opus implementation session.

```diff
 planning/handoff.md                      | 137 +++++-------
 planning/plans/sdlc-block-run-review.md  | 142 ------------
 planning/plans/sdlc-telemetry-updates.md | 363 -------------------------------
 planning/status.md                       |   5 +-
 4 files changed, 58 insertions(+), 589 deletions(-)
```

---

## 2026-06-23 — Fixed brain-sync step in the harness `/log-work`

The harness `log-work.md` brain-sync step was carrying three bugs cloned from the original
learn-ai command and never re-tokenized: it referenced learn-ai's "13-spec table", told the
agent to update the README's Quick Status section **"for learn-ai"** regardless of which
project it ran in, and ended with "skip this step silently" (which masked failures). Net
effect downstream: a generated project's `/log-work` either edited the wrong brain section or
silently no-op'd, so subrepo status rarely reached the company brain.

Fix: made the step slug-agnostic — it now locates *this* project's `###` subsection in the
brain `README.md` (the same project as the `docs/projects/*.md` it just read), updates "this
project's progress table", and **fails loudly** (STOP + report) when it can't find the
section instead of skipping or editing another project's. The `{{SLUG}}` token for the
brain-doc path is unchanged (still substituted by `/new-project`).

Already-generated projects were patched directly in the same session (all 9 downstream repos
+ this template), so no manual pull is needed for this change — D18 propagation applies to
future clones only.

```diff
 .claude/commands/log-work.md   | ~10 +-
 log.md                         |  + (this entry)
```

---

## 2026-06-23 — Merged planf3-harness-improvements + tac8-adoptions to main

Both long-running harness branches landed on `main` (merge commit `38fd5ac`). `planf3-harness-improvements` fast-forwarded; `tac8-adoptions` was a 3-way merge. The four conflicts (`.gitignore`, `log.md`, `planning/decisions/index.md`, `planning/status.md`) were all additive doc/index conflicts — no engine-code conflict (`sdlc-run.js` + `commands/README.md` auto-merged) — resolved keep-both, with D27/D28/D29 reconciled into the decisions index. All engines `node --check` clean post-merge. `main` now carries the full Plan F3 lean `sdlc-block` (D18–D29) + the TAC8 adoptions (D27 phase state, Python hooks parked in `need-python-hooks/`, `/patch`, E2E templates, `/conditional_docs`). **Nothing propagated downstream yet** — wrote `planning/handoff.md` for the next agent: validate the lean `/sdlc-block` on a real downstream spec, then propagate engines + new commands to the four repos, then decide the Python-hook wiring. Branches merged but not deleted.

---

## 2026-06-23 — Canonical SDLC workflow docs + agnostic engine fix (D29)

Created `docs/workflows/` as the canonical reference for the SDLC pipelines (authored here, copied verbatim into every project): `index.md` (hub — three engines compared, shared concepts, model tiering, token overview), `sdlc-run.md`, `sdlc-task.md`, `sdlc-block.md` (the lean F3 design — D22–D28), and `commands.md` (the manual Phase 1–7 lifecycle). Each page has mermaid flow diagrams, parameter/flag tables, per-stage detail, when/why, and a token-usage section with `_TBD_` placeholders + the few measured figures we have (`expose-api-and-telegram-bot`). Derived from the **current engine source**, not the stale learn-ai docs (whose `/sdlc-block` page predated the entire lean redesign). Wired into `docs/index.md`. Also rewrote the stale `/sdlc-block` section in `.claude/commands/README.md` (it still described the pre-D23/D24 "full sdlc-task per task per wave" model) + added `--verify-depth`.

**Moved the docs out of learn-ai** (they shouldn't live in a product repo): `git rm`'d the three `docs/agentic-workflows/*.md`, repointed `learn-ai/docs/index.md` + the `CLAUDE.md` "keep pipeline docs in sync" rule at `base-template/docs/workflows/`. (Committed separately in the learn-ai repo.)

**Closed a D5 agnostic leak the doc pass surfaced ([D29](planning/decisions/D29-engine-agnostic-paths.md)):** `sdlc-task.js` worktree-setup coned a hardcoded stack-specific include list (`app components hooks lib ...`) and the `implement`/`fix` commit prompts in `sdlc-run.js`/`sdlc-task.js` named `app/, components/, __tests__/` + `.tsx` examples. Generalized to cone all tracked top-level dirs (`git ls-tree HEAD --name-only -d`, matching `/init-worktree`) and to "changed source/content files (from git status)". All three engines `node --check` clean; prompt/recipe-only.

```diff
 .claude/commands/README.md                   |  ~25 +-
 .claude/workflows/sdlc-run.js                |   8 +-
 .claude/workflows/sdlc-task.js               |  ~12 +-
 docs/index.md                                |  ~14 +
 docs/workflows/{index,sdlc-run,sdlc-task,sdlc-block,commands}.md | new (5 files)
 planning/decisions/D29-engine-agnostic-paths.md | new
 planning/decisions/index.md                  |   8 +
```

---

## 2026-06-23 — TAC8 Adoptions Task 5 — persistent phase state in sdlc-run.js (D27)

Shipped the last TAC8 adoption: `sdlc-run` now leaves a machine-readable breadcrumb of where a run
is. After each pipeline phase **resolves**, a new `recordPhaseState()` helper writes (overwriting)
a small JSON file at `planning/<concept>/sdlc/sdlc-state.json` — alongside D22's
`execution-plan.json`.

**Schema:** `{spec_slug, started_at, updated_at, current_phase, completed_phases, failed_phase,
task_number, resume_from}`. `completed_phases` grows monotonically (deduped — a multi-pass fix
records `"fix"` once but bumps `updated_at` each pass); on a phase abort, `failed_phase` +
`resume_from` are set to the phase name and `completed_phases` is left untouched.

**Why a writer agent:** the workflow runtime has no filesystem access and cannot call `Date.now()`,
so `recordPhaseState()` spawns a cheap **Haiku** agent that stamps timestamps via `date`, reads the
existing file to preserve `started_at`, and writes the JSON. The write is best-effort — a failure
logs a warning and never aborts the pipeline.

**Call sites (14):** failure + success records at generate-tasks / implement / fix; completion
records at test / review / ui-test (both the skip branch and the server-run converge point) /
document / wrap-up. Matches the spec's verify list.

**Not a resume engine, by design.** The state file is gitignored runtime state — crash visibility
plus a `resume_from` hint. The committed report files (scout) remain the authoritative resumption
signal; `--from <stage>` (D17) remains the explicit-resume lever. Building a second, state-driven
resume path would compete with the scout and read uncommitted data — strictly worse.
[D27](planning/decisions/D27-sdlc-run-phase-state.md) records this and the deferred `sdlc-task`
(parallel, per-task) variant.

Gitignored `planning/*/sdlc/sdlc-state.json` (mirroring the `.claude/logs/` precedent from Tasks
1–4). D27 numbered ahead of the F3 branch's D18–D26 to avoid collision; the index notes the gap.
All three engines `node --check` clean. `sdlc-run.js`-only engine change; **not yet propagated
downstream.**

```diff
 .claude/workflows/sdlc-run.js               |  ~90 +++++++++
 .gitignore                                  |   3 +
 planning/decisions/D27-sdlc-run-phase-state.md | (new)
 planning/decisions/index.md                 |   ~10 +++
 planning/status.md                          |   edits
```

---

## 2026-06-23 — P2 block-state persistence (D28)

Implemented the third validation-run bug fix: cross-invocation resume state for `sdlc-block.js`. A new gitignored breadcrumb `planning/<spec>/sdlc/sdlc-block-state.json` records per-task status (`pending`/`merged`/`escalated`/`skipped` + commit/branch/worktree), written by a cheap Haiku helper (`writeBlockState`) after Analyze and once per wave. On re-invocation a Haiku loader reads the file before Analyze; its task map **additively** augments Analyze's git-derived resume sets — `merged` tasks go to `doneTasks` (skip the wave loop), `escalated` tasks are forced to `complete-unmerged-fail` so the wave loop escalates them directly instead of re-deriving limbo worktrees through a ~12k-outTok triage wave (the dominant waste in the expose-api-and-telegram-bot run). Augments, never replaces, the committed-report scout (consistent with D27); the dependency graph still comes from Analyze / D22's execution-plan.json. Wrote [D28](planning/decisions/D28-sdlc-block-task-state.md) (numbered to avoid colliding with D27 on `tac8-adoptions`), updated `decisions/index.md` and `.gitignore` (added both `sdlc-state.json` and `sdlc-block-state.json` runtime breadcrumbs). All three engines `node --check` clean. Not yet validated end-to-end or propagated.

```diff
 .claude/workflows/sdlc-block.js              | ~90 +++++++
 .gitignore                                   |   5 +
 planning/decisions/D28-sdlc-block-task-state.md | new
 planning/decisions/index.md                  |   7 +
```

---

## 2026-06-23 — TAC8 Adoptions Tasks 1–4 — Python hooks, /patch command, E2E test templates, /conditional_docs

Integrated four new harness capabilities from the TAC8 protocol review, all committed on `tac8-adoptions` branch:

**Task 1: Python Security & Logging Hooks.** Added pre/post tool-use instrumentation hooks (`pre_tool_use.py`, `post_tool_use.py`) for security compliance and structured logging. Hooks fire before each tool invocation and after completion, enabling auditability and instrumentation without baking policy into the engines. Registered in `.claude/settings.json` under `settings.hooks`.

**Task 2: `/patch` Lightweight Hotfix Command.** New command for surgical git-diff patching — apply fixes without triggering a full spec workflow. Scoped for small, targeted changes (config updates, doc fixes, simple refactors). Complements the full SDLC pipeline for quick turnarounds.

**Task 3: E2E Test Template Library.** Four reusable test templates (`e2e:test_auth_gate`, `e2e:test_crud_api`, `e2e:test_error_handling`, `e2e:test_ui_form`) with step-by-step guides and example assertions. Scaffolding + README documenting template purpose and invocation. Reduces setup friction for validation gates.

**Task 4: `/conditional_docs` Routing Command.** Task-type documentation router — dispatches to type-specific documentation based on spec characteristics (feature vs. fix vs. chore; content vs. infrastructure). Single entry point for finding the right doc template without guessing.

All harness mechanisms kept project-agnostic. The `/patch` command, hooks config, E2E templates, and `/conditional_docs` router are installed in both root `.claude/` and propagated to `scaffold/` for new-project generation.

```diff
 .claude/commands/README.md                    |   7 ++
 .claude/commands/conditional_docs.md          |  85 +++++++++++++++++
 .claude/commands/e2e/README.md                |  41 +++++++++
 .claude/commands/e2e/test_auth_gate.md        | 127 ++++++++++++++++++++++++++
 .claude/commands/e2e/test_crud_api.md         | 117 ++++++++++++++++++++++++
 .claude/commands/e2e/test_error_handling.md   | 109 ++++++++++++++++++++++
 .claude/commands/e2e/test_ui_form.md          |  72 +++++++++++++++
 .claude/commands/patch.md                     |  61 +++++++++++++
 .claude/hooks/post_tool_use.py                |  30 ++++++
 .claude/hooks/pre_tool_use.py                 |  30 ++++++
 .claude/settings.json                         |  26 ++++++
 .gitignore                                    |   3 +
 scaffold/.claude/commands/conditional_docs.md |  85 +++++++++++++++++
 scaffold/.claude/commands/e2e/README.md       |  13 +++
 scaffold/.claude/commands/patch.md            |  61 +++++++++++++
 scaffold/.claude/settings.json                |  26 ++++++
 16 files changed, 893 insertions(+)
```

---

## 2026-06-23 — P0 + P1 harness bug fixes from validation run review

Reviewed the `harness-update-review.md` from the expose-api-and-telegram-bot validation run on the lean sdlc-block (D23/D24). Found three bugs: **P0** baseline snapshot files written but untracked blocks merge (fixed `snapshotBlockBaselines()` in sdlc-block.js to run `git add` + commit after writing baselines); **P1** sdlc-run test stage invents emoji-prohibition gate not present in harness.json, failing specs that never declared the pattern (fixed by removing hardcoded EMOJI CHECK section and adding explicit guard against inventing out-of-config checks); **P2** no cross-invocation block-state persistence + emoji gate no-ops when integration branch is `main` (deferred to next session — known follow-up D23/D24 "Reconsider if"). P0 and P1 committed at 5d11d41.

```diff
 planning/handoff.md | 179 ++++++++++++++++++++++++++++++++--------------------
 planning/status.md  |   2 +-
 2 files changed, 112 insertions(+), 69 deletions(-)
```

---

## 2026-06-23 — TAC8 adoptions plan written

Reviewed the TAC8/ADW agentic repo (`~/agentic-portfolio`) — specifically its `.claude/` commands + hooks and the `adws/` Python autonomous workflow engine (ADW = AI Developer Workflow). Produced a full comparison report: TAC8 is ahead on explicit persistent phase state, autonomous GitHub issue processing (webhook + cron), E2E test scaffolding, and Python hook security guards; our harness is ahead on triple-tier model selection, ADR-driven decision log, dependency-ordered orchestration, and stack-specific validation policy. The autonomous webhook trigger (TAC8's ZTE) was explicitly excluded from adoption — the python-orchestration-system's Telegram bot + expose-api spec already covers the same architectural pattern. Wrote `planning/plans/tac8-adoptions.md` with five ordered tasks (Python hooks → /patch → E2E templates → /conditional_docs → persistent phase state D27); updated `planning/index.md` to register the new plan.

```diff
 planning/handoff.md | 146 ++++++++++++++++++++++++----------------------------
 planning/index.md   |   4 ++
 2 files changed, 70 insertions(+), 80 deletions(-)
```

---

## 2026-06-23 — Handoff written for Plan F3 propagation

Completed D26 parity work; wrote updated `planning/handoff.md` with full guidance for the next session's propagation to python-orchestration-system (which has the expose-api-and-telegram-bot spec ready to validate the lean sdlc-block on a real multi-task effort) and consolidation of lean block validation. Plan F3 steps 1–3 are engine-complete and `node --check` passing; STEP 4 propagation to the four downstream repos remains (uncommitted per-repo for review).

```diff
 planning/handoff.md | 189 ++++++++++++++++++++++++++++++-------------------------
 1 file changed, 99 insertions(+), 90 deletions(-)
```

---

## 2026-06-23 — Plan F3: sdlc-run D6 richer-check parity (D26)

Ported the D6 richer-check dispatch + `snapshotBaselines()` from `sdlc-task.js` into `sdlc-run.js`,
completing the D24 consolidated back-half. The lean block's `workflow('sdlc-run', '--from test')` now
handles all four check kinds (baseline-diff, count-delta, warning-scan, forbidden-pattern-scan).
`count-delta` skips cleanly when `taskNumber === null` (full-spec mode has no previous-task report).
All engines `node --check` clean. Additive + default-preserving (command-kind behavior unchanged).
ADR D26 written. See [D26](planning/decisions/D26-sdlc-run-d6-parity.md).

---

## 2026-06-23 — Plan F3 step 3: lean sdlc-block engine (D23 + D24)

Built the centerpiece — `sdlc-block` repurposed in place into "a more powerful `/sdlc-run`" (a fresh
implement agent per task + one consolidated back-half). Opus driving; `sdlc-task --implement-only` was
the only delegatable building block. All engines `node --check` clean; `harness.schema.json` +
`execution-plan.schema.json` parse. **Not yet validated on a real multi-task spec, not propagated.**

- **D24 config surface.** `block.verify` enum (`consolidated` default / `consolidated+review`) added to
  `harness.schema.json` (top-level `block`, `additionalProperties:false`), `scaffold/planning/harness.json`,
  and `docs/harness-json.md` (new section + top-level row). CLI override `--verify-depth`.
- **`sdlc-task.js` — `--implement-only` mode.** New flag: worktree-setup → implement → (one review pass
  only with `--review`) and STOP — skips test/fix/ui-test/document/wrap-up and the merge hand-off.
  Returns `finalVerdict` (FAIL / IMPLEMENTED / the review verdict). The width-≥2 building block the lean
  block fans out for genuine parallel waves; the worktree full-pipeline path is untouched.
- **D23 — `sdlc-block.js` shared setup + in-place execution + rollback.** `harness-config` already once;
  `baseline-snapshot` hoisted to once-per-block `snapshotBlockBaselines` (no-op without a D6 baseline-diff
  check). Wave loop rewritten: a width-1 wave runs the task **in place on the integration branch** via an
  **inlined** implement (+ optional localization review) agent that shares the block's config (no
  worktree, no merge); a width-≥2 wave isolates each task in a worktree via `/sdlc-task --implement-only`
  then merges in order. Pre-task HEAD captured; a failed in-place implement is `git reset --hard`'d back
  before retry/escalation. Resume keys on landed `task<N>-implement.md`. The inline-implement duplication
  is the deliberate resolution of D23-shared-setup vs D24-don't-duplicate (user-approved): `workflow()`
  can't share JS state, so reusing a sub-engine per task would re-pay the ×N setup D23 kills. See
  [D23](decisions/D23-lean-block-shared-setup.md).
- **D24 — `sdlc-block.js` consolidated back-half + verify knob.** After all tasks land (and only when no
  escalations/skips), the block seeds one spec-level `implement.md` from the per-task reports, then runs
  ONE `test → review → fix → (ui-test) → document → wrap-up` over the integrated tree via
  `workflow('sdlc-run', '<slug> --from test')` — the back-half reuse (`/sdlc-run --from test` = D17). Its
  wrap-up owns status.md/log.md/the spec Amendment Log (D18); the block's slim Report writes only
  `block-workflow.md` (no status/log). The block's own Playwright sweep was **removed** (the back-half's
  ui-test stage covers it); its dead Playwright schemas + `renderUiTestPrompt` were deleted. `block.verify`
  / `--verify-depth` resolved (CLI > harness.json > `consolidated`); per-task review is non-gating. See
  [D24](decisions/D24-consolidated-back-half.md).
- **Known follow-ups (before propagation).** (1) `/sdlc-run` D6 richer-check parity so the reused
  back-half handles baseline-diff/warning-scan/forbidden-pattern (currently command-kind only). (2) The
  emoji gate (`git diff main..HEAD`) no-ops when the integration branch is `main`; a dedicated
  integration branch is the documented fix. (3) End-to-end validation on a real multi-task spec (token
  drop + that the consolidated back-half catches what per-task verification would have). Both recorded in
  the D23/D24 "Reconsider if" sections.

---

## 2026-06-23 — Plan F3 step 2: engine guards (D19 preflight, D18 wiring, D22 plan relocation)

Implemented the small-engine-guards slice of Plan F3 (sequencing step 2), Opus driving directly. All
three engines `node --check` clean; the new `execution-plan.schema.json` parses.

- **D19 — property-based authoring guard (engine half complete; ADR written).** Because the engines have
  no filesystem access (they orchestrate agents), the thin-spec check rides the **existing** early agent
  in each engine — no new agents. `sdlc-block.js`: STEP 4b in the Sonnet pre-flight (full signal set,
  aborts `ready=false`). `sdlc-run.js`: `specThin`/`thinReason` on the scout schema + a STEP 9, evaluated
  ONLY on a fresh implement-stage run (never on resume), with a JS abort. `sdlc-task.js`: `specThin` on
  worktree-setup (STEP 6c), evaluated only on a fresh worktree, aborted only when not `--under-block`
  (the block already validated on main). Placeholder detection scoped to scaffold sentinels (`{{`, empty
  AC); never flags bare `TODO`/`<...>` or the Amendment Log seed. See [D19](decisions/D19-property-based-authoring-guard.md).
- **D18 — living-artifact specs (engine wiring complete; ADR written).** `sdlc-run.js`: wrap-up is the
  single amendment writer on main (chosen over the fix loop, which can run 3×) — appends one dated line
  per genuine deviation to the spec's `## Amendment Log`, updates the provenance stub, stages the spec;
  `WRAPUP_SCHEMA` gains `amendments[]`. Worktree path: `sdlc-task.js` wrap-up records lines in a new
  `## Amendment Log Entry (D18)` section of the deferred `task<N>-log.md` (body `_none_` when clean), and
  the merge-time appliers (`clean-worktree.md` step 6.5g.5 + `sdlc-block.js` report step) append them to
  the spec on main in task order — single sequential writer, no `additiveFiles` needed. See
  [D18](decisions/D18-living-artifact-specs.md).
- **D22 — execution-plan.json authored at /generate-tasks (complete; ADR written).** New
  `.claude/workflows/execution-plan.schema.json` contract. `/generate-tasks` step 12 writes + commits the
  dependency graph (from its step-6 file-ownership analysis) when recommending a block; `waves` omitted
  (engine computes). `sdlc-block.js` Analyze STEP 1 now validates parses + schema-shape + **task-set
  matches current `### N.` headings** before loading verbatim and skipping the Opus graph derivation;
  absent/malformed/stale → falls back to deriving. The agent stays on Opus (one agent, both branches);
  the saving is the skipped derivation reasoning. See [D22](decisions/D22-execution-plan-authored-at-generate-tasks.md).

Remaining: step 3 (the lean block engine — D23 shared setup + in-place sequential + rollback, D24
consolidated back-half + `block.verify`) — the largest/highest-risk change; build last and validate on a
real multi-task spec before propagating. Then step 4 (downstream propagation).

## 2026-06-23 — Plan F3 step 1: prompt/template layer (D20, D21, D25 complete; D18/D19 authoring halves)

Implemented the low-risk prompt/template slice of Plan F3 (sequencing step 1), Opus driving with one
Sonnet sub-agent for isolated ADR prose. No engine (`.claude/workflows/*.js`) code touched yet.

- **D20 — clarify-before-generate gate (complete).** Added `planning.clarify: boolean` (default false)
  to `harness.schema.json` (new top-level `planning` object), the `scaffold/planning/harness.json` stub,
  and `docs/harness-json.md` (table row + dedicated section + config-absent note). Wired a clarify step
  into `plan.md` / `feature.md` / `generate-tasks.md`: when `planning.clarify` is true **or** `--clarify`
  is passed **and** the prompt is genuinely ambiguous, ask 2–4 targeted questions before writing;
  otherwise behave exactly as today. ADR `D20-clarify-before-generate.md` + index row.
- **D19 — property-based authoring self-check (authoring half).** Added a pre-report self-check step to
  all three authoring commands: every `### N.` task names ≥1 file, AC non-empty/observable, Validation
  Commands present (or harness.json fallback), no leftover template sentinels — with the load-bearing
  caveat that legitimate `<...>` (generics/prose) and bare `TODO`/`TBD` are **not** flagged. Engine
  preflight half + ADR land in step 2.
- **D21 — honest pipeline recommendation (complete, prompt-only).** Rewrote `/generate-tasks` step 11 +
  the Report examples for the repurposed `sdlc-block` ("a fresh implement agent per task at near-`sdlc-run`
  cost"): default `/sdlc-run` even past 4 tasks for homogeneous/sequential blocks; recommend the lean
  block for per-task implement isolation or true parallelism; recommend `--verify-depth consolidated+review`
  (≈38k tok × N) only when end-only localization would be hard. ADR `D21-honest-pipeline-recommendation.md`
  + index row (forward-refs D23/D24 for the engine behavior).
- **D18 — living-artifact specs (template half).** Added an append-only `## Amendment Log` (seeded
  `_No amendments yet._`) + a one-line `status:` / `last-run:` provenance stub to `spec-template.md` and
  the `plan.md` / `feature.md` / `generate-tasks.md` output formats. Engine wiring (wrap-up/fix appends +
  deferred-merge path) + ADR land in step 2.
- **D25 — considered-and-rejected record (complete).** Sonnet sub-agent authored
  `D25-considered-and-rejected.md` (XML format deferred; per-phase SVG, mega-skill dispatch table,
  cross-plan reference graph rejected), reviewed and accepted; index row added.

Renumbered command instruction steps and fixed internal cross-references. JSON (schema + stub) parses;
all engines still `node --check` clean.

## 2026-06-23 — Revise Plan F3 per the architecture reframe; rewrite handoff for an Opus+Sonnet session

Reviewed the Plan F3 effort with the user before implementation and reframed it based on measured `sdlc-block` telemetry. The decisive input: the user almost never runs `sdlc-block` and its current behavior **is not worth preserving** — they live in `sdlc-run`. So rather than tuning the block, D21–D24 now **repurpose `sdlc-block` in place** into "a more powerful `sdlc-run`": keep the name + orchestration machinery (waves, retry/triage, worktree-for-parallel, ordered merge) but discard the wasteful per-task full pipeline. The one capability `sdlc-run` lacks and the new block adds is a **fresh implement agent per task** (today `sdlc-run` runs one implement agent across all tasks); everything else (shared setup once per block, in-place sequential execution, one consolidated back-half) drives the ≈200k/task waste out. Because the old behavior is deliberately discarded, the byte-identity guardrail no longer binds `sdlc-block` (it still binds `sdlc-run` + the shared `planning.clarify` toggle). Second decision: **per-task review defaults OFF**, with `/generate-tasks` recommending `consolidated+review` when task size/complexity would make end-only localization hard.

Revised `planning/plans/planf3-harness-improvements.md` to match: reframed Steer A + Guardrail #2; D21 recommendation now also decides the per-task-review suggestion (piggybacks the step-8 D10/D13 signal); D22 defines plan validity as parses + schema-match + task-set-match (stale plans fall back to the Opus analyzer, justifying schema formalization as the load-time validator); D23 makes in-place sequential the default substrate and adds the missing failure-rollback requirement (`git reset --hard` to pre-task SHA before retry on the shared branch); D24 collapses the three-way verify matrix to two modes (`consolidated` default / `consolidated+review`); D19 scopes placeholder detection to scaffold sentinels only so a valid spec is never blocked. Also caught a latent contradiction in the original plan — D23's "no knob, derived from wave width" silently broke the byte-identity guardrail; the reframe dissolves it. Rewrote `planning/handoff.md` for a fresh **Opus** instance that drives the engine/judgment work directly and **delegates mechanical isolated pieces to Sonnet sub-agents** (D18 template inserts, D20 doc/schema plumbing, D25 prose, bookkeeping), explicitly NOT running `/sdlc-block` on this effort (self-modification hazard + heavy file overlap trips the D9 disjoint-owner guard). No engine or command code changed yet; branch `planf3-harness-improvements`, ADRs D18–D25 still to be authored as each lands.

```diff
 planning/handoff.md                           | 189 ++++++++++++--------------
 planning/plans/planf3-harness-improvements.md | 155 ++++++++++++++-------
 planning/status.md                            |  10 +-
 3 files changed, 203 insertions(+), 151 deletions(-)
```

## 2026-06-23

Reviewed the "Plan F3" planning meta-skill article against our SDLC harness and, combined with user-supplied sdlc-block token telemetry, produced an eight-ADR improvement plan (D18–D25) targeting planning quality and a lean sdlc-block redesign. The eight ADRs span planning-quality changes (D18 living-artifact specs, D19 property guard, D20 clarify gate) and telemetry-driven lean sdlc-block work (D21 honest recommendation, D22 relocate execution-plan.json to /generate-tasks, D23 shared setup + isolation only for true parallelism, D24 consolidated verify depth knob, D25 considered-and-rejected); the lean-block redesign is the centerpiece, driven by measured telemetry showing approximately 200k redundant tokens per task on sequential blocks. Formalized the work in a self-contained plan at planning/plans/planf3-harness-improvements.md, indexed it in planning/index.md, pointed status.md Current focus at the plan, and wrote planning/handoff.md carrying the decision rationale and measured telemetry table. No engine or command code has changed; work lives on branch planf3-harness-improvements, ready for a fresh agent to implement starting at sequencing step 1 (D20).

```diff
 planning/index.md  | 4 ++++
 planning/status.md | 6 ++++--
 2 files changed, 8 insertions(+), 2 deletions(-)
```

---

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
string sees the correct unicode ranges. Verified: post-fix the class matches real emoji characters and
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
