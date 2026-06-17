---
name: sdlc-task
description: Run a single task through implement, test, review, and document stages.
enable_subagent_tools: true
---
# sdlc-task

## Instructions

1. Check out an isolated branch: `git checkout -b <spec-slug>-task<N>`
2. Read the scout state from `planning/tasks/<slug>/reports/`.
3. Spawn an `implement` subagent (using `invoke_subagent`).
4. Run the validation suite (via command) or spawn a `test` subagent.
5. Spawn a `review-task` subagent.
6. Handling the Fix loop: if review fails, spawn a fix subagent, test again, and review.
7. Spawn a `document` subagent.
8. Writing `taskN-log.md` and sending a completion message to the parent.
