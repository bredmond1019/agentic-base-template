#!/usr/bin/env python3
"""Fixture suite for check_lane_agents.py (BT.6.A).

Self-contained, no pytest dependency, matching the fixture style of
test_check_lane_records.py: builds a synthetic `.fleet-locks/` corpus in a temp dir (never the
repo's real planning/ tree) and drives the real check_lane_agents.py module against it, both by
calling its functions directly and by running it as a subprocess against `--lock-dir`, so both
the validation logic and the CLI/exit-code contract are exercised.

D68 applies: a checker never observed going red is not evidence. Every negative fixture here
asserts a non-zero exit or a named diagnostic against a record built to trip exactly that rule --
none of them merely runs the checker and hopes.

Run: python3 scripts/test_check_lane_agents.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_lane_agents.py"

_spec = importlib.util.spec_from_file_location("check_lane_agents", MODULE_PATH)
check_lane_agents = importlib.util.module_from_spec(_spec)
sys.modules["check_lane_agents"] = check_lane_agents
_spec.loader.exec_module(check_lane_agents)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _valid_registry(**overrides) -> dict:
    record = {
        "agent_name": "base-template-b6",
        "repo": "base-template",
        "lane": "lane-coordination",
        "roadmap": "lane-coordination-roadmap",
        "started_at": _iso(_now() - timedelta(minutes=10)),
        "heartbeat": _iso(_now() - timedelta(minutes=1)),
    }
    record.update(overrides)
    return record


def _valid_lease(**overrides) -> dict:
    record = {
        "repo": "base-template",
        "lane": "lane-coordination",
        "agent": "base-template-b6",
        "acquired_at": _iso(_now() - timedelta(minutes=1)),
        "kind": "exclusive",
    }
    record.update(overrides)
    return record


# --- dependency hygiene ----------------------------------------------------------------------

def check_dependency_free() -> None:
    """The docstring is allowed to *mention* jsonschema; an actual import of it (or any other
    third-party package) is not."""
    import ast

    tree = ast.parse(MODULE_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    stdlib_and_local = {
        "argparse", "json", "os", "re", "sys", "datetime", "pathlib", "typing",
        "__future__", "check_lane_agents",
    }
    third_party = imported - stdlib_and_local
    check("check_lane_agents.py imports no third-party package (no jsonschema)",
          third_party == set(), f"unexpected imports: {sorted(third_party)}")


# --- positive: valid round-trip -----------------------------------------------------------

def check_positive_registry_and_lease_roundtrip() -> None:
    registry_problems = check_lane_agents.check_registry_record(_valid_registry())
    lease_problems = check_lane_agents.check_lease_record(_valid_lease())
    check("a valid registry claim round-trips with no problems",
          registry_problems == [], f"problems: {registry_problems}")
    check("a valid lease round-trips with no problems",
          lease_problems == [], f"problems: {lease_problems}")


# --- negative (a): missing required field --------------------------------------------------

def check_negative_missing_required_field() -> None:
    record = _valid_registry()
    del record["agent_name"]
    problems = check_lane_agents.check_registry_record(record)
    check("a registry claim missing `agent_name` is rejected",
          any("agent_name" in p for p in problems), f"problems: {problems}")


# --- negative (b): duplicate exclusive lease ------------------------------------------------

def check_negative_duplicate_exclusive_lease() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        _write_json(lock_dir / "leases" / "lease-alpha.json",
                    _valid_lease(lane="alpha", agent="agent-alpha", kind="exclusive"))
        _write_json(lock_dir / "leases" / "lease-beta.json",
                    _valid_lease(lane="beta", agent="agent-beta", kind="exclusive"))

        rc = check_lane_agents.run(lock_dir, quiet=True)
        check("two exclusive leases on the same repo makes run() fail",
              rc == 1, f"rc: {rc}")

        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--lock-dir", str(lock_dir), "--quiet"],
            capture_output=True, text=True,
        )
        check("the CLI exits non-zero on a duplicate exclusive lease",
              proc.returncode != 0, proc.stdout + proc.stderr)
        check("the failure names the first claimant (lane `alpha`, agent `agent-alpha`)",
              "alpha" in proc.stdout and "agent-alpha" in proc.stdout, proc.stdout)
        check("the failure names the second claimant (lane `beta`, agent `agent-beta`)",
              "beta" in proc.stdout and "agent-beta" in proc.stdout, proc.stdout)


# --- negative (c): stale heartbeat ----------------------------------------------------------

def check_negative_stale_heartbeat() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        stale_heartbeat = _now() - timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 60)
        _write_json(lock_dir / "lane-agents" / "agent-stale.json",
                    _valid_registry(agent_name="stale-agent", heartbeat=_iso(stale_heartbeat)))

        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--lock-dir", str(lock_dir), "--quiet"],
            capture_output=True, text=True,
        )
        check("a stale-heartbeat registry claim makes the CLI exit non-zero",
              proc.returncode != 0, proc.stdout + proc.stderr)
        check("the failure names the agent",
              "stale-agent" in proc.stdout, proc.stdout)
        check("the failure reports the heartbeat age",
              "stale" in proc.stdout.lower(), proc.stdout)


# --- negative (d): malformed JSON -----------------------------------------------------------

def check_negative_malformed_json() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        path = lock_dir / "lane-agents" / "agent-broken.json"
        _write(path, "{ this is not valid json")

        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--lock-dir", str(lock_dir), "--quiet"],
            capture_output=True, text=True,
        )
        check("malformed JSON makes the CLI exit non-zero",
              proc.returncode != 0, proc.stdout + proc.stderr)
        check("malformed JSON is reported as a named parse error, not silently skipped",
              "does not parse" in proc.stdout, proc.stdout)


def check_negative_nonexistent_path_is_named_error() -> None:
    """_load() reports a missing path as a named error rather than treating it as absent."""
    record, error = check_lane_agents._load(Path("/does/not/exist/agent-ghost.json"))
    check("a nonexistent record path is reported as a named error",
          error is not None and "does not exist" in error, f"error: {error}")
    check("a nonexistent record path yields no record",
          record is None, f"record: {record}")


# --- asymmetry: shared legal, exclusive illegal ---------------------------------------------

def check_shared_vs_exclusive_asymmetry() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        _write_json(lock_dir / "leases" / "lease-shared-1.json",
                    _valid_lease(lane="one", agent="agent-one", kind="shared"))
        _write_json(lock_dir / "leases" / "lease-shared-2.json",
                    _valid_lease(lane="two", agent="agent-two", kind="shared"))
        shared_rc = check_lane_agents.run(lock_dir, quiet=True)
        check("two shared leases on the same repo pass",
              shared_rc == 0, f"rc: {shared_rc}")

    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        _write_json(lock_dir / "leases" / "lease-excl-1.json",
                    _valid_lease(lane="one", agent="agent-one", kind="exclusive"))
        _write_json(lock_dir / "leases" / "lease-excl-2.json",
                    _valid_lease(lane="two", agent="agent-two", kind="exclusive"))
        exclusive_rc = check_lane_agents.run(lock_dir, quiet=True)
        check("two exclusive leases on the same repo fail",
              exclusive_rc == 1, f"rc: {exclusive_rc}")


# --- boundary: heartbeat exactly at the threshold --------------------------------------------

def check_boundary_heartbeat_exactly_at_threshold() -> None:
    now = _now()
    exactly_at_threshold = now - timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS)
    age = check_lane_agents.staleness_seconds(_iso(exactly_at_threshold), now=now)
    check("staleness_seconds reports (approximately) the threshold itself",
          age is not None and abs(age - check_lane_agents.STALE_THRESHOLD_SECONDS) < 1,
          f"age: {age}")

    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        _write_json(lock_dir / "lane-agents" / "agent-boundary.json",
                    _valid_registry(agent_name="boundary-agent",
                                     heartbeat=_iso(exactly_at_threshold)))
        rc = check_lane_agents.run(lock_dir, quiet=True, now=now)
        check("a heartbeat exactly AT the threshold does not trip staleness (`>`, not `>=`)",
              rc == 0, f"rc: {rc}")

    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        just_past = now - timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 1)
        _write_json(lock_dir / "lane-agents" / "agent-past.json",
                    _valid_registry(agent_name="past-agent", heartbeat=_iso(just_past)))
        rc = check_lane_agents.run(lock_dir, quiet=True, now=now)
        check("a heartbeat one second PAST the threshold trips staleness",
              rc == 1, f"rc: {rc}")


# --- positive: no records is not a failure ----------------------------------------------------

def check_no_records_is_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--lock-dir", str(lock_dir), "--quiet"],
            capture_output=True, text=True,
        )
        check("an empty corpus exits 0 (not a failure)",
              proc.returncode == 0, proc.stdout + proc.stderr)
        check("an empty corpus says so explicitly",
              "no lane-agent records found" in proc.stdout, proc.stdout)


def main() -> int:
    check_dependency_free()
    check_positive_registry_and_lease_roundtrip()
    check_negative_missing_required_field()
    check_negative_duplicate_exclusive_lease()
    check_negative_stale_heartbeat()
    check_negative_malformed_json()
    check_negative_nonexistent_path_is_named_error()
    check_shared_vs_exclusive_asymmetry()
    check_boundary_heartbeat_exactly_at_threshold()
    check_no_records_is_not_a_failure()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_lane_agents.py holds against the fixture corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
