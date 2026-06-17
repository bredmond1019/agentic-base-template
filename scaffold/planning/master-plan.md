---
type: Plan
title: {{PROJECT_NAME}} Master Plan
description: Strategic roadmap and phase specifications for {{PROJECT_NAME}}.
---

# {{PROJECT_NAME}} — Master Plan

*Living document. Created {{DATE}}.*

## The Goal, Stated Plainly

{{DESCRIPTION}}

<!-- 2–3 paragraphs: what the project is, why it matters, and what "ready" means — the
     competence or delivery checkpoint that signals Phase completion. -->

## The Destination

<!-- The named product or outcome. If commercial: the buyer, the differentiator, and the
     through-line connecting the builder to the product. -->

## Architecture / Design Overview

<!-- The key structural design: how the system is organized, its layers, an ASCII diagram if
     useful, and the load-bearing design decisions. Keep deployment specifics out — those are
     injected via config. -->

---

## Phase 0 — Foundation

### Block A — Foundation setup
- **What:** Configure the environment, scaffold the project skeleton, and verify the toolchain.
- **Why:** Establish a clean, reproducible starting point before any feature work.
- **Build notes:** <!-- specific tasks, tools, conventions -->
- **Acceptance criteria:** Codebase builds; the run/test commands in `CLAUDE.md` succeed; the
  planning infrastructure is in place.

---

## Phase 1 — Core

<!-- One sub-section per block, same structure as Phase 0. This is where the first shippable
     feature set lives. -->

---

## Phase 2 — Depth / Hardening

<!-- Hardening, optimization, second-layer features. Same block structure. -->

---

## Phase 3+ — Differentiating Build

<!-- The capstone or the hardest, most-differentiating work. -->

---

## Quick Reference Sequence Table

| Phase | Block | What | Why | Role in destination |
|---|---|---|---|---|
| 0 | A | Foundation setup | Clean starting point | Enables everything downstream |

---

*Sequenced by dependency and competence, not calendar. When life gets in the way, pick up
where you left off.*
