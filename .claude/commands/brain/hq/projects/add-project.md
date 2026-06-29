# Add Project — Onboard a new project into the company brain

## Variables

$ARGUMENTS — project name or brief description. Examples: "rust-cli", "client-acme-crm",
             "personal-knowledge-feed"

## Instructions

1. If $ARGUMENTS is not provided, ask the user for: project name, one-line description,
   project type (personal · client · infrastructure).
2. Derive a `kebab-case-slug` for use in filenames.
3. Create `docs/projects/<slug>.md` with this template containing OKF frontmatter:

   ```markdown
   ---
   type: ProjectContext
   title: <Project Name> Project Context
   description: <One-line description>
   ---

   # <Project Name>

   ## What It Is
   <One paragraph: what it does, stack, hosting, purpose in the portfolio>

   ## Purpose
   <Why this exists — portfolio artifact, client contract, personal tooling, etc.>

   ## Current Status (as of DATE)
   **Status:** Not started
   **Current focus:** —

   ## Progress
   *(Add phases/specs once planning is done)*

   ## Local Path
   <path if known, e.g. ~/Documents/agentic-portfolio/<slug>>

   ## For Full Context
   *(Add pointer to project's own planning/ directory once it exists)*
   ```

4. Add the project directory to `.gitignore` if it will have its own git repo (ask the user).
5. Add a row to the `## Projects` table in `README.md`.
6. Add an entry to `docs/index.md` under Section 2 (The Two Projects) or the projects section.
7. Add a link to the new project document in `docs/projects/index.md`.
8. Report: files modified, and suggest next step:
   "Open Claude Code in the project directory and run /new-project + /scaffold-project to
   generate the full planning infrastructure."

## Notes

- This creates the BRAIN entry only — it does not scaffold the actual project repo.
- For client projects, use a generic description in docs (e.g. "local gym CRM") rather
  than the client's full legal name.
- Every new project whose code will have its own git repo should be added to .gitignore here.
