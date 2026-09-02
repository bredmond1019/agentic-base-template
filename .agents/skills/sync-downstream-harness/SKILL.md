---
name: sync-downstream-harness
description: >
  Runs scripts/sync_downstream_harness.py to copy changed .claude/commands/*.md + .claude/workflows/ files into every repo scaffolded from base-template, reports what changed per repo, and can commit both halves (--commit) across the repo and the brain vault.
---

# sync-downstream-harness — Pull the harness into every scaffolded repo

Automates the manual "update loop" `docs/using-the-template.md` §6 describes: copies base-template's
current `.claude/commands/*.md` (flat root only — never `.claude/commands/brain/`) and
`.claude/workflows/` (the SDLC engines + `templates/`) into every repo discovered via `brain.toml`
that already has its own `.claude/workflows/` directory. Never deletes a repo's own customizations
(e.g. `feature.md`). See `planning/decisions/D48-downstream-harness-sync-script.md` for why this
exists — `.claude/workflows/*.js` has no equivalent of `/sync-global-commands`' global install path,
so a harness fix here doesn't reach a downstream repo until this runs.

## Variables

$ARGUMENTS — optional flags, space-separated:
- `--repo <slug>` — limit to one repo (repeatable: `--repo bastion --repo mev`). Default: all
  eligible repos.
- `--apply` — write changes. Default is dry-run (report only, nothing written).
- `--message "<text>"` — description recorded in each synced repo's `planning/.template-version`,
  and used as the commit subject under `--commit`. Default: `"harness pull"`. Use something
  specific (e.g. the decision id driving the pull).
- `--commit` — after applying, commit each repo's own half and make one brain commit for all the
  `planning/.template-version` stamps. **Requires `--apply`**; passing it alone is a usage error
  and exits 2. See step 5.
- `--commit-pending` — widen `--commit`'s pathspec to every base-template-**owned** path the repo
  has dirty, not only what this run wrote. **Requires `--commit`.** The catch-up case: an earlier
  `--apply` that was never committed leaves files that are current on disk and unrecorded in git,
  and they never appear in a dry run because their content already matches. Ownership is computed
  from the same source sets `--apply` writes from, so a repo's own file is never swept in; an owned
  path whose content *differs* from base-template is **withheld and reported**, never staged under a
  "sync base-template" subject. Measured 2026-09-02: 103 such paths across 18 repos.

## Instructions

1. **Guard — confirm you are in the base-template root.**

   Run:
   ```bash
   test -f .claude/workflows/sdlc-flow.js && echo "Guard: OK — running from base-template root" || echo "ABORT: .claude/workflows/sdlc-flow.js not found. Run this command from the base-template root."
   ```
   (This used to test for `sdlc-run.js`, which was retired — the guard aborted on every run.)

2. **Dry run first, always** — even if `$ARGUMENTS` includes `--apply`, run once without it first
   so the report is visible before anything is written:
   ```bash
   python3 scripts/sync_downstream_harness.py <$ARGUMENTS minus --apply, if present>
   ```
   Read the per-repo file list. If a repo shows an unexpectedly large diff (e.g. hundreds of lines
   in one engine file), that's very likely just a stale repo catching up several pulls at once —
   confirmed harmless in practice (D48's provenance) via `diff <target file> <base-template file>`
   showing the sync produces a byte-identical copy, not corruption. Flag it in the report either way.

3. **Guard — check for a live orchestration lane before applying.** This overwrites
   `.claude/workflows/*.js` in every synced repo. If a lane is mid-flight in one of them, its
   engine file changes underneath the process already executing it — that has happened. If either
   check shows a live lane in a repo this run would touch, **stop and do not pass `--apply`** until
   it finishes or the operator confirms it is safe:
   ```bash
   python3 scripts/fleet_concurrency_check.py status
   grep -l 'lifecycle: active' planning/orchestration-run/*/notes.md 2>/dev/null
   ```
   The first prints the registry as JSON — `active` lists registered lanes, `exclusive_leases` the
   held repo locks (D61); both empty means nothing is live. The subcommand is `status`; there is no
   `list`. Run the second inside each target repo too, not only here.

4. **If `--apply` was requested, run it for real:**
   ```bash
   python3 scripts/sync_downstream_harness.py <$ARGUMENTS>
   ```
   This writes the changed files and updates each synced repo's `planning/.template-version`
   (`commit:` + `synced:` fields). Without `--commit` it does **not** commit.

4b. **Per repo, before committing:** check for pre-existing unrelated dirty state so it doesn't get
   swept into the harness-pull commit by accident:
   ```bash
   cd <repo_path> && git status --short | grep -v '\.claude/' | grep -v 'planning/\.template-version'
   ```
   If that prints anything, it's unrelated in-progress work in that repo — leave it out of the
   commit (stage `.claude/` and `planning/.template-version` explicitly, never `git add -A`).

5. **Commit.** Prefer `--commit`; the manual recipe below is the fallback and the explanation.

   **(0) The one-command path:**
   ```bash
   python3 scripts/sync_downstream_harness.py --apply --commit --message "<what this pull is>"
   ```
   It makes **N+1** commits: one per repo for that repo's own `.claude/`/`.agents/`/`scripts/`/
   `hooks/` half, then **one** brain commit carrying every `planning/.template-version` stamp. Each
   pathspec is explicit and derived from what the run actually wrote; the script never runs
   `git add -A`. A repo whose harness tree lives in the brain's own index (the `engines_only` brain
   root) is folded into the brain commit rather than committed twice. Per repo it prints the short
   sha, `nothing to commit`, or `COMMIT FAILED: <reason>`; any failure exits 1.

   `--commit` does not relax step 4b — run that check first. The script stages only what it wrote,
   so unrelated work is never swept in, but a repo with uncommitted edits to a file this sync
   overwrites has already lost them by then.

   **Doing it by hand** takes **two** commits, in different repos, because the synced files do not
   all belong to the same git repo:

   **(a) The sub-repo owns `.claude/` and `.agents/`:**
   ```bash
   git -C <repo_path> add .claude .agents
   git -C <repo_path> commit -m "chore(harness): pull base-template <short-hash> — <one line>"
   ```

   **(b) The brain repo owns every `planning/.template-version`.** In a vaulted repo `planning/` is
   a symlink into the brain's `_planning/` vault, so that file is tracked by `agentic-portfolio`,
   not by the sub-repo. **Do not put it in the sub-repo's `git add`** — it fails with
   `fatal: pathspec 'planning/.template-version' is beyond a symbolic link` **and aborts the entire
   add, staging nothing at all**, so the `.claude/` files you meant to commit are silently left
   behind. Measured 2026-08-13 across all 16 repos. Commit the stamps together from the brain root,
   with an explicit pathspec (never `git add -A` there — one repo tracks every vault):
   ```bash
   cd <brain_root>
   git commit -o <path>/_planning/<slug>/.template-version ... -m "chore(harness): stamp .template-version across N repos — base-template <short-hash>"
   ```

   Portfolio-tier repos (`rag-engine-rs`, `workflow-engine-rs`, `claude-sdk-rs`) gitignore
   `.claude/`/`planning/` entirely by design (D8, published-repo hygiene) — the sync still updates
   those files locally (harmless), and only their `.agents/` mirrors are tracked. Don't force-add
   the rest.

6. **Second consumers of the `tasks.json` contract.** `core/orchestrator` used to carry one — an
   independent `SDLC_FLOW` workflow implementation. **It was retired**: `app/schemas/sdlc_schema.py`
   and `docs/sdlc-flow-workflow.md` were both deleted by orchestrator commit `75b6c8e`
   ("or-x2-sdlc-evals-retirement-task1"), and `SDLC_FLOW` now survives there only as a string in
   `app/database/eval_record.py`. Verified 2026-08-13 — there is nothing to cross-check in
   orchestrator any more, so do not go looking for those paths.
   If a *new* second implementation of the contract ever appears, re-add it here by name; the point
   of this step is that a contract with two implementations needs both checked, not that
   orchestrator specifically matters.

7. **Sweep for already-broken specs** the fix should also repair: any repo's `planning/*/tasks.md`
   still using the old `### <prefix>.<n>.<n>` heading pattern with `**Status:** Not started` can be
   converted cleanly (write its `tasks.json`, trim `tasks.md`'s Step-by-Step Tasks section to a
   pointer). A spec already `In progress` or `Done` needs no touching — leave it. See
   `core/bastion/planning/13.1-persistent-agent-panel/` for a worked example of this conversion.

8. **Report:** which repos were synced, how many files each, which repos had nothing to sync, any
   repo skipped (no `.claude/workflows/`, or gitignored), any spec found + fixed in step 7, and —
   if `--commit` was used — the commit count and every `COMMIT FAILED` line, never summarised away.

## Notes

- Run this after any change to `.claude/commands/*.md` (flat) or `.claude/workflows/` lands in
  base-template — the same trigger as `/sync-global-commands`, just for the repos that consume the
  harness as project source rather than as installed slash commands.
- The script never deletes. A file in a downstream repo's `.claude/` that doesn't exist in
  base-template (a repo's own command) is left untouched, always.
- `--repo` accepts the `slug` field from `brain.toml`'s `[[repos]]` entries, not the directory name
  (usually the same, but check `brain.toml` if unsure).
- **Why `--commit` is N+1 commits and not one.** Each repo's `planning/` is a symlink into the
  brain's `_planning/` vault, so `<repo>/planning/.template-version` is tracked by the brain, not by
  the repo. Staging both halves in one `git add` fails with `beyond a symbolic link` **and aborts
  the whole add** — committing nothing while appearing to run. The script stages the stamp through
  its real vault path instead, and `scripts/test_sync_downstream_harness.py` carries a positive
  control asserting that staging the symlinked face still fails.
