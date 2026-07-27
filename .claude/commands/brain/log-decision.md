# Log Decision — Create a cross-repo architectural decision in docs/decisions/

## Variables

$ARGUMENTS — the decision to record. Can be brief ("use Tailscale for all private
             tooling, never open inbound ports") or detailed (several sentences with rationale).

## Execution Model

**Run entirely inline. Spawn no subagent.** This is a small, single-file append/edit —
a subagent round trip adds latency without adding value.

## Instructions

1. If $ARGUMENTS is not provided, stop and ask the user to describe the decision.
2. Scan the decisions directory `docs/decisions/` or read `docs/decisions/index.md` to find the last decision number.
3. Determine the next number (D{N+1}).
4. Create a new markdown file named `docs/decisions/D{N+1}-<kebab-case-title>.md`.
5. The file must contain OKF YAML frontmatter:
   ```yaml
   ---
   type: Decision
   title: D{N+1} — Short Title (3–6 words)
   description: One-sentence summary.
   ---
   ```
   followed by the document body:
   ```markdown
   # D{N+1} — Short Title (3–6 words)

   *   **Decision:** <what was decided — one sentence>
   *   **Why:** <the constraint, insight, or tradeoff that drove the choice>
   *   **Cross-repo impact:** <which projects / docs this affects>
   ```
6. Register the new decision in `docs/decisions/index.md` by appending a new item to the list:
   `*   [D{N+1}: Short Title](file://~/agentic-portfolio) - <one-sentence summary>.`
7. Ask the user: "Should this also be added to the DECISIONS.md in [affected project(s)]?"
   If yes, tell them which file to open — do NOT edit sub-project DECISIONS.md files from this repo (they each carry their own append-only log with different numbering).

## Notes

- This records CROSS-REPO decisions — choices that affect multiple projects or the overall practice strategy.
- Per-project decisions (e.g. "use pgvector over Weaviate" in the orchestration repo) belong in that project's own DECISIONS.md, not here.
- Append-only: never edit or remove existing entries.
