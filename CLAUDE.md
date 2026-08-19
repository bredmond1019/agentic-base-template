# CLAUDE.md — working on `base-template`

This repo is the **software-factory source**: the curated harness + tokenized document
scaffold that `/new-project` clones. You are not building a product here — you are curating the
thing every new project starts from. Read `README.md` first for the layout and the
generation flow.

## Before you change anything

- **Orientation + current state:** `planning/context.md` (why this repo exists + governing rules)
  → `planning/status.md` (current focus + progress). Or run `/prime`.
- **Symlink warning:** the `planning/` directory is actually a local symlink pointing to the company brain repo's `_planning/` vault (e.g. `_planning/base-template/`). The brain repo is responsible for tracking all planning files under Git. Do not track `planning/` in this project's public Git repository (it is gitignored).
- **Symlink traps:** `rg`/`grep`/`find` are symlink-blind by default — a search that must include `planning/` content needs `-L`/`--follow`. `git mv` fails through the symlink face ("source directory is empty") — move planning files via the real vault path (`.../_planning/<slug>/...`), never via `planning/...`. Planning changes are committed in the brain repo (`agentic-portfolio`) with an explicit pathspec, never in this repo.
- **What this is + layout:** `README.md`
- **How to use it:** `docs/using-the-template.md`
- **Why the harness looks the way it does:** `planning/decisions/` (keep/drop ADRs + the
  Phase-2 adoption record D5).
- **What changed and when:** `log.md`

## The two halves — don't mix them

| Half | Path | Purpose | Goes into new projects? |
|---|---|---|---|
| **Harness** | `.claude/` | The SDLC pipeline (commands + engines) — ships *mechanism* only | Yes — copied as-is |
| **Scaffold** | `scaffold/` | Tokenized project docs (CLAUDE, README, log, planning/ incl. `harness.json` stub) | Yes — copied + token-substituted |
| **Template meta** | `CLAUDE.md`, `README.md`, `log.md`, `planning/`, `docs/` | The template's *own* docs, change history, and pipeline config | **No** — never copied into a project |

A new project must start with a **clean** log and a `D1-initial-okf` decision — so the template's
own `log.md` / `planning/` (this repo's harness history, decisions, and `harness.json`) stay at
the root and out of `scaffold/`.

## The update loop (how to evolve the harness)

When a discovery in a downstream project improves the harness:

1. Make the change **here**, in `base-template` — not only in the project where you found it.
2. If it's a keep/drop or behavioral call, add an atomic ADR under `planning/decisions/`
   explaining *why*.
3. Append a dated `log.md` entry describing *what* changed.
4. Commit. The new commit hash becomes the provenance stamp for the next generated project.
5. **Run `/sync-downstream-harness`** (dry-run first, then `--apply`) to pull the change into every
   already-scaffolded repo — see `planning/decisions/D48-downstream-harness-sync-script.md`. This
   is not optional busywork: a fix that lives only here isn't fixed anywhere real work happens.
   Committing the pull takes **two** commits in **two** repos: the sub-repo owns `.claude/` and
   `.agents/`, while every `planning/.template-version` is tracked by the brain repo through the
   vault symlink. Staging them together fails with `beyond a symbolic link` and **aborts the whole
   `git add`**, silently committing nothing — see the command's step 5.
   `core/orchestrator` used to hold a second, independent implementation of the `tasks.json`
   contract worth cross-checking; it was **retired** (`app/schemas/sdlc_schema.py` and
   `docs/sdlc-flow-workflow.md` deleted by orchestrator `75b6c8e`, verified 2026-08-13), so there is
   no longer a second consumer to check. Re-add one here by name if another ever appears.
6. **If the change touched `.claude/workflows/sdlc-task.js` or `sdlc-flow.js` behaviorally**
   (new flag, changed default, new pipeline stage, changed commit convention, changed state-file
   contract — not a comment-only or token-tiering tweak), also review the matching
   `.agents/skills/sdlc-task/SKILL.md` / `sdlc-flow/SKILL.md`. These are the manual-replication
   guides a shell-less agent (e.g. Gemini, which cannot invoke the `claude` CLI or run the `.js`
   directly) follows step-by-step to reproduce the same pipeline. They do **not** auto-sync from
   the `.js`, and true semantic verification needs an agent to actually read both side by side
   (the adversarial-verify pattern used for the 2026-08 rewrite: one agent per engine rewrites the
   guide, a stronger model then re-checks the highest-stakes sections against source with line
   citations) — drift here is silent until it corrupts a real run (a stale worktree-default or a
   missed D46 vault-commit rule can misfire git state in a vaulted repo, not just look wrong).
   `planning/harness.json`'s `skill-guide-sync` check (`scripts/check_skill_sync.py`) is a
   mechanical tripwire, not a substitute for that: it hashes the highest-risk translated-into-prose
   regions of each engine (isolation/branch-naming, triage/bail taxonomy, D46 vault-commit routing)
   and fails the moment any of them changes without the manifest being re-stamped. A failure there
   means "go re-verify the guide," not "the guide is wrong." After re-verifying (and fixing, if
   needed), re-stamp with `python3 scripts/check_skill_sync.py --update` and commit the manifest
   alongside the SKILL.md change — never run `--update` without having actually re-checked the
   section first, or the tripwire becomes decorative.

Downstream projects **do not auto-sync** — pulling is still a deliberate, reviewed step (the
script never commits for you) — but it is no longer a fully manual copy-paste; `/sync-downstream-
harness` does steps 5's mechanical part. Repos still diverge by design after the pull (their own
customizations are never touched) — keep changes here additive and well-documented.

## Standing rules

1. **Keep the harness project-agnostic — `.claude/` ships mechanism, never project facts.** No
   project-specific skills, paths, or stack assumptions in the engines. Stack *policy* (validation
   commands, ports/routes, whether a UI-test stage exists) lives in each project's
   `planning/harness.json`; the engines read it and ship **no stack defaults** (config absent →
   fall back to the spec's `## Validation Commands` + disable the UI-test stage). See
   [D5](planning/decisions/D5-okf-phase-2-adopted.md). Universal rules (e.g. no emoji in docs,
   parallel port = `port + taskNumber`) stay hardcoded — they are mechanism, not facts.
2. **Tokenize, don't hardcode** in `scaffold/`. Use the tokens in `README.md`; never bake a
   real project name/slug/date into a scaffold file.
3. **Preserve the load-bearing names** the SDLC engines depend on — the settled OKF conventions:
   lowercase docs (`status.md`, `master-plan.md`, `context.md`, scaffold `log.md`), the
   concept-folder `planning/<concept>/` model with pipeline state under a reserved
   `planning/<concept>/sdlc/`, and `index.md` for directory listings. Renames are a
   lockstep-with-the-workflows change, not piecemeal. (The template's *own* root `README.md`
   keeps its name by design.)
4. **Never edit a settled decision** — supersede it with a new atomic ADR and link back.
5. **Every new `.md` under `docs/` or `planning/` must open with OKF YAML frontmatter.**
   Required fields: `type` (e.g. Decision, Index, Reference, Plan, Log, ProjectStatus, LocalContext,
   Guide, Handoff); `title` (human-readable); `description` (one-line summary for embedding).
   Optional but strongly encouraged: `doc_id` (kebab-case stable id, defaults to filename stem);
   `layer` (list from closed vocab: `factory` · `brain` · `engine` · `console` · `surface` ·
   `infra` · `business` · `content` · `meta`); `project` (`base-template` for this repo's own
   docs; omit for scaffold/ files); `status` (`active` · `draft` · `deprecated` · `superseded` ·
   `archived`); `keywords` (3–7 topic terms); `related` (list of doc_ids). Canonical guide:
   `agentic-portfolio/docs/okf-frontmatter.md` (governed by brain decision D27).
   Adding a file to a directory requires updating that directory's `index.md` — propagate up
   the chain as needed (e.g. a new `docs/workflows/` file → update `docs/workflows/index.md`
   and `docs/index.md` if the scope changes).
6. **Prose backticks inside an engine's agent-prompt template must be escaped as `` \` ``.**
   The prompts in `.claude/workflows/sdlc-*.js` are template literals, so a bare backtick around
   a command (`` `git commit` ``) *terminates the template* and the following word is parsed as
   code. **`node --check` on the whole file does not catch this** — stray backticks pair up on
   adjacent lines, file-level parity survives, and the file compiles while the template boundaries
   silently shift. That is not hypothetical: it shipped in four places, rendered `engines-parse`
   green for a full session, and silently removed `sdlc-task` and `sdlc-flow` from the Workflow and
   Skill registries (misdiagnosed at the time as a stale launcher cache). The gating
   `prompt-template-parse` check (`scripts/check_prompt_templates.py`) parses each prompt region
   *in isolation*, which is what actually detects it. If it fails, fix the escaping — never
   re-baseline it, and do not conclude from a green `node --check` that a prompt is intact.
7. **Work that requires the operator is filed as a graph edge, never left as prose.** A decision,
   a credential, a judgement call, or a review that only the operator can make/hold/give is filed
   as a `{"type":"operator", slug, exit, start, what?}` entry in `depends_on` on the block(s) it
   gates — `slug` kebab-case and prefixed `operator-`, `exit` naming the artifact whose existence
   ends the gate (never a description of the work), `start` a paste-ready command. A single
   reducible yes/no on a fixed payload uses `{"type":"approval", slug, what, digest}` instead.
   **Why:** an operator/approval edge inherits the effective priority of everything it gates and
   surfaces in `/next` as the reason work can't start; prose in a handoff, a `note` field, or an
   `## Open questions` bullet surfaces nowhere and is exactly how these get left for days. This
   rule ships from here because it must reach every repo scaffolded from this template. **A
   scaffolded repo with no `planning/state.json`** cannot file the edge — in that case say so
   explicitly in the handoff and name who is expected to file it once a `state.json` exists;
   never error, and never silently drop the item.

   **The failure mode is filing it as a `carryover[]` entry instead**, which looks equivalent at
   write time and behaves nothing alike: a carryover entry gates no block, so the work is never
   forced. Measured 2026-08-19 across the fleet — **30 of 202 `carryover[]` entries are operator
   work misfiled this way**, against 46 correctly-filed `operator` edges. `/handoff`, `/wrap-up`,
   `/log-work` and `/begin-orchestration` all now ask this question *before* offering the
   `carryover[]` kind table, because that is where the misfiling happens.
8. **`carryover[]` has exactly four kinds: `defect`, `deferred`, `drift`, `env`** (HQ D72).
   `constraint` and `known_issue` are **retired** — okf-core preserves them only through its
   `CarryoverKind::Unknown(String)` fallback so legacy entries still round-trip; never mint new
   ones. Route at write time to one of three homes, not two: operator-only work to an `operator`
   edge (rule 7), permanently-true facts to `reference[]`, and only what is left to `carryover[]`.
   The authoritative field table is `docs/state/state-schema.md`; commands restate only what an
   agent needs inline. **Never author a typed `clears_when` that is already satisfied** — it
   retires the entry on its first `mev carryover` sweep while the finding is still live, which is
   strictly worse than no predicate.

9. **If it is not in `state.json`, it does not exist.** Everything that has to get done is filed
   into one of the graph's containers — a block in `tracks[].blocks[]`, an `operator`/`approval`/
   `block`/`external` edge in a block's `depends_on`, a `carryover[]` entry, a `reference[]` fact,
   a `backlog[]` row, an `epics[]` entry — and the routing table is at the top of
   `.claude/workflows/block-registration.md`. A markdown file is where work is *described*; the
   graph is where it is *held*. Prose gates nothing, sorts nowhere and appears on no board, so an
   item living only in a plan, a review, a handoff or an `## Open questions` bullet is **lost, not
   deferred** — six drift tickets filed on disk where the drift detector could not see them, and 30
   of 202 `carryover[]` entries holding operator work that gates nothing, are the measured version
   of this. Rules 7 and 8 are two instances of it. Where a document and the graph disagree, the
   graph wins.

<!-- BEGIN:response-style -->
## Response Style

Optimize every reply for an operator scanning several concurrent agent sessions. Default to the
shortest response that fully answers. Long prose is the failure mode, not thoroughness.

**Shape**

1. **First line = the outcome.** What happened, and did it work. No preamble, no restating the ask.
2. **Then the specifics, if any** — bullets, one line each, max ~6. Facts, not narration.
3. **Last line = the ask, if any** — one question the user can answer in a word.

Ceiling for a normal turn: **~150 words / ~15 lines**. Only depth the user explicitly asked for
(a review, a design rationale, a plan document) may exceed it.

**Cut**

- Reasoning narration — how you got there, what you considered, what you almost did. Report
  conclusions; the transcript already holds the steps.
- Justifying decisions that worked out. Explain only what was non-obvious or that the user may
  want to reverse.
- Unasked-for "what's next", roadmaps, option menus, and status recaps.
- Tables or headings for fewer than ~4 rows/sections — a sentence or bullets is faster to read.
- Self-assessment and stage direction: "the finding that reframes everything", "worth your
  attention", "one thing I want to flag", praise, hedging, apology.
- Re-explaining anything already in a file you just wrote. Link the path instead.

**Keep — these earn their space**

- Failures, blocks, and anything not matching what was asked: say it first, plainly, with the
  real error text.
- Assumptions the user might reject, and decisions that need their call.
- Security, data-loss, or money implications.
- Exact identifiers where they *are* the content: `src/serve/handlers/attention.rs:101`, a
  version, an error code. Never a paragraph describing what a one-line reference would say.

**Register**

Plain English for status, decisions, and trade-offs. Technical depth only where it changes what
the user does next. One idea per sentence; no stacked em-dash asides.
<!-- END:response-style -->
