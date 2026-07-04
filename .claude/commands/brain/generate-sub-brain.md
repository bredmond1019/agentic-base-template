# Generate Sub-Brain — Scaffold a new tier sub-brain

Stands up a new **tier** (a tracked sub-folder of the company brain) with the full sub-brain shape:
README · CLAUDE · log · top-level `index.md` · `docs/projects/index.md` · and a `planning/` carrying the
**D30 file pack** (`status.md` rollup target + `knowledge.md` + `memory.md` + `artifacts/`). It then
registers the tier with HQ. This is the reusable primitive behind the four hand-built tiers (`core`,
`portfolio`, `side`, `client`) — the same unit used to stand up a **client's brain** later.

A tier is a container for project repos, but it **is** registered in `brain.toml` as its own
`tier="_root"` self-entry (mirroring the `core` block) so `mev emit-state` treats the tier's
`index.md` as a cache doc and can regenerate its rollup — its nested projects are then registered
separately (each via `/new-project <tier> …`). A tier gets its own seeded `.claude/commands/` +
`.agents/skills/`; agents can also fall back to the HQ harness, which resolves the brain
root by walking up to `brain.toml` (so `/log-work`, `/prime`, etc. work from any depth).

## Variables

- **Tier**: lowercase kebab-case tier name (e.g. `research`, `client`). Reserved/existing: `core`,
  `portfolio`, `side`, `client`.
- **Description** (optional): one line describing what the tier holds (defaults to a generic line).

## Prerequisites

- `brain.toml` at the brain root; `base-template/scaffold/` present (the D30 file-pack source).
- The tier must **not** already exist. If `<tier>/` is present, STOP and report it.

## Instructions

1. If `$ARGUMENTS` lacks the tier name, prompt for it (+ optional description). Validate it's a clean
   kebab-case slug and that `<tier>/` does not already exist.

2. **Create the tier skeleton:**
   ```
   <tier>/
   ├── README.md            # "<tier> Sub-Brain" — what it holds
   ├── CLAUDE.md            # "<tier> Agent Instructions"
   ├── log.md               # tier work log (type: Log, empty)
   ├── index.md             # top-level sub-brain index
   ├── docs/
   │   └── projects/
   │       └── index.md     # per-repo cache index (empty list)
   └── planning/
       ├── status.md        # tier ROLLUP target + Momentum + Metrics + now/next/blocked scalars
       ├── knowledge.md     # distilled semantic residue (D35) — empty seed
       ├── memory.md        # distilled episodic residue (D35) — empty seed
       ├── artifacts/
       │   └── .gitkeep
       └── index.md         # planning index
   ```
   Every `.md` opens with OKF frontmatter (`type`, `title`, `description` + `doc_id`/`layer:[meta]`/
   `project: brain`/`status: active`/`keywords`/`related`). **Template these from the existing tiers** —
   `core/`, `portfolio/`, `side/`, and `client/` are the canonical reference shape; copy their structure
   and adapt the names. The `knowledge.md`/`memory.md` seeds follow the D35 promotion-entry format
   documented in `docs/planning-conventions.md` §3 (start with "no entries yet").

3. **`planning/status.md` must be a valid rollup target** — it carries:
   - frontmatter `now`/`next`/`blocked` scalars (D30);
   - a `## Rollup — repos in this tier` section with the **generated-region sentinels** (the exact
     markers `mev emit-state` splices into — do NOT hand-edit inside them) and an empty seed:
     ```markdown
     <!-- BEGIN generated:tier-rollup -->
     | Repo | Now | Next | Blocked |
     |------|-----|------|---------|
     | _none yet_ | — | — | — |
     <!-- END generated:tier-rollup -->
     ```
     (`mev emit-state --write`, driven by `/log-work`, fills this in as repos join the tier.)
   - `## Momentum` (five queues) and `## Metrics` body sections per `docs/planning-conventions.md`.

4. **Register the tier with HQ:**
   - **`brain.toml`** — add a `tier="_root"` self-entry mirroring the `core` block: `slug=<tier>`,
     a unique two-letter `prefix`, `tier="_root"`, `repo_path="<tier>"`,
     `status_file="<tier>/planning/status.md"`, `cache_doc="<tier>/index.md"`,
     `heading="<tier> Sub-Brain"`. (Nested projects get their own `tier="<tier>"` entries later via
     `/new-project`.)
   - **Root `planning/state.json`** — add a `tiers[]` entry:
     `{ "tier": "<tier>", "rollup": "<tier>/planning/state.json", "summary": "…" }`. This is what
     drives tier state discovery — `mev` reads root `tiers[]`, not `brain.toml`, to find sub-brain state.
   - **`<tier>/planning/state.json`** — author as `kind:"brain"` (empty `focus`, `repos: []`,
     `cross_repo` copied from a sibling tier, `tiers: []`).
   - **`.gitignore`** — add a `# <tier>/ Tier` section header (the tier's `docs/`+`planning/` are tracked
     by default; `/new-project` appends each nested project repo here as it is created).
   - **HQ `CLAUDE.md`** — note the new tier where the tiers/structure are described.
   - **HQ `docs/projects/index.md`** — add the tier to the tier-aware listing.
   - **HQ `docs/index.md`** — add the tier sub-brain if the structural map lists tiers.

5. **Validate:** the new files carry OKF frontmatter and pass `mev validate-brain` (run it if available);
   the tier matches the shape of the existing four (same files, same status.md sections + ROLLUP markers).

6. **Report:** the tier path + files created; the HQ files updated (`brain.toml` self-entry, root
   `planning/state.json` `tiers[]`, `.gitignore`, `CLAUDE.md`, indexes); each nested repo carries its
   own two-letter prefix; next step — `/new-project <tier> <name>` to add the first project.
