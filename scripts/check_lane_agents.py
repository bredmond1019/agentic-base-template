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
timestamp (a registry claim's `heartbeat`, or a lease's `heartbeat` when present, else its
`acquired_at` -- see `lease_liveness_timestamp()`; `acquired_at` is now immutable per
lease.schema.json and no longer doubles as the heartbeat) is older than
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
REGISTRY_OPTIONAL = ["current_block", "block_started_at"]
REGISTRY_ALLOWED = set(REGISTRY_REQUIRED) | set(REGISTRY_OPTIONAL)
REGISTRY_SLUG_FIELDS = ("repo", "lane", "roadmap")
REGISTRY_TIMESTAMP_FIELDS = ("started_at", "heartbeat", "block_started_at")

LEASE_REQUIRED = ["repo", "lane", "agent", "acquired_at", "kind"]
LEASE_ALLOWED = set(LEASE_REQUIRED) | {"scope", "heartbeat"}
LEASE_SLUG_FIELDS = ("repo", "lane")
LEASE_TIMESTAMP_FIELDS = ("acquired_at", "heartbeat")
LEASE_KIND_VALUES = {"exclusive", "shared"}
LEASE_SCOPE_VALUES = {"repo", "fleet"}

# STALE THRESHOLD -- DERIVED, 2026-08-23, from measured block durations, not chosen by feel.
# The old value (90 minutes) is exactly what produced the incident this threshold exists to fix:
# mev-23 went stale at 94 minutes, base-template-f8 at 91, engine-rs-37 at 95 -- three healthy
# lanes tripping within a 4-minute band is the threshold measuring itself, not three slow lanes.
#
# MEASUREMENT: consecutive same-lane "closed"/"bailed" timestamp deltas in this roadmap's
# planning/roadmaps/autonomous-foundation/lane-log.jsonl, across every repo in the fleet (not
# just base-template) -- 46 samples spanning base-template, engine-rs, bastion, mev, okf-core and
# brain. Distribution: median 50 min, p90 120 min, max observed 215 min (base-template's
# BT.ticket.sdlc-task-tier-spec-resolution). One concrete datum from THIS chain: block 1
# (BT.ticket.exclusive-lease-refuses-every-register) ran 12:33Z-13:06Z, 33 minutes, for a
# four-task ticket whose Validate task alone runs 38 gated checks -- a ten-block chain of those
# spends much of its life within a factor of two of a 90-minute window, which is why 90 trips so
# often it looks like three separate incidents instead of one systematic one.
#
# CHOSEN VALUE: 180 minutes (3 hours) -- comfortably above the measured p90 (120 min, 1.5x
# headroom) and above the single largest measured interval (215 min is within ~1x, the rest of
# the corpus sits well under half of 180), so a normal block, even a slow one, cannot trip it on
# its own. Re-check this number the same way if lane-log.jsonl gathers a materially different
# distribution -- do not bump it by feel.
#
# WHAT ELSE THIS CONTROLS: fleet_concurrency_check.py's `_non_stale_exclusive_leases` reads this
# exact constant (via `_LANE_AGENTS.STALE_THRESHOLD_SECONDS`, not a second copy) to decide when an
# exclusive lease stops blocking the fleet, so raising it also raises how long an abandoned
# exclusive lease can block everyone else. Raising it now is safe only because
# BT.ticket.exclusive-lease-refuses-every-register (earlier in this same chain) already scoped
# the exclusive-lease refusal to the requesting repo -- before that fix, a longer threshold would
# have meant a longer fleet-wide stall instead of a longer single-repo stall. That ordering is why
# this block depends on that one.
STALE_THRESHOLD_SECONDS = 180 * 60

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


def load_repo_paths(brain_root: Path) -> dict:
    """slug -> absolute repo path, from brain.toml's [[repos]] table. {} if unreadable. Mirrors
    check_lane_records.py's helper of the same name so the two scripts can never disagree about
    which slug a given repo path resolves to."""
    toml_path = brain_root / "brain.toml"
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python < 3.11 fallback, not expected in this fleet
        return {}
    try:
        with open(toml_path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception:                               # noqa: BLE001 - report, never raise
        return {}
    out = {}
    for entry in data.get("repos", []):
        slug = entry.get("slug")
        repo_path = entry.get("repo_path")
        if slug and repo_path:
            out[slug] = (brain_root / repo_path).resolve()
    return out


def resolve_own_repo(explicit: Optional[str] = None, start: Optional[Path] = None) -> Optional[str]:
    """The repo slug THIS checker run is attributed to (BT.ticket.fleet-wide-gates-red-on-
    another-lanes-data) -- used to scope the GATING VERDICT to this repo's own records while
    still reporting every record the scan finds, fleet-wide. Precedence: explicit `--repo`, else
    the brain.toml `[[repos]]` slug whose `repo_path` resolves to `start` (default: cwd).

    Returns None when it cannot be determined -- callers must then treat every record as OWN
    (fail closed): narrowing the verdict without knowing which repo "this one" is would silently
    waive every foreign-looking record instead of gating on all of them, which is the wrong
    direction to fail in."""
    if explicit:
        return explicit
    brain_root = find_brain_root(start)
    if brain_root is None:
        return None
    repo_paths = load_repo_paths(brain_root)
    here = (start or Path.cwd()).resolve()
    for slug, path in repo_paths.items():
        if path == here:
            return slug
    return None


def _record_repo(record) -> Optional[str]:
    """The `repo` field a record declares, or None if the record is not a dict or the field is
    missing/not a string -- ownership can't be determined for it either way."""
    if isinstance(record, dict):
        v = record.get("repo")
        if isinstance(v, str) and v:
            return v
    return None


def is_foreign(record_repo: Optional[str], own_repo: Optional[str]) -> bool:
    """True only when BOTH `record_repo` and `own_repo` are known and they differ. The
    fail-closed default -- `own_repo` unresolved, or a record with no readable `repo` field --
    is False (treated as OWN, so it still gates); never silently treated as foreign."""
    return own_repo is not None and record_repo is not None and record_repo != own_repo


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
        cb = record.get("current_block")
        if cb is not None and not (isinstance(cb, str) and cb):
            problems.append("`current_block` must be a non-empty string when present")
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
        scope = record.get("scope")
        if scope is not None and scope not in LEASE_SCOPE_VALUES:
            problems.append(
                f"`scope` value `{scope}` is not one of {sorted(LEASE_SCOPE_VALUES)}"
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


def lease_liveness_timestamp(record: dict) -> str:
    """The timestamp a lease's staleness is judged on: `heartbeat` when present, else
    `acquired_at` -- the fallback that keeps every lease already on disk (none of which carry
    `heartbeat` yet) judged exactly as before. `acquired_at` no longer doubles as the heartbeat
    (lease.schema.json now documents it as immutable); this is the single place that rule lives
    so fleet_concurrency_check.py's `_non_stale_exclusive_leases` can import it and the two
    scripts can never disagree about which leases are live."""
    heartbeat = record.get("heartbeat")
    if isinstance(heartbeat, str) and heartbeat:
        return heartbeat
    return record.get("acquired_at", "")


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

def run(lock_dir: Optional[Path], quiet: bool, now: Optional[datetime] = None,
        repo: Optional[str] = None) -> int:
    """`repo`, if given, pins the repo this run is attributed to (else resolved from cwd via
    brain.toml -- see `resolve_own_repo`). A record whose own `repo` field differs from that is
    FOREIGN: still fully validated and still printed under FAIL, but it does not add to `failed`
    and therefore cannot flip the exit code (BT.ticket.fleet-wide-gates-red-on-another-lanes-
    data) -- reporting is unchanged, only the gating verdict is scoped."""
    own_repo = resolve_own_repo(repo)

    total = 0
    failed = 0
    foreign_failed = 0
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
            foreign = is_foreign(_record_repo(record), own_repo)
            if foreign:
                foreign_failed += 1
            else:
                failed += 1
            tag = " [FOREIGN -- reported, not gating]" if foreign else ""
            lines.append(f"FAIL {path}{tag}")
            lines.extend(f"       {p}" for p in problems)
        elif not quiet:
            lines.append(f"ok   {path}")

    valid_leases = []
    for path in lease_files:
        total += 1
        record, load_err = _load(path)
        problems = [load_err] if load_err else check_lease_record(record)
        if not problems and isinstance(record, dict):
            liveness_field = "heartbeat" if record.get("heartbeat") else "acquired_at"
            age = staleness_seconds(lease_liveness_timestamp(record), now)
            if age is not None and age > STALE_THRESHOLD_SECONDS:
                problems.append(
                    f"stale lease: agent `{record.get('agent')}` {liveness_field} is "
                    f"{age:.0f}s old (threshold {STALE_THRESHOLD_SECONDS}s) -- liveness against "
                    f"ListAgents is the caller's job, not this checker's"
                )
        if problems:
            foreign = is_foreign(_record_repo(record), own_repo)
            if foreign:
                foreign_failed += 1
            else:
                failed += 1
            tag = " [FOREIGN -- reported, not gating]" if foreign else ""
            lines.append(f"FAIL {path}{tag}")
            lines.extend(f"       {p}" for p in problems)
        else:
            valid_leases.append((path, record))
            if not quiet:
                lines.append(f"ok   {path}")

    # Duplicate-exclusive-lease detection, over records that individually validated. Both
    # claimants share the same `repo` (the dict key), so that key is what ownership is judged
    # against.
    by_repo: dict = {}
    for path, record in valid_leases:
        by_repo.setdefault(record["repo"], []).append((path, record))

    for repo_key, entries in by_repo.items():
        exclusive = [(p, r) for p, r in entries if r.get("kind") == "exclusive"]
        if len(exclusive) > 1:
            foreign = is_foreign(repo_key, own_repo)
            if foreign:
                foreign_failed += 1
            else:
                failed += 1
            tag = " [FOREIGN -- reported, not gating]" if foreign else ""
            claimants = ", ".join(
                f"lane `{r['lane']}` agent `{r['agent']}` ({p})" for p, r in exclusive
            )
            lines.append(
                f"FAIL duplicate exclusive lease(s) on repo `{repo_key}`: {claimants}{tag}"
            )

    for line in lines:
        print(line)

    if total == 0:
        print("no lane-agent records found (not a failure)")
        return 0

    if foreign_failed:
        print(f"\n{total} record(s) checked, {failed} failed (own-repo, gating) + "
              f"{foreign_failed} failed (foreign repo, reported only, not gating)")
    else:
        print(f"\n{total} record(s) checked, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lock-dir", default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--repo", default=None,
                     help="pin the repo this run is attributed to for gating-verdict scoping "
                          "(default: resolved from cwd via brain.toml's [[repos]] table)")
    args = ap.parse_args()

    lock_dir = resolve_lock_dir(args.lock_dir)
    return run(lock_dir, args.quiet, repo=args.repo)


if __name__ == "__main__":
    sys.exit(main())
