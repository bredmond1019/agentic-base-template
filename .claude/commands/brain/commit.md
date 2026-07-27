# Commit — Stage and commit brain-level doc changes.

## Variables

$ARGUMENTS — optional commit message override or scope hint.

## Execution Model

**Run entirely inline. Spawn no subagent.** Committing is a handful of git commands plus a
confirmation prompt — the round trip through a subagent adds latency without adding value.

## Instructions

1. Run `git status` and `git diff --stat` to see what changed.
2. This repo is docs-only. Every commit uses the `docs:` type.
   - Format: `docs(<scope>): <summary>` — e.g. `docs(career): add new SMB lead`, `docs(content): log published post`
   - Scope hints: `career`, `content`, `decisions`, `brand`, `infrastructure`, `business`, `commands`, `projects`
   - Keep the summary under 72 characters.
   - If `$ARGUMENTS` is provided, use it as the message or incorporate it as the scope/summary.
3. Show the staged files and proposed message to the user and ask for confirmation before committing.
4. On confirmation, stage the relevant files and commit. Do not use `git add -A` — add files explicitly by name.
5. Do not push. Do not use `--no-verify`.

## Context / Files to Read

None — this command runs git commands only.
