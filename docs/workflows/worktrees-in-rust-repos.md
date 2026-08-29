---
type: Guide
title: Worktrees in Rust repos — the sibling-symlink convention
description: Why a `path = "../<crate>"` Cargo dependency cannot resolve from inside a worktree, and the sibling-symlink convention that fixes it.
doc_id: base-template-worktrees-in-rust-repos
layer: [factory]
project: base-template
status: active
keywords: [worktree, cargo, path dependency, symlink, trees, sibling repo, workspace]
related: [base-template-workflows-index, sdlc-task, sdlc-flow]
---

# Worktrees in Rust repos — the sibling-symlink convention

**New here? Read [`index.md`](index.md) first** — diagram and vocabulary.

## The symptom

You created a worktree with `/init-worktree` (or `git worktree add trees/<branch>`) inside a Rust
repo whose `Cargo.toml` has a `path = "../<crate>"` dependency on a sibling repo. Building or
running any cargo command inside that worktree fails to resolve the dependency — `cargo metadata`
or `cargo build` reports it cannot find the crate at the path the manifest names, even though the
same manifest builds fine from the repo root.

This does **not** mean the repo structurally cannot use worktrees. It means the worktree is
missing a symlink.

## Why it happens

A worktree lives one directory level deeper than the repo it was cut from:

```
<repo>/                          <repo>/trees/<branch>/
  Cargo.toml                       Cargo.toml   (checked out copy)
  ../<crate>/  ← resolves here     ../<crate>/  ← resolves to <repo>/trees/<crate>, NOT <repo>/../<crate>
```

`path = "../<crate>"` in the manifest is resolved relative to the manifest's own location. From
the repo root, `../<crate>` reaches the repo's parent directory — where sibling repos actually
live. From `<repo>/trees/<branch>/`, the exact same `../<crate>` instead reaches `<repo>/trees/`,
one level short of where the sibling repo is. There is nothing there unless something puts it
there.

## The fix

Place one symlink per sibling crate directly inside `<repo>/trees/`, named after the crate, and
pointing at the real sibling repo:

```bash
cd <repo>/trees
ln -s ../../<crate> <crate>
```

(`../../<crate>` because `trees/` is two levels below the sibling's actual location: one level
from `<repo>/trees/` back up to `<repo>/`, then one more to the repos' shared parent, where
`<crate>` lives beside `<repo>`.) Every worktree created under `trees/` after that shares the same
symlink — it is a property of `trees/` itself, not of any one branch.

## How to check an existing set

List what `trees/` already has, and what the manifest actually needs, side by side:

```bash
ls -l <repo>/trees/ | grep '\->'
grep 'path = "\.\./' <repo>/Cargo.toml
```

A complete set has exactly one `trees/` symlink per distinct sibling named in a `path = "../..."`
dependency. A worktree that fails to resolve one specific crate is missing that one symlink, not
necessarily the whole set.

## Worked examples

`core/engine-rs/trees/` carries symlinks for `claude-code-rs`, `mev` and `okf-core`.
`core/bastion/trees/` carries symlinks for `bella`, `claude-code-rs`, `engine-rs`, `mev` and
`okf-core`. These two are **instances of the convention, not the convention itself** — a new Rust
repo scaffolded from this template starts with no `trees/` symlinks at all and needs this same
treatment the first time someone cuts a worktree in it, whatever its own sibling dependencies turn
out to be.

## What this is NOT

This is unrelated to the vaulted `planning/` symlink (D46) that every scaffolded repo carries into
`_planning/<slug>/`. That symlink is repaired through a completely different mechanism and is
documented elsewhere — do not confuse the two when a worktree is misbehaving.

## The cost of not knowing

On 2026-08-23 a lane hit a failing worktree in this exact shape, concluded from it that the repo
structurally could not use worktrees at all, and spread that claim to two other lanes. It was
headed for a forced row in `/begin-orchestration`'s isolation table — permanent policy for every
future lane — before being retracted. The convention itself was never in question; only the
missing symlink was. This page exists so the next lane that hits the same failure finds the fix
instead of re-deriving the wrong conclusion.
