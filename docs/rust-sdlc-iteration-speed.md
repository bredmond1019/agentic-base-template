---
type: Guide
title: Rust SDLC Iteration Speed
description: Why agent-driven Rust pipelines get slow (linking and a rotten target/, not testing) and the five measured fixes that reverse it — with the numbers from engine-rs.
doc_id: rust-sdlc-iteration-speed
layer: [factory, engine]
status: active
keywords: [rust, cargo, nextest, link time, sdlc, iteration speed, sccache, cargo clean]
related: [harness-json, using-the-template, brain:d57-rust-sdlc-iteration-speed]
---

# Rust SDLC Iteration Speed

**The one-line version: in an agent-driven Rust repo, the SDLC loop is slow because of LINKING and
a bloated `target/`, not because of testing. Measure before you tune, and fix those before you
weaken any check.**

End state in `engine-rs`: a full 1215-test suite runs in **2.8s**, and the per-task tripwire after
a real source edit is **6.4s** — down from ~3m10s.

This is the generalized playbook from a 2026-07-29 investigation in `core/engine-rs`, where
`/sdlc-flow` runs on a 10-task spec had grown to nearly two hours. Governed by
[D57](file:///Users/brandon/Dev/agentic-portfolio/docs/decisions/D57-rust-sdlc-iteration-speed.md).

---

## 1. Measure first — the ratio is the whole diagnosis

Before changing anything, get these four numbers. They take ten minutes and they decide everything
that follows:

```bash
# 0. Check for a rotten target/ FIRST — see 4b. This is often the whole answer.
du -sh target target/debug/incremental

# warm the tree first so you are measuring steady state, not a cold build
cargo check --workspace --all-targets

time cargo fmt --check                          # expect: <1s
time cargo clippy -- -D warnings                # tripwire (fastCommand) form — expect: seconds to tens of seconds
time cargo clippy --all-targets -- -D warnings  # authoritative (command) form, end-of-flow only — see D55
touch <the-crate-you-edit-most>/src/lib.rs
time cargo nextest run --lib --workspace        # the per-task tripwire cost
time cargo nextest run --workspace              # the end-gate cost
```

Now compare the **build** line cargo prints (`Finished ... in Xs`) against the **run** line nextest
prints (`Summary [Xs] N tests run`). In `engine-rs` that was:

| | |
|---|---|
| Running 1044 tests | **1.8s** |
| Everything else | **2m42s** |

When the ratio looks like that, every instinct to "run fewer tests" or "test at checkpoints instead
of per task" is aimed at the wrong thing. You would give up the per-task failure attribution that
makes a bounded fix loop work, and save almost nothing.

**The diagnostic question is not "are we testing too often?" but "why does each test run cost
minutes when the tests take seconds?"**

---

## 2. Fix 1 — one integration-test binary per crate (usually the biggest win)

cargo builds **a separate test binary for every `tests/*.rs` file**. Each one statically links your
crate plus its entire dependency graph. At 25 files x ~20MB, that was ~500MB of linking on every
full test run.

Collapse them into one binary:

```
crates/<crate>/tests/
├── it/
│   ├── main.rs          <- the only test target; `mod` declarations only
│   ├── feature_a.rs
│   └── feature_b.rs
└── fixtures/
```

`tests/it/main.rs`:

```rust
//! The single integration-test binary. Every file under `tests/it/` is a module of THIS binary.
//! Adding a test: create `tests/it/<name>.rs` and add one `mod <name>;` line below.
//! Do NOT add a new `tests/*.rs` file — that silently reintroduces a second binary.
mod feature_a;
mod feature_b;
```

`Cargo.toml` (the explicit target is required — module paths resolve relative to the target root):

```toml
[[test]]
name = "it"
path = "tests/it/main.rs"
```

**Measured effect** (`engine-core`, 25 files → 1 binary; on a bloated `target/` — see 4b, which
compounded further):

| | before | after |
|---|---|---|
| Full-suite build after a one-line edit | 2m24s | **35s** |
| Full-suite run | 58s | **2.2s** |
| Full suite, nothing changed | minutes | **2.9s** |

### The isolation caveat — this is safe ONLY under nextest

Merging binaries means merging processes **under `cargo test`**, where tests in one binary share a
process. Anything relying on process isolation (env vars, `set_current_dir`, global state, a
`static` singleton) can start interfering.

`cargo nextest run` executes **every test in its own process** regardless of binary packing, so the
collapse is behaviour-preserving there. Adopt nextest (fix 2) *before* collapsing, not after.

### Gotchas

- Fixture paths that are CWD-relative (`"tests/fixtures/x.json"`) still resolve — CWD is the crate
  root either way. Paths built from the *source file* location may need updating.
- A file with top-level inner attributes (`#![...]`) cannot become a module as-is.
- Leave cargo's `autotests` at its default. Setting `autotests = false` would make a stray
  `tests/foo.rs` silently *never run*, which is far worse than it silently building a second binary.
- Test paths change from `<binary>::<test>` to `<module>::<test>`; update any tooling that filters
  by binary name.

---

## 3. Fix 2 — `cargo nextest run`, never plain `cargo test`

Beyond enabling fix 1, nextest runs tests as parallel processes instead of libtest's
serial-per-binary model. Install with `brew install cargo-nextest`.

Make it stick, because agents default to `cargo test` from training data:

1. A numbered standing rule in the repo's `CLAUDE.md`.
2. A `PreToolUse` hook in `.claude/settings.json` that denies `cargo test` and explains the rewrite
   (with an escape hatch env var for the one task that owns full-suite validation).
3. `planning/harness.json` — **both** `command` and `fastCommand` on the `test` check. Changing only
   `fastCommand` leaves the end gate paying the full link tax, which is where 1–3 runs per flow go.

```json
{ "name": "test",
  "command": "cargo nextest run --workspace",
  "fastCommand": "cargo nextest run --lib --workspace",
  "purpose": "Test suite — AUTHORITATIVE for verdict", "gates": true }
```

---

## 4. Fix 3 — do not add `sccache` to a local agent loop

`sccache` is the reflexive "make Rust faster" answer and it is **wrong for this workload**. It
refuses to cache incremental compilations, and cargo passes `-C incremental` for the dev/test
profile — so every call falls through to plain rustc plus a wrapper hop.

Verify before believing any claim about it:

```bash
sccache --show-stats
#   Compile requests            25
#   Compile requests executed    0     <-- doing nothing
#   Cache hits                   0
```

`Compile requests executed: 0` means it is pure overhead. The two are mutually exclusive: making
sccache work requires `CARGO_INCREMENTAL=0`, which is the wrong trade for a loop that re-edits **one
crate 10–30 times in a row** — exactly what incremental compilation exists for.

Keep sccache for **cold CI builds** (no incremental state to reuse), set there via `RUSTC_WRAPPER`
plus `CARGO_INCREMENTAL=0` — never in a committed `.cargo/config.toml` a local loop reads.

Record the reasoning where the next person will look, or it gets re-added on the same intuition.

---

## 4b. Fix 3b — a rotten `target/` silently taxes every build (the sleeper)

This one was found last and turned out to be the largest single lever. Check it **first** on any
repo that has been iterated in for months:

```bash
du -sh target target/debug/incremental
```

In `engine-rs`: **40GB total, 17GB of it `incremental/`**. `cargo clean` reported
**930,599 files / 78.4GiB removed**. Cargo stats and fingerprints that tree on every invocation, and
incremental state accumulates across branches, rebases, and abandoned builds — none of it is ever
garbage-collected.

The result is counterintuitive enough to be worth stating plainly:

> After `cargo clean`, a **from-scratch cold build of the entire workspace took 48.9s** — while the
> *incremental* build after a one-line edit had been taking **2m24s** on the bloated tree. The cold
> build was nearly 3x faster than the incremental one it replaced.

Measured effect on `engine-rs` (this is *after* fixes 1–3 were already in):

| | before clean | after clean |
|---|---|---|
| Per-task tripwire (`--lib --workspace`, after an edit) | 1m17s | **6.4s** |
| Full suite, cold from scratch | — | **54s** (48.9s build + 2.2s run) |
| Full suite, steady state | 2.9s | 2.8s |
| `target/` size | 40GB | **1.7GB** |
| Disk free | 141GB | **179GB** |

`cargo clean` itself took 3m20s — almost all of it deleting 930k files. Budget for that once.

**Make it routine.** There is no cargo-native GC, so this needs a human or a cron habit: clean when
`target/` passes a few GB, or after any long-running branch/rebase-heavy stretch. `cargo-sweep`
(`cargo sweep --time 15`) automates the time-based version if you want it hands-off. On a machine
running scheduled builds (see `scripts/routine.sh`), fold it into the routine.

**Caveat on generalizing:** the exact multiplier depends on how bloated the tree got. The
directional finding — *a large stale `target/` makes incremental builds slower than cold ones* — is
what to carry forward, not the specific 12x.

## 5. Fix 4 — `[profile.dev]` link-time settings

```toml
[profile.dev]
# Keep panic/backtrace line numbers; drop full DWARF type descriptions (the biggest link-time cost
# for a type-heavy, generic-dependency-laden crate).
debug = "line-tables-only"
# Skip macOS's dsymutil debug-info-bundling pass (a slow post-link step, run once per binary).
split-debuginfo = "unpacked"
```

Backtraces still resolve. This compounds with fix 1 — fewer binaries, each cheaper to link.

---

## 6. Authoring-side: stop making non-code tasks pay for a compile

A `tasks.json` task that declares a non-empty `validation_commands` array runs **those commands
instead of** the project-wide gating checks as its per-task tripwire (`/sdlc-flow`, `/sdlc-task`).

```json
{ "task_id": 9, "title": "Document the feature", "files": ["docs/thing.md"],
  "validation_commands": ["test -f docs/thing.md", "grep -q '^type:' docs/thing.md"] }
```

Docs-only and config-only tasks cannot break a Rust build and should not pay minutes to validate a
paragraph. The end review still re-runs the full gating suite over the integrated tree, so this
changes only what the *tripwire* costs, never what is ultimately validated. Leave the array `[]` for
any task touching `.rs` files.

Related: task **boundaries have a price** in a compile-expensive repo. At ~1–3 minutes of link per
task, a 10-task spec spends materially more on gates than a 6-task one. Worth weighing during
`/generate-tasks` decomposition — though not at the expense of disjoint file ownership, which
matters more.

---

## 7. What NOT to do

- **Don't move to checkpoint-only testing.** The per-task tripwire's value is *attribution*: a
  failure at task 4 has one suspect and a live implementing context. The same failure surfacing at
  the end review has ten suspects, a fixed attempt budget, and a fresh agent — that is how a run
  bails. You would trade ~30 minutes of gate for a much worse tail.
- **Don't reach for `fastCommand` first.** It buys speed by accepting a weaker per-task signal. Fix
  the link cost first — it is a bigger win and costs no signal at all.
- **Don't drop `clippy` from the tripwire reflexively.** Measure it, and re-measure after the other
  fixes — the balance shifts. In `engine-rs` clippy went from ~13% of a 3m10s tripwire to ~75% of a
  26s one, purely because everything around it got faster. It still earns its place in the tripwire:
  it's cheap, and it catches real issues mid-task (`derivable_impls`) that would otherwise reach the
  end review as a blind pile. **That 18.9s/~75% figure describes the narrow lib+bins form only.**
  `cargo clippy --all-targets -- -D warnings` — needed to close the blind gate where test-only
  blocks shipped green over real lint violations (`mev`, `okf-core`, 2026-08-03) — is a separate,
  more expensive form: measured on `engine-rs` at ~9.61s warm vs. the narrow form's ~2.89s, a ~3.3x
  multiplier (~6.72s / ~26% of the 26s tripwire if it replaced the narrow form outright). Per
  [D55](file:///Users/brandon/Dev/agentic-portfolio/base-template/planning/decisions/D55-all-targets-clippy-placement.md),
  the wide form goes in the authoritative `command` only (end-of-flow review); the narrow form
  keeps its `fastCommand` seat in the per-task tripwire, so this bullet's original number and
  conclusion still hold for the tripwire specifically — revisit only if the narrow form itself
  becomes the thing you actually wait on.
- **Don't assume; measure.** Both `sccache` and "tests are slow" were confident, plausible, and
  wrong. Every number in this doc came from a command, not an intuition.

---

## 8. Checklist for a new Rust repo

- [ ] `brew install cargo-nextest`
- [ ] `tests/it/main.rs` layout + `[[test]]` target from the very first integration test
- [ ] `harness.json` `test` check: nextest in **both** `command` and `fastCommand`
- [ ] `harness.json` `clippy` check: `--all-targets -- -D warnings` in `command`, narrow
      `-- -D warnings` in `fastCommand` (D55)
- [ ] `build` check: `"perTask": false`
- [ ] `[profile.dev]` `debug = "line-tables-only"`, `split-debuginfo = "unpacked"`
- [ ] `CLAUDE.md` standing rule: nextest, never `cargo test` + the tests/it layout
- [ ] `PreToolUse` hook denying `cargo test`
- [ ] No `sccache` in `.cargo/config.toml`
- [ ] `validation_commands` set on docs-only / config-only tasks at `/generate-tasks` time
- [ ] `du -sh target` — clean it when it passes a few GB (no cargo-native GC exists)
- [ ] Re-measure the section-1 numbers once the repo has ~10 integration tests
