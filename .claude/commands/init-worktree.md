# Init Worktree — Create an isolated git worktree for an SDLC spec or task.

## Variables

$ARGUMENTS — spec slug with optional task number.

Examples:
- `1.1-site-credibility-fixes`   → worktree name: `1.1-site-credibility-fixes`   at `trees/1.1-site-credibility-fixes/`
- `1.1-site-credibility-fixes 3` → worktree name: `1.1-site-credibility-fixes-task3` at `trees/1.1-site-credibility-fixes-task3/`

The spec slug is the directory name under `planning/tasks/` (e.g. `1.3-projects-add-current`,
`2.2-learn-paths-accuracy-refresh`). This matches the worktree naming `/sdlc-task` uses, so
`/clean-worktree` can find and merge whatever this command (or `/sdlc-task`) created.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and print usage:
   ```
   Usage: /init-worktree <spec-slug> [task-N]
   Examples:
     /init-worktree 1.1-site-credibility-fixes
     /init-worktree 1.1-site-credibility-fixes 3
   ```

2. **Parse arguments:** split `$ARGUMENTS` on whitespace. First token is `specSlug`. If a second token exists and is a number, it is `taskNum`; otherwise no task number.

3. **Derive worktree name:** lowercase `specSlug`, append `-task<taskNum>` if `taskNum` is set.
   - `1.1-site-credibility-fixes`    → `1.1-site-credibility-fixes`
   - `1.1-site-credibility-fixes 3`  → `1.1-site-credibility-fixes-task3`

4. **Verify CWD is repo root:**
   ```bash
   git rev-parse --show-toplevel
   ```
   If the output does not match the current directory, stop with: "Run this command from the repo root, not from inside a subdirectory."

5. **Check for name collision:**
   ```bash
   git worktree list
   git branch --list <worktreeName>
   ```
   - If `trees/<worktreeName>` appears in worktree list → stop: "Worktree '<worktreeName>' already exists. Run `/clean-worktree <args>` first."
   - If branch `<worktreeName>` exists but worktree directory does not → stop: "Branch '<worktreeName>' exists as an orphan. Delete it first with: `git branch -D <worktreeName>`"

6. **Create the trees directory:**
   ```bash
   mkdir -p trees
   ```

7. **Create the worktree without checkout:**
   ```bash
   git worktree add --no-checkout trees/<worktreeName> -b <worktreeName>
   ```

8. **Configure sparse checkout (cone mode):**
   ```bash
   git -C trees/<worktreeName> sparse-checkout init --cone
   git -C trees/<worktreeName> sparse-checkout set app components hooks lib content scripts docs planning .claude __tests__ __mocks__ types
   git -C trees/<worktreeName> checkout
   ```
   This checks out the source, content, test, and planning trees. Root-level files
   (`CLAUDE.md`, `package.json`, `package-lock.json`, `tsconfig.json`, `next.config.mjs`,
   `middleware.ts`, `jest.config.*`, etc.) are included automatically by cone mode.

9. **Copy local env files if present** (both are gitignored and must be copied manually):
   ```bash
   if [ -f .env ]; then cp .env trees/<worktreeName>/.env; echo "Copied .env"; else echo ".env not found — skipping"; fi
   if [ -f .env.local ]; then cp .env.local trees/<worktreeName>/.env.local; echo "Copied .env.local"; else echo ".env.local not found — skipping"; fi
   ```

10. **Create initial empty commit to establish the branch head:**
    ```bash
    git -C trees/<worktreeName> commit --allow-empty -m "chore: init worktree <worktreeName>"
    ```

11. **Verify — run these and display the output:**
    ```bash
    git worktree list
    git -C trees/<worktreeName> sparse-checkout list
    ls trees/<worktreeName>/
    git -C trees/<worktreeName> log --oneline -1
    ```

12. **Report success** and print next-step instructions:
    ```
    Worktree '<worktreeName>' ready at trees/<worktreeName>/

    To run the SDLC pipeline in isolation:
      1. Open a new Claude Code session with working directory set to:
           <absolute-path-to-repo>/trees/<worktreeName>
      2. Run: /sdlc-run <specSlug>[ <taskNum>]

    Note: install dependencies in the worktree before any build/test runs:
      cd trees/<worktreeName> && npm ci   (node_modules is NOT shared across worktrees)

    When the pipeline is done, return to the main repo session and run:
      /clean-worktree <original-args>
    ```

## Notes

- Sparse checkout includes `planning/` in full so the scout, plan, and wrap-up agents can read STATUS.md, MASTER_PLAN.md, and write report files. It includes `content/` in full so bilingual (EN + pt-BR) content tasks have both locales available.
- `.claude/` is included so all commands and workflows resolve correctly when the CWD is the worktree.
- Root-level files are included automatically by cone mode — no need to list them explicitly.
- **`node_modules/` is not part of the checkout and is not shared between worktrees.** Run `npm ci` inside the worktree before `npm test` / `npm run build`. (`/sdlc-task` handles this itself; only matters for a manual session.)
- `.env` / `.env.local` are gitignored and must be copied manually (step 9).
- All `git commit` calls inside the pipeline will commit to branch `<worktreeName>`, not `main`, because git detects the worktree context automatically.
- When the pipeline finishes, run `/clean-worktree` from the main repo session to merge the branch and clean up.
