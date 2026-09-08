#!/usr/bin/env python3
"""Report whether another agent holds an exclusive lease on this repo (BT.ticket.the-repo-lease-
stops-nobody).

WHY THIS EXISTS: /begin-orchestration Step 4 has a lane take an exclusive repo lease before its
first block, and /orchestrate rule 10 releases and re-takes it at every block boundary. Nothing
reads that lease at commit time -- a concurrent session can (and, measured twice -- 2026-09-05
commit d89093f, 2026-09-07 commit 8b49968 -- has) committed straight through a held exclusive
lease with no signal on either side. This script makes a held lease OBSERVABLE on demand. It does
not enforce anything and is not wired to any git hook: base-template has no `hooks/` directory and
no `.git/hooks/pre-commit` to attach one to (measured 2026-09-07), so invoking this check
automatically at commit time is out of scope for this block and left for whoever owns a future
hook chain.

NEVER FAILS CLOSED. Exit code is always 0, regardless of a missing lock dir, a missing lease
file, an empty file, unparseable JSON, a record missing expected fields, or an unreadable file. An
install-state check that can fail closed would wedge exactly the repo it is meant to protect.

LOCK-DIR RESOLUTION mirrors scripts/check_lane_agents.py's `resolve_lock_dir` precedence exactly,
so the two mechanisms can never disagree about where the shared lock store lives: explicit
`--lock-dir`, else the `FLEET_LOCK_DIR` environment variable, else a `brain.toml` discovered by
walking up from cwd, joined with `.fleet-locks`.

LEASE RECORD FIELDS, per `.claude/workflows/lease.schema.json` and
`.claude/commands/begin-orchestration.md` Step 4: `repo`, `lane`, `agent`, `acquired_at`, `kind`,
optionally `heartbeat` and `scope`. `current_block` is not part of lease.schema.json itself but is
carried on the lane-agent REGISTRY record (`lane-agents/agent-<agent_name>.json`) -- this script
best-effort cross-references that record (same lock dir, same agent name) to report the holder's
current block when one is findable; its absence is never an error.

CALLER IDENTITY: `--agent` explicit, else the `FLEET_AGENT_NAME` environment variable, else
"unknown caller" -- and an unknown caller is treated as foreign (still warn), because silently
staying quiet just because identity could not be resolved is the wrong direction to fail in for a
check whose entire job is to surface a lease that might not be the caller's own.

Usage:
    check_repo_lease.py [--lock-dir DIR] [--repo REPO] [--agent AGENT] [--verbose]

    --lock-dir DIR   override the shared lock directory (default: resolved the same way
                     check_lane_agents.py resolves it)
    --repo REPO      override this repo's slug (default: this script's parent directory name)
    --agent AGENT    override the caller's agent identity (default: FLEET_AGENT_NAME env var,
                     else "unknown caller")
    --verbose        when there is nothing to warn about (no lease, or the caller's own lease),
                     print a single quiet confirmation line instead of nothing

Exit code: always 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOCK_SUBDIR = ".fleet-locks"
LEASE_SUBDIR = "leases"
REGISTRY_SUBDIR = "lane-agents"


# --- lock-dir / repo resolution (mirrors check_lane_agents.py's precedence) --------------------

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
    nothing resolves."""
    if explicit:
        return Path(explicit)
    if os.environ.get("FLEET_LOCK_DIR"):
        return Path(os.environ["FLEET_LOCK_DIR"])
    brain_root = find_brain_root()
    if brain_root is not None:
        return brain_root / LOCK_SUBDIR
    return None


def resolve_repo_slug(explicit: Optional[str] = None) -> str:
    """This repo's slug: explicit --repo, else this script's own repo directory name (the parent
    of the `scripts/` directory this file lives in)."""
    if explicit:
        return explicit
    return Path(__file__).resolve().parent.parent.name


def resolve_agent_identity(explicit: Optional[str] = None) -> str:
    """The caller's own agent identity: explicit --agent, else FLEET_AGENT_NAME env var, else the
    literal string "unknown caller" (never None -- an unresolved caller must still be able to be
    compared against a lease's `agent` field and come out foreign, not silently skipped)."""
    if explicit:
        return explicit
    env_val = os.environ.get("FLEET_AGENT_NAME")
    if env_val:
        return env_val
    return "unknown caller"


# --- record loading (never raises) -------------------------------------------------------------

def _load_json_quiet(path: Path) -> Optional[dict]:
    """Read and parse a JSON object at `path`. Returns None on ANY failure -- missing file, empty
    file, unparseable JSON, a permission error, a path that is a directory, or a top-level value
    that isn't an object. Never raises."""
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except Exception:                                # noqa: BLE001 - report nothing, never raise
        return None
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except Exception:                                # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    return data


def _heartbeat_age_seconds(record: dict) -> Optional[float]:
    """Seconds since the record's liveness timestamp (`heartbeat` if present and parseable, else
    `acquired_at`), or None if neither is usable. Never raises."""
    for field in ("heartbeat", "acquired_at"):
        v = record.get(field)
        if not isinstance(v, str) or not v:
            continue
        try:
            ts = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:                            # noqa: BLE001
            continue
        return (datetime.now(timezone.utc) - dt).total_seconds()
    return None


def _format_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown age"
    seconds = max(0.0, seconds)
    if seconds < 90:
        return f"{int(seconds)}s"
    minutes = seconds / 60.0
    if minutes < 90:
        return f"{minutes:.0f}m"
    hours = minutes / 60.0
    return f"{hours:.1f}h"


def _find_current_block(lock_dir: Path, agent: str) -> Optional[str]:
    """Best-effort: the `current_block` a lane-agent registry record names for `agent`, or None.
    Never raises; absence is never an error -- `current_block` is optional on that record too."""
    if not agent or agent == "unknown caller":
        return None
    record = _load_json_quiet(lock_dir / REGISTRY_SUBDIR / f"agent-{agent}.json")
    if record is None:
        return None
    cb = record.get("current_block")
    if isinstance(cb, str) and cb:
        return cb
    return None


def check_repo_lease(lock_dir: Optional[Path], repo: str, caller_agent: str,
                      verbose: bool = False) -> str:
    """Return the message to print (possibly empty). Never raises."""
    if lock_dir is None:
        return "" if not verbose else "no lock directory resolved -- nothing to check"

    lease_path = lock_dir / LEASE_SUBDIR / f"lease-{repo}.json"
    record = _load_json_quiet(lease_path)
    if record is None:
        return "" if not verbose else f"no lease held on `{repo}` -- nothing to warn about"

    holder = record.get("agent")
    if not isinstance(holder, str) or not holder:
        # A lease record with no readable holder can't be attributed to anyone -- can't safely
        # call it "foreign" or "own"; say nothing rather than fabricate a holder name.
        return "" if not verbose else f"lease on `{repo}` has no readable `agent` field"

    if holder == caller_agent:
        return "" if not verbose else f"lease on `{repo}` is held by the caller ({holder}) -- own lease, nothing to warn about"

    lane = record.get("lane") if isinstance(record.get("lane"), str) and record.get("lane") else "unknown lane"
    age = _format_age(_heartbeat_age_seconds(record))
    current_block = _find_current_block(lock_dir, holder)

    lines = [
        "=" * 72,
        f"WARNING: repo `{repo}` has an EXCLUSIVE LEASE held by ANOTHER agent",
        "=" * 72,
        f"  holder:         {holder}",
        f"  lane:           {lane}",
        f"  heartbeat age:  {age}",
    ]
    if current_block:
        lines.append(f"  current block:  {current_block}")
    lines.append(
        "This is a WARNING, not a block -- the repo lease is advisory. Nothing enforces it at "
        "commit time; proceeding is permitted, but the tree may move underneath you."
    )
    lines.append("=" * 72)
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lock-dir", default=None)
    parser.add_argument("--repo", default=None)
    parser.add_argument("--agent", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        lock_dir = resolve_lock_dir(args.lock_dir)
        repo = resolve_repo_slug(args.repo)
        caller_agent = resolve_agent_identity(args.agent)
        message = check_repo_lease(lock_dir, repo, caller_agent, verbose=args.verbose)
        if message:
            print(message)
    except Exception as exc:                          # noqa: BLE001 - never fail closed
        if args.verbose:
            print(f"check_repo_lease: suppressed internal error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
