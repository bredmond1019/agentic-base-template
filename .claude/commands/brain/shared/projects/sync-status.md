# Sync Status — Refresh brain cache docs from sub-project status files.

This command is **`brain.toml`-driven**. It reads each repo's live `status_file`, surgically updates
its `cache_doc` with a `synced_from` watermark, and regenerates the owning tier's rollup. Use when
brain docs have drifted, or after working in a sub-project without using its `/log-work` command.

## Variables

$ARGUMENTS — optional: a `slug` from brain.toml to sync only one repo.
  Default (no args): sync every registered repo whose `status_file` exists on disk.

## Instructions

1. **Resolve the manifest.** Read `brain.toml` (at BRAIN_ROOT — the directory containing it).
   - If `$ARGUMENTS` is set: find the `[[repos]]` entry with matching `slug`. If not found, STOP and
     list the valid slugs.
   - If empty: all `[[repos]]` entries are candidates.

2. **For each repo to sync:**
   a. Skip if `slug == "brain"` — the brain root's README is its own cache; use `/log-work` there.
   b. Read `<BRAIN_ROOT>/<status_file>`. If the file doesn't exist on disk, skip and note it.
   c. Extract: the `timestamp` frontmatter field + the current focus line.
   d. Surgically update `<BRAIN_ROOT>/<cache_doc>`:
      - Refresh the **Current Status** date + focus line to match `status_file`.
      - Set frontmatter `synced_from` to the `status_file`'s `timestamp` verbatim (full ISO-8601).
        This watermark is what `mev validate-brain --sync` compares — copy it exactly.
      - Do not rewrite unchanged sections.
   e. **`_root` repos** (`tier == "_root"`, slug != "brain"): also update only THIS repo's `###`
      subsection in `README.md`'s `## Quick Status` (verify the heading matches `heading` before
      writing — never touch another project's subsection).

3. **Regenerate tier rollups.** After syncing, for each tier that had at least one repo synced:
   open `<BRAIN_ROOT>/<tier>/planning/status.md` and replace only the lines between
   `<!-- ROLLUP:BEGIN -->` and `<!-- ROLLUP:END -->`. Rebuild one row per `[[repos]]` entry in that
   tier (manifest order): linked project name → one-line focus → `synced_from` date (`—` if unset).
   Do not touch `## Momentum`, `## Metrics`, or any other section.

4. **Report.** For each repo: cache updated (new `synced_from`) or "already in sync". For each tier:
   rollup regenerated. Note any repos skipped and why.

## Context / Files to Read

- `brain.toml`
- Each target repo's `status_file` (from manifest)
- Each target repo's `cache_doc` (from manifest)
- `README.md` (for _root repo Quick Status subsections)
- Each affected tier's `<tier>/planning/status.md`
