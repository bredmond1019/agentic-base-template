---
name: start-block
description: >-
  Mark a spec as In progress in planning/STATUS.md — find the target block
  (or the first non-Done block), verify all preceding blocks are Done, flip its status,
  update Current focus, and bump Last updated. Use when the user says "start block",
  "begin <spec>", or "mark <spec> in progress" before working on it.
---

# Start Block — Mark a block as in-progress in STATUS.md.

## Inputs

Optional block identifier to start (e.g. `1.1-site-credibility-fixes`), taken from the user's
request. If omitted, defaults to the first block that is not `Done` in STATUS.md.

## Instructions

1. Read `planning/STATUS.md`.
2. Identify the target block:
   - If a block identifier is provided, find that block by identifier. If not found, say so and stop.
   - If omitted, find the first block that is not `Done`.
3. Check preconditions:
   - If the block is already `In progress`, report that and stop.
   - If the block is `Done`, report that and stop.
   - If any block that must precede this one (all blocks above it in the sequence) is not `Done`, report which ones are incomplete and stop — do not skip the sequence.
4. Update the block's status to `In progress` in STATUS.md. Preserve all other content and formatting.
5. Update the **Current focus** line to reflect this block.
6. Bump the **Last updated** date.
7. Write the updated STATUS.md.

## Context / Files to Read

- `planning/STATUS.md`

## Report

- Which block was marked in-progress.
- The updated Current focus line.
- Success or failure of the file write.
