#!/usr/bin/env python3
"""Fixture suite for the TARGET staleness verdict (BT.ticket.lane-heartbeat-goes-stale-mid-block,
task 1): a stale-but-otherwise-valid own-repo record must be REPORTED but must NOT gate.

NEW, currently UNGATED file -- deliberately separate from scripts/test_check_lane_agents.py, which
is a gates:true harness row and must not carry a red case while the checker is unfixed. This file
is run by hand (and later wired into planning/harness.json once green, in task 5) so the
before/after behavior can be observed without red-gating every concurrent lane in this repo.

Dependency-free, stdlib only, same discipline as scripts/test_check_lane_agents.py: every record
is built under a tempfile.mkdtemp() lock dir and passed via `--lock-dir` / the `run(lock_dir, ...)`
`lock_dir` argument -- the real `.fleet-locks` directory is never read or written.

Drives the module under test through its `run(lock_dir, quiet, now, repo)` entry point
(check_lane_agents.py:349) so `now` can be injected rather than sleeping for hours.

D68 applies: a checker never observed going red is not evidence. Case (a) below is EXPECTED TO
FAIL against the current, unfixed scripts/check_lane_agents.py -- that failure, pasted verbatim,
is this task's completion evidence. Case (b) is the positive control proving the exit-code
assertion in (a) is a real instrument: without a case that CAN fail, a passing case (a) would
prove nothing.

Run: python3 scripts/test_lane_staleness_verdict.py
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_lane_agents.py"

_spec = importlib.util.spec_from_file_location("check_lane_agents", MODULE_PATH)
check_lane_agents = importlib.util.module_from_spec(_spec)
sys.modules["check_lane_agents"] = check_lane_agents
_spec.loader.exec_module(check_lane_agents)

OWN_REPO = "base-template"

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _valid_registry(**overrides) -> dict:
    record = {
        "agent_name": "base-template-stale-verdict",
        "repo": OWN_REPO,
        "lane": "lane-coordination",
        "roadmap": "lane-coordination-roadmap",
        "started_at": _iso(_now() - timedelta(minutes=10)),
        "heartbeat": _iso(_now() - timedelta(minutes=1)),
    }
    record.update(overrides)
    return record


def _valid_lease(**overrides) -> dict:
    record = {
        "repo": OWN_REPO,
        "lane": "lane-coordination",
        "agent": "base-template-stale-verdict",
        "acquired_at": _iso(_now() - timedelta(minutes=1)),
        "kind": "exclusive",
    }
    record.update(overrides)
    return record


def _run_captured(lock_dir: Path, now=None, repo: str = OWN_REPO):
    """Call check_lane_agents.run() directly (never a subprocess, so `now` can be injected) and
    return (rc, stdout)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = check_lane_agents.run(lock_dir, quiet=True, now=now, repo=repo)
    return rc, buf.getvalue()


# --- case (a): staleness is reported but does not gate --------------------------------------
#
# EXPECTED RED against today's checker: staleness currently appends to `problems`, which
# increments `failed` and flips the exit code (check_lane_agents.py:371-380 for claims,
# :396-404 for leases). Task 2 makes this green by separating the STALENESS finding from the
# GATING verdict.

def check_own_stale_registry_claim_does_not_gate() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        now = _now()
        stale_delta = timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 60)
        stale_heartbeat = now - stale_delta
        agent_name = "base-template-stale-registry"
        _write_json(
            lock_dir / "lane-agents" / f"agent-{agent_name}.json",
            _valid_registry(agent_name=agent_name, heartbeat=_iso(stale_heartbeat)),
        )

        rc, out = _run_captured(lock_dir, now=now)
        check("TARGET: an own-repo registry claim past the staleness threshold does NOT fail "
              "the gating verdict (rc == 0)",
              rc == 0, f"rc: {rc}, output: {out}")
        check("the stale registry claim's agent name still appears in the output",
              agent_name in out, out)
        expected_age = int(stale_delta.total_seconds())
        check(f"the stale registry claim's age (~{expected_age}s) still appears in the output",
              str(expected_age) in out or f"{expected_age - 1}" in out or f"{expected_age + 1}" in out,
              out)


def check_own_stale_lease_does_not_gate() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        now = _now()
        stale_delta = timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 60)
        stale_heartbeat = now - stale_delta
        agent_name = "base-template-stale-lease"
        _write_json(
            lock_dir / "leases" / "lease-base-template.json",
            _valid_lease(agent=agent_name, heartbeat=_iso(stale_heartbeat)),
        )

        rc, out = _run_captured(lock_dir, now=now)
        check("TARGET: an own-repo lease past the staleness threshold does NOT fail "
              "the gating verdict (rc == 0)",
              rc == 0, f"rc: {rc}, output: {out}")
        check("the stale lease's agent name still appears in the output",
              agent_name in out, out)


# --- case (b): positive control -- the gate still bites on a structural problem -------------
#
# Proves the exit-code assertion in case (a) is a real instrument: a structurally invalid
# own-repo record (missing a REGISTRY_REQUIRED field) must still fail run(), both today and
# after task 2. Without this case, case (a) passing would prove nothing.

def check_own_structurally_invalid_registry_claim_still_gates() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        now = _now()
        record = _valid_registry(agent_name="base-template-missing-roadmap")
        del record["roadmap"]
        _write_json(lock_dir / "lane-agents" / "agent-base-template-missing-roadmap.json", record)

        rc, out = _run_captured(lock_dir, now=now)
        check("POSITIVE CONTROL: an own-repo registry claim missing a required field "
              "(`roadmap`) still fails the gating verdict (rc == 1)",
              rc == 1, f"rc: {rc}, output: {out}")
        check("the missing-field failure names the missing field",
              "roadmap" in out, out)


# --- case (c): an abandoned claim is still reported (block AC3) -----------------------------
#
# Same stale record as case (a); asserts BOTH the agent name and the numeric age are present in
# the output, not merely that some line was printed -- so the caller can still make the
# abandoned-vs-slow call against ListAgents.

def check_stale_claim_still_names_agent_and_age() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        now = _now()
        stale_delta = timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 500)
        stale_heartbeat = now - stale_delta
        agent_name = "base-template-abandoned-check"
        _write_json(
            lock_dir / "lane-agents" / f"agent-{agent_name}.json",
            _valid_registry(agent_name=agent_name, heartbeat=_iso(stale_heartbeat)),
        )

        rc, out = _run_captured(lock_dir, now=now)
        expected_age = int(stale_delta.total_seconds())
        check("the abandoned-vs-slow call needs the agent name in the output",
              agent_name in out, out)
        check("the abandoned-vs-slow call needs the numeric age in the output",
              any(str(expected_age + d) in out for d in range(-2, 3)), out)
        # Not asserting rc here -- case (a)/(b) already cover the gating verdict itself; this
        # case is specifically about the reported CONTENT surviving the report-not-gate change.
        del rc


def main() -> int:
    check_own_stale_registry_claim_does_not_gate()
    check_own_stale_lease_does_not_gate()
    check_own_structurally_invalid_registry_claim_still_gates()
    check_stale_claim_still_names_agent_and_age()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- the staleness verdict matches the TARGET (reported, not gating; "
          "structural failures still gate).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
