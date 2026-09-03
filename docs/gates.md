---
type: Reference
title: The gates — every check base-template runs on itself
description: 54 of base-template's gated checks in planning/harness.json, what each one protects, and how to run one on its own. The harness itself carries 71 gating of 73 as of 2026-09-03 — see the drift note below.
doc_id: base-template-gates
layer: [factory]
project: base-template
status: active
keywords: [gates, harness, checks, validation, tripwire, regression]
related: [base-template-capabilities, harness-json, base-template-docs-index, harness-verdict-scoping]
---

# The gates

What "passing" means in this repo. This page lists 54 checks, all of them gating — one red check
fails the run. `planning/harness.json` itself carries **71 gating of 73 total as of 2026-09-03**
(`python3 -c "import json;print(sum(1 for c in
json.load(open('planning/harness.json'))['validation']['checks'] if c.get('gates')))"`); this page
has drifted **17** checks behind and needs a full catch-up pass, tracked as a `carryover[]` entry
rather than fixed here (out of scope for a surgical `/close-out` patch — see
[harness-json.md](harness-json.md) for the schema and how to configure your own).

Four of the newest are from `BT.chore.harness-*` / `BT.chore.agents-md-is-canonical` (2026-09-03):
`sync-skills-tests`, `agent-docs`, `agent-docs-tests` (all gating) and `global-skills-fresh`
(**non-gating**, because a global install is per-machine and a CI checkout has none — the same
reason `toolchain-freshness` does not gate). Note this page's "all of them gating" line is now
false for that one: run the command above rather than trusting the sentence.

## What this page is for

`base-template` ships no application, so its gates are almost entirely **tripwires on itself**:
they catch a harness change that would silently corrupt a real run in a downstream repo. Two
things read the same list — the engines' Test stage and the push gate — so a check here is not
advisory.

You are on this page because a check went red and you want to know what it protects, or because
you added a capability and need to know where its guard belongs.

## Quickstart

All commands below are **terminal** commands, run from the repo root.

```
# run one check
python3 scripts/check_block_records.py --quiet

# see the full authoritative list (this page is a convenience copy)
python3 -c "import json;print('\n'.join(c['name'] for c in json.load(open('planning/harness.json'))['validation']['checks']))"
```

Two traps that have cost real time here:

- **A piped command's exit code is the pipe's, not the check's.** `python3 scripts/x.py | tail`
  reports success while the script exits 1. Redirect to a file, then check `$?`.
- **`planning/harness.json` is the authority, not this page.** If they disagree, the JSON wins
  and this table is what needs fixing.

## How to read the table

Rows ending `-tests` are **fixture suites guarding another check** — they prove the checker can
still fail, so the tripwire cannot rot into a no-op. If one of those goes red, the checker's own
logic broke, not the thing it inspects.

## Corpus and record shape

These check that files on disk have the shape the rest of the system assumes.

| Check | Protects | Run |
|---|---|---|
| `frontmatter-presence` | Every corpus `.md` in this repo opens with OKF frontmatter, unterminated or displaced included. A displaced block fails all four `validate-brain` flags at once and reads as a corpus-wide regression. | `for f in $(git ls-files -- '*.md'); do python3 scripts/check_frontmatter_presence.py "$f" < "$f" \|\| exit 1; done` |
| `block-naming-guard` | The `<REPO>.<phase>.<block>` block-ID convention. Scans the fleet, but the verdict is scoped to this repo. | `python3 scripts/check_block_naming.py` |
| `block-record-schema` | Block records under `planning/blocks/` satisfy `block.schema.json`. | `python3 scripts/check_block_records.py --quiet` |
| `check-block-records-tests` | Fixtures over `check_block_records.py`'s `spec_dir` rule. | `python3 scripts/test_check_block_records.py` |
| `sdlc-workflow-required-tests` | `sdlc_workflow` stays a required, enum-checked field on a block record. | `python3 scripts/test_sdlc_workflow_required.py` |
| `lane-record-schema` | Every `lane-<name>.json` validates against `lane.schema.json`, in both the roadmap and legacy layouts. | `python3 scripts/check_lane_records.py --quiet` |
| `check-lane-records-tests` | Positive and negative fixtures for the lane-record checker. | `python3 scripts/test_check_lane_records.py` |
| `worked-example-lane-gate` | The worked lane example inside `generate-roadmap.md` still validates — a doc example that no longer parses teaches the wrong shape. | `python3 scripts/check_worked_example_lane.py` |
| `lane-agent-schema` | Registry claims and repo leases validate, and no two lanes claim the same exclusive lease. | `python3 scripts/check_lane_agents.py --quiet` |
| `check-lane-agents-tests` | Fixtures for the lane-agent checker, including stale-heartbeat and duplicate-lease cases. | `python3 scripts/test_check_lane_agents.py` |
| `message-schema` | Cross-lane messages match `message.schema.json` — five-kind enum, no priority field, `durable_home` present. | `python3 scripts/check_messages.py --quiet` |
| `check-messages-tests` | One positive round-trip per message kind plus five negative fixtures. | `python3 scripts/test_check_messages.py` |
| `escalations-schema` | Every roadmap's `escalations.jsonl` matches `escalation.schema.json`. | `python3 scripts/check_escalations.py --quiet` |
| `escalations-schema-tests` | Fixtures for the escalation checker, one per failure mode. | `python3 scripts/test_check_escalations.py` |
| `task-gate-boundaries` | No task's `validation_commands` quietly narrows a `gates: true` harness check. | `python3 scripts/check_task_gate_boundaries.py` |
| `task-gate-boundaries-tests` | Fixtures for the task-gate-boundary checker. | `python3 scripts/test_check_task_gate_boundaries.py` |

## Engine integrity

The two engines are the highest-blast-radius files in the repo: a bad edit here misfires git
state in every downstream repo. These are the guards.

| Check | Protects | Run |
|---|---|---|
| `engines-parse` | Both engines parse. The only build gate this docs/JS repo has. | `for f in .claude/workflows/sdlc-task.js .claude/workflows/sdlc-flow.js; do node --check "$f" \|\| exit 1; done` |
| `prompt-template-parse` | Each agent-prompt template literal parses **in isolation**. A stray backtick pairs up across lines, so `node --check` passes while the template boundaries silently shift — this shipped once and removed both engines from the registry. | `python3 scripts/check_prompt_templates.py` |
| `prompt-template-tests` | Fixtures proving the template detector can still fire. | `python3 scripts/test_check_prompt_templates.py` |
| `engine-parse-gate-extension-filter-tests` | The engine-parse gate's `.js`-only extension filter, extracted from live engine source. | `python3 scripts/test_engine_parse_gate_extension_filter.py` |
| `skill-guide-sync` | Drift tripwire between the engines and their Gemini-facing `SKILL.md` replication guides. Red means "go re-verify the guide", not "the guide is wrong". | `python3 scripts/check_skill_sync.py` |
| `skill-sync-tripwire-tests` | The skill-sync hashing/manifest logic itself. | `python3 scripts/test_check_skill_sync.py` |
| `cli-invocations` | Detection before authoring: a `mev`/`bastion` verb or flag named in `.claude/`/`.agents/` prose that the installed binary doesn't actually define. | `python3 scripts/check_cli_invocations.py` |
| `cli-invocations-tests` | Fixtures for the verb/flag gate, including the false-positive class its first regex draft produced. | `python3 scripts/test_check_cli_invocations.py` |
| `engine-docs-sync` | Same tripwire for the prose pages `docs/workflows/sdlc-task.md` and `sdlc-flow.md`. | `python3 scripts/check_engine_docs_sync.py` |
| `engine-docs-sync-tests` | The engine-docs-sync hashing/manifest logic itself. | `python3 scripts/test_check_engine_docs_sync.py` |
| `state-write-validation-tests` | The validate-then-commit contract: an engine never commits a `state.json` it has not validated. | `python3 scripts/test_state_write_validation.py` |
| `commit-safety-guard-tests` | An engine cannot commit an empty tree in a worktree run. | `python3 scripts/test_commit_safety_guard.py` |
| `git-env-strip-tests` | The nine-variable `GIT` environment strip both engines prefix their git calls with. | `python3 scripts/test_git_env_strip.py` |
| `worktree-setup-binding-guard` | Both engines resolve `repoRoot` once in the engine, so a worktree run cannot adopt the brain root as the repo root. | `python3 scripts/test_worktree_setup_binding_guard.py` |
| `work-assertion-tests` | A run must prove its commits actually contain the work. | `python3 scripts/test_work_assertion.py` |
| `bails-record-tests` | `bails[]` is append-only — a retried bail is annotated, never erased. | `python3 scripts/test_bails_record.py` |
| `bail-path-runtime` | The bail path never mints `new Date()` inside a runtime that must stay deterministic. | `python3 scripts/test_bail_path_runtime.py` |
| `resume-task-state-merge-tests` | `--resume` merges the prior tasks map forward instead of re-initialising it. | `python3 scripts/test_resume_task_state_merge.py` |
| `block-close-decision-tests` | A block closes only on a genuinely complete run, not on a resume that landed one last task. | `python3 scripts/test_block_close_decision.py` |
| `post-emit-hook-tests` | The optional `postEmitCommitCommand` hook: absent key is a no-op, a failure is reported and never swallowed. | `python3 scripts/test_post_emit_hook.py` |
| `d16-tasks-json-fallback-tests` | Both engines derive `tasks.json` from `tasks.md` instead of bailing, in a D45-conformant shape. | `python3 scripts/test_d16_tasks_json_fallback.py` |
| `tier-spec-resolution-tests` | The tier-spec resolution rule (root-only, tier-only, both-present-root-wins, neither). | `python3 scripts/test_tier_spec_resolution.py` |
| `validation-commands-override-tests` | A per-task `validation_commands` override augments the project's gating checks — it never skips them. | `python3 scripts/test_validation_commands_override.py` |

## Authoring rules

These fire on *what a command or spec says*, not on code — the rules that keep an authored
artifact from producing a confident, silent false pass.

| Check | Protects | Run |
|---|---|---|
| `command-hazards` | Two command shapes that silently false-pass here: a negated invocation of a non-POSIX tool, and its siblings. | `python3 scripts/check_command_hazards.py --quiet` |
| `command-docs-no-write-path` | No command or skill instructs an agent to run the write-and-push wrappers directly. | `python3 scripts/check_command_docs_no_write_path.py --quiet` |
| `command-docs-no-write-path-tests` | Fixtures for that checker, including the real regression it was written for. | `python3 scripts/test_check_command_docs_no_write_path.py` |
| `lease-steps-contract` | Steps 3/4 of `/begin-orchestration` (both copies) name the E_QUIESCE_LEASE_HELD quiesce consequence, `--agent` as the holder's self-exemption, and the absent-scope-means-repo rule — not the false "refuses every other agent" claim. | `python3 scripts/test_lease_steps_contract.py` |
| `ungateable-criteria-rule-tests` | The un-gateable-acceptance-criteria rule in `/ticket` and `/generate-tasks` still fires on undeclared external evidence. | `python3 scripts/test_ungateable_criteria_rule.py` |
| `extraction-port-gate-rule-tests` | The extraction/port-block authoring rule in `block-registration.md`. | `python3 scripts/test_extraction_port_gate_rule.py` |
| `emoji-gate-diff-scoped-tests` | The emoji gate stays scoped to the diff, not the whole tree. | `python3 scripts/test_emoji_gate_diff_scoped.py` |
| `failure-output-shape` | Every registered check names the **file** it failed on, in `FAIL <path> <text>` form. | `python3 scripts/check_failure_output_shape.py` |
| `nextest-artifact-wrapper-tests` | The nextest wrapper that turns a test name into the corpus path the test actually read. | `python3 scripts/test_nextest_artifact_wrapper.py` |

## Fleet coordination

Checks over the machinery that lets several lanes run at once without colliding.

| Check | Protects | Run |
|---|---|---|
| `sync-guard-tests` | The engines-only sync guard: the brain root never receives `commands/*.md`, while normal repos still do. | `python3 scripts/test_sync_downstream_harness.py` |
| `harness-schema-realpath` | `harness.schema.json` resolves through the `planning/` symlink correctly, fleet-wide. | `python3 scripts/test_harness_schema_realpath.py` |
| `fleet-concurrency-check-tests` | The two-heavy-repos rule: third lane refused, clean release, stale-entry expiry, graceful degradation. | `python3 scripts/test_fleet_concurrency_check.py` |
| `orchestration-run-contract-tests` | The run-record contract — one record per `(repo, roadmap)`, addressed rather than rotated. | `python3 scripts/test_orchestration_run_contract.py` |
| `consolidator-discovery-tests` | The consolidator's selection invariants across repos. | `python3 scripts/test_consolidator_discovery.py` |
| `roadmap-status-discovery-tests` | The `/roadmap-status` join: realpath dedup, liveness from `updated_at` and never from `status` alone. | `python3 scripts/roadmap_status_discovery.py --self-test` |
| `commander-drain-tests` | `commander_drain.sh`'s commit scope and orphan routing, with git and `bastion` shimmed so nothing is committed. | `scripts/test_commander_drain.sh` |

## See also

- [capabilities.md](capabilities.md) — everything the factory can do, and how to invoke it.
- [harness-json.md](harness-json.md) — the `harness.json` schema, stack profiles, and how to add a check.
- [harness.md](harness.md) — why a fleet-reading check scopes its **verdict** to this repo while scanning fleet-wide.
- The `run-the-gates` skill (`.claude/skills/run-the-gates/SKILL.md`) — how to run these and trust the answer.
