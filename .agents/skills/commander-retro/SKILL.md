---
name: commander-retro
description: >
  Run at the end of a multi-lane run, in the commander's own session. Reconstructs the run from disk for what a drain could see, uses the session's memory only for what no artifact records, tags every claim OBSERVED/INFERRED/UNKNOWN. Read-only except for the retro file.
---

# Commander retro — the drain's own account of the run

Run once, after a multi-lane run ends. **This is NOT a drain.** Do not run the six steps, do not
call `emit_state_write.sh`, do not commit, do not stamp a heartbeat, do not send alerts. Read-only
except for the one file named in Step 5.

**Findings written here follow [`finding-discipline.md`](../workflows/finding-discipline.md)** —
evidence travels with the claim, and a counted set is not the same as an impression.

## Variables

```
Usage: /commander-retro <roadmap-slug>... [--since <YYYY-MM-DD>] [--out <path>]
```

| Flag | Default | What it does |
|---|---|---|
| `<roadmap-slug>...` | required unless `--since` | The run's roadmaps. A run usually spans several. |
| `--since <date>` | — | Select by drain/lane-log activity instead of by slug — a roadmap is not a run. |
| `--out <path>` | `planning/open-work/orchestration-runs/retros/commander-retro-<YYYY-MM-DD>.md` | Where the retro lands. |

## Step 0 — Run this in the commander's own session

**Run it in the session that drove the drains, not a fresh one.** Two of the sections below —
*where this session was wrong* and *where the instructions failed you* — have no source other than
the agent that lived the run, and no fresh reader can reconstruct them from disk. The 2026-09-02
retro's most credible section was exactly that one, and it exists only because the session wrote it.

## Step 1 — Memory is required for some sections and forbidden for others

**A DRAIN is stateless; the SESSION is not.** Each drain's instructions carry nothing forward, but
the `/loop` session that ran 26 of them accumulated all 26 in context. That distinction decides
where recollection is evidence and where it is contamination:

| Section | Source | Why |
|---|---|---|
| A (what the drains did), B (`processing/`), C (blindness) | **Disk only** | The question *is* what a drain can see. Filling a gap from memory answers a different question and hides the hole |
| D (instrument failures), *where this session was wrong* | **Memory, with disk to check it** | No artifact records a judgement call, or a wrong claim you later withdrew |
| E (where the instructions failed you) | **Memory** | Only the reader who followed them knows where they misled |

**"I remember it" is never `OBSERVED`.** In sections A–C, a thing you recall but cannot cite is an
`UNKNOWN` — that is precisely the finding. Tag every claim with exactly one of:

- **`OBSERVED:`** — you are looking at the artifact now. Cite it: path, line, sha, or command **and
  its output**.
- **`INFERRED:`** — reasoning from an artifact to something it does not literally say. Name the
  artifact and the gap.
- **`UNKNOWN:`** — no artifact on disk answers this. **This is the most valuable answer in the
  exercise.** An `UNKNOWN` is a hole in what a drain can see, which is the entire point. Never guess
  to avoid one; never soften one into an `INFERRED` — and **never resolve one from memory**, which
  is the specific way this command fails when run in the right session.

A retro that reads well and cites nothing is worse than three honest `UNKNOWN`s.

## Step 2 — Where the evidence lives

Read all of these first. **A missing one is itself a finding** — report it `UNKNOWN` and say which
question it made unanswerable.

| Artifact | Answers |
|---|---|
| `planning/roadmaps/<slug>/drain-log.jsonl` | how many drains, over what window, what each routed |
| `planning/open-work/index.md` | every recovery item and alert previously surfaced |
| `<lock_dir>/commander-heartbeats/` | when a drain last ran, per commander |
| `<lock_dir>/queue/<repo>/<lane>/{inbox,processing,done}/` + `receipts.jsonl` | drained, completed, and anything stuck across drains |
| `<lock_dir>/lane-agents/` · `<lock_dir>/leases/` | claims and their ages |
| `$LOG_DIR/.emit_wrote` | the last manifest the derive-and-commit path would have used |
| `git log --oneline --grep='\[routine\]'` (brain) | what the commit path actually committed, and when |
| each repo's `planning/orchestration-run/<slug>/{notes.md,review.md}` | what the lanes recorded |
| `planning/roadmaps/<slug>/escalations.jsonl` | what was escalated, if anything |

Resolve `<lock_dir>` and `<brain_root>` the way `check_lane_agents.py` does — walk up for
`brain.toml`. Never assume a repo-relative path.

**Two traps that give a clean-looking wrong answer here specifically:** a piped command's `$?` is
the pipe's — redirect, then check; and `rg`/`find` are symlink-blind while every `planning/` is a
vault symlink — pass `-L`.

## Step 3 — Derive the run's events, then answer for each

**Do not work from a list someone handed you.** Build the event list from the artifacts in Step 2:
every bail, every stale claim, every red gate a lane did not cause, every message that sat
undrained, every escalation. Then, per event, answer three questions:

1. **Could a drain have detected this from artifacts on disk at the time?** Name the exact artifact
   and the check. If not, `UNKNOWN`, and name what would have had to exist.
2. **Would the six steps as written have surfaced it**, or does detecting it need a step the command
   does not have? Be specific about which step.
3. **Was it in scope?** Reaping a stale lease, implementing a block, editing another lane's chain
   are all explicitly out of scope. **"I could have seen it and correctly must not act" is a good
   answer** — then say what the *reporting* path should have been, because surfacing is never out
   of scope.

## Step 4 — The five questions only the commander can answer

### A. What the drains actually did
`OBSERVED` only. Drains, window, messages drained/routed/completed, orphans in each of the three
cases, what got committed. **Recount every figure** rather than repeating one the log asserts.

### B. What crossed drains in `processing/`
A message left in `processing/` is evidence something did not finish. What, and do the artifacts
say why?

### C. The liveness join — the judgement no script makes
`check_lane_agents.py` gives timestamp age; `ListAgents` gives liveness. Joining them to tell
*abandoned* from *merely slow* is the drain's job, not the script's.

- Did you actually perform the join? `OBSERVED` or `UNKNOWN`.
- For each stale-but-live lane, what did the rules as written tell you to report?
- **If the rules produced no finding on a lane that was genuinely stuck — or a finding on a healthy
  one — say which, and what signal would tell them apart.** Zero false positives and zero true
  positives are the same number; distinguish them.

### D. Instrument failures — the most transferable output
**Every command that returned a plausible, confidently wrong answer.** For each: what it said, what
was true, why it lied, and the correct invocation. These generalise past this run and past this
fleet, which is why they get their own section rather than being folded into events.

Include your own. A retro that lists only what it caught is worthless — record where **this session
was wrong**, what corrected it, and whether the correction came from a peer rather than from you.

### E. Where the instructions failed you
Quote the lines. Per item: what you did, what it should have said, what the corrected line is.
Cover at least — two parts of the command disagreeing; a path, threshold, filename or tool named
imprecisely; anything where following it literally would have been wrong; and whether the report
format had room for what mattered.

Then, from the receiving end: **what do `/begin-orchestration` and `/orchestrate` tell lanes to do
that shows up in your queue or lock records as consistently wrong, missing or malformed?** You are
the only agent that sees every lane's records. And: is there anything a lane sends you that you have
no defined action for?

### F. The one change
One paragraph: if exactly one thing changed before the next run — a command edit, a schema field, a
threshold, a step, a script — what is it, and what specifically does it prevent that happened this
run? **Then name the runner-up you are not choosing, and why.** A retro that recommends everything
recommends nothing.

## Step 5 — Output

Write `--out` with OKF frontmatter (`type: Log`, `layer: [meta]`, `project: brain`) and add its row
to the retros `index.md` (standing rule 7). That file is the deliverable and may be as long as the
evidence warrants.

**Do not file blocks, tickets or carryover entries, and do not edit any lane record.** If the retro
surfaces work, name it in the file and let `/consolidate-fleet` or a human route it — a retro that
also files is two jobs, and the filing half will not be reviewed.

Then reply in chat, **at most 15 lines**: section A's counts, your three highest-value `UNKNOWN`s,
and section F's one change. The file carries the rest.

## Worked example

`planning/open-work/orchestration-runs/retros/commander-retro-2026-09-02.md` — 26 drains, seven
lanes. Its section 2 (five instrument failures, every one clean-looking and wrong) is the part that
proved most reusable; its section 3 ("where this session was wrong", seven entries) is what makes
the rest credible.
