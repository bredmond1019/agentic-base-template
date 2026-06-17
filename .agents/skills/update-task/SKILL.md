---
name: update-task
description: >-
  Record progress in a task spec — mark a step done (prepend ✅) and/or append
  a dated note to the spec's ## Notes section, auto-detecting the current spec from
  STATUS.md if none is named. Does not touch STATUS.md. Use when the user says "mark step
  N done", "note that…", or "update the task" mid-implementation.
---

# Update Task — Record progress in a task spec.

## Inputs

Space-separated values, taken from the user's request, in this order:
  1. Target spec identifier, e.g. `1.1-site-credibility-fixes` (optional — if omitted, auto-detects the
     current spec from `planning/STATUS.md`).
  2. Step number to mark done, e.g. `3`. Pass `0` to append a note without marking a step.
  3. Note text (everything after the step number) to append to the spec's `## Notes` section.

Examples:
  `3 Finished scaffolding`                                          ← auto-detect spec, mark step 3, append note
  `0 Still investigating the pt-BR parity gap`                       ← auto-detect spec, note only
  `1.1-site-credibility-fixes 2 Fixed the retired model id in frontmatter`  ← explicit spec, mark step 2, append note
  `1.1-site-credibility-fixes 0 Investigating the pt-BR parity gap`      ← explicit spec, note only

## Instructions

1. **Resolve the target spec.**
   - If the first token matches a spec identifier pattern (e.g. `1.1-site-credibility-fixes`,
     `1.3-projects-add-current`), resolve to `planning/tasks/<name>/tasks.md` and verify the file
     exists. If it does not exist, stop:
     > "No spec found at planning/tasks/<name>/tasks.md — invoke the **generate-tasks** skill on <name> to create it."
   - Otherwise (first token is a number or the input is empty), read `planning/STATUS.md` to
     identify the current spec and load it. If no spec exists, say so and stop.

2. Parse the remaining arguments:
   - Step number: first integer token after the (optional) spec identifier. `0` = note-only.
   - Note text: all remaining text after the step number. May be empty.

3. Read the task spec.

4. If a non-zero step number was given, mark that step heading done by prepending `✅` to the
   matching `### <N>.` line. If the step is already marked done, report that and skip.

5. If note text was provided, append it to the `## Notes` section of the spec, prefixed with
   today's date:
   ```
   **YYYY-MM-DD**: <note text>
   ```

6. Write the updated spec back. Preserve all other content and formatting exactly.

7. Report what changed (see Report).

## Context / Files to Read

- `planning/STATUS.md` — only if no spec identifier was provided in the input
- The target `planning/tasks/<name>/tasks.md`

## Report

- Which spec was updated (full relative path).
- Which step was marked done (if any), or "no step marked" if step was 0.
- The note appended (if any), or "no note added".
- One-line success or failure of the file write.
