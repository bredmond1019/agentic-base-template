---
type: Guideline
title: Hosted CI for public repos
description: How the four reusable gate workflows work, how a repo opts in, and the actionlint -> act -> push local-validation loop.
doc_id: base-template-ci
layer: [factory, infra]
project: base-template
status: active
keywords: [CI, GitHub Actions, reusable workflows, actionlint, act, hosted runners, harness.json]
related: [base-template-docs-index, harness-json, D65-fleet-ci-split-by-visibility]
---

# Hosted CI for public repos

Every eligible public repo runs its own `planning/harness.json` gated checks on GitHub-hosted
runners, on push and pull_request, via a thin caller workflow that invokes a reusable workflow
owned by `base-template`. See [D65](../../docs/decisions/D65-fleet-ci-split-by-visibility.md) for
why public repos get hosted CI (private repos are out of scope for this block).

## The four reusable workflows

All four live in `base-template/.github/workflows/`, declare `on: workflow_call`, and mirror the
target stack's `harness.json` gates in declared order. They take repo-specific knobs as inputs
rather than hardcoding them, so one workflow file serves every repo on that stack.

| Workflow | Stack | Gates run (in order) | Key inputs |
|---|---|---|---|
| `gate-rust.yml` | Rust | `cargo fmt --check`, `cargo clippy`, test (`cargo test` or `cargo nextest run --workspace`), `cargo build --release` | `runs-on` (default `ubuntu-latest`), `clippy-args` (default `-- -D warnings`), `needs-nextest` (default `false`), `test-command` |
| `gate-python-uv.yml` | Python (uv) | the two `database` import probes, `ruff`, `pylint`, `pytest --collect-only`, `pytest` | `runs-on` (default `ubuntu-latest`) |
| `gate-flutter.yml` | Flutter | `dart format --output=none --set-exit-if-changed .`, `flutter analyze`, `flutter test --exclude-tags e2e` | `runs-on` (default `ubuntu-latest`) |
| `gate-node-docs.yml` | Node/docs (base-template itself) | `node --check` sweep over the four SDLC engines, `python3 scripts/test_sync_downstream_harness.py` | `runs-on` (default `ubuntu-latest`) |

`gate-rust.yml`'s `clippy-args` and `needs-nextest` exist because two repos deviate from the
default: `bella` needs `--all-targets` clippy, and `engine-rs` needs `cargo nextest run
--workspace` for its `test` gate.

## How a repo opts in

1. Add `.github/workflows/ci.yml` to the target repo (committed in **that repo's own git**, not
   HQ's — every eligible repo is gitignored from HQ).
2. Point it at the reusable workflow matching the repo's stack, e.g.:

   ```yaml
   name: ci
   on:
     push:
     pull_request:
   jobs:
     gate:
       uses: bredmond1019/agentic-base-template/.github/workflows/gate-rust.yml@main
       with:
         clippy-args: "--all-targets -- -D warnings"   # only if the repo deviates
   ```

3. Set any inputs the repo needs (runner OS, clippy args, `needs-nextest`) — do not fork the
   reusable workflow to add a one-off step; add an input instead.
4. Verify locally (see below) before pushing.

`base-template`'s own `ci.yml` calls `gate-node-docs.yml` via the local relative path
(`./.github/workflows/gate-node-docs.yml`) since it lives in the same repo; every other caller
references the reusable workflow by its full `owner/repo/path@ref` form.

## The local validation loop

Hosted minutes are not the place to debug a CI YAML typo. The loop, in order:

1. **`actionlint <file>`** — lints workflow YAML for schema errors, unknown contexts, and shell
   issues, with zero network calls. Run this first on every new or edited workflow file.
2. **`act --dryrun`** (or a full `act` run where the job can be exercised locally) — executes the
   workflow in Docker against the repo's own contents, catching logic errors `actionlint` can't
   see (missing files, wrong working directory, a gate that doesn't actually run).
3. **Push** — only after both of the above are clean.
4. **`gh run view --log-failed`** — if a hosted run still fails, pull just the failed job's log
   instead of scrolling the full run; rerun only the failed jobs, not the whole workflow.

`actionlint` and `act` are not installed by default: `brew install actionlint act`.

`act` is **not a perfect replica of a hosted runner** — Docker-based `act` runs can behave
differently around OS-specific tooling (notably Flutter, and anything macOS-only), and a real
hosted run may still be the first true green signal for those repos. Where a check could not be
verified locally, that is recorded explicitly in the Deviations table below rather than assumed.

## Deviations

Per-repo departures from the default reusable-workflow shape (runner OS, extra install steps, a
check that cannot run hosted or could not be verified with `act`), with the reason. Seeded empty —
populated as repos are wired up in later tasks of this block.

| Repo | Deviation | Reason |
|---|---|---|
| _none yet_ | | |
