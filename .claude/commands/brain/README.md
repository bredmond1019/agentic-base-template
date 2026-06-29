# brain/ — Command reference directory

This directory is base-template's reference copy of all brain-level commands.
It is organized to match how they are distributed in practice:

- `shared/` — commands available in HQ and all sub-brains.
  `sync-brain-commands` (brain repo) distributes these to each sub-brain's `.claude/commands/shared/`.
  `generate-sub-brain` bootstraps new sub-brains from this tree.
- `hq/` — HQ-only commands (`agentic-portfolio`). Never distributed to sub-brains.

**NOT synced by `sync-global-commands`** — brain commands are never installed in `~/.claude/commands/`.
**Update manually** when brain commands change: copy the updated file(s) from `../.claude/commands/`
into the appropriate subdirectory here, then commit.
