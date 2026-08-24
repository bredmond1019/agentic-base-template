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


# --- current_block / block_started_at: optional, load-bearing case is absence --------------

# A REAL live claim, copied verbatim from .fleet-locks/lane-agents/agent-base-template-4c.json
# on 2026-08-23 -- every claim on disk today lacks current_block and block_started_at, and a
# regression here red-gates the whole fleet at once, so the absence case is asserted against an
# actual on-disk record rather than an invented one.
REAL_LIVE_CLAIM_WITHOUT_NEW_FIELDS = {
    "agent_name": "base-template-4c",
    "repo": "base-template",
    "lane": "base-template",
    "roadmap": "autonomous-foundation",
    "started_at": "2026-08-23T12:17:35Z",
    "heartbeat": "2026-08-23T17:11:53Z",
}


def check_real_live_claim_without_new_fields_validates() -> None:
    problems = check_lane_agents.check_registry_record(REAL_LIVE_CLAIM_WITHOUT_NEW_FIELDS)
    check("a real live claim lacking current_block/block_started_at validates exactly as today",
          problems == [], f"problems: {problems}")


def check_registry_with_both_new_fields_valid() -> None:
    record = _valid_registry(
        current_block="BT.ticket.lanes-do-not-record-their-current-block",
        block_started_at=_iso(_now() - timedelta(minutes=3)),
    )
    problems = check_lane_agents.check_registry_record(record)
    check("a registry claim with both current_block and block_started_at present validates",
          problems == [], f"problems: {problems}")


def check_registry_malformed_block_started_at_rejected() -> None:
    record = _valid_registry(
        current_block="BT.ticket.lanes-do-not-record-their-current-block",
        block_started_at="not-a-timestamp",
    )
    problems = check_lane_agents.check_registry_record(record)
    check("a malformed block_started_at is rejected",
          any("block_started_at" in p for p in problems), f"problems: {problems}")


def check_registry_empty_current_block_rejected() -> None:
    record = _valid_registry(
        current_block="",
        block_started_at=_iso(_now() - timedelta(minutes=3)),
    )
    problems = check_lane_agents.check_registry_record(record)
    check("an empty current_block is rejected",
          any("current_block" in p for p in problems), f"problems: {problems}")


def check_lane_schema_json_unchanged_by_this_task() -> None:
    lane_schema = REPO_ROOT / ".claude" / "workflows" / "lane.schema.json"
    text = lane_schema.read_text()
    check("lane.schema.json does not define current_block (mev's LaneRecord is deny_unknown_fields)",
          '"current_block"' not in text, "lane.schema.json unexpectedly mentions current_block")
    check("lane.schema.json does not define block_started_at",
          '"block_started_at"' not in text, "lane.schema.json unexpectedly mentions block_started_at")


# --- scope: optional, defaults to repo, rejects unknown values -----------------------------

def check_lease_scope_values() -> None:
    absent = check_lane_agents.check_lease_record(_valid_lease())
    repo_scoped = check_lane_agents.check_lease_record(_valid_lease(scope="repo"))
    fleet_scoped = check_lane_agents.check_lease_record(_valid_lease(scope="fleet"))
    bad = check_lane_agents.check_lease_record(_valid_lease(scope="everything"))
    check("a lease with no `scope` key is valid (absent means repo)",
          absent == [], f"problems: {absent}")
    check("a lease with `scope: repo` is valid",
          repo_scoped == [], f"problems: {repo_scoped}")
    check("a lease with `scope: fleet` is valid",
          fleet_scoped == [], f"problems: {fleet_scoped}")
    check("a lease with `scope: everything` is rejected and names the bad value",
          bad != [] and any("everything" in p for p in bad), f"problems: {bad}")


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


# --- lease heartbeat: present/absent, fallback, cross-script agreement -----------------------

def check_lease_heartbeat_allowed_and_validated() -> None:
    with_heartbeat = check_lane_agents.check_lease_record(
        _valid_lease(heartbeat=_iso(_now() - timedelta(minutes=1))))
    check("a lease with a `heartbeat` key round-trips with no problems",
          with_heartbeat == [], f"problems: {with_heartbeat}")

    bad_heartbeat = check_lane_agents.check_lease_record(
        _valid_lease(heartbeat="not-a-timestamp"))
    check("a lease with a malformed `heartbeat` is rejected",
          any("heartbeat" in p for p in bad_heartbeat), f"problems: {bad_heartbeat}")


def check_lease_liveness_timestamp_prefers_heartbeat() -> None:
    old_acquired = _iso(_now() - timedelta(hours=5))
    fresh_heartbeat = _iso(_now() - timedelta(minutes=1))
    record = _valid_lease(acquired_at=old_acquired, heartbeat=fresh_heartbeat)
    picked = check_lane_agents.lease_liveness_timestamp(record)
    check("lease_liveness_timestamp() reads `heartbeat` when present, ignoring a stale `acquired_at`",
          picked == fresh_heartbeat, f"picked: {picked}")


def check_lease_without_heartbeat_falls_back_to_acquired_at() -> None:
    """THE LOAD-BEARING CASE: a fixture copied verbatim from a real, currently-live lease on
    disk (.fleet-locks/leases/lease-base-template.json, which -- like every lease in the fleet
    today -- lacks `heartbeat`) must be judged on `acquired_at` exactly as before this change."""
    real_lease_fixture = {
        "repo": "base-template",
        "lane": "base-template",
        "agent": "base-template-4c",
        "acquired_at": _iso(_now() - timedelta(minutes=2)),
        "kind": "shared",
    }
    check("a real-shaped lease fixture has no `heartbeat` field",
          "heartbeat" not in real_lease_fixture)
    picked = check_lane_agents.lease_liveness_timestamp(real_lease_fixture)
    check("lease_liveness_timestamp() falls back to `acquired_at` when `heartbeat` is absent",
          picked == real_lease_fixture["acquired_at"], f"picked: {picked}")

    problems = check_lane_agents.check_lease_record(real_lease_fixture)
    check("the real-shaped lease fixture (no heartbeat) still validates cleanly",
          problems == [], f"problems: {problems}")

    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        stale_acquired = _now() - timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 60)
        no_heartbeat_stale = dict(real_lease_fixture)
        no_heartbeat_stale["acquired_at"] = _iso(stale_acquired)
        _write_json(lock_dir / "leases" / "lease-no-heartbeat.json", no_heartbeat_stale)
        rc = check_lane_agents.run(lock_dir, quiet=True)
        check("a lease with no heartbeat and a stale acquired_at is still flagged stale "
              "(unchanged behavior)", rc == 1, f"rc: {rc}")


def check_lease_with_fresh_heartbeat_survives_stale_acquired_at() -> None:
    """A lease heartbeated recently must NOT be flagged stale even though its (immutable)
    acquired_at is old -- this is the whole point of splitting the two fields."""
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        old_acquired = _now() - timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 3600)
        fresh_heartbeat = _now() - timedelta(minutes=1)
        _write_json(lock_dir / "leases" / "lease-heartbeated.json",
                    _valid_lease(acquired_at=_iso(old_acquired), heartbeat=_iso(fresh_heartbeat)))
        rc = check_lane_agents.run(lock_dir, quiet=True)
        check("a lease with a fresh heartbeat is NOT stale despite a very old acquired_at",
              rc == 0, f"rc: {rc}")


def check_lease_cross_script_agreement_with_fleet_concurrency_check() -> None:
    """check_lane_agents.py and fleet_concurrency_check.py must reach the SAME liveness verdict
    for the same lease record -- asserted directly, not inferred from the shared import."""
    import importlib.util as _ilu

    fcc_path = REPO_ROOT / "scripts" / "fleet_concurrency_check.py"
    _fcc_spec = _ilu.spec_from_file_location("fleet_concurrency_check", fcc_path)
    fleet_concurrency_check = _ilu.module_from_spec(_fcc_spec)
    sys.modules["fleet_concurrency_check"] = fleet_concurrency_check
    _fcc_spec.loader.exec_module(fleet_concurrency_check)

    now = _now()
    fresh_heartbeat_stale_acquired = _valid_lease(
        acquired_at=_iso(now - timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 3600)),
        heartbeat=_iso(now - timedelta(minutes=1)),
    )
    no_heartbeat_stale_acquired = _valid_lease(
        acquired_at=_iso(now - timedelta(seconds=check_lane_agents.STALE_THRESHOLD_SECONDS + 60)),
    )

    for label, record in [
        ("fresh heartbeat / stale acquired_at", fresh_heartbeat_stale_acquired),
        ("no heartbeat / stale acquired_at", no_heartbeat_stale_acquired),
    ]:
        with tempfile.TemporaryDirectory() as td:
            lock_dir = Path(td) / ".fleet-locks"
            _write_json(lock_dir / "leases" / "lease-agree.json", record)

            checker_age = check_lane_agents.staleness_seconds(
                check_lane_agents.lease_liveness_timestamp(record), now=now)
            checker_is_live = not (checker_age is not None
                                    and checker_age > check_lane_agents.STALE_THRESHOLD_SECONDS)

            survivors = fleet_concurrency_check._non_stale_exclusive_leases(lock_dir)
            fcc_is_live = len(survivors) == 1

            check(f"check_lane_agents and fleet_concurrency_check agree on liveness ({label})",
                  checker_is_live == fcc_is_live,
                  f"checker_is_live={checker_is_live} fcc_is_live={fcc_is_live}")


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


# --- BT.ticket.fleet-wide-gates-red-on-another-lanes-data: foreign vs. own verdict scope -----
#
# Task 1 of that block: replay the measured instance (3) from the block record as a FAILING
# fixture against the UNCHANGED checker -- today a bad record belonging to ANOTHER repo is just
# as fatal as one belonging to this repo, which is the bug. These two functions assert the
# TARGET (post-task-3) behavior, so they are expected to be RED until the verdict is scoped:
#   - the foreign case asserts rc == 0 (not fatal) -- FAILS today, because today it is fatal.
#   - the own case asserts rc != 0 (still fatal) -- PASSES today AND after the fix, proving the
#     fix narrows the verdict rather than loosening it entirely.
#
# The measured incident: BT.ticket.validate-brain-is-a-write-and-push-path bailed at task 1 on a
# registry claim belonging to agent `agentic-portfolio-01` (repo `agentic-portfolio`, i.e. HQ,
# NOT base-template) whose heartbeat was 6439s old against the THEN-current 5400s (90min)
# threshold -- a margin of 1039s past threshold. STALE_THRESHOLD_SECONDS has since been
# independently raised to 180min (see the constant's own derivation comment above), so replaying
# the literal 6439s would not even trip staleness under today's threshold. The fixture below
# reproduces the same SHAPE -- a claim just past whatever the current threshold is, by the same
# ~1039s margin -- rather than the now-stale literal value, so it exercises the real bug (verdict
# not scoped by ownership) instead of a threshold that has already moved on.

def check_foreign_stale_registry_claim_reports_but_is_not_fatal() -> None:
    """TARGET behavior (task 3): a stale registry claim belonging to ANOTHER repo is reported but
    does not fail the gating verdict. RED today -- the unchanged checker fails it just like an
    own-repo record."""
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        stale_seconds = check_lane_agents.STALE_THRESHOLD_SECONDS + 1039
        stale_heartbeat = _now() - timedelta(seconds=stale_seconds)
        _write_json(
            lock_dir / "lane-agents" / "agent-agentic-portfolio-01.json",
            _valid_registry(
                agent_name="agentic-portfolio-01",
                repo="agentic-portfolio",
                lane="lane-coordination",
                heartbeat=_iso(stale_heartbeat),
            ),
        )

        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--lock-dir", str(lock_dir), "--quiet"],
            capture_output=True, text=True,
        )
        check("a stale registry claim belonging to ANOTHER repo is still REPORTED in the output",
              "agentic-portfolio-01" in proc.stdout, proc.stdout + proc.stderr)
        check("EXPECTED RED before task 3: a stale claim belonging to ANOTHER repo must NOT fail "
              "the gating verdict (rc == 0) -- today it does, because the verdict is not yet "
              "scoped by record ownership",
              proc.returncode == 0, f"rc: {proc.returncode}, output: {proc.stdout + proc.stderr}")


def check_own_stale_registry_claim_is_still_fatal() -> None:
    """The other direction of the same fixture: a stale registry claim belonging to THIS repo
    (base-template) must still fail the gating verdict, both today and after task 3 -- proving
    the eventual fix narrows the verdict rather than loosening it for everyone."""
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        stale_seconds = check_lane_agents.STALE_THRESHOLD_SECONDS + 1039
        stale_heartbeat = _now() - timedelta(seconds=stale_seconds)
        _write_json(
            lock_dir / "lane-agents" / "agent-base-template-own.json",
            _valid_registry(
                agent_name="base-template-own",
                repo="base-template",
                heartbeat=_iso(stale_heartbeat),
            ),
        )

        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--lock-dir", str(lock_dir), "--quiet"],
            capture_output=True, text=True,
        )
        check("a stale registry claim belonging to THIS repo is REPORTED in the output",
              "base-template-own" in proc.stdout, proc.stdout + proc.stderr)
        check("a stale registry claim belonging to THIS repo still fails the gating verdict "
              "(rc != 0), both today and after task 3",
              proc.returncode != 0, f"rc: {proc.returncode}, output: {proc.stdout + proc.stderr}")


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
    check_real_live_claim_without_new_fields_validates()
    check_registry_with_both_new_fields_valid()
    check_registry_malformed_block_started_at_rejected()
    check_registry_empty_current_block_rejected()
    check_lane_schema_json_unchanged_by_this_task()
    check_lease_scope_values()
    check_negative_missing_required_field()
    check_negative_duplicate_exclusive_lease()
    check_negative_stale_heartbeat()
    check_negative_malformed_json()
    check_negative_nonexistent_path_is_named_error()
    check_shared_vs_exclusive_asymmetry()
    check_lease_heartbeat_allowed_and_validated()
    check_lease_liveness_timestamp_prefers_heartbeat()
    check_lease_without_heartbeat_falls_back_to_acquired_at()
    check_lease_with_fresh_heartbeat_survives_stale_acquired_at()
    check_lease_cross_script_agreement_with_fleet_concurrency_check()
    check_boundary_heartbeat_exactly_at_threshold()
    check_foreign_stale_registry_claim_reports_but_is_not_fatal()
    check_own_stale_registry_claim_is_still_fatal()
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
