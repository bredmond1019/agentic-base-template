---
type: Guide
title: Lane coordination — the operator's guide to the layer under orchestration
description: The registry, leases, message queue, ping contract and commander — what to run, how to tell installed-and-idle from running, and what to check when something looks stuck.
doc_id: base-template-lane-coordination-guide
layer: [factory]
project: base-template
status: active
keywords: [lane coordination, registry, lease, message queue, commander, FLEET_LOCK_DIR]
related: [base-template-workflows-index, base-template-orchestration-guide, plan-lane-coordination, base-template-docs-index]
---

# Lane coordination — the operator's guide to the layer under orchestration

Five mechanisms that let concurrent lanes claim identity, avoid each other's working trees, pass
messages, and get swept automatically. [`orchestration.md`](orchestration.md) covers the lane
lifecycle above this.

> Paths are relative to the brain root (`agentic-portfolio/`) unless marked as this repo's.

---

## Quickstart

```bash
# Where is the lock directory?  --lock-dir > $FLEET_LOCK_DIR > <brain.toml dir>/.fleet-locks
python3 scripts/check_lane_agents.py          # registry claims + lease conflicts
python3 scripts/check_messages.py             # queued messages
./scripts/commander_drain.sh                  # sweep the queue  (WRITES TO THE REAL TREE — see §5)
```

**Read this before anything else:** both checkers exit `0` **silently on an empty corpus**, and
`harness.json` gates on exactly that. **A green gate does not mean the system is running.**

| You see | It means |
|---|---|
| `no lane-agent records found` / `no message records found`, exit 0 | **Installed and idle.** Nothing has claimed or sent anything. |
| `N record(s) checked, 0 failed` | **Running.** |
| `FAIL duplicate exclusive lease(s) on repo …` | Two lanes claim the same repo. Both are named — see [§6](#6-troubleshooting). |

Only this page tells idle from running. The gate cannot.

---

## 1. The five pieces

Each shipped to fix one measured incident. The artifact is authoritative; this page does not
restate schemas.

| Piece | Problem it solves | Artifact |
|---|---|---|
| **Registry** | `ListAgents` nicknames are unstable across restart and carry no repo/lane/roadmap — measured with 11 concurrent peers, 2026-08-21 — so a lane could not be addressed by role. | [`lane-agent.schema.json`](../../.claude/workflows/lane-agent.schema.json) |
| **Leases** | The largest measured incident class in the corpus: one lane discarding another's uncommitted work, because nothing let it discover the tree was held. | [`lease.schema.json`](../../.claude/workflows/lease.schema.json) |
| **Message queue** | A cross-lane signal ("bastion:BA.21.A is unblocked") existed only as prose someone happened to notice. | [`message.schema.json`](../../.claude/workflows/message.schema.json) |
| **Ping contract** | Keeps a fast informal channel from replacing the durable one: every claim is written to disk *and* sent, and every received claim is verified before being acted on. | [`ping-agent/SKILL.md`](../../.claude/skills/ping-agent/SKILL.md) |
| **Commander** | Nothing swept the queue or re-derived generated surfaces without a human doing it by hand. | [`orchestration-commander.md`](../../.claude/commands/orchestration-commander.md) |

Design rationale and deliberate cuts: [`planning/lane-coordination/plan.md`](../../planning/lane-coordination/plan.md).

---

## 2. Setup

**Lock-directory precedence**, identical in every tool: `--lock-dir` flag → `FLEET_LOCK_DIR` env →
`brain.toml` found by walking up, joined with `.fleet-locks`. The reference implementation is
`resolve_lock_dir()` in `scripts/check_lane_agents.py`, mirrored in `check_messages.py` and
`fleet_concurrency_check.py`.

```
<lock_dir>/
  lane-agents/agent-*.json      # registry claims
  leases/lease-*.json           # repo leases
  queue/<repo>/<lane>/
    inbox/ processing/ done/    # message states
    receipts.jsonl              # append-only state-transition ledger
  commander-heartbeats/         # written only by commander_drain.sh
```

---

## 3. Verify it works (cold start)

Run against a **scratch** `FLEET_LOCK_DIR`, never the real `.fleet-locks`. Full captured output:
`planning/BT.ticket.lane-coordination-operator-guide/evidence/`.

**Empty corpus** — both checkers exit 0 silently. That is the baseline, not a pass.

**A claim + a lease.** Hand-write `lane-agents/agent-test1.json` and `leases/lease-test1.json` to
their schemas, then:

```
ok   .../lane-agents/agent-test1.json
ok   .../leases/lease-test1.json
2 record(s) checked, 0 failed          exit 0
```

**A conflicting lease.** Add a second `"kind": "exclusive"` lease on the same `repo`:

```
FAIL duplicate exclusive lease(s) on repo `base-template`: lane `…-task` agent `…test1`
     (.../lease-test1.json), lane `some-other-lane` agent `…test2` (.../lease-test2.json)
3 record(s) checked, 1 failed          exit 1
```

Two *shared* leases do not conflict. Only exclusive-on-exclusive or exclusive-on-shared does.

**A message end to end.** Drop two envelopes in `queue/<repo>/<lane>/inbox/`, then `drain_queue()`
and `complete_message()` move them `inbox → processing → done`, appending one receipt per
transition. Re-running the checker over the drained queue still exits 0.

---

## 4. Sending and receiving

- **A message's address is its directory**, not a field inside it:
  `queue/<repo>/<lane>/inbox/<ts>-<uuid>.json`.
- **To see what is queued:** list that lane's `inbox/` and `processing/`.
- **A file in `processing/` across two drains** = something started routing it and did not finish.
  That is evidence, not a bug (`orchestration-commander.md` step 2).
- **A drain never moves twice at once**, and never twice for one `message_id`. A repeated receipt
  for one transition is the double-processing signal `check_messages.py` exists to catch.

The agent-facing send/verify/respond contract — envelope composition, verifying before acting, the
interrupt discipline, the four-verdict response — is owned by
[`ping-agent/SKILL.md`](../../.claude/skills/ping-agent/SKILL.md). The operator-relevant half:
**every ping is written to disk as well as sent**, so the record survives a missed message.

---

## 5. Running the commander

```bash
./scripts/commander_drain.sh [--repo NAME] [--lane NAME]
```

> **There is no dry-run or `--help` that stops short of the real tree.** `find_brain_root` walks up
> from the *script's own location*, so it always resolves the real `agentic-portfolio`.
> `HEARTBEAT_DIR` is hardcoded to `$BRAIN_ROOT/.fleet-locks/commander-heartbeats` and is `mkdir -p`'d
> before the inbox is even read, and the heartbeat file is written at the end whether the drain
> succeeded or failed. **`FLEET_LOCK_DIR` does not redirect this** — it only changes the
> informational inbox count. Your first invocation writes to the fleet-shared lock directory.

Defaults: `--repo` is this repo's basename, `--lane` is `main`.

| Knob | Default | What it does |
|---|---|---|
| `COMMANDER_DRAIN_TIMEOUT_SECS` | `900` | Deliberately not `bastion ask`'s 180s — a drain reads the whole queue plus fleet state. |
| `COMMANDER_LAUNCH_CMD` | Sonnet | Model tier for the drain turn. |
| `FLEET_LOCK_DIR` | per §2 | Informational inbox count only — **not** `HEARTBEAT_DIR`. |

**The commit rule: the commander re-derives, it never detects.** It does not scan `git status`
guessing which dirty files look derived. It runs `scripts/emit_state_write.sh` and commits exactly
the paths that script's own manifest names (`$LOG_DIR/.emit_wrote`, the `I_EMIT_WROTE` set).
Anything dirty outside that manifest is an **authored orphan** — reported, never committed. A drain
reporting an authored orphan is the commander working correctly: a human wrote something, and it
refuses to guess whether that belongs in its commit.

**Nothing schedules a drain today.** Kind-triggered drains need no scheduler — a lane sends
`RENDEZVOUS` or `LEASE_RELEASE` and the receiver drains at its next block boundary. The 20–30
minute heartbeat has no invoker: cron on the Mac Mini is blocked behind `HQ.8.A`.

---

## 6. Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| A lane will not start | Stale or duplicate exclusive lease on the repo, or the registry claim never ran | `check_lane_agents.py --lock-dir <dir>` for a `FAIL duplicate exclusive lease` line — it names both claimants. Confirm the lock dir resolved where you expect (§2). |
| A lease looks stale | Never released at lane close | The lease's `acquired_at` age — it doubles as the heartbeat. The checker reports age and agent but has no `ListAgents` access, so it **cannot** tell abandoned from slow. Join it against `ListAgents` yourself. |
| Sent a message, nothing happened | Undrained, or a drain died mid-route | `queue/<repo>/<lane>/{inbox,processing}/` and `receipts.jsonl`. Zero receipts = undrained. One `inbox->processing` and nothing since = interrupted drain, not a lost message. |
| The drain never runs | Nothing schedules the heartbeat (`HQ.8.A`) | Whether the sender used a self-triggering kind (§4). Otherwise run the wrapper by hand. |
| All four `validate-brain` flags red, naming an unrelated repo | One file's OKF frontmatter fence is displaced or duplicated — a `---` not at line 1 fails all four at once | Find the file whose frontmatter isn't at line 1. The repo named is often just the first the sweep reached, not the one that broke. |

---

## See also

- [`orchestration.md`](orchestration.md) — the lane lifecycle above this layer.
- [`ping-agent/SKILL.md`](../../.claude/skills/ping-agent/SKILL.md) — agent-facing ping contract.
- [`orchestration-commander.md`](../../.claude/commands/orchestration-commander.md) — the six-step drain.
- [`planning/lane-coordination/plan.md`](../../planning/lane-coordination/plan.md) — design, `BT.6.A`–`BT.6.E`.
