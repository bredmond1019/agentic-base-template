#!/usr/bin/env python3
"""Re-stamp a lane's claim and lease heartbeat between block boundaries (BT.ticket.lane-
heartbeat-goes-stale-mid-block, task 3).

WHY A SEPARATE SCRIPT: check_lane_agents.py's own module docstring fixes it as read-only --
"this block ships the shapes, this checker, and read helpers only" -- so a writer does not
belong there. WHY A SCRIPT AT ALL, RATHER THAN ENGINE-ONLY JS: not every lane is driven by
/orchestrate's engines. A lane driven BY HAND never reaches /orchestrate rule 10's
release-and-re-take, so the heartbeat re-stamp that happens there as a side effect never fires
for it either -- measured 2026-09-08, a hand-driven lane's claim sat un-re-stamped across two
closed blocks, ~34 minutes from tripping the staleness threshold. A standalone script is callable
from both the engines (mid-block, non-fatally) and a hand-driven lane's own shell.

WHAT THIS NEVER DOES:
  - never rewrites `started_at` (claim) or `acquired_at` (lease) -- those mark ACQUISITION time,
    and re-stamping them on every heartbeat is the exact data loss
    BT.ticket.lane-claim-and-lease-have-no-heartbeat fixed. Only `heartbeat` (and, optionally,
    `current_block` / `block_started_at`) ever move.
  - never creates a claim or lease that does not already exist. A missing record means this lane
    does not hold what it thinks it holds; that is reported and the run exits non-zero, never
    silently repaired by fabricating a record.
  - never adds a key outside REGISTRY_ALLOWED / LEASE_ALLOWED (check_lane_agents.py) -- the
    schemas' `additionalProperties: false` would reject it, and this script must never write a
    shape that checker itself would flag.

LOCK-DIR RESOLUTION: reuses check_lane_agents.py's own `resolve_lock_dir` (--lock-dir env var,
else FLEET_LOCK_DIR, else a brain.toml discovered by walking up from cwd) rather than a second
copy of that precedence, so this writer and that checker can never disagree about which
directory "the" lock dir is.

Usage:
    lane_heartbeat.py --agent <name> --repo <repo> [--lock-dir DIR] [--current-block <id>]

    --agent NAME        the ListAgents nickname whose claim (agent-<name>.json) is re-stamped.
    --repo REPO          the repo slug whose lease (lease-<repo>.json) is re-stamped.
    --lock-dir DIR       override the shared lock directory (same precedence as
                         check_lane_agents.py; see resolve_lock_dir there).
    --current-block ID   when given, and the claim record already carries a `current_block`
                         field, also re-stamp `current_block` to ID and `block_started_at` to
                         now, in the SAME write as the heartbeat. A claim that has never carried
                         `current_block` is left without it -- this flag never adds the field to
                         a record that does not already have it.

Exit code 0 when both the claim and the lease were found and re-stamped. Exit code 1 if either
record is missing (the path is named in the output) -- never created.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _import_check_lane_agents():
    """Import check_lane_agents.py from this same scripts/ directory. See
    fleet_concurrency_check.py's `_import_check_lane_agents` for why a plain `import
    check_lane_agents` is not reliable when this module is itself loaded via
    `importlib.util.spec_from_file_location` (the way the test suite loads it): that path is
    never added to sys.path by the loader, so the import must locate the sibling file by this
    file's own path instead of trusting the caller's sys.path state."""
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import check_lane_agents  # noqa: E402 - deliberate late/local import, see docstring above

    return check_lane_agents


_LANE_AGENTS = _import_check_lane_agents()


def _now_iso(now: Optional[datetime] = None) -> str:
    """Current (or injected) UTC time, formatted in the TIMESTAMP_RE grammar
    check_lane_agents.py enforces (e.g. `2026-09-08T12:34:56Z`)."""
    reference = now or datetime.now(timezone.utc)
    return reference.isoformat().replace("+00:00", "Z")


def _load_record(path: Path):
    """Return (record, error). error is a human-readable string naming `path` on any failure --
    missing, unreadable or unparseable -- so the caller can report exactly what was not found,
    never silently proceed as if a record existed."""
    if not path.exists():
        return None, f"missing claim/lease record: {path}"
    try:
        with open(path) as fh:
            record = json.load(fh)
    except Exception as exc:                       # noqa: BLE001 - report, never raise
        return None, f"does not parse: {path}: {exc}"
    if not isinstance(record, dict):
        return None, f"top level is not an object: {path}"
    return record, None


def _write_record(path: Path, record: dict) -> None:
    """Round-trip JSON exactly as the records already on disk are written -- indent=2 plus a
    trailing newline -- so this writer never introduces a formatting diff unrelated to the
    fields it actually changed."""
    path.write_text(json.dumps(record, indent=2) + "\n")


def restamp_claim(claim_path: Path, now_str: str, current_block: Optional[str]) -> Optional[str]:
    """Re-stamp `heartbeat` on the claim at `claim_path`, and -- only when `current_block` is
    given AND the record already carries a `current_block` key -- also re-stamp `current_block`
    and `block_started_at` in the same write. Returns an error string on failure, else None.
    NEVER touches `started_at`; NEVER adds a key the record did not already have (that would
    reach outside REGISTRY_ALLOWED for a claim that predates the optional field)."""
    record, err = _load_record(claim_path)
    if err:
        return err

    record["heartbeat"] = now_str
    if current_block is not None and "current_block" in record:
        record["current_block"] = current_block
        record["block_started_at"] = now_str

    _write_record(claim_path, record)
    return None


def restamp_lease(lease_path: Path, now_str: str) -> Optional[str]:
    """Re-stamp `heartbeat` on the lease at `lease_path`. NEVER touches `acquired_at` --
    lease.schema.json documents it as immutable, and re-stamping it on every heartbeat was the
    exact data loss BT.ticket.lane-claim-and-lease-have-no-heartbeat fixed. `heartbeat` is an
    OPTIONAL field on a lease (lease.schema.json), so this write also legitimately ADDS the key
    the first time a lease's heartbeat is ever re-stamped -- `heartbeat` is within LEASE_ALLOWED,
    so that is not a schema violation."""
    record, err = _load_record(lease_path)
    if err:
        return err

    record["heartbeat"] = now_str

    _write_record(lease_path, record)
    return None


def run(lock_dir: Path, agent: str, repo: str, current_block: Optional[str] = None,
        now: Optional[datetime] = None) -> int:
    """Re-stamp both the claim (agent-<agent>.json) and the lease (lease-<repo>.json) under
    `lock_dir`. Returns 0 only when BOTH re-stamps succeed; 1 if either record is missing or
    unreadable, naming the path in the printed output."""
    now_str = _now_iso(now)

    claim_path = lock_dir / _LANE_AGENTS.REGISTRY_SUBDIR / f"agent-{agent}.json"
    lease_path = lock_dir / _LANE_AGENTS.LEASE_SUBDIR / f"lease-{repo}.json"

    failed = False

    claim_err = restamp_claim(claim_path, now_str, current_block)
    if claim_err:
        print(f"FAIL {claim_err}")
        failed = True
    else:
        print(f"ok   re-stamped claim heartbeat: {claim_path}")

    lease_err = restamp_lease(lease_path, now_str)
    if lease_err:
        print(f"FAIL {lease_err}")
        failed = True
    else:
        print(f"ok   re-stamped lease heartbeat: {lease_path}")

    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", required=True,
                     help="the ListAgents nickname whose claim is re-stamped")
    ap.add_argument("--repo", required=True,
                     help="the repo slug whose lease is re-stamped")
    ap.add_argument("--lock-dir", default=None,
                     help="override the shared lock directory (same precedence as "
                          "check_lane_agents.py's resolve_lock_dir)")
    ap.add_argument("--current-block", default=None,
                     help="when given, and the claim already carries `current_block`, also "
                          "re-stamp current_block and block_started_at in the same write")
    args = ap.parse_args()

    lock_dir = _LANE_AGENTS.resolve_lock_dir(args.lock_dir)
    if lock_dir is None:
        print("FAIL could not resolve a lock directory (no --lock-dir, no FLEET_LOCK_DIR, "
              "no brain.toml found walking up from cwd)")
        return 1

    return run(lock_dir, args.agent, args.repo, current_block=args.current_block)


if __name__ == "__main__":
    sys.exit(main())
