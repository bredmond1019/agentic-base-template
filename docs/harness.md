---
type: Reference
title: "harness.md: gated-check verdict scoping for fleet-shared data"
description: "The rule for any gated check whose input is fleet-shared state: attribute the gating VERDICT to this repo's own subtree while still REPORTING everything the scan finds."
doc_id: harness-verdict-scoping
layer: [factory]
project: base-template
status: active
keywords: [gated checks, verdict scoping, delta attribution, fleet-shared state, D64, ownership, harness]
related: [harness-json, brain:D64-push-gate-delta-attribution, base-template-docs-index]
---

# Gated-check verdict scoping for fleet-shared data

A rule for anyone writing or reviewing a gated check whose input is data shared across the whole
fleet — a lane registry, a repo lease, a message queue, a live-config census — rather than data
scoped to this repo alone.

## What this page is for

Some checks read data the **whole fleet** writes — a lane registry, a repo lease, a message queue.
Run naively, such a check fails your repo because a *different* repo left a bad record, so a lane
goes red for something it cannot fix. This page is the rule that prevents that, and the FAIL-line
format every check must use.

Read it before writing or reviewing a gated check whose input is not scoped to this repo. For the
list of checks that already exist, see [gates.md](gates.md).

## Quickstart

Writing a check that reads fleet-shared data? It must do all three, in a **terminal**-runnable
script:

```
python3 scripts/check_lane_agents.py --quiet   # a worked example of all three
```

1. **Scan fleet-wide** — read every record, from every repo.
2. **Report everything** — print another repo's bad record; that is how it gets fixed.
3. **Fail only on your own** — attribute by the record's own `repo` field, never by path.

Every failure line reads `FAIL <path> <text>` — the path names the **artifact**, not the test.
The [`failure-output-shape`](gates.md) gate enforces this.

## The rule

**A gated check that reads fleet-shared state attributes its gating VERDICT to this repo's own
subtree, while still REPORTING everything the scan finds.**

- The **scan stays fleet-wide.** Read every record, from every repo, the same as before.
- Only the **verdict narrows.** A malformed or stale record belonging to another repo is printed —
  it must still be visible, because surfacing it is how it ever gets fixed — but it does not fail
  this repo's run.
- A malformed or stale record belonging to **this repo** still fails the verdict. A check that fails
  on nothing is not a check.
- **Attribution is by ownership of the record — its own `repo` field — never by path scoping of the
  scan.** Path scoping (only reading records that happen to sit under this repo's own directory)
  would silently narrow what gets reported too, which defeats the point: the whole reason to keep
  scanning fleet-wide is so a foreign break is still caught and reported by *someone's* run, even
  though it does not block that run.

## Why: this is the Test-stage counterpart of HQ D64

HQ D64 (`agentic-portfolio/docs/decisions/D64-push-gate-delta-attribution.md`)
already settled this question for the push gate: `hooks/pre-push` validates the whole corpus, but
blocks only on errors new since this clone's last successful push — "attribution is by delta, never
by path," because deleting a doc can surface the resulting error on a file the push never touched, and
a path-scoped gate would wave that straight through.

The SDLC engines' Test stage never inherited that principle, and every lane's `planning/` is a
symlink into one shared vault, so any gated check can *reach* fleet-wide state whether or not it
should be judged by it. Three checks were found bailing lanes on other lanes' data this way —
`message-schema`, `lane-agent-schema`, and `harness-schema-realpath` — in every case failing a lane
that could not itself fix the record. This document states the fix once, as a pattern, so the next
fleet-reading check inherits it instead of repeating the same measured failure. Full instance-by-
instance evidence: `planning/blocks/BT.ticket.fleet-wide-gates-red-on-another-lanes-data.json`.

## For the next fleet-reading check

If a new gated check reads any file outside this repo's own `planning/`/`docs/` tree — a registry,
a lease, a queue, a cross-repo census, or anything else that another lane's session can write —
implement it this way:

1. Resolve "this repo" once (the check's own repo slug — e.g. via `brain.toml`'s `[[repos]]` table),
   fail closed if it cannot be resolved (never silently treat "unknown" as "not foreign").
2. Keep the scan over the full fleet-shared dataset.
3. Report every finding, foreign or not.
4. Compute the gating exit status from only the findings whose record's own `repo` field matches this
   repo.
5. Test both directions explicitly: a foreign bad record must be reported and non-fatal; an own bad
   record must still be fatal. A test suite that only proves the first direction cannot tell you the
   check still catches anything.

See [`scripts/check_lane_agents.py`](../scripts/check_lane_agents.py) and [`scripts/check_messages.py`](../scripts/check_messages.py) for a worked implementation
(`resolve_own_repo`, `is_foreign`), and their test files for the both-directional fixtures.

## The FAIL line format (BT.ticket.checks-must-name-their-failing-artifact)

**A gated check reporting a failure prints a line of the shape:**

```
FAIL <path> <human text>
```

`FAIL` is the literal first token. `<path>` is the second token — a repo-relative or absolute path
to the artifact that broke (the file/record the check was validating), with no internal
whitespace, so a parser can split on the first two tokens and treat the remainder as free-form
text. When a check has genuinely no artifact to name for a given failure, it emits the explicit
`<no-artifact>` token in the path position — never a guessed or fabricated path, and never silent
omission of the field.

The reference implementation is [`scripts/check_lane_agents.py`](../scripts/check_lane_agents.py), which already emits this shape —
one `FAIL <path>` line per bad record, e.g.:

```
FAIL .fleet-locks/lane-agents/agent-agentic-portfolio-01.json
       stale registry claim: agent `agentic-portfolio-01` heartbeat is 6439s old (threshold 5400s)
```

(the human text may wrap onto indented continuation lines, as `check_lane_agents.py` does; a
parser only needs the first `FAIL <path>` line per finding.) The format was chosen to match this
script exactly, so it is also the regression fixture: `check_lane_agents.py`'s output must never
change shape as other checks are brought into conformance.

Anything that parses check output against this contract — the SDLC engines' Test stage,
`hooks/pre-push` stage 2, and `BT.ticket.bails-must-be-append-only`'s bail record
`failing_artifact` field — reads this line. `scripts/check_failure_output_shape.py` is the gate
that enforces it: it drives each registered check against a known-bad fixture and asserts the
output carries a parseable `FAIL <path>` (or `FAIL <no-artifact>`) line.

### Per-check audit (2026-08-24)

Audited every check registered in `planning/harness.json` (45 total) against the format above.

**Conforms today** — already emits `FAIL <path>` on a real failure:

| Check | Script |
|---|---|
| `lane-agent-schema` | [`scripts/check_lane_agents.py`](../scripts/check_lane_agents.py) (the reference) |
| `block-record-schema` | `scripts/check_block_records.py` |
| `lane-record-schema` | `scripts/check_lane_records.py` |
| `message-schema` | `scripts/check_messages.py` |
| `command-hazards` | `scripts/check_command_hazards.py` |
| `command-docs-no-write-path` | `scripts/check_command_docs_no_write_path.py` |

**Can be made to conform** — already names the offending path in its failure output, just not
under the `FAIL <path>` prefix; a mechanical rewrite of the print statement is sufficient:

| Check | Script | Current shape |
|---|---|---|
| `frontmatter-presence` | `scripts/check_frontmatter_presence.py` | `{path}:1: ABSENT — ...` |
| `block-naming-guard` | `scripts/check_block_naming.py` | `blocking (this repo): {dir}: does not match ...` |
| `skill-guide-sync` | `scripts/check_skill_sync.py` | `- {engine_file} [{anchor}] -> review {skill_file}: {reason}` |
| `engine-docs-sync` | `scripts/check_engine_docs_sync.py` | `- {engine_file} [{anchor}] -> review {docs_md} {section}: {reason}` |
| `prompt-template-parse` | `scripts/check_prompt_templates.py` | `ERROR: {rel} not found` / failure list keyed by path |
| `worked-example-lane-gate` | `scripts/check_worked_example_lane.py` | `FAIL: {text}` — has the `FAIL` token but the path (when present, e.g. `args.command`) is not reliably the second token |

**Genuinely cannot name a single artifact path, by design** — the check's failure is about a
directory, an engine string, or a shell exit code, not a file it read; these emit `FAIL
<no-artifact> <text>`:

| Check | Script | Why no artifact |
|---|---|---|
| `engines-parse` | `node --check` over `.claude/workflows/sdlc-*.js` | the failing artifact IS the engine file, already reported by `node`'s own error; no further mapping needed beyond passing that path through |

**Test suites (`test_*.py`, `--self-test` runners)** — the remaining 27 registered checks
(`sync-guard-tests`, `tier-spec-resolution-tests`, `skill-sync-tripwire-tests`,
`engine-docs-sync-tests`, `d16-tasks-json-fallback-tests`, `emoji-gate-diff-scoped-tests`,
`prompt-template-tests`, `orchestration-run-contract-tests`, `consolidator-discovery-tests`,
`roadmap-status-discovery-tests`, `state-write-validation-tests`, `harness-schema-realpath`,
`ungateable-criteria-rule-tests`, `validation-commands-override-tests`,
`check-block-records-tests`, `engine-parse-gate-extension-filter-tests`,
`fleet-concurrency-check-tests`, `extraction-port-gate-rule-tests`, `check-lane-records-tests`,
`resume-task-state-merge-tests`, `block-close-decision-tests`, `commit-safety-guard-tests`,
`check-lane-agents-tests`, `git-env-strip-tests`, `check-messages-tests`,
`commander-drain-tests`, `command-docs-no-write-path-tests`,
`work-assertion-tests`, `bails-record-tests`, `bail-path-runtime`) are unit-test suites over the
checker scripts themselves, run against synthetic fixtures rather than fleet artifacts. A failure
is a Python `AssertionError`/traceback, which already names the failing test file and line — the
same class of problem `cargo nextest`-backed checks have (a test name, not a file the test read),
addressed by `scripts/nextest_artifact_wrapper.py` (task 3). This ticket's `out_of_scope` excludes
changing what any check considers a failure; routing these through an equivalent wrapper (mapping
a failing Python test to the fixture path it exercised, or `<no-artifact>` when that mapping is
unavailable) is follow-on work for task 3, not a new finding — noted here so the audit is
complete.
