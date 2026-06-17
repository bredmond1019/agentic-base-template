---
name: sdlc-block
description: Orchestrate a full spec through dependency-ordered waves of parallel sdlc-task pipelines.
enable_subagent_tools: true
---
# sdlc-block

## Instructions

1. Pre-flight checks (clean working tree).
2. Parsing `tasks.md` and `breakdown.md` to compute topological waves, generating `execution-plan.json` (you can invoke `.agents/scripts/compute-waves.ts`).
3. Using `invoke_subagent` with `Workspace: 'share'` to spawn parallel `sdlc-task` workers for each wave.
4. Yielding execution to wait for subagent completion messages.
5. Performing `git merge --no-ff` on passing branches.
6. Updating `STATUS.md` and `DEVLOG.md`.
