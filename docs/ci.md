---
type: Guideline
title: Hosted CI for public repos
description: How the four reusable gate workflows work, how a repo opts in, and the actionlint -> act -> push local-validation loop.
doc_id: base-template-ci
layer: [factory, infra]
project: base-template
status: active
keywords: [CI, GitHub Actions, reusable workflows, actionlint, act, hosted runners, harness.json]
related: [base-template-docs-index, harness-json, brain:D65-fleet-ci-split-by-visibility]
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
| `gate-rust.yml` | Rust | `cargo fmt --check`, `cargo clippy`, test (`cargo test` or `cargo nextest run --workspace`), `cargo build --release` | `runs-on` (default `ubuntu-latest`), `clippy-args` (default `-- -D warnings`), `needs-nextest` (default `false`), `test-command`, `sibling-repos` |
| `gate-python-uv.yml` | Python (uv) | the two `database` import probes, `ruff`, `pylint`, `pytest --collect-only`, `pytest` | `runs-on` (default `ubuntu-latest`) |
| `gate-flutter.yml` | Flutter | `dart format --output=none --set-exit-if-changed .`, `flutter analyze`, `flutter test --exclude-tags e2e` | `runs-on` (default `ubuntu-latest`) |
| `gate-node-docs.yml` | Node/docs (base-template itself) | `node --check` sweep over the four SDLC engines, `python3 scripts/test_sync_downstream_harness.py` | `runs-on` (default `ubuntu-latest`) |

`gate-rust.yml`'s `clippy-args` and `needs-nextest` exist because two repos deviate from the
default: `bella` needs `--all-targets` clippy, and `engine-rs` needs `cargo nextest run
--workspace` for its `test` gate.

`gate-rust.yml` also always installs `sccache` (`mozilla-actions/sccache-action`) before the
gate steps — every eligible Rust repo's `.cargo/config.toml` sets `build.rustc-wrapper =
"sccache"` for local dev speed, and without the binary present a hosted runner fails every
`cargo` invocation before fmt/clippy/test even run. `engine-rs` deliberately carries no such
config (see its own `.cargo/config.toml`), so the install step is a harmless no-op there.

`gate-rust.yml`'s `sibling-repos` input (newline-separated `owner/repo` list) checks out
additional repos one level above this repo's own checkout, for workspace members with a
cross-repo path dependency (e.g. `mev = { path = "../mev" }`). Several of the eligible Rust
repos are only buildable at all with this — a single-repo checkout cannot resolve their
manifests, hosted or local. See the Deviations table for which repos use it and why.

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
check that cannot run hosted or could not be verified with `act`), with the reason. Also carries
the two repos that are still red after real hosted runs, with why, per the Task 7 rule: if a gate
genuinely cannot run hosted (or is failing for a reason unrelated to the CI wiring itself), say so
explicitly rather than silently dropping it from the workflow.

**Hosted-run results (8/8 pushed and inspected; 6/8 green):**

| Repo | Result | Run |
|---|---|---|
| `mev` | green | after adding sibling-repo checkout |
| `bastion` | green | after adding sibling-repo checkout + a real toolchain-drift clippy fix |
| `bella` | green | first push |
| `claude-code-rs` | green | first push |
| `bastion-ui` | green | first push |
| `base-template` (`gate-node-docs.yml`, local caller) | green | first push |
| `engine-rs` | **red** | pre-existing failing test, unrelated to CI wiring — see below |
| `orchestrator` | **red** | pytest needs infra an isolated checkout doesn't have — see below |

| Repo | Deviation | Reason |
|---|---|---|
| `orchestrator` | not exercised with `act`; verified with `actionlint` only | `act --dryrun` cannot resolve the reusable `gate-python-uv.yml` reference until `base-template`'s CI workflows are pushed to `origin/main` (that push happens in a later task of this block) — confirmed by running `act --dryrun` locally, which fails with "no such file or directory" fetching the un-pushed reusable workflow from the remote. |
| `orchestrator` | **still red on a real hosted run** — 16 failed / 10 errors in `pytest` (the AUTHORITATIVE `test` gate) | Two independent, genuine infra gaps a single-repo checkout can't close, not a CI-wiring bug: (1) several tests need a live Postgres at `localhost:5432` (`sqlalchemy.exc.OperationalError: connection refused`) and hosted CI runs no DB service for this repo; (2) several more expect a brain root (`brain.toml`) and `planning/retrieval-golden-set.yaml` walked up from cwd — both live in HQ's `planning/` symlink target, which is gitignored from `orchestrator`'s own repo and so does not exist in an isolated hosted checkout. Standing up a Postgres service and fabricating brain fixtures inside a public repo's CI is out of scope for this block (Task 7 is push/confirm/record, not new test infrastructure) — recorded here rather than silently weakening `gate-python-uv.yml`'s `pytest` gate or dropping it. |
| `bastion-ui` | not exercised with `act`; verified with `actionlint` only | Same un-pushed-reusable-workflow gap as `orchestrator`, compounded by Flutter under `act` being unreliable in general (Docker-based act runs don't replicate the Flutter SDK toolchain well) — a real hosted run is expected to be the first true green signal for this repo. It came back green on the first push. |
| `mev` | opts into `sibling-repos: bredmond1019/okf-core` | `mev`'s `Cargo.toml` path-depends on `okf-core = { path = "../okf-core" }`. `okf-core` itself has no `harness.json` (excluded from this block's eligible-targets list) but is still a required build input — a single-repo checkout can't even run `cargo fmt`/`clippy` without it present, hosted or local. |
| `bastion` | opts into `sibling-repos` with **five** repos: `bella`, `mev`, `okf-core`, `engine-rs`, `claude-code-rs` | `bastion`'s `Cargo.toml` path-depends directly on `bella/crates/bella-engine`, `mev`, `okf-core`, and three `engine-rs` crates (`engine-serve`, `engine-contract`, `engine-core`). The fifth entry, `claude-code-rs`, is a **transitive** requirement: `engine-core` depends on it via `{ workspace = true }`, resolved from `engine-rs`'s own workspace root as `../claude-code-rs` — i.e. relative to `engine-rs`'s checkout, which lands it as a sibling of `bastion`'s checkout too once `engine-rs` is itself checked out one level up. Discovered by iterating on real hosted failures (`cargo metadata`/`cargo clippy` "unable to update" one repo at a time), not by static analysis up front — a reminder that a workspace's transitive path deps aren't visible from the top-level `Cargo.toml` alone. |
| `bastion` | one real source fix: `src/config.rs`'s `walk_up_from` changed from a `match` to `?` | Hosted CI's `dtolnay/rust-toolchain@stable` resolved rustc 1.97.1 / clippy 0.1.97 vs. this machine's locally-installed 1.95.0 / 0.1.95 — the newer clippy's `question_mark` lint fires on a pattern the older one didn't. Confirmed by reproducing clean on local `cargo clippy -- -D warnings` before the fix and clean after; behaviorally identical, not a lint suppression. Anticipated deviation was "may need `macos-latest`" (bastion is a macOS ops CLI) — that did **not** turn out to be needed; `ubuntu-latest` builds and tests it fine. |
| `engine-rs` | opts into `sibling-repos` with three repos: `claude-code-rs`, `mev`, `okf-core` | Same path-dependency shape as `mev`/`bastion` above — `engine-rs`'s workspace root path-depends on all three as `../<repo>` (`claude-code-rs` directly; `mev`/`okf-core` transitively surfaced the same way `bastion`'s `claude-code-rs` need did). |
| `engine-rs` | **still red on a real hosted run** — `cargo nextest run --workspace`, 1 of 1781 tests fails: `workflows::lead_ingest::tests::duplicate_post_does_not_create_a_second_document` (`assertion left == right failed: left: 2, right: 1`) | **Confirmed not a CI-wiring issue**: reproduced identically on a local run of the same test at the same commit (`cargo nextest run -p engine-core workflows::lead_ingest::tests::duplicate_post_does_not_create_a_second_document`) before any CI change was pushed. This is a pre-existing failing test in `engine-rs`'s own application code (a real dedup bug in the `lead_ingest` workflow, or a pre-existing test bug), unrelated to hosted-runner environment or this block's workflow wiring. Out of scope for a CI-infrastructure task to fix — flagged here per the "say so explicitly rather than silently dropping it" rule; `cargo nextest run --workspace` runs in full as `harness.json` declares, and this is what it genuinely finds. |
