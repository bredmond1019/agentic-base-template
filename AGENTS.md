# AGENTS.md — working on `base-template`

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
| **Harness** | `.claude/` + `.agents/` | The SDLC pipeline (commands, engines, and skills) — ships *mechanism* only | Yes — copied as-is |
| **Scaffold** | `scaffold/` | Tokenized project docs (AGENTS, CLAUDE, GEMINI, README, log, planning/ incl. `harness.json` stub) | Yes — copied + token-substituted |
| **Template meta** | `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `README.md`, `log.md`, `planning/`, `docs/` | The template's *own* docs, change history, and pipeline config | **No** — never copied into a project |

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
   **Before committing in this fleet, consult the `commit-in-this-fleet` skill.**
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

   The same obligation applies to `docs/workflows/sdlc-task.md` and `sdlc-flow.md` — the
   human-readable prose explanation of each engine, distinct from the SKILL.md replication guides
   above. They do **not** auto-sync from the `.js` either. `planning/harness.json`'s
   `engine-docs-sync` check (`scripts/check_engine_docs_sync.py`, modelled on
   `scripts/check_skill_sync.py`) hashes the same class of behaviour-defining regions — flags and
   their defaults, the stage list, isolation/branch naming, the triage/bail taxonomy, the
   bookkeep/state-write contract — against `scripts/engine_docs_sync_manifest.json`, and fails the
   moment one changes without the docs page being re-verified. A failure there means "go re-read
   `docs/workflows/*.md` against the engine," not "the doc is wrong" — a hash cannot tell whether
   prose is true, only that the thing it describes moved. After re-verifying (and correcting the
   page, if needed), re-stamp with `python3 scripts/check_engine_docs_sync.py --update` and commit
   the manifest alongside the doc change — **never run `--update` without having actually re-read
   the affected section first, or this tripwire becomes decorative too.** When writing or rewriting
   internal documentation under `docs/`, follow the **`write-repo-doc`** skill.
7. **`sdlc-task`/`sdlc-flow` are the ONLY hand-edited Antigravity-facing skill mirrors — every
   other one is generated.** For every other skill, the Claude-facing `SKILL.md` is the sole
   authored source: edit that copy, never its Antigravity-facing mirror directly. The generator
   (`scripts/generate_skill_surfaces.py`) replaces the mirror's **body only**, copied verbatim from
   the authored source; it never authors or rewrites an existing mirror file's **frontmatter** —
   that half is per-surface (wrap width, `>` vs `>-` folding all vary across the real mirrors) and
   is preserved byte-for-byte, safe to hand-edit in place. Run it after any authored-skill body
   change:
   ```bash
   python3 scripts/generate_skill_surfaces.py          # write mode
   python3 scripts/generate_skill_surfaces.py --check   # report only; exits non-zero on drift
   ```
   `planning/harness.json`'s `skill-surfaces-generated` check runs `--check` and gates on it — a
   hand-edited mirror body reds the suite until it is regenerated. **The two exclusions, and why
   they are destructive if missed:** `sdlc-task` and `sdlc-flow` are registered skill slugs with
   **no authored source at all** — they are the hand-authored manual-replication guides named in
   item 6 above, hashed against the engines by `scripts/check_skill_sync.py`. A run fed the bare
   registry (rather than the registry intersected with the skill slugs that actually have an
   authored source) would overwrite and destroy both on its first pass — the generator reports them
   `skipped-no-source` instead. Symmetrically, an authored skill with no registry entry (e.g.
   `epic`, `write-operating-doc`) has deliberately no counterpart on the other surface and must
   never gain a mirror. Full contract and the operator decision that settled the
   frontmatter-preservation rule: `planning/archive/BT.3.G/decision.md`.

Downstream projects **do not auto-sync** — pulling is still a deliberate, reviewed step (the
script never commits for you) — but it is no longer a fully manual copy-paste; `/sync-downstream-
harness` does steps 5's mechanical part. Repos still diverge by design after the pull (their own
customizations are never touched) — keep changes here additive and well-documented.

## Where the tool-specific half lives

This file is **surface-neutral**: everything in it is true whichever agent is reading it. Anything
that names a particular tool's directories or affordances lives in that tool's own file instead:

| File | Holds | How it loads |
|---|---|---|
| `AGENTS.md` (this file) | architecture, conventions, standing rules, the update loop | imported by the others |
| `CLAUDE.md` | the Fleet & Core Skills table for `.claude/skills/`, Claude-specific notes | Claude Code reads it, and it imports this file with `@AGENTS.md` |
| `GEMINI.md` | the same table for `.agents/skills/`, Antigravity-specific notes | **generated** from this file plus that tail |

**Do not add tool-specific paths or nouns here**, and do not edit `GEMINI.md` by hand — it is
generated, so a hand edit is overwritten on the next sync. Edit this file, or `CLAUDE.md`'s tail.

## Recording what you find

Measured 2026-09-03: **no file in this fleet carried any instruction about this**, which is why
every `## Known bugs` section still reads "None known at initialization." Route a finding by asking
who needs it, in this order:

| The finding is | Goes to | Because |
|---|---|---|
| Something that must be **tracked, scheduled or gated** | `planning/state.json` | Prose gates nothing, sorts nowhere, and shows up on no board. See standing rule 9 and `.claude/workflows/block-registration.md`. |
| True for **any agent** working here — a build trap, a repo convention, a gotcha | **`AGENTS.md`** | Both surfaces read it. |
| True only for **one tool** — a Claude Code permission quirk, an Antigravity resolution behaviour | that tool's own file | Never duplicate it into the other; that is how the two drifted in the first place. |

**When: at the moment of discovery, not at handoff.** A finding you intend to write up later is a
finding you will describe from memory, less precisely, if at all.

**A finding written only into a markdown file is documentation, not work.** If something has to
*happen*, it needs a `state.json` entry as well — the doc explains it, the graph carries it.

## Standing rules

1. **Keep the harness project-agnostic — `.claude/` and `.agents/` ship mechanism, never project facts.** No
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
   Consult the **`write-okf-markdown`** skill before authoring or editing markdown files.
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
   never error, and never silently drop the item. For notification rules, consult the
   **`notify-operator`** skill.

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
   `.claude/workflows/block-registration.md`. Consult the **`edit-state-json`** and
   **`derive-state-safely`** skills before modifying state. A markdown file is where work is
   *described*; the graph is where it is *held*. Prose gates nothing, sorts nowhere and appears on
   no board, so an item living only in a plan, a review, a handoff or an `## Open questions` bullet
   is **lost, not deferred** — six drift tickets filed on disk where the drift detector could not see
   them, and 30 of 202 `carryover[]` entries holding operator work that gates nothing, are the
   measured version of this. Rules 7 and 8 are two instances of it. Where a document and the graph
   disagree, the graph wins.

10. **The running engine is a snapshot — editing `.claude/` mid-session does not change the session.**
    The Workflow harness copies the engine `.js` into
    `~/.claude/projects/<proj>/<session>/workflows/scripts/sdlc-<engine>-wf_<runid>.js` and executes
    that copy. Committing an engine fix to `main` — even rebasing the running worktree onto it —
    does **not** change what the next run executes. The same holds for
    `.claude/commands/*.md`. **Only restarting the session picks the change up, and a long
    `/orchestrate` chain cannot restart itself.** Consult the **`stop-or-continue`** skill for
    the exact trigger rules.

    **The snapshot is per-SESSION, not per-launch — the `-wf_<runid>` filename invites the wrong
    inference and is the single most misleading thing about this rule.** A second Workflow call in
    the same session does not re-read the source; it re-executes the same cached bytes, however many
    times the engine was edited and committed in between. Measured by md5 on 2026-08-24: two launches
    one session apart, separated by two commits that provably changed `sdlc-task.js`, produced
    **byte-identical** snapshots (`071241e01a07ddc0e727f2d50d7a36cc` both times) against a working
    tree at `457eb3dda65f9969307cc204734d830f` — 3 `new Date()` calls in each snapshot versus 2 in
    the tree. So the operative consequence is stronger than "not reliably": **a block whose subject
    IS the engine can never verify its own fix in the session that wrote it.** The fix will be on
    disk, committed, and provably absent from the engine actually executing.

    **Why this rule exists rather than a note: the failure is self-concealing.** A stale engine
    emits the pre-fix command, the stage runs it faithfully, and the pre-fix failure comes back —
    which reads as an unreliable agent, not a stale binary. On 2026-08-19
    `BT.ticket.retire-unused-engines` was re-run **four times** against an engine that never
    changed, and the run record wrote the whole episode up as an agent-fidelity problem before
    anyone hashed the snapshots. Measured that day: one run executed an engine **two fixes stale**,
    another **one fix stale**, in both cases with the fix present on `main` and in the worktree.

    **So, in order of preference:**
    1. **Fix it somewhere that takes effect immediately** — the spec, `tasks.json`, `harness.json`,
       or a script the engine shells out to. Rescoping a task's `files[]` is what finally unblocked
       the block above; the two engine-side fixes for the same bug did not.
    2. **If it must be the engine, verify the snapshot before re-running**, and read an unchanged
       snapshot as "this re-run proves nothing" rather than as evidence about the fix. Prefer md5
       over grep — a count can match by coincidence, and an identical hash is unarguable:
       ```bash
       md5 -q .claude/workflows/sdlc-task.js
       md5 -q ~/.claude/projects/<proj>/<session>/workflows/scripts/sdlc-*-wf_<runid>.js
       ```
       Equal hashes mean the snapshot IS the tree. Unequal means it is stale, and per the
       per-session note above it will stay stale for the rest of this session — re-launching does
       not refresh it, so go to step 3.
    3. **Otherwise record the fix as pending** in the run record and let a fresh session take it.

    Never conclude an engine fix "did not work" from a run whose snapshot predates it. Full evidence:
    `planning/knowledge.md` (Gotchas) and
    `planning/orchestration-run/command-hardening/review.md`. This is a standing argument for moving
    orchestration into `engine-rs`, where the executing engine's version is explicit.

11. **A command that creates a new `.md` must seed it with OKF frontmatter — and a command that
    edits one must not displace or orphan its frontmatter.** A file created under `planning/`
    without frontmatter reports the same missing-fence error on `--graph`, `--state`, `--links`
    **and** `--structure`, so a single omitted `---` looks like a corpus-wide regression rather
    than one bad file. `/update-task` created the fleet's first `amendments.md` this way on
    2026-08-19 and took the corpus from 0 to 7 errors. Seeding content without frontmatter is not a
    smaller version of rule 5 — it is a breach of it. The edit case is the same failure by a
    different door: on 2026-08-22 the `sdlc-task` bookkeep stage wrote its "Current focus"
    paragraph into `base-template/planning/status.md` twice in the wrong places — once above the
    opening `---` fence, once inside the block — and a file whose frontmatter no longer starts at
    line 1 fails all four `validate-brain` flags at once, red-gating every concurrent lane on a
    file it never touched. `hooks/check_frontmatter.py` (brain repo) and
    `scripts/check_frontmatter_presence.py` (this repo, `harness.json`'s `frontmatter-presence`
    check) both gate this at commit time and at gate time. Consult the **`write-okf-markdown`**
    and **`run-the-gates`** skills.

<!-- BEGIN:response-style -->
## Response Style

You are read by an operator scanning several concurrent agent sessions. Long prose is the failure
mode, not thoroughness.

1. **First line = the outcome** — what happened, and whether it needs them.
2. **Then the specifics** — bullets, one line each, max ~6. Facts, not narration.
3. **Last line = the ask**, if there is one. One question, answerable in a word.

**Ceiling: 10 lines for a normal turn, 20 for an end-of-run report.** Only depth the operator
explicitly asked for may exceed it.

Durable detail goes to disk — the commands already require that. **Link the path; do not restate
the file.** Lead with failures, blocks, and anything that did not match the ask, in plain words with
the real error text. Cut reasoning narration, unasked-for next steps, and self-assessment.

Full rationale, the complete cut-list, and worked before/after examples: the
**`report-to-the-operator`** skill.
<!-- END:response-style -->

<!-- BEGIN:session-continuity -->
## Stopping, continuing, and handing off

**Run to completion. Never stop, clear, or hand off because context is getting large.** There is no
token band, no percentage, and no "the next block would be cleaner in a fresh session." A chain runs
every block it was given; a lane that stops after one block and waits to be relaunched by hand
defeats the entire point of the run and puts the operator back in the loop after every block. If
context genuinely runs out, the harness summarizes and you keep going — that is its job, not yours.

There is exactly **one** reason to end a session early, and it is about correctness, not cost:
**something the running session depends on changed underneath it** — an engine, command file,
installed binary (`mev`, `bastion`), hook or `settings.json` edited this session, or a `CLAUDE.md` /
`GEMINI.md` / `AGENT.md` you already read. The running session is a launch-time snapshot
(base-template standing rule 10), so it keeps producing pre-change results, which read as an
unreliable agent rather than a stale snapshot. **Name the trigger, finish the unit of work in flight,
and say plainly that a fresh session is needed.** Do not present it as a context-budget decision,
and do not go looking for the trigger as an excuse to stop. Consult the **`stop-or-continue`** skill.

Whenever you do hand off, write the entry point first — `status.md`, `handoff.md`, a spec's
`tasks.json`, or an orchestration-run `notes.md` — so the next agent starts from an artifact instead
of from your memory.
<!-- END:session-continuity -->

