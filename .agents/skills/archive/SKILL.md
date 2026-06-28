---
name: archive
description: Retire a folder/file into planning/archive/ — but distill its durable residue into knowledge.md/memory.md/decisions/ FIRST (D35 "never archive empty-handed" gate). Depth-agnostic; reads brain.toml. Sets status:archived and updates the archive + parent index.
---

# Archive — Retire a folder/file into `planning/archive/`, distilling its durable residue first.

This skill is **`brain.toml`-driven and depth-agnostic** — it works unchanged at a brain root, inside a
tier sub-brain (`core/` · `portfolio/` · `side/` · `client/`), or standalone. It is the **manual
archive-time gate** of the D35 distillation loop: *nothing leaves the embedded corpus until its durable
residue is promoted into `knowledge.md` / `memory.md` / `decisions/`.* Archival is a **ratchet, not a
drop**. The automated sweep (D35 §4) is a future harness — out of scope here.

## Parameters

- **Target** (required): path of the folder/file to archive.
- **Note** (optional): a short "what it was" used for the archive registry row.

## Instructions

### Step 0 — Resolve manifest + archive home
1. Walk up from cwd for `brain.toml` (first line `# brain.toml`) → `BRAIN_ROOT` (none ⇒ standalone; steps
   still apply locally).
2. Find the **nearest `planning/` at or above the target** — its `planning/archive/` is `ARCHIVE_DIR`, and
   its `planning/{knowledge,memory}.md` + `decisions/` are the promotion destinations. Create `ARCHIVE_DIR`
   + an `index.md` (`type: Index`, `status: archived`, "Folder · What it was · Status" header) if absent.
3. If the target looks **active** (recent `status: active`, in-flight blocks, named as now/next), STOP and
   confirm before archiving.

### Step 1 — Read for residue
4. Read the target in full. Ask: what durable residue here goes unretrievable once it leaves the corpus?

### Step 2 — Distill (route, don't summarize) — WRITE BEFORE MOVING
5. Route each nugget per the D35 table → promote into the warm files:
   - how-it-works / live convention → `knowledge.md`; unlogged decision → `decisions/DXX` (or a knowledge
     entry citing it); "tried X, failed because Y" → `memory.md` (+ guardrail/eval candidate); a changed
     fact → `memory.md` temporal entry with `supersedes`; a worked trajectory → `memory.md` skill/workflow
     candidate; pure ephemera → nothing.
6. Each entry uses the **provenance format** verbatim, appended under the right section (never overwrite):
   ```md
   - **<claim / fact / convention / lesson>**
     source: <path>.md · date: <ISO> · supersedes: <prior | —> · freshness: <as-of date>
   ```
7. A conscious "nothing durable" verdict is allowed; a **skipped** pass is not.

### Step 3 — Move + mark
8. `git mv` target → `ARCHIVE_DIR/<name>/` (plain `mv` only if untracked).
9. Set `status: archived` on the moved frontmatter (top file + any nested `status: active` docs).

### Step 4 — Index propagation
10. Add a row to `ARCHIVE_DIR/index.md`; update the parent `planning/index.md` (and chain) that lost the folder.

### Step 5 — Report
11. Report: entries promoted (with provenance) + destination; the move; frontmatter set to archived; both
    index files updated; whether residue was judged empty and why.

Governed by D35 (the loop) and D30 (the file pack it promotes into) — see `agentic-portfolio/docs/decisions/`.
Never embeds/re-indexes — archives stay out of the corpus; the promoted warm entries restore retrievability.
