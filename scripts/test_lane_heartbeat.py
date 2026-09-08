#!/usr/bin/env python3
"""Fixture suite for scripts/lane_heartbeat.py (BT.ticket.lane-heartbeat-goes-stale-mid-block,
task 3).

Dependency-free, stdlib only, same discipline as scripts/test_check_lane_agents.py and
scripts/test_lane_staleness_verdict.py: every record is built under a tempfile.mkdtemp() lock
dir and passed via the module's own `run(lock_dir, agent, repo, current_block, now)` entry point
so `now` can be injected rather than sleeping -- the real `.fleet-locks` directory is never read
or written.

Run: python3 scripts/test_lane_heartbeat.py
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
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location(
    "lane_heartbeat", SCRIPTS_DIR / "lane_heartbeat.py"
)
lane_heartbeat = importlib.util.module_from_spec(_spec)
sys.modules["lane_heartbeat"] = lane_heartbeat
_spec.loader.exec_module(lane_heartbeat)

_check_spec = importlib.util.spec_from_file_location(
    "check_lane_agents", SCRIPTS_DIR / "check_lane_agents.py"
)
check_lane_agents = importlib.util.module_from_spec(_check_spec)
sys.modules["check_lane_agents"] = check_lane_agents
_check_spec.loader.exec_module(check_lane_agents)

OWN_REPO = "base-template"
AGENT = "base-template-heartbeat-test"

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _valid_claim(**overrides) -> dict:
    now = _now()
    record = {
        "agent_name": AGENT,
        "repo": OWN_REPO,
        "lane": "lane-coordination",
        "roadmap": "lane-coordination-roadmap",
        "started_at": _iso(now - timedelta(hours=2)),
        "heartbeat": _iso(now - timedelta(minutes=5)),
    }
    record.update(overrides)
    return record


def _valid_lease(**overrides) -> dict:
    now = _now()
    record = {
        "repo": OWN_REPO,
        "lane": "lane-coordination",
        "agent": AGENT,
        "acquired_at": _iso(now - timedelta(hours=2)),
        "kind": "exclusive",
    }
    record.update(overrides)
    return record


def _seed(lock_dir: Path, claim: dict, lease: dict) -> tuple[Path, Path]:
    claim_path = lock_dir / "lane-agents" / f"agent-{claim['agent_name']}.json"
    lease_path = lock_dir / "leases" / f"lease-{lease['repo']}.json"
    _write_json(claim_path, claim)
    _write_json(lease_path, lease)
    return claim_path, lease_path


# --- (a) heartbeat moves; started_at/acquired_at are byte-identical -------------------------

def check_heartbeat_moves_acquisition_fields_untouched() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        claim = _valid_claim()
        lease = _valid_lease()
        claim_path, lease_path = _seed(lock_dir, claim, lease)

        pre_started_at = claim["started_at"]
        pre_acquired_at = lease["acquired_at"]
        pre_heartbeat_claim = claim["heartbeat"]
        pre_heartbeat_lease = lease.get("heartbeat")

        rc = lane_heartbeat.run(lock_dir, AGENT, OWN_REPO)
        check("run() exits 0 when both records exist", rc == 0, f"rc: {rc}")

        post_claim = json.loads(claim_path.read_text())
        post_lease = json.loads(lease_path.read_text())

        check("claim started_at is byte-identical before/after",
              post_claim["started_at"] == pre_started_at,
              f"before: {pre_started_at}, after: {post_claim['started_at']}")
        check("lease acquired_at is byte-identical before/after",
              post_lease["acquired_at"] == pre_acquired_at,
              f"before: {pre_acquired_at}, after: {post_lease['acquired_at']}")
        check("claim heartbeat moved",
              post_claim["heartbeat"] != pre_heartbeat_claim,
              f"before: {pre_heartbeat_claim}, after: {post_claim['heartbeat']}")
        check("lease heartbeat moved (or was newly written)",
              post_lease.get("heartbeat") != pre_heartbeat_lease,
              f"before: {pre_heartbeat_lease}, after: {post_lease.get('heartbeat')}")


# --- (b) positive control: frozen-clock heartbeat equals the injected time ------------------

def check_frozen_clock_heartbeat_equals_injected_time() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        claim = _valid_claim()
        lease = _valid_lease()
        claim_path, lease_path = _seed(lock_dir, claim, lease)

        frozen_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        expected = _iso(frozen_now)

        rc = lane_heartbeat.run(lock_dir, AGENT, OWN_REPO, now=frozen_now)
        check("run() exits 0 with a frozen clock", rc == 0, f"rc: {rc}")

        post_claim = json.loads(claim_path.read_text())
        post_lease = json.loads(lease_path.read_text())

        check("POSITIVE CONTROL: claim heartbeat equals the injected frozen time exactly",
              post_claim["heartbeat"] == expected,
              f"expected: {expected}, got: {post_claim['heartbeat']}")
        check("POSITIVE CONTROL: lease heartbeat equals the injected frozen time exactly",
              post_lease["heartbeat"] == expected,
              f"expected: {expected}, got: {post_lease['heartbeat']}")


# --- (c) --current-block never adds the field to a claim that never had it ------------------

def check_current_block_never_added_when_absent() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        claim = _valid_claim()
        assert "current_block" not in claim
        lease = _valid_lease()
        claim_path, _ = _seed(lock_dir, claim, lease)

        rc = lane_heartbeat.run(lock_dir, AGENT, OWN_REPO, current_block="BT.ticket.some-block")
        check("run() exits 0", rc == 0, f"rc: {rc}")

        post_claim = json.loads(claim_path.read_text())
        check("current_block is NOT added to a claim that never carried it",
              "current_block" not in post_claim, post_claim)
        check("block_started_at is NOT added either",
              "block_started_at" not in post_claim, post_claim)


def check_current_block_updated_when_already_present() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        now = _now()
        claim = _valid_claim(
            current_block="BT.ticket.old-block",
            block_started_at=_iso(now - timedelta(hours=1)),
        )
        lease = _valid_lease()
        claim_path, _ = _seed(lock_dir, claim, lease)

        frozen_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        rc = lane_heartbeat.run(
            lock_dir, AGENT, OWN_REPO, current_block="BT.ticket.new-block", now=frozen_now
        )
        check("run() exits 0", rc == 0, f"rc: {rc}")

        post_claim = json.loads(claim_path.read_text())
        check("current_block is updated to the new value",
              post_claim.get("current_block") == "BT.ticket.new-block", post_claim)
        check("block_started_at is re-stamped to the injected time",
              post_claim.get("block_started_at") == _iso(frozen_now), post_claim)


# --- (d) a missing claim or lease exits non-zero and names the path -------------------------

def check_missing_claim_exits_nonzero_and_names_path() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        lease = _valid_lease()
        _write_json(lock_dir / "leases" / f"lease-{lease['repo']}.json", lease)
        # No claim file written at all.

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lane_heartbeat.run(lock_dir, AGENT, OWN_REPO)
        out = buf.getvalue()

        check("run() exits non-zero when the claim is missing", rc != 0, f"rc: {rc}")
        expected_path = str(lock_dir / "lane-agents" / f"agent-{AGENT}.json")
        check("the missing claim's path is named in the output",
              expected_path in out, out)
        check("no claim file was created",
              not (lock_dir / "lane-agents" / f"agent-{AGENT}.json").exists(), out)


def check_missing_lease_exits_nonzero_and_names_path() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        claim = _valid_claim()
        _write_json(lock_dir / "lane-agents" / f"agent-{claim['agent_name']}.json", claim)
        # No lease file written at all.

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lane_heartbeat.run(lock_dir, AGENT, OWN_REPO)
        out = buf.getvalue()

        check("run() exits non-zero when the lease is missing", rc != 0, f"rc: {rc}")
        expected_path = str(lock_dir / "leases" / f"lease-{OWN_REPO}.json")
        check("the missing lease's path is named in the output",
              expected_path in out, out)
        check("no lease file was created",
              not (lock_dir / "leases" / f"lease-{OWN_REPO}.json").exists(), out)


# --- the writer's output must satisfy check_lane_agents.py itself ---------------------------

def check_post_write_fixture_passes_the_checker() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        claim = _valid_claim()
        lease = _valid_lease()
        _seed(lock_dir, claim, lease)

        rc = lane_heartbeat.run(lock_dir, AGENT, OWN_REPO)
        check("run() exits 0", rc == 0, f"rc: {rc}")

        checker_rc = check_lane_agents.run(lock_dir, quiet=True, repo=OWN_REPO)
        check("check_lane_agents.py exits 0 against the fixture directory the writer just wrote",
              checker_rc == 0, f"checker rc: {checker_rc}")


def main() -> int:
    check_heartbeat_moves_acquisition_fields_untouched()
    check_frozen_clock_heartbeat_equals_injected_time()
    check_current_block_never_added_when_absent()
    check_current_block_updated_when_already_present()
    check_missing_claim_exits_nonzero_and_names_path()
    check_missing_lease_exits_nonzero_and_names_path()
    check_post_write_fixture_passes_the_checker()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- lane_heartbeat.py re-stamps heartbeat only, never acquisition fields, "
          "never creates a missing record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
