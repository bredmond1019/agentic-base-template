#!/usr/bin/env python3
"""Validate lane-agent registry claims and repo leases (BT.6.A).

Dependency-free on purpose, same discipline as check_lane_records.py and check_block_records.py:
`jsonschema` is not installed anywhere in this fleet, so a validator that imports it validates
nothing and reports success. This checks the constraints in lane-agent.schema.json and
lease.schema.json -- required/allowed keys, the slug and timestamp grammars, and the two
cross-record rules the schemas cannot express on their own -- by hand.

FILE LAYOUT: one record per claim, under the shared advisory lock directory that
fleet_concurrency_check.py already established (`<brain_root>/.fleet-locks/`, resolved with the
identical --lock-dir / FLEET_LOCK_DIR / brain.toml-walk-up precedence, so both mechanisms agree on
one location without either hardcoding the other's path). Registry claims live at
`<lock_dir>/lane-agents/agent-*.json`; leases live at `<lock_dir>/leases/lease-*.json`. Writing
into this layout is BT.6.E's job (this block ships the shapes, this checker, and read helpers
only) -- the layout is fixed now so BT.6.E has a stable target rather than inventing its own.

DUPLICATE EXCLUSIVE LEASE: two "exclusive" leases on the same repo is an error naming both
claimants (repo, lane, agent for each) -- a message naming only one claimant is useless for
deciding which to release. Two "shared" leases on the same repo are legal by design (that
asymmetry is the entire point of lease.schema.json's `kind` field) and are never flagged.

STALE-LEASE / STALE-CLAIM DETECTION AND ITS BOUNDARY: a record is "stale" when its liveness
timestamp (a registry claim's `heartbeat`, or a lease's `acquired_at` -- lease.schema.json's
`acquired_at` description states it "doubles as the lease's heartbeat") is older than
STALE_THRESHOLD_SECONDS. This script CANNOT call ListAgents -- it has no access to which agent
nicknames are currently live -- so it never decides "abandoned" vs. "slow." It reports the
timestamp age and the agent name only; joining that against ListAgents liveness to tell "agent
absent from ListAgents" (an abandoned lane, a named recovery item for BT.6.D) apart from "agent
live but heartbeat old" (a merely slow lane, not an incident) is strictly the CALLER's job.

Usage:
    check_lane_agents.py [--lock-dir DIR] [--quiet]

    --lock-dir DIR   override the shared lock directory (default: resolved the same way
                     fleet_concurrency_check.py resolves it -- FLEET_LOCK_DIR env var, else a
                     brain.toml discovered by walking up from cwd, joined with .fleet-locks)
    --quiet          print only failures and the summary

Exit code 1 if any record fails validation, or a duplicate exclusive lease / stale record is
found. Exit code 0 on a clean corpus, INCLUDING a corpus with zero records -- that is the state of
every repo today, before BT.6.E ever writes a claim, and must stay silent (matches
check_lane_records.py's "no lane records found" precedent).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")

REGISTRY_REQUIRED = ["agent_name", "repo", "lane", "roadmap", "started_at", "heartbeat"]
REGISTRY_ALLOWED = set(REGISTRY_REQUIRED)
REGISTRY_SLUG_FIELDS = ("repo", "lane", "roadmap")
REGISTRY_TIMESTAMP_FIELDS = ("started_at", "heartbeat")

LEASE_REQUIRED = ["repo", "lane", "agent", "acquired_at", "kind"]
LEASE_ALLOWED = set(LEASE_REQUIRED)
LEASE_SLUG_FIELDS = ("repo", "lane")
LEASE_TIMESTAMP_FIELDS = ("acquired_at",)
LEASE_KIND_VALUES = {"exclusive", "shared"}

# STALE THRESHOLD: measured block durations in this fleet run 20-60 minutes (base-template
# CLAUDE.md standing rules, D57 measurement), so the threshold must clear a normal long block
# with margin or every healthy lane reports stale on its own longest block. Matched to
# fleet_concurrency_check.py's DEFAULT_TTL_SECONDS (90 minutes), which was set against the same
# fleet measurement for the same reason -- one number for "how long is too long" across both
# advisory mechanisms rather than two that could drift apart.
STALE_THRESHOLD_SECONDS = 90 * 60

REGISTRY_FILE_RE = re.compile(r"^agent-.*\.json$")
LEASE_FILE_RE = re.compile(r"^lease-.*\.json$")

LOCK_SUBDIR = ".fleet-locks"
REGISTRY_SUBDIR = "lane-agents"
LEASE_SUBDIR = "leases"


# --- lock-dir resolution (mirrors fleet_concurrency_check.py's precedence exactly) ----------

def find_brain_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from `start` (default: cwd) looking for a directory containing brain.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def resolve_lock_dir(explicit: Optional[str] = None) -> Optional[Path]:
    """Resolve the shared lock directory. Precedence: explicit --lock-dir, then FLEET_LOCK_DIR
    env var, then a brain.toml discovered by walking up from cwd. Returns None (never raises) if
    nothing resolves -- callers must then treat "no records found" as the (silent) result rather
    than erroring, since an unresolved lock dir with zero claims is indistinguishable from a repo
    that has never taken one."""
    if explicit:
        return Path(explicit)
    if os.environ.get("FLEET_LOCK_DIR"):
        return Path(os.environ["FLEET_LOCK_DIR"])
    brain_root = find_brain_root()
    if brain_root is not None:
        return brain_root / LOCK_SUBDIR
    return None


# --- record validation ------------------------------------------------------------------------

def _check_common(record, required, allowed, slug_fields, timestamp_fields) -> list:
    problems = []
    if not isinstance(record, dict):
        return ["top level must be an object"]

    unknown = sorted(set(record) - allowed)
    if unknown:
        problems.append(f"unknown key(s): {', '.join(unknown)}")

    for field in required:
        v = record.get(field)
        if v is None or (isinstance(v, str) and not v):
            problems.append(f"required field `{field}` is missing or empty")

    for field in slug_fields:
        v = record.get(field)
        if isinstance(v, str) and v and not SLUG_RE.match(v):
            problems.append(f"`{field}` value `{v}` does not match slug pattern")

    for field in timestamp_fields:
        v = record.get(field)
        if isinstance(v, str) and v and not TIMESTAMP_RE.match(v):
            problems.append(f"`{field}` value `{v}` is not an ISO-8601 timestamp with timezone")

    return problems


def check_registry_record(record) -> list:
    """Return errors for one lane-agent registry claim, against lane-agent.schema.json."""
    problems = _check_common(record, REGISTRY_REQUIRED, REGISTRY_ALLOWED,
                              REGISTRY_SLUG_FIELDS, REGISTRY_TIMESTAMP_FIELDS)
    if isinstance(record, dict):
        v = record.get("agent_name")
        if v is not None and not (isinstance(v, str) and v):
            problems.append("`agent_name` must be a non-empty string")
    return problems


def check_lease_record(record) -> list:
    """Return errors for one lease record, against lease.schema.json."""
    problems = _check_common(record, LEASE_REQUIRED, LEASE_ALLOWED,
                              LEASE_SLUG_FIELDS, LEASE_TIMESTAMP_FIELDS)
    if isinstance(record, dict):
        v = record.get("agent")
        if v is not None and not (isinstance(v, str) and v):
            problems.append("`agent` must be a non-empty string")
        kind = record.get("kind")
        if kind is not None and kind not in LEASE_KIND_VALUES:
            problems.append(
                f"`kind` value `{kind}` is not one of {sorted(LEASE_KIND_VALUES)}"
            )
    return problems


def _parse_timestamp(value: str) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        # Python's fromisoformat accepts "Z" only from 3.11+; normalize by hand for portability.
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return None
        return dt
    except ValueError:
        return None


def staleness_seconds(timestamp_value: str, now: Optional[datetime] = None) -> Optional[float]:
    """Age of `timestamp_value` in seconds relative to `now` (default: current UTC time), or
    None if the timestamp cannot be parsed."""
    dt = _parse_timestamp(timestamp_value)
    if dt is None:
        return None
    reference = now or datetime.now(timezone.utc)
    return (reference - dt).total_seconds()


# --- discovery ----------------------------------------------------------------------------

def _discover(directory: Path, file_re: re.Pattern) -> list:
    if not directory.is_dir():
        return []
    found = []
    for name in os.listdir(directory):
        if file_re.match(name):
            found.append(directory / name)
    return sorted(found)


def discover_registry_files(lock_dir: Path) -> list:
    return _discover(lock_dir / REGISTRY_SUBDIR, REGISTRY_FILE_RE)


def discover_lease_files(lock_dir: Path) -> list:
    return _discover(lock_dir / LEASE_SUBDIR, LEASE_FILE_RE)


def _load(path: Path):
    """Return (record, error). error is a named string on any read/parse failure -- a
    nonexistent or unreadable path is reported, never silently treated as absent, matching
    check_lane_records.py's discipline."""
    try:
        with open(path) as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, f"path does not exist: {path}"
    except Exception as exc:                       # noqa: BLE001 - report, never raise
        return None, f"does not parse: {exc}"


# --- main check pass ------------------------------------------------------------------------

def run(lock_dir: Optional[Path], quiet: bool, now: Optional[datetime] = None) -> int:
    total = 0
    failed = 0
    lines = []

    registry_files = discover_registry_files(lock_dir) if lock_dir else []
    lease_files = discover_lease_files(lock_dir) if lock_dir else []

    for path in registry_files:
        total += 1
        record, load_err = _load(path)
        problems = [load_err] if load_err else check_registry_record(record)
        if not problems and isinstance(record, dict):
            age = staleness_seconds(record.get("heartbeat", ""), now)
            if age is not None and age > STALE_THRESHOLD_SECONDS:
                problems.append(
                    f"stale registry claim: agent `{record.get('agent_name')}` heartbeat is "
                    f"{age:.0f}s old (threshold {STALE_THRESHOLD_SECONDS}s) -- liveness against "
                    f"ListAgents is the caller's job, not this checker's"
                )
        if problems:
            failed += 1
            lines.append(f"FAIL {path}")
            lines.extend(f"       {p}" for p in problems)
        elif not quiet:
            lines.append(f"ok   {path}")

    valid_leases = []
    for path in lease_files:
        total += 1
        record, load_err = _load(path)
        problems = [load_err] if load_err else check_lease_record(record)
        if not problems and isinstance(record, dict):
            age = staleness_seconds(record.get("acquired_at", ""), now)
            if age is not None and age > STALE_THRESHOLD_SECONDS:
                problems.append(
                    f"stale lease: agent `{record.get('agent')}` heartbeat (acquired_at) is "
                    f"{age:.0f}s old (threshold {STALE_THRESHOLD_SECONDS}s) -- liveness against "
                    f"ListAgents is the caller's job, not this checker's"
                )
        if problems:
            failed += 1
            lines.append(f"FAIL {path}")
            lines.extend(f"       {p}" for p in problems)
        else:
            valid_leases.append((path, record))
            if not quiet:
                lines.append(f"ok   {path}")

    # Duplicate-exclusive-lease detection, over records that individually validated.
    by_repo: dict = {}
    for path, record in valid_leases:
        by_repo.setdefault(record["repo"], []).append((path, record))

    for repo, entries in by_repo.items():
        exclusive = [(p, r) for p, r in entries if r.get("kind") == "exclusive"]
        if len(exclusive) > 1:
            failed += 1
            claimants = ", ".join(
                f"lane `{r['lane']}` agent `{r['agent']}` ({p})" for p, r in exclusive
            )
            lines.append(
                f"FAIL duplicate exclusive lease(s) on repo `{repo}`: {claimants}"
            )

    for line in lines:
        print(line)

    if total == 0:
        print("no lane-agent records found (not a failure)")
        return 0

    print(f"\n{total} record(s) checked, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lock-dir", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    lock_dir = resolve_lock_dir(args.lock_dir)
    return run(lock_dir, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
