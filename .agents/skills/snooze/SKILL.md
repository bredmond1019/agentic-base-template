---
name: snooze
description: >
  Hide a stale Attention item for a few days by setting snoozed_until.
---

# Snooze — Hide a stale Attention item for a few days.

## Purpose

The quick "not now, but don't lose it" disposition for an item on the **Attention board** (stale
`carryover[]` or aging `backlog[]`). Sets `snoozed_until = today + N` so the item disappears from the
board and the `W_STATE_*_STALE` warnings until that date, **regardless of age** — then it resurfaces.

Distinct from **keep / re-affirm** (which bumps `reviewed` for a *full* threshold reset via
`/attention`). Snooze is a short nap; keep is "I looked, it's still valid, reset the clock."

Usage: `/snooze <slug> [--days N]` — default **3 days**.

## When to use

- An Attention item is real but you genuinely can't act on it this week.
- You want the nag to stop briefly without pretending you re-affirmed it.

Do **not** use snooze to permanently silence something — that's what **promote** (→ block/backlog),
**resolve** (delete when `clears_when` is met), or **archive** are for. Snooze always comes back.

## Steps

1. **Resolve the target.** Parse `<slug>` and optional `--days N` (default `3`). Find the item:
   - Search every `planning/state.json` (walk up to `brain.toml`, then all `[[repos]]` + `tiers[]`)
     for a `carryover[]` entry **or** HQ `backlog[]` node whose `slug` matches `<slug>`.
   - If it matches more than one file, list the matches and ask which; if none, say so and stop.

2. **Compute the wake date.** `snoozed_until = <today> + N days`, formatted `YYYY-MM-DD`. Use the real
   current date. (If you cannot determine today's date confidently, ask rather than guess.)

3. **Write it — via the `/update-state` discipline** (this is an *authored* field edit):
   - Read [`docs/state/state-schema.md`](../../docs/state/state-schema.md) if unsure of shape.
   - Set `snoozed_until` on the matched entry only. Do not touch any other field.
   - Validate the JSON parses.

4. **Regenerate + verify:**
   - `mev emit-state --write` (from the brain root) — repaints every Attention board so the item drops off.
   - `mev validate-brain --state` — confirm the matching `W_STATE_*_STALE` warning is gone and no
     `E_STATE_DATE_FORMAT` was introduced.

5. **Report:** one line — `snoozed '<slug>' until <date> (N days)` — and remind that it will resurface then.

## Notes

- Snoozing is per-item, not per-repo. The same slug in two repos is two items — you snoozed one.
- Thresholds and the wake mechanic live in `state-schema.md` → "Attention surface"; the board + warnings
  are produced by `mev` (`emit-state` / `validate-brain --state`).
- Sibling commands: `/attention` (full triage) · `/backlog-ticket` · `/capture`.
