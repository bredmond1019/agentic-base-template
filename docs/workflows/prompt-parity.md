---
type: Reference
title: Prompt parity — sdlc-flow, sdlc-task, and the one-off commands
description: "Where the two SDLC engines' stage prompts agree, where they deliberately differ, how the shared master library keeps them from drifting, and why the one-off stage commands were retired."
doc_id: sdlc-prompt-parity
layer: [factory]
project: base-template
status: active
keywords: [prompt parity, sdlc-flow, sdlc-task, drift, stage prompts, one-off commands]
related: [base-template-workflows-index, sdlc-flow, sdlc-task]
---

# Prompt parity

`sdlc-flow.js` and `sdlc-task.js` are **self-contained** — the Workflow harness runs one file per
engine, so neither can import the other and every shared stage prompt existed twice on disk. A third
copy lived in the one-off stage commands (`/implement`, `/test`, `/fix`, …) for a human driving the
pipeline by hand.

Three copies of one instruction is three chances to drift, and all three had. This page is the
register: what is **intended** difference (§2), what was **drift** and how it was closed (§3), why
the third copy was retired rather than repaired (§4), and the shared library that stops the first
two recurring (§5).

Audited 2026-08-30 against `sdlc-task.js` (16 prompt regions) and `sdlc-flow.js` (20).

---

## 1. What is already identical

Verified byte-identical except for the run-root variable name (`runDir` vs `worktreePath`):

`detect-vault` · `resolve-repo-root` · `verify-setup-binding` · `verify-vault-commit` ·
`baseline-snapshot` · `state-load` · the triage prompt (including the whole
"before you assert this pre-dates the task" evidence clause) · `renderCommitSafetyGuard` ·
`renderWorkAssertion` · `skipCountRegressionResult` · the emoji-gate Python script · the D46 vaulted
commit recipe · the D64 validate-then-rollback `state.json` mutation script.

That set is the de-facto shared library. It is what the extraction in §5 started from.

---

## 2. Intended differences — do not "fix" these

| # | Difference | Why it is correct |
|---|---|---|
| I1 | **`/tmp` scratch paths** are `<block>-task-*` vs `<block>-flow-*` | Two engines can run against the same block; a shared path would collide. |
| I2 | **Per-task `validation_commands` semantics (D63)**: task **augments** the harness `gates:true` checks; flow **substitutes** them | Flow's end review unconditionally re-runs the full suite over the integrated tree, so a narrowed per-task tripwire is safe there. Task has no review, so its tripwire must never drop a project gate. Both engines carry this rationale in a source comment at the `usingOverride` branch. |
| I3 | **Task has a terminal `reconcile` stage (D56); flow does not** | Flow's consolidated review already re-runs every check in its authoritative form. Reconcile is task's substitute for that review. |
| I4 | **Flow writes `sdlc/worklog.md` + `state.json`; task writes `state.json` only** | Task is the lean engine; its run history lives entirely in `state.json`. See the note in `renderOnPassStateWriteRecipe`. |
| I5 | **Flow has Review / Docs / Wrap-up / PR / auto-merge stages; task has `bookkeep`** | The engines' stated scope split. Task's `bookkeep` is deliberately *not* a wrap-up: it flips authored status markers and commits, and explicitly does not write a `log.md` narrative or a D18 amendment log (that is `/log-work`'s job). |
| I6 | **Flow's `harness.json` loader keeps the `flow` block** (`autoMerge`, `testDepth`, `prBase`, `bailReasons[]`); task's does not | Only partly correct — see D5 and D6 below. `autoMerge`/`prBase` are genuinely flow-only. |
| I7 | **Task's implement stage reports `filesReadKb`; flow's does not** | Documented as not-yet-implemented in flow, not as a decision: `sdlc-flow.js` line ~702 says "flow stages do not self-report it yet". Tracked as D7 below rather than here. |

---

## 3. Drift between the two engines — CLOSED 2026-08-30

All eight are fixed. Kept here as a record of what each one was, because every row is a shape the
next edit could reintroduce, and three of them are now pinned by a test.

| # | Drift | What it would have cost | Resolution |
|---|---|---|---|
| **D1** | `expect_red` / D68 inverted-verdict checks existed only in `sdlc-task.js` (`grep -c expect_red`: task 11, flow 0). | A block whose deliverable is a test observed *failing* could not run through `/sdlc-flow` at all — the task passed only once the test it was meant to add was already green. | Ported to flow: `ENUMERATE_PROMPT` STEP 5, the `taskExpectRed` schema field, the subset-guard abort, `expectRedFor()`, and the inverted-verdict branch of `renderTaskCheckList`. |
| **D2** | The D16 derive-from-**block-record** fallback existed only in `sdlc-task.js`; flow resolved a block record as its spec source (D65) but recovered only from `tasks.md`. | The *same* block-record spec with an invalid `tasks.json` aborted under one engine and recovered under the other. | Ported flow's `derive-tasks-json-from-record` branch, selected on `specSource`. |
| **D3** | Flow dropped the engine-parse gate on the per-task override path — `renderTaskCheckList(...)` *or* `renderCheckList(...)`, and only the latter carried `engineFiles`. | A task both editing `.claude/workflows/*.js` and declaring its own `validation_commands` skipped `prompt-template-parse` at the tripwire — the check that exists because `node --check` cannot see a stray backtick. Flow's end review still caught it, so latency, not a hole. | Override arm now renders the task's commands **and** `renderEngineParseChecks`. Pinned by `test_flow_engine_override_still_runs_the_hardcoded_engine_parse_gate`, with a non-vacuity check against the pre-fix shape. |
| **D4** | The D8 completeness self-check was a real checklist in task and one sentence in flow. | The engine used for *larger* specs had the weaker completeness gate. | Task's step 5 copied verbatim into flow — stub forms enumerated, scoped `grep -nE` included. |
| **D5** | `flow.bailReasons[]` was read by flow only. | A project could not declare a project-specific immediate-bail reason for `/sdlc-task` runs, though bail classification is engine-agnostic. | Task now reads it. See the naming note below. |
| **D6** | `flow.testDepth` was read by flow only; task resolved `testDepthFlag \|\| 'fast'`. | `testDepth: full` was honoured by one engine and silently ignored by the other, though both accept `--test-depth`. | Task now reads it, same precedence: flag > config > `fast`. |
| **D7** | `filesReadKb` telemetry was task-only. Flow's rollup accepted the field but no flow prompt asked for it. | Flow's D15 input-cost estimate was systematically low. | Flow's implement prompt reports it; `recordFilesRead()` and the schema field added. |
| **D8** | Emoji-gate prose and the `allPassed` definition differed, though the executed Python was identical. | Cosmetic then — but it is the divergence class that becomes real the next time one side is edited. | Reconciled on task's more specific wording. |

**On the `flow` config block's name.** `testDepth` and `bailReasons` are now read by both engines,
so the block is misnamed. It was **not** renamed: six repos set it on disk today and one (`jynx`)
carries real project-specific `bailReasons` there, so a rename would silently drop them. Both
engines' source, both docs pages and `sdlc-task`'s SKILL.md say so explicitly; `autoMerge` and
`prBase` remain genuinely flow-only and `/sdlc-task` ignores them.

**What the two sync tripwires caught, which is the point of having them.** Re-stamping
`skill_sync_manifest.json` / `engine_docs_sync_manifest.json` was not a formality — the anchors
flagged four statements these changes made false: `sdlc-task.md`'s "there is no `harness.json`
config key for this — CLI-flag-only", `sdlc-flow.md`'s "its D16 derive path only derives from
`tasks.md`", the mirror of that claim on `sdlc-task.md`, and `sdlc-task`'s SKILL.md bail list
presenting five reasons as the complete set. Each was corrected before `--update` ran.

---

## 4. The one-off commands — RETIRED 2026-08-31

`/implement`, `/test`, `/fix`, `/review-task`, `/document`, `/process-tasks` and `/conditional_docs`
are **deleted**, along with `docs/workflows/commands.md` and their `.agents/skills/` mirrors. Run
[`/sdlc-task`](sdlc-task.md) or [`/sdlc-flow`](sdlc-flow.md) instead — they perform every one of
those stages against the current spec format with the gates wired in. `/update-docs` survives for
ad-hoc documentation work outside a run; `/patch`, `/review-PR` and `/close-out` are unaffected.

**Why they went rather than being repaired.** They were a hand-driven third copy of what the engines
already do, nobody was running them, and they had drifted onto an older data model — written against
`tasks.md` prose, never migrated through D45 (bare-array `tasks.json`) or D65 (block record as the
planning unit). Repairing all eight findings below would have meant maintaining that third copy
forever, which is the problem this whole page exists to remove.

The findings are kept because they are the argument for the decision, and because anyone tempted to
reimplement one of these commands should read what the last version got wrong.

| # | Drift | Consequence |
|---|---|---|
| **C1** | `/implement`, `/fix`, `/review-task`, `/document` all take `planning/<slug>/tasks.md` and read its `## Step-by-Step Tasks` prose. None of them mentions `tasks.json` or `planning/blocks/<id>.json`. | The manual ladder cannot drive a spec authored the way `/generate-tasks` authors one today. |
| **C2** | `/test`'s emoji gate is hardcoded to `main..HEAD` and is not scoped to this run's own commits. The engines scope to the commit SHAs recorded in `state.json`. | On any repo whose base branch is not `main`, or any shared branch with a concurrent session, `/test` fails on a diff it never produced — the exact bug the engines' scoping fixed. |
| **C3** | `/test` runs each check's `command` and ignores the D6 check *kinds* — `baseline-diff`, `warning-scan`, `skip-count-regression`, `count-delta`, `rule-scan` — which the engines' `renderCheckList` handles explicitly. It also ignores `gates`, `perTask`, and `fastCommand`. | A project using any non-plain check kind gets a wrong verdict from `/test`, silently. |
| **C4** | `/implement` has no post-commit work assertion (D81), no commit-safety guard, no D46 vault-commit step for its own code commit, and no D8 completeness self-check. | Every guard the engines added after a real incident is absent from the manual path. |
| **C5** | `/implement`, `/test`, `/fix`, `/review-task`, `/document` all instruct "record it the way `/sdlc-flow` and `/sdlc-task` do (D31)" and then write `sdlc/worklog.md`. **`/sdlc-task` has no worklog** (I4). | The stated contract is wrong for one of the two engines it cites. |
| **C6** | `/review-task` lacks flow's review-stage `localized` judgement and its IDENTITY INTEGRITY check (flagging a handle/URL that contradicts `CLAUDE.md`). | The manual review is weaker than the automated one it is meant to mirror. |
| **C7** | `/document` has no BOOTSTRAP mode and does not invoke the `write-repo-doc` skill; flow's docs stage does both (its step 2b and 3b). `/document` defers to `/update-docs`, which *does* carry the skill. | Reachable, but the manual path silently produces docs held to a lower standard unless the operator knows to run `/update-docs` first. |
| **C8** | `/process-tasks` derives eligibility from `planning/status.md` prose, not `state.json` `depends_on` edges. | Contradicts the standing rule that the graph is authoritative; it cannot see operator/approval/external gates at all. |

---

## 5. The shared master library

The drift above was all one structural problem: the same block authored twice, with nothing
comparing the copies. The fix is a single master copy plus a gate that proves the engines match it.

**How it works.** `.claude/workflows/prompts/shared.js` holds the master copy of every block that is
identical in both engines, each wrapped in `// <<shared:NAME>> … <</shared:NAME>>`. Both engines
carry the same markers around their own inlined copy.
[`scripts/build_engines.py`](../../scripts/build_engines.py) replaces each engine's marked region
with the library's version, **in place** — position is never changed, so `const` ordering and TDZ
behaviour are preserved exactly.

```
.claude/workflows/prompts/shared.js     the master copy — edit HERE
        │
        │  python3 scripts/build_engines.py --write
        ▼
.claude/workflows/sdlc-task.js   ──┐
.claude/workflows/sdlc-flow.js   ──┴─  self-contained, committed, shipped downstream
```

The engines stay self-contained because they must: the Workflow harness copies **one** `.js` per
engine into a per-session snapshot and executes that copy (standing rule 10), so `import` is not
available to them. Downstream repos receive the already-built engines and never run the build.

**The workflow.** Edit the block in `shared.js`, run `python3 scripts/build_engines.py --write`,
commit the library and both engines together. Editing an engine's inlined copy directly accomplishes
nothing — the next build overwrites it, and the gate fails until it does.

**Two gated checks:**

| Check | What it does |
|---|---|
| `engines-inlined` | Rebuilds both engines in memory and fails if either differs from disk by a byte. Also fails on an **orphan master** — a block in the library that no engine marks. |
| `build-engines-tests` | 17 fixtures over the builder: marker parsing and its refusals, drift inside an inlined region being caught, engine-local code and region *position* preserved, a marker with no master erroring rather than blanking the region, and the orphan-master case. |

> **Why the orphan check exists.** It was added because the failure happened. Landing cut 2, the two
> new masters went into the library while neither engine got the matching markers — so both engines
> called functions that were never inlined. `node --check` passes on that (the call is syntactically
> fine) and it would have thrown at run time. An orphan master is the more dangerous direction of
> the two: the block sits in the library looking authoritative while no engine contains it.

**The extraction was proved behaviour-neutral rather than assumed to be.** The first cut took the 23
blocks that were already byte-identical in both engines (~230 lines), and the engines after
extraction are byte-identical to the engines before it once the marker lines are stripped. Nothing
about what either engine does could have changed, because none of their executable bytes did. The
gate was also positively controlled: a simulated hand-edit inside an inlined region makes it exit 1.

**What is deliberately NOT in the library.** A block only belongs here while it is byte-identical in
both engines. Where they genuinely must differ — the run-root variable (`runDir` vs `worktreePath`),
worklog vs no worklog, review vs terminal reconcile — the block stays engine-local and is recorded
in §2 as intended. A shared library needing a per-engine flag every second line has not removed the
duplication, only moved it somewhere harder to read.

### Cut 2 — the two embedded scripts (2026-08-31)

Two blocks of **executable code** were duplicated in full, one copy per engine, byte-identical once
the run root is normalised:

| Master | Size | Was duplicated in |
|---|---|---|
| `renderEmojiGate({ runRoot, baseSha, stateFile, recordedCommitsJson })` | 36 lines of Python | both test prompts |
| `renderStateFlipScript({ runRoot, indent })` | 58 lines of Python | task's bookkeep, flow's wrap-up |

These matter more than their line count. They are not prose describing behaviour — they *are* the
behaviour: a gate that decides which diff to judge, and a validated read-modify-write of
`state.json` with byte-exact rollback. A divergence between two copies of either is a defect, not a
wording difference. `baseSha` is genuinely per-engine (setup-time HEAD for the lean engine, the PR
base for flow) so the master takes it as a parameter; `indent` exists only because the two prompts
nest the script at different depths.

Verified the same way as cut 1: each of the four call sites renders text byte-identical to what that
engine emitted before the change.

**A correction to what this section previously claimed.** The first version of this page said the
blocks differing "only by the run-root variable name" were the biggest remaining duplication. That
was wrong, and measuring it is what showed why: normalising the run root and engine name across all
27 differing blocks leaves only **two** that become identical, and both are statement-level, not
real shared blocks. The rest have small residual diffs — 3 to 12 lines — that are **accurate
engine-specific facts**, not drift:

- `STATE_WRITE_SCHEMA`, `TEST_SCHEMA`, `TRIAGE_SCHEMA` say "+ worklog.md" in flow. True there,
  false in task (I4).
- `TRIAGE_SCHEMA` calls the bail a "draft-PR handoff" in flow. Task opens no PR.
- `verifySetupBinding` says "in-place run" vs "branch-mode run" — each engine's own vocabulary.
- `STAGE_SCHEMA` carries `reportFile` in flow only.

Forcing these into the library would require either a conditional in every second line or making
one engine's schema description lie. **They stay engine-local**, and that is the library working as
designed rather than a gap in it.

### How much is actually shareable — measured per stage

Pairing each stage prompt across the two engines and normalising the run-root and engine names,
**75% of paired prompt lines are already common** (333 of 445). Per stage:

| Stage | task | flow | common |
|---|---:|---:|---:|
| implement / test | 90 | 91 | **96%** |
| triage | 38 | 38 | **100%** |
| state-load, detect-vault, resolve-repo-root, verify-setup-binding, baseline-snapshot | — | — | **100%** |
| derive-tasks-json (both variants) | 39–42 | 40–43 | **95%** |
| verify-vault-commit | 12 | 12 | 92% |
| harness-config | 20 | 20 | 85% |
| state-writer | 23 | 29 | 74% |
| setup | 133 | 65 | 29% — but see below |

### Why `setup` scores lowest, and why the number misleads

Three causes, and only the second is a real engine difference.

1. **Step renumbering, which dominates.** The same content sits at different step numbers — task's
   STEP 2b "Create the worktree" is flow's STEP 3, task's STEP 2c "Fix the planning/ symlink" is
   flow's STEP 3.5, task's STEP 4 "Report pipeline-start inputs" is flow's STEP 6. A line-order diff
   scores that as different. Measured **order-insensitively, setup is 61% shared, not 29%**. The
   sharpest case: the worktree-creation recipe (`a.`–`g.` — mkdir, `worktree add`, sparse-checkout
   cone, checkout, the `.env` copy loop, the guard-exempt init commit) is **18 lines in each engine
   and 94% identical**, and its *only* difference is the cross-reference "report them in STEP 4" vs
   "STEP 6".
2. **One genuinely different mode.** Task's non-worktree mode is three lines: use whatever branch you
   are on. Flow's branch mode is 41 lines that *create and check out* a new branch in the main tree,
   with a dirty-tree guard, a free-name search and a verify step — because flow terminates in a PR
   and needs a branch to open it from. This is real and stays engine-local.
3. **Different code organisation for identical information.** Flow factors its two modes into
   `worktreeRecipe` / `branchRecipe` consts; task inlines both in the prompt. Folding flow's consts
   back in moves the score only 29% → 30%.

**Step numbers are a coupling mechanism.** A shared block saying "report them in STEP 4" can only
live in one engine's numbering. Shared text should cross-reference steps by *name* — "the
pipeline-start-inputs step" — leaving numbering a per-engine concern.

### Cut 3 — the engine profile (planned)

The differing lines in the high-overlap stages fall into four classes, and only the last resists
sharing:

| Class | Example | Absorbable |
|---|---|---|
| Accidental wording | "the run root" vs "the worktree root"; "lean /sdlc-task pipeline" vs "/sdlc-flow pipeline"; a line-wrap difference | Yes — and several are simply wrong |
| Value substitution | `${baseSha}..HEAD` vs `${prBase}..HEAD` | Yes |
| A fact expressible as a noun | "Write ONE JSON file" vs "Write two files"; "state.json" vs "state.json + worklog.md"; "draft-PR handoff" | Yes |
| A whole structural step | flow's worklog append; the D63 augment-vs-substitute note | No — but as ONE named slot, not scattered |

So: an **engine profile** object per engine holding nouns only (`runRootLabel`, `stateArtifacts`,
`diffBase`, `name`), plus **named slots** where a whole step differs. The discipline that keeps this
from becoming the thing D83 warns against:

> A profile substitutes **nouns**. A slot inserts a **whole step**. Neither may contain
> `kind === 'flow' ? … : …` inside shared text. The moment a master needs to know which engine it
> serves in order to decide *logic*, the block belongs back in the engine.

**A live defect this surfaced.** Flow runs on a plain branch **by default**, yet eight prompt sites
tell the agent it runs "from the worktree root". In branch mode `worktreePath` *is* the repo root, so
those sites contradict flow's own `W` preamble, which correctly says "MAIN WORKING TREE, on branch
X". Nobody chose that; it is stale wording the profile's `runRootLabel` removes by construction.

### Cut 3 — landed 2026-08-31

Three stage prompts became masters, each behind named seams:

| Master | Was | Seams |
|---|---|---|
| `renderTriagePrompt` | 38 lines × 2, **zero** residual difference | `engineName`, `bailReasons`, `bailRecipe` |
| `renderTestPrompt` | 90 lines × 2, 96% common | `enginePhrase`, `runRootLabel`, `diffBase`, `emojiScopeNote` |
| `renderImplementPrompt` | 88 lines × 2, 94% common | `roleIntro`, `runRootLabel`, `extraReturnFields` |

Verified by **executing** both templates and comparing rendered output, not by diffing source — at a
parameterised seam the source *must* differ, so a textual compare cannot see through it. `/sdlc-task`
renders byte-identical in all three. `/sdlc-flow` differs in exactly two places, both deliberate: one
line-wrap point adopted from the task engine, and the implement prompt's opening sentence becoming
mode-aware.

**Three more stale-worktree sites fixed**, beyond the eight in the defect fix above: the implement
prompt's "you run IN PLACE in the shared worktree", `STATE_LOAD_SCHEMA`'s "read from the worktree",
and the review-fix prompt's wrapped "All Bash from the / worktree root". The second had been
classified in an earlier revision of this page as a legitimate engine difference. It was drift.

### The sync anchors had drifted, and the re-stamps were blessing it

Worth recording because it is a property of the tripwire design, not a one-off.

`skill-guide-sync` and `engine-docs-sync` anchor on **hand-picked line ranges**, and `--update`
re-hashes whatever currently sits at those numbers. Every extraction in cuts 1–3 shifted the file;
every `--update` dutifully re-stamped the *new* window. By the end, **five of the real anchors were
watching unrelated code**:

| Anchor | Was pointing at |
|---|---|
| `sdlc-task.js::isolation-and-branch-naming` | `postEmitHookRan` schema properties |
| `sdlc-task.js::bookkeep-vault-commit` | `const allTasks = enumResult.allTasks` |
| `sdlc-flow.js::isolation-and-branch-naming` | the PR schema's `isDraft` |
| `sdlc-flow.js::bookkeep-vault-commit` | the `BAIL_REASONS` array |
| `sdlc-flow.js::flags-and-defaults` | `verifyVaultCommit`'s closing lines |

Each would have reported green forever while the code it is named for changed freely. The script
already ships `--relocate` for exactly this (it finds an anchor's recorded hash at its new offset),
but it cannot recover once `--update` has stamped the wrong window — the recorded hash *is* the
wrong region by then. All five were re-picked from content and the doc sections re-verified.

**The guard added:** each anchor now declares an `EXPECT` marker — one distinctive line its range
must still contain — checked before any hash comparison. Drift is caught mechanically instead of by
someone thinking to look. Both fixture suites assert every real anchor declares a marker and still
brackets it.

> **If you move code near an anchor:** run `--relocate`, not `--update`. `--update` is only for
> "I re-read the guide and it is still accurate." Using it as a way to make a red check go green is
> how all five of these drifted.

### Remaining

The D46 vault-commit recipe (~20 lines, differs only by run root), `renderCheckList` (identical but
for the `/tmp` prefix, I1), `ENUMERATE_PROMPT` and the derive prompts, `harness-config` (85%), and
`setup`'s worktree-creation recipe (94%, needs its step cross-references de-numbered first). The
state-writer stays split at 59% — that gap is flow's worklog, a genuine difference (I4).

**Then `engine-rs`.** A port package is prepared and waiting at
[`planning/engine-rs-port/`](../../planning/engine-rs-port/index.md): per-stage four-bin
classification, Rust-ready text split STABLE/BODY for the cache breakpoint, the schema fields each
stage needs, token-cost estimates, test assertions, and a script that re-extracts the current JS
prompt so a stale quote cannot be ported by mistake. The ticket it serves is
`EN.ticket.prompt-parity-with-the-js-engines`.

`SDLC_FLOW` / `SDLC_TASK` consume the same masters — but by classification, not wholesale: environment and orientation text ports verbatim; an enforceable invariant becomes a
node rather than prose (engine-rs runs checks in Rust via `run_checks`, so re-prompting them would
move an enforced invariant back somewhere a model can ignore it); project-specific rules belong in
`harness.json` or `CLAUDE.md`; anything redundant with the JSON schema is dropped. Prompt text is
not free, and `STABLE_SYSTEM_PROMPT` is held byte-stable so it caches.

---

## Keeping this page true

This page is **not** covered by `scripts/check_engine_docs_sync.py` — that check hashes the
behaviour-defining regions of `sdlc-flow.md` and `sdlc-task.md`, not this register. Re-run the audit
by extracting each engine's prompt regions with the same opener/closer rule
`scripts/check_prompt_templates.py` uses, and diffing the shared stages side by side.
