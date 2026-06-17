---
name: commit
description: >-
  Stage and commit changes with a conventional commit message — inspect git status/diff,
  split code vs docs into separate commits when both changed, draft a <type>(<scope>):
  message, and confirm before committing. Never pushes, never uses --no-verify or
  git add -A. Use when the user says "commit", "commit my changes", or "make a commit".
---

# Commit — Stage and commit changes with a conventional message.

## Inputs

Optional commit message override or scope hint, taken from the user's request.

## Instructions

1. Run `git status` and `git diff --stat` to see what changed.
2. Determine the commit strategy:
   - **Only code changed** (no `planning/` or `DEVLOG.md`): one code commit.
   - **Only planning/docs changed** (`planning/`, `DEVLOG.md`, `*.md`): one `docs:` commit.
   - **Both changed**: two commits — code first, then docs.
3. Draft a short conventional commit message:
   - Format: `<type>(<scope>): <summary>` — e.g. `feat: add Company Brain post (EN+pt-BR)`, `docs: update STATUS.md for block 2`
   - Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
   - Keep the summary under 72 characters.
   - If a message override or scope hint was provided, use it as the message or incorporate it as the scope/summary.
4. Show the staged files and proposed message to the user and ask for confirmation before committing.
5. On confirmation, stage the relevant files and commit. Do not use `git add -A` — add files explicitly by name.
6. Do not push. Do not use `--no-verify`.

## Context / Files to Read

None — this skill runs git commands only.
