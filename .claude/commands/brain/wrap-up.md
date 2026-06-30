# Wrap Up — Log work and commit at the end of a brain session.

Runs `/log-work` then `/commit` in sequence. Use this after finishing a piece of brain-level
work (docs, business ops, planning) to append a log entry and commit everything cleanly.
For a full end-of-context hand-off to a fresh agent, use `/handoff` instead.

## Variables

$ARGUMENTS — free-text note about what was done (passed straight through to `/log-work`
             as its narrative). May be brief ("updated career.md with Upwork lead") or
             detailed. **Required** — the brain's `/log-work` stops and asks if omitted.

## Instructions

1. **Drain any durable caveat first.** If this session surfaced something the next agent must not
   lose — a constraint, a known-issue/don't-re-investigate fact, an environmental gotcha, or a
   not-yet-ticketed deferred follow-on — append it to `planning/state.json` `carryover[]` (field shape
   in `planning/state-schema.md`). `/wrap-up` writes no handoff file, so `carryover[]` is the only
   place this kind of note survives. Skip if the session produced none.

2. Run `/log-work $ARGUMENTS` — appends the log entry and updates `planning/status.md`.
   Wait for it to complete before continuing.

3. Run `/commit` — stages and commits all remaining changes with a `docs:` message.

That's it. No handoff file, no context summary — just (drain →) log + commit.
