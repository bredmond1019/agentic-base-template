---
name: prime
description: >-
  Orient to the project at the start of a session — read the core docs
  (README, CLAUDE.md, planning/CONTEXT.md, planning/STATUS.md), survey the file
  tree, and summarize what the repo does, its layout, current focus, and standing
  rules. Use when the user says "prime", "orient", "get up to speed", or starts a
  session and needs repo context before any other work. Read-only.
---

# Prime — Orient to this repo at the start of a session.

## Instructions

1. Read each file listed in **Context / Files to Read** in order.
2. Run `git ls-files` to see the full tracked file tree.
3. Summarize your understanding in plain prose:
   - What this repo does (one paragraph).
   - Key directories and what lives in each.
   - Current project phase and focus (from CONTEXT.md and STATUS.md).
   - Anything flagged as standing rules worth keeping in mind.
4. Do not edit any file. This skill is read-only.

## Context / Files to Read

- `README.md`
- `CLAUDE.md`
- `planning/CONTEXT.md`
- `planning/STATUS.md`
