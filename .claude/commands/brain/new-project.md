# New Project — Scaffold a new sub-project into a tier by cloning the `base-template/` software factory

Creates a new sub-project by cloning the curated **`base-template/`** harness + tokenized OKF scaffold,
substituting tokens, stamping provenance, onboarding it to the company brain **inside the chosen tier**,
registering it in **`brain.toml`**, and generating the project's master plan.

This command is **`brain.toml`-driven**: it scaffolds into `<tier>/<slug>/`, appends a `[[repos]]` entry,
writes the per-repo cache into that tier's `docs/projects/`, and adds the row to the tier rollup — so the
new project is immediately visible to `/log-work`, `/prime`, and the indexer with no hand-wiring.

## Variables

- **Project Description**: Project Name, one-sentence description, project type
  (personal · client · infrastructure), and whether to init a separate git repo (yes/no).
- **Tier**: which sub-brain the project belongs to — `core` · `portfolio` · `side` · `client`, or
  `_root` for a top-level project (like `learn-ai` / `base-template`, scaffolded at the brain root).
- **Planning doc (optional, recommended)**: path to the brain planning doc from the prior session
  (e.g., `planning/my-idea/plan.md`), used as source material for master-plan generation in step 9.

## Prerequisites

- `base-template/` must exist at the brain root (the factory source). If missing, stop and say so.
- `brain.toml` must exist at the brain root.
- **The chosen tier must already exist** (a `<tier>/` directory with `planning/status.md`). If it does
  **not**, STOP and tell the user to run **`/generate-sub-brain <Tier>`** first. (`_root` is always valid.)

## Instructions

1. If parameters are missing from `$ARGUMENTS`, prompt for: Project Name; two-letter uppercase project prefix (e.g. 'BA' for Bastion). **This 2-letter prefix must be unique across all projects in `brain.toml`.**; one-sentence description;
   Project Type; **Tier** (`core`/`portfolio`/`side`/`client`/`_root`); **Stack**
   (`Rust` / `Next.js` / `FastAPI` / `Other`); git init (yes/no); planning-doc path (optional).

2. Derive a `kebab-case-slug`. Determine the scaffold target:
   - tiered: `PROJECT_DIR = <tier>/<slug>`, `CACHE_DIR = <tier>/docs/projects`,
     `TIER_STATUS = <tier>/planning/status.md`.
   - `_root`: `PROJECT_DIR = <slug>`, `CACHE_DIR = docs/projects`, no tier rollup.
   - **Validate the tier exists** (per Prerequisites) before proceeding.

3. **Onboard to the brain — create the cache** `CACHE_DIR/<slug>.md` with OKF frontmatter (note the
   `synced_from` watermark — D29, set to today's full ISO date at creation):
   ```markdown
   ---
   type: ProjectContext
   title: <Project Name> Project Context
   description: <One-sentence description>
   doc_id: <slug>
   layer: [<best-fit layer>]
   project: <slug>
   status: active
   synced_from: "<today ISO date>"
   keywords: [<3–7 terms>]
   ---

   # <Project Name>

   ## What It Is
   <One-sentence description + stack/hosting.>

   ## Purpose
   <Why this exists — portfolio artifact, client contract, personal tooling, etc.>

   ## Current Status (as of <today's date>)
   **Status:** Not started
   **Current focus:** Phase 0, Block A

   ## Progress
   | Phase | Block / Spec | Status |
   |---|---|---|
   | Phase 0 | Block A — Foundation setup | Not started |

   ## Local Path
   `~/Dev/agentic-portfolio/<PROJECT_DIR>`

   ## For Full Context
   See `../<PROJECT_DIR>/planning/`.
   ```

4. **Register in `brain.toml`** — append a `[[repos]]` block (manifest order: group with its tier):
   ```toml
   [[repos]]
   slug = "<slug>"
   prefix = "<prefix>"
   tier = "<tier>"            # or "_root"
   repo_path = "<PROJECT_DIR>"
   status_file = "<PROJECT_DIR>/planning/status.md"
   cache_doc = "<CACHE_DIR>/<slug>.md"
   heading = "<slug>"
   ```

5. **Add the tier-rollup row + propagate `index.md`:**
   - **tiered:** the tier rollup in `TIER_STATUS` is a **generated region**
     (`<!-- BEGIN generated:tier-rollup --> … <!-- END generated:tier-rollup -->`, columns
     `Repo | Now | Next | Blocked`) — do **NOT** hand-edit inside the sentinels. `mev emit-state` (run by
     `/log-work`) fills the new project's row from its `[[repos]]` entry. Just ensure the tier's
     `status.md` carries the sentinel pair. Momentum/Metrics are untouched.
   - add the cache to `CACHE_DIR/index.md`.
   - **_root:** add a row to the `## Projects` table and the `## Quick Status` in `README.md`, and an
     entry in `docs/index.md`; add the cache to `docs/projects/index.md`.
   - If the project uses a separate git repo, append `<PROJECT_DIR>/` to the brain root `.gitignore`.

6. **Capture template provenance:** `TEMPLATE_COMMIT=$(git -C base-template rev-parse HEAD)`.

7. **Clone the harness + scaffold** (never copy `base-template/.git`, its root meta, or its
   `planning/decisions/`):
   ```bash
   mkdir -p <PROJECT_DIR>
   cp -R base-template/.claude  <PROJECT_DIR>/.claude     # harness (commands + workflows + skills)
   cp -R base-template/scaffold/.  <PROJECT_DIR>/         # tokenized docs incl. the D30 file pack
   ```
   After this, `<PROJECT_DIR>/` has `.claude/`, root `CLAUDE.md`/`README.md`/`log.md`, and
   `planning/` with `context.md`, `status.md` (Momentum + Metrics + now/next/blocked scalars — D30),
   `master-plan.md`, `knowledge.md`, `memory.md`, `artifacts/.gitkeep`, `harness.json`,
   `harness.examples.md`, `index.md`, `decisions/{index,D1-initial-okf}.md`.

8. **Stamp provenance + substitute tokens.** Write `<PROJECT_DIR>/planning/.template-version`
   (`template`/`commit`/`generated`). Then replace every `{{TOKEN}}` across `<PROJECT_DIR>/`, passing
   values via the **environment** (never interpolate into the sed/perl script):

   | Token | Value |
   |---|---|
   | `{{PROJECT_NAME}}` | Project Name |
   | `{{SLUG}}` | kebab-case slug |
   | `{{DESCRIPTION}}` | one-sentence description |
   | `{{PROJECT_TYPE}}` | personal · client · infrastructure |
   | `{{DATE}}` | today (YYYY-MM-DD) |
   | `{{TEMPLATE_COMMIT}}` | `$TEMPLATE_COMMIT` |
   | `{{VERIFIED_HANDLES}}` | `none` |

   ```bash
   export PROJECT_NAME="…" SLUG="…" PREFIX="…" DESCRIPTION="…" PROJECT_TYPE="…" \
          DATE="<today>" TEMPLATE_COMMIT="$TEMPLATE_COMMIT" VERIFIED_HANDLES="none"
   ( cd <PROJECT_DIR> && grep -rl '{{' . | while IFS= read -r f; do
       perl -pi -e 's/\{\{(\w+)\}\}/exists $ENV{$1} ? $ENV{$1} : $&/ge' "$f"; done )
   ```
   Verify none remain: `grep -rn '{{' <PROJECT_DIR>` must print nothing.

   > **Note on the harness `log-work`:** the cloned `.claude/commands/log-work.md` is now
   > **`brain.toml`-driven** — it carries **no `{{SLUG}}` token** (it resolves the cache/rollup from the
   > manifest at runtime). So after substitution there is correctly nothing for `{{SLUG}}` to replace in
   > that file; that is expected, not a miss.

9. **Scaffold stack-specific docs** — create starter docs in `<PROJECT_DIR>/docs/` based on the
   Stack chosen in step 1. These give `/document` real stubs to patch into from block one onward.
   All files must include OKF frontmatter with `type`, `title`, `description`, `project: <slug>`,
   `status: active`. Use `{{PROJECT_NAME}}` substituted values (tokens were replaced in step 8).

   **Rust:**
   - `docs/architecture.md` — sections: Overview, Module Map (stub `src/` tree), Core Types, Data Flow
   - `docs/cli.md` — sections: Synopsis, Subcommands (list from `src/main.rs` if readable), Global Flags,
     Exit Codes, Examples

   **Next.js:**
   - `docs/architecture.md` — sections: Overview, Directory Map, Data Fetching Strategy, Key Components
   - `docs/pages.md` — sections: Page Routes, API Routes, Middleware, Auth

   **FastAPI:**
   - `docs/architecture.md` — sections: Overview, Module Map, Request/Response Flow, Key Components
   - `docs/api-reference.md` — sections: Authentication, Endpoints (table: Method / Path / Description),
     Request Schemas, Response Schemas, Error Codes

   **Other:**
   - `docs/architecture.md` — sections: Overview, Module Map, Key Components

   After creating, add a row for each doc to `docs/index.md` (the scaffold stub already exists from
   step 7). Do not add content beyond the section headings and a one-line placeholder per section —
   `/document` fills in real content as blocks ship; `/update-docs --bootstrap` generates full content
   on demand.

10. **Generate the master plan** — replace the scaffold placeholder with a real, project-specific
    `<PROJECT_DIR>/planning/master-plan.md` by following `base-template/.claude/commands/generate-master-plan.md`
    IN THIS SESSION. Inputs: the planning doc from step 1 (or ask the user for the goal), plus
    `<PROJECT_DIR>/CLAUDE.md` + `planning/context.md`. Output must pass all generate-master-plan property
    checks (every block has What/Why/Files/Out-of-scope/Acceptance; no `{{TOKEN}}` or stub comments left).

11. **Init git if requested** — `git init` inside `<PROJECT_DIR>/`.

12. **Report:** tier + `PROJECT_DIR`; the `[[repos]]` block appended to `brain.toml`; brain files modified
    (cache, tier rollup row / README + indexes, `.gitignore`); clone provenance `@ $TEMPLATE_COMMIT`; that
    no `{{ }}` tokens remain; stack docs created (list files); the generated master plan summary
    (phases/blocks); next step — open Claude Code in `<PROJECT_DIR>/` and run `/generate-tasks phase0-blockA`.
