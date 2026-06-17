---
type: Index
title: {{PROJECT_NAME}}
description: {{DESCRIPTION}}
---

# {{PROJECT_NAME}}

{{DESCRIPTION}}

## Prerequisites

<!-- What must be installed (runtime, package manager, services). -->

## Setup

```bash
# Numbered steps from zero to running.
```

## Running locally

```bash
# The exact commands from CLAUDE.md.
```

## Tests

```bash
# One-liner to run the test suite.
```

## Directory map

```
{{SLUG}}/
├── .claude/        ← Claude Code commands + SDLC workflow engines
├── .agents/        ← Gemini/Antigravity skill twins
├── planning/       ← context, status, master-plan, harness.json, decisions/, <concept>/
└── <source dirs>
```

## Documentation

| Doc | Contents |
|---|---|
| [planning/context.md](planning/context.md) | Orientation + governing principles |
| [planning/master-plan.md](planning/master-plan.md) | Strategy + phase specifications |
| [planning/status.md](planning/status.md) | Current progress |
| [planning/harness.json](planning/harness.json) | SDLC validation/UI-test config (see `harness.examples.md`) |

---

*Initialized {{DATE}} from `base-template` (commit `{{TEMPLATE_COMMIT}}`).*
