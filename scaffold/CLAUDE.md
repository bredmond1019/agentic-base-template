# CLAUDE.md — {{PROJECT_NAME}}

{{DESCRIPTION}}

## Before you start

- **Strategic context:** `planning/CONTEXT.md` (read first) → `planning/STATUS.md` (current state)
- **Plan:** `planning/MASTER_PLAN.md` — the phase/block sequence
- **Decisions log:** `planning/decisions/` (start at `planning/decisions/index.md`) — check
  before relitigating any settled choice

## Standing rules

1. **Every block/task ships with tests** covering its core functionality. No exceptions.
2. **Maintain OKF frontmatter** on every markdown file.
3. **Sequence, not calendar** — work the order in `MASTER_PLAN.md`; pick up where you left off.
4. **Decisions are append-only** — never edit a settled decision; supersede it with a new
   atomic file in `planning/decisions/` and link back.
5. <!-- Add project-specific standing rules here (prompt handling, registries, deployment
   boundaries, code style, etc.). -->

## Known bugs

None known at initialization.

## Build / test / run

```bash
# Replace with this project's actual commands.
# <install>
# <build>
# <test>
# <run>
```

## Directory map

```
{{SLUG}}/
├── .claude/        ← Claude Code commands + SDLC workflow engines
├── .agents/        ← Gemini/Antigravity skill twins
├── planning/       ← CONTEXT, STATUS, MASTER_PLAN, decisions/, tasks/
└── <source dirs>   ← add as the project grows
```

## What NOT to touch

<!-- Reference-only code, generated files, migration history, etc. List them as they appear. -->

---

## SDLC pipeline

This project carries the curated SDLC harness. Run `/prime` to orient, then drive structured
work through `/generate-tasks → /implement → /test → /review-task → /document → /log-work`.
See `.claude/commands/README.md` for the full pipeline reference.

> **Stack note:** the harness was seeded from a Next.js project; the test/validation gates in
> the SDLC engines still assume npm/Node. Adapt the validation commands in `/test` and the
> `workflows/*.js` engines to this project's stack.
