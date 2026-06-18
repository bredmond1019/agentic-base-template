# DEVLOG — base-template

*The template's own change history. One dated entry per session, newest at the top. This file
records changes to the **factory** — it is never copied into generated projects.*

---

## 2026-06-18 — Dropped the `.agents/` twin (single-harness)

Removed the `.agents/` tree (Gemini/Antigravity skill twins + `compute-waves.ts`) from the
template. It was generated from `.claude/commands/`, not authored independently, and existed only
for occasional non-Claude sessions — so maintaining it meant a double-write on every harness edit
plus OKF Phase 2's dedicated P4b "twin mirror pass" to fight drift. For a solo factory that
permanent cost outweighed the occasional benefit; if a skill-form runtime is needed again,
regenerate `.agents/` from `.claude/` rather than hand-maintaining a twin.

Changes: deleted `.agents/`; `/new-project` and both root/scaffold docs no longer reference it;
OKF Phase 2 **P4b is removed** and all twin-alignment gates voided (`.claude/` is the only harness
tree); added `planning/decisions/D4-drop-agents-twin.md` (supersedes the `.agents/`-twin
assumptions in D1/D2; the deferred `.agents` engine-variant note in D3 is moot). The planned
Phase-2 adoption ADR was renumbered `D4-okf-phase-2-adopted` → `D5` to free D4 for this decision.

```diff
- .agents/   (skill twins + scripts/compute-waves.ts)
```

---

## 2026-06-17 — OKF Phase 2 plan seeded (planning, not yet executed)

Wrote a self-contained Phase 2 execution plan into `planning/okf-phase-2/plan.md` so a session
opened in this repo is fully primed without needing the brain. It restates the settled decisions
(brain D15–D18 + the `sdlc/` path resolution) and gives the ordered task list: rewrite the three
SDLC engines to `planning/<concept>/` + `planning/<concept>/sdlc/`, restructure the scaffold to
lowercase names + concept-folders + `index.md`, update the harness skills, generalize the
stack-coupling (closing D3), self-apply to this repo's meta, and regression-check. Added
`planning/index.md` (active-work pointer + D17 self-application) and a "Before you change anything"
pointer in `CLAUDE.md`. **No harness/scaffold files changed yet** — the rewrite (and its provenance
commit + the D4 ADR that supersedes D3) happens when the plan is executed.

---

## 2026-06-17 — Template established (WS3)

Stood up `base-template/` as its own git repo, gitignored from the brain. Seeded the harness
from learn-ai's corrected (post-WS1) `.claude/` + `.agents/` twins and curated it down to the
project-agnostic SDLC core.

**Kept (project-agnostic core):**
- SDLC pipeline: `sdlc-run` / `sdlc-task` / `sdlc-block` (engines), `init-worktree`,
  `clean-worktree`, `start-block`, `generate-tasks`, `process-tasks`, `update-task`,
  `review-task`, `breakdown`, `implement`, `test`, `fix`, `review-workflow`, `document`.
- General: `prime`, `status`, `plan`, `commit`, `log-work`, `update-docs`, `session-recap`,
  `chore`, `feature`.
- `.agents/scripts/compute-waves.ts` (backs `sdlc-block`).

**Dropped (project-specific):**
- `write-learn-module`, `write-blog-post`, `blog-idea` — learn-ai content authoring.
- `playwright` + `.claude/skills/playwright-cli/` — browser-test tooling, learn-ai-specific.
- `dev`, `stop-dev`, `build` — Next.js/npm-specific (port 3003, `npm run dev/build`). A new
  project defines its own run/build commands; a stack-agnostic stub would carry no real value.

**Generalized in place:**
- `update-docs` (both twins): removed hardcoded learn-ai doc names (`DEPLOYMENT.md`,
  `OPERATIONS.md`, `docs/agentic-workflows/`) and Next paths; now recurses `docs/` generically.
- `log-work` (both twins): brain-sync target `../docs/projects/learn-ai.md` → `{{SLUG}}` token.
- All skill/command `description` identity labels: "learn-ai" qualifier generalized.
- SDLC engine header/`description` labels: dropped the `(learn-ai)` identity tags.
- Both `README.md` indexes rewritten to project-agnostic, tokenized form (dropped commands
  removed, npm/bilingual gates described as adapt-to-your-stack).

**Built:** the tokenized `scaffold/` (complete-OKF docs with `{{TOKENS}}`), folding in the
section depth from the deprecated pos `scaffold-project.md` (CONTEXT Governing Principles +
Fast Facts; MASTER_PLAN phase structure). Decisions use the atomic `planning/decisions/`
form, not a single `DECISIONS.md`.

**Notes / retired:** `generate-new-docs.js` was already absent from learn-ai — nothing to
retire. The pos `scaffold-project` command is to be marked superseded by `/new-project` +
`base-template` (deletion deferred to OKF Phase 2).

**Known deferred (OKF Phase 2):** the SDLC engines (`sdlc-run/block/task.js`) and several skill
bodies (`test`, `generate-tasks`, `review-task`) still carry npm/Next/content-validation and
bilingual/public-narrative assumptions. Generalizing them to be fully stack-agnostic is Phase-2
work — see `planning/decisions/D3-engine-stack-deferred.md`. The user also flagged that the
`.agents` `sdlc-block`/`sdlc-task` may want an improved variant; tracked there too.

```diff
(initial harness + scaffold + template meta — no application code)
```
