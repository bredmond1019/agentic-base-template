---
type: Guide
title: Lane coordination — the operator's guide to the layer under orchestration
description: What the registry, leases, message queue, ping contract and commander are, how to set them up, what to run, and what to do when something looks stuck.
doc_id: base-template-lane-coordination-guide
layer: [factory]
project: base-template
status: active
keywords: [lane coordination, registry, lease, message queue, ping-agent, commander, FLEET_LOCK_DIR, cold start]
related: [base-template-workflows-index, base-template-orchestration-guide, plan-lane-coordination, base-template-docs-index]
---

# Lane coordination — the operator's guide to the layer under orchestration

> **Paths below are relative to the brain root** (`agentic-portfolio/`) — the directory containing
> `brain.toml` — except where a path is explicitly given relative to this repo (`base-template/`).

[`orchestration.md`](orchestration.md) covers the **lane lifecycle** — what a lane is, the phases
of one `/orchestrate` run. This page covers the layer underneath it: five pieces that let
concurrent lanes across repos claim identity, avoid stepping on each other's working trees, pass
messages, and get swept by an automated drain. `BT.6.A`–`BT.6.E` shipped all five across two days
(2026-08-21/22); this page is where an operator learns what each does, how to set it up, and what
to do when it looks stuck.

---

## 1. What this layer is

Five pieces, each shipped to fix one measured incident. Cite the artifact — this page does not
restate a schema's field table or the lane lifecycle's phases:

| Piece | Measured problem it solves | Authoritative artifact |
|---|---|---|
| **Registry** (lane-agent claims) | `ListAgents` nicknames are unstable across restart and carry no repo/lane/roadmap — measured live with 11 concurrent peers on 2026-08-21 — so a lane could not be addressed by role. | [`.claude/workflows/lane-agent.schema.json`](../../.claude/workflows/lane-agent.schema.json) |
| **Leases** | The largest measured incident class in the corpus: one lane discarding or sweeping another lane's uncommitted work because nothing let it discover another lane already held the tree. | [`.claude/workflows/lease.schema.json`](../../.claude/workflows/lease.schema.json) |
| **Message queue** | A cross-lane signal ("bastion:BA.21.A is now unblocked") existed only as prose a human happened to notice, so the waiting lane idled with no typed carrier for it. | [`.claude/workflows/message.schema.json`](../../.claude/workflows/message.schema.json) |
| **Ping contract** | The send/verify/respond discipline that keeps a fast informal channel from replacing the durable one — every claim is written to disk *and* sent, and every received claim is verified before being acted on. | [`.claude/skills/ping-agent/SKILL.md`](../../.claude/skills/ping-agent/SKILL.md) |
| **Commander** | Nothing swept the queue, re-derived generated surfaces, or reported the remainder without a human doing it by hand. | [`.claude/commands/orchestration-commander.md`](../../.claude/commands/orchestration-commander.md) |

Design rationale and what was deliberately cut: [`planning/lane-coordination/plan.md`](../../planning/lane-coordination/plan.md).

---

## 2. Setup

**Where the lock directory lives, and how its path resolves.** All three mechanisms —
registry, leases, and the message queue — share one advisory lock directory, resolved with the
*identical* precedence everywhere in the fleet: an explicit `--lock-dir` flag, else the
`FLEET_LOCK_DIR` environment variable, else a `brain.toml` discovered by walking up from the
current directory, joined with `.fleet-locks`. `scripts/check_lane_agents.py` is the one
implementation all three mechanisms mirror — its `resolve_lock_dir()` (and the identical function
in `scripts/check_messages.py`, `scripts/fleet_concurrency_check.py`) is the citation, not a
restatement, if the precedence ever needs re-verifying.

**Layout**, by reference rather than by copy — see each checker's module docstring for the full
detail:

```
<lock_dir>/
  lane-agents/agent-*.json      # registry claims (lane-agent.schema.json)
  leases/lease-*.json           # repo leases (lease.schema.json)
  queue/<repo>/<lane>/
    inbox/ processing/ done/    # message states (message.schema.json)
    receipts.jsonl              # append-only inbox->processing, processing->done ledger
  commander-heartbeats/         # written only by scripts/commander_drain.sh — see §5
```

**The state of the world today: nothing is running.** The corpus holds **zero** registry claims,
**zero** leases, and **zero** queues. Both `check_lane_agents.py` and `check_messages.py` exit `0`
silently against an empty `.fleet-locks` — that is by design, matching the precedent
`check_lane_records.py` already set for "no records found," and it is the exact state every repo
is in before `BT.6.E` (writing claims/leases) or a real `ping-agent` send ever runs.

**Say the consequence out loud: a green gate does not mean the system is running.** `harness.json`
gates on `check_lane_agents.py --quiet` and `check_messages.py --quiet` both passing — and they
pass, silently, on a corpus with nothing in it. **Installed and idle** is a different state from
**running**, and only this page (and the cold-start walkthrough below) tells the two apart; the
gate cannot.

---

## 3. Cold-start walkthrough

Every command below was **executed** during this block, in a scratch `FLEET_LOCK_DIR` pointed
outside the fleet — never the real `.fleet-locks` — with full captured output under
`planning/BT.ticket.lane-coordination-operator-guide/evidence/`. What follows is the real output,
condensed; the evidence files carry the untruncated captures.

### (a) Empty corpus — both checkers, silent success

```bash
FLEET_LOCK_DIR=<scratch>/fleet-locks-test python3 scripts/check_lane_agents.py
# no lane-agent records found (not a failure)   exit_code=0
FLEET_LOCK_DIR=<scratch>/fleet-locks-test python3 scripts/check_messages.py
# no message records found (not a failure)      exit_code=0
```

### (b) A valid registry claim + an exclusive lease

Hand-write `lane-agents/agent-test1.json` (matching `lane-agent.schema.json`'s six required
fields) and `leases/lease-test1.json` (matching `lease.schema.json`, `"kind": "exclusive"`), then:

```bash
python3 scripts/check_lane_agents.py --lock-dir <scratch>/fleet-locks-test
```
```
ok   <scratch>/fleet-locks-test/lane-agents/agent-test1.json
ok   <scratch>/fleet-locks-test/leases/lease-test1.json

2 record(s) checked, 0 failed
exit_code=0
```

### (c) A duplicate exclusive lease — the checker names both claimants

Add a second exclusive lease on the same `repo` ("base-template"), different lane and agent:

```
FAIL duplicate exclusive lease(s) on repo `base-template`: lane `lane-coordination-operator-guide-task`
agent `base-template-test1` (.../leases/lease-test1.json), lane `some-other-lane` agent
`base-template-test2` (.../leases/lease-test2.json)

3 record(s) checked, 1 failed
exit_code=1
```

Two *shared* leases on the same repo would not trigger this — only exclusive-on-exclusive (or
exclusive-on-shared) is the conflict `lease.schema.json`'s `kind` field exists to catch.

### (d) A message: inbox → processing → done, with receipts

Hand-write two message envelopes (kinds `FINDING` and `RENDEZVOUS`) into
`queue/base-template/main/inbox/`, matching `message.schema.json`:

```bash
python3 scripts/check_messages.py --lock-dir <scratch>/fleet-locks-test
# 2 record(s) checked, 0 failed   exit_code=0
```

Then drain and complete (the same helpers `check_messages.py` exposes and the commander's step 1
calls — `drain_queue()`, `complete_message()`):

```
moved: ecf5526b-... FINDING
moved: 3c8444fe-... RENDEZVOUS
complete_message(ecf5526b-...) -> True
complete_message(3c8444fe-...) -> True
```

`receipts.jsonl` now carries one `inbox->processing` and one `processing->done` line per
message_id; both files now sit in `done/`. Re-running `check_messages.py` over the drained queue:

```
2 record(s) checked, 0 failed   exit_code=0
```

### (e) `scripts/commander_drain.sh` — the boundary that could not be crossed here

`bash -n scripts/commander_drain.sh` parses clean (`exit_code=0`), but the script could **not** be
invoked with real arguments in this task without breaking the "never write to the real
`.fleet-locks`" rule. Read directly from the script:

- `find_brain_root` walks up from the script's own location, not from `FLEET_LOCK_DIR` — it always
  resolves the real `agentic-portfolio` brain, never a scratch one.
- `HEARTBEAT_DIR` is hardcoded to `$BRAIN_ROOT/.fleet-locks/commander-heartbeats` and is
  `mkdir -p`'d unconditionally near the top of the script, before the inbox is even read.
  `FLEET_LOCK_DIR` only affects the informational inbox count, not this path.
- It composes a prompt into the brain's real log directory and invokes `bastion ask` against a
  live tmux session.
- The heartbeat file is written unconditionally at the end, success or failure — even a
  deliberately-failing invocation still stamps the real heartbeat file.

**This is the boundary, stated plainly: the script has no dry-run or `--help` mode that stops
short of the real `.fleet-locks` tree.** An operator's first real invocation of
`commander_drain.sh` always writes to the fleet-shared lock directory. Full captures:
`planning/BT.ticket.lane-coordination-operator-guide/evidence/_e_commander_drain_boundary.txt`.

---

## 4. Sending and receiving, from the operator's side

A message's address is its directory, not a field inside it —
`queue/<repo>/<lane>/inbox/<ts>-<uuid>.json`. To see what is queued for a lane, list its `inbox/`
and `processing/`; a file sitting in `processing/` across more than one drain means something
started routing it and did not finish — that is evidence, not a bug, per
`orchestration-commander.md` step 2.

A drain moves a message `inbox/ → processing/` (one receipt appended), routes and acts on it, then
`processing/ → done/` (a second receipt appended) once fully handled — never both moves at once,
and never twice for the same `message_id` (a repeated receipt for one transition is a named
error, the double-processing signal `check_messages.py` exists to catch).

The **agent-facing** send/verify/respond contract — composing an envelope, verifying a claim
before acting on it, the interrupt discipline, and the four-verdict response shape — is owned by
[`.claude/skills/ping-agent/SKILL.md`](../../.claude/skills/ping-agent/SKILL.md); this page does
not duplicate it. As an operator, the piece worth knowing going in: every ping is written to disk
*in addition to* being sent, so the durable record survives even if the fast channel is missed.

---

## 5. Running the commander

```bash
./scripts/commander_drain.sh [--repo NAME] [--lane NAME]
```

`--repo`/`--lane` default to this repo's basename and `main`. Three knobs, all with defaults:

| Knob | Default | What it does |
|---|---|---|
| `COMMANDER_DRAIN_TIMEOUT_SECS` | `900` | Deliberately not `bastion ask`'s own 180s default — a drain reads the whole queue plus fleet state and can legitimately run long. |
| `COMMANDER_LAUNCH_CMD` | Sonnet | The model tier the drain turn runs on. |
| `FLEET_LOCK_DIR` | resolved per §2 | Only affects the informational inbox count read by the wrapper — **not** `HEARTBEAT_DIR` (see §3e); it does not redirect the drain away from the real tree. |

**Nothing schedules a drain today.** Kind-triggered drains need no scheduler — a lane sends
`RENDEZVOUS` or `LEASE_RELEASE` and the receiving lane drains at its own next block boundary — but
the 20–30 minute heartbeat drain has no invoker: cron on the Mac Mini is blocked behind `HQ.8.A`.
Until that lands, a drain happens only when an operator runs the wrapper by hand.

**The commit rule, in the operator's terms.** The commander **re-derives, it never detects** — it
does not scan `git status` guessing which dirty files look derived. It runs
`scripts/emit_state_write.sh`, and commits **exactly** the paths that script's own manifest names
(`$LOG_DIR/.emit_wrote`, the `I_EMIT_WROTE` set) — nothing more. Anything left dirty outside that
manifest is an **authored orphan**: the drain **reports** it, and does **not** commit it. If a
drain's report names an authored orphan, that is the commander working correctly, not a bug — it
means a human wrote something that has not yet been committed, and the commander is refusing to
guess whether that file belongs in its commit.

---

## 6. Troubleshooting

| Symptom | Likely cause | What to check |
|---|---|---|
| A lane will not start | A stale or duplicate exclusive lease is already held on the repo, or the registry claim step never ran. | `check_lane_agents.py --lock-dir <dir>` for a `FAIL duplicate exclusive lease` line naming both claimants (§3c); confirm the lock dir resolved to the one you expect (§2 precedence). |
| A lease looks stale | `acquired_at` is far older than a normal block duration and was never released at lane close. | The lease's `acquired_at` age (`lease.schema.json`: it doubles as the lease's heartbeat) — `check_lane_agents.py` reports the age and agent name but, having no `ListAgents` access, cannot itself tell "abandoned" from "merely slow"; join it against `ListAgents` yourself before deciding. |
| A message was sent but nothing happened | The message is sitting in `inbox/` (no drain has run yet) or stuck in `processing/` (a drain started routing it and did not finish). | List `queue/<repo>/<lane>/{inbox,processing}/` and `receipts.jsonl` for that `message_id` — zero receipts means undrained; one `inbox->processing` receipt with none since means an interrupted drain, not a lost message. |
| The drain never runs | Nothing schedules the heartbeat drain — cron on the Mac Mini is blocked behind `HQ.8.A` — so only kind-triggered drains (`RENDEZVOUS`/`LEASE_RELEASE`) or a manual `commander_drain.sh` invocation happen at all. | Whether the sending lane used a kind that self-triggers a drain (§4); otherwise run `./scripts/commander_drain.sh` by hand. |
| All four `validate-brain` flags red at once, naming an unrelated repo | A single file's OKF frontmatter fence got displaced or duplicated — a `---` no longer at line 1 fails `--structure`, `--links`, `--graph` and `--state` simultaneously, reading as a corpus-wide regression rather than one bad file (standing rule 11). | Find the file whose frontmatter isn't at line 1 first — the repo the error names is often just the first one the sweep reached, not the one that broke. |

---

## See also

- [`orchestration.md`](orchestration.md) — the lane lifecycle this layer sits underneath.
- [`.claude/skills/ping-agent/SKILL.md`](../../.claude/skills/ping-agent/SKILL.md) — the
  agent-facing send/verify/respond contract.
- [`.claude/commands/orchestration-commander.md`](../../.claude/commands/orchestration-commander.md) —
  the full six-step drain procedure.
- [`planning/lane-coordination/plan.md`](../../planning/lane-coordination/plan.md) — design and
  scope cuts across `BT.6.A`–`BT.6.E`.
